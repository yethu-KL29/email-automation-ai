import asyncio
import hashlib
import json
import re
import threading
from contextlib import contextmanager
from datetime import UTC, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from job_outreach.composer import compose
from job_outreach.config import Settings
from job_outreach.db import (
    Candidate,
    Company,
    Contact,
    Database,
    DiscoveryRun,
    Job,
    Match,
    Outbox,
    Outreach,
    Resume,
    Search,
    Setting,
    Suppressed,
    audit,
    required,
)
from job_outreach.discovery import BoardSource
from job_outreach.domain import (
    JobData,
    SearchProfile,
    canonical_url,
    digest,
    freshness,
    match_job,
    utcnow,
)
from job_outreach.gmail import GmailClient, build_message
from job_outreach.security import normalize_email


class Conflict(ValueError):
    pass


_locks: dict[int, threading.Lock] = {key: threading.Lock() for key in (1, 2, 3)}


@contextmanager
def exclusive(db: Database, key: int):
    """Cross-process PostgreSQL lock; SQLite preview is single process only."""
    if db.engine.dialect.name == "postgresql":
        with db.engine.connect() as connection:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": 910000 + key}
            )
            if not acquired:
                raise Conflict("Another run is active")
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": 910000 + key})
    else:
        if not _locks[key].acquire(blocking=False):
            raise Conflict("Another run is active")
        try:
            yield
        finally:
            _locks[key].release()


def singleton(session: Session) -> Candidate:
    candidate = session.scalar(select(Candidate).order_by(Candidate.id).limit(1))
    if not candidate:
        candidate = Candidate()
        session.add(candidate)
        session.flush()
    return candidate


def get_search(session: Session) -> SearchProfile:
    row = session.scalar(select(Search).limit(1))
    return SearchProfile.model_validate(row.preferences) if row else SearchProfile()


def boards(session: Session, config: Settings) -> list[dict]:
    row = session.scalar(select(Setting).where(Setting.key == "source_boards"))
    return row.value["boards"] if row else config.source_boards


async def discover(db: Database, config: Settings) -> dict:
    with exclusive(db, 1):
        with db.session() as s:
            run = DiscoveryRun()
            s.add(run)
            s.flush()
            run_id = run.id
            configs = [b for b in boards(s, config) if b.get("enabled", True)]
        results = {}
        semaphore = asyncio.Semaphore(3)
        # Serialize boards per provider, and allow concurrency across providers.
        provider_locks = {source: asyncio.Lock() for source in ["ashby", "greenhouse", "lever"]}
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=3),
            headers={"User-Agent": "JobOutreach/0.1 local-personal-tool"},
        ) as client:

            async def one(board):
                key = board["source"] + ":" + board["board"]
                try:
                    async with semaphore, provider_locks[board["source"]]:
                        jobs = await BoardSource(board, client).fetch()
                        inserted = 0
                        with db.session() as session:
                            for item in jobs:
                                company = session.scalar(
                                    select(Company).where(
                                        Company.name == item.company,
                                        Company.domain == item.company_domain,
                                    )
                                )
                                if company is None:
                                    company = Company(name=item.company, domain=item.company_domain)
                                    session.add(company)
                                    session.flush()
                                url_key = digest(canonical_url(str(item.apply_url)))
                                existing = session.scalar(
                                    select(Job).where(
                                        or_(
                                            (Job.source == item.source)
                                            & (Job.external_id == item.external_id),
                                            Job.url_key == url_key,
                                        )
                                    )
                                )
                                if existing:
                                    existing.data = item.model_dump(mode="json")
                                    existing.last_verified_at = utcnow()
                                    existing.status = "open"
                                else:
                                    session.add(
                                        Job(
                                            company_id=company.id,
                                            source=item.source,
                                            external_id=item.external_id,
                                            url_key=url_key,
                                            title=item.title,
                                            data=item.model_dump(mode="json"),
                                        )
                                    )
                                    inserted += 1
                                session.flush()
                            current = session.get(DiscoveryRun, run_id)
                            current.metrics = {
                                **current.metrics,
                                key: {
                                    "retrieved": len(jobs),
                                    "inserted": inserted,
                                    "outcome": "success",
                                },
                            }
                        results[key] = {
                            "retrieved": len(jobs),
                            "inserted": inserted,
                            "outcome": "success",
                        }
                        await asyncio.sleep(0.3)
                except Exception as exc:
                    # Do not put full provider responses or URLs containing keys in logs.
                    results[key] = {"outcome": "failed", "error_type": type(exc).__name__}

            await asyncio.gather(*(one(b) for b in configs))
        with db.session() as s:
            run = s.get(DiscoveryRun, run_id)
            run.completed_at = utcnow()
            run.metrics = results
            run.outcome = (
                "no_sources"
                if not configs
                else (
                    "partial_failure"
                    if any(x["outcome"] == "failed" for x in results.values())
                    else "success"
                )
            )
            return {"id": run.id, "outcome": run.outcome, "sources": results}


def run_matches(session: Session) -> dict:
    candidate = singleton(session)
    resume = session.scalar(
        select(Resume)
        .where(Resume.candidate_id == candidate.id)
        .order_by(Resume.version.desc())
        .limit(1)
    )
    if not resume:
        raise Conflict("Upload a resume first")
    search = get_search(session)
    if not search.enabled:
        return {"matched": 0, "disabled": True}
    count = 0
    for job in session.scalars(select(Job).where(Job.status == "open").limit(10000)):
        data = JobData.model_validate(job.data)
        result = match_job(candidate.profile, data, search)
        result["freshness"] = freshness(data.posting_date, hours=search.max_age_hours)
        result["meets_minimum"] = result["eligible"] and result["score"] >= search.minimum_score
        row = session.scalar(
            select(Match).where(
                Match.candidate_id == candidate.id,
                Match.job_id == job.id,
                Match.resume_id == resume.id,
            )
        )
        if row:
            row.result, row.score = result, result["score"]
        else:
            session.add(
                Match(
                    candidate_id=candidate.id,
                    job_id=job.id,
                    resume_id=resume.id,
                    score=result["score"],
                    result=result,
                )
            )
        count += 1
    return {"matched": count, "method": "lexical-v1"}


def find_contacts(session: Session, job: Job) -> dict:
    company = required(session, Company, job.company_id)
    description = job.data["description"]
    emails = set(
        re.findall(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", description)
    )
    for value in sorted(emails)[:20]:
        try:
            email = normalize_email(value.rstrip("."))
        except ValueError:
            continue
        local, domain = email.rsplit("@", 1)
        official = bool(company.domain) and domain == company.domain.lower()
        recruiting = bool(re.search(r"career|recruit|talent|hiring|^hr$|jobs", local))
        verified = official and recruiting
        existing = session.scalar(
            select(Contact).where(Contact.job_id == job.id, Contact.email == email)
        )
        if not existing:
            start = max(description.lower().find(email.lower()) - 100, 0)
            session.add(
                Contact(
                    company_id=company.id,
                    job_id=job.id,
                    email=email,
                    contact_type="OFFICIAL_CAREERS_INBOX" if verified else "UNVERIFIED",
                    source_url=job.data["canonical_url"],
                    evidence=description[start : start + 350],
                    verified_at=utcnow() if verified else None,
                )
            )
    session.flush()
    contacts = list(session.scalars(select(Contact).where(Contact.job_id == job.id)))
    return {
        "status": "CONTACT_FOUND"
        if any(c.verified_at for c in contacts)
        else "NEEDS_REVIEW"
        if contacts
        else "NOT_FOUND",
        "contacts": len(contacts),
        "apply_url": job.data["apply_url"],
    }


def editable(outreach: Outreach):
    if outreach.status in {"SENDING", "SEND_UNCERTAIN", "SENT", "REPLIED", "INTERVIEW", "CLOSED"}:
        raise Conflict(
            "Delivery record is locked; reconcile uncertain delivery before any further action"
        )


def snapshot(session: Session, outreach: Outreach, config: Settings) -> str:
    contact = required(session, Contact, outreach.contact_id)
    resume = required(session, Resume, outreach.resume_id)
    candidate = required(session, Candidate, outreach.candidate_id)
    return digest(
        json.dumps(
            {
                "subject": outreach.subject,
                "body": outreach.body,
                "to": contact.email,
                "contact_verified": str(contact.verified_at),
                "resume": resume.content_hash,
                "profile": candidate.profile,
                "sender": config.sender_email,
                "name": config.sender_name,
            },
            sort_keys=True,
        )
    )


def validate_outreach(session: Session, outreach: Outreach):
    contact = required(session, Contact, outreach.contact_id)
    resume = required(session, Resume, outreach.resume_id)
    candidate = required(session, Candidate, outreach.candidate_id)
    if not contact.verified_at or contact.contact_type == "UNVERIFIED":
        raise Conflict("Verify contact provenance before approval")
    if not candidate.profile.get("verified"):
        raise Conflict("Review and verify candidate profile")
    if not outreach.subject.strip() or not outreach.body.strip():
        raise Conflict("Draft is empty")
    if "\n" in outreach.subject or "\r" in outreach.subject:
        raise Conflict("Invalid subject")
    if Path(resume.file_path).suffix != ".pdf":
        raise Conflict("Upload and select a PDF resume for sending")
    if hashlib.sha256(Path(resume.file_path).read_bytes()).hexdigest() != resume.content_hash:
        raise Conflict("Resume changed on disk; upload it again")
    if session.scalar(select(Suppressed).where(Suppressed.email == contact.email)):
        raise Conflict("Recipient is suppressed")


def sending_stopped(session: Session) -> bool:
    row = session.scalar(select(Setting).where(Setting.key == "sending_shutdown"))
    return bool(row and row.value.get("disabled"))


def queue_send(session: Session, outreach: Outreach, config: Settings) -> dict:
    if outreach.status != "APPROVED":
        raise Conflict("Approve this draft before sending")
    validate_outreach(session, outreach)
    if outreach.approval_hash != snapshot(session, outreach, config):
        raise Conflict("Profile, draft, sender or recipient changed; approve again")
    if sending_stopped(session):
        raise Conflict("Sending is globally stopped")
    if config.dry_run:
        return {"dry_run": True, "status": "APPROVED", "message": "No email sent or queued"}
    if not config.sending_enabled:
        raise Conflict("Sending is disabled in configuration")
    contact = required(session, Contact, outreach.contact_id)
    if not config.allow_recruiter_delivery and contact.email != config.test_recipient.lower():
        raise Conflict("Only the configured test recipient may receive email")
    if session.scalar(select(Outbox).where(Outbox.outreach_id == outreach.id)):
        raise Conflict("Send operation already exists; do not enqueue again")
    session.add(Outbox(outreach_id=outreach.id, operation_key=str(uuid4())))
    audit(session, "outreach", outreach.id, "queued")
    return {"dry_run": False, "status": "queued"}


def raw_message(session: Session, outreach: Outreach, config: Settings, operation: str) -> str:
    contact = required(session, Contact, outreach.contact_id)
    resume = required(session, Resume, outreach.resume_id)
    return build_message(
        config.sender_email,
        config.sender_name,
        contact.email,
        outreach.subject,
        outreach.body,
        Path(resume.file_path).read_bytes(),
        f"resume-v{resume.version}.pdf",
        operation,
    )


def deliver_one(db: Database, config: Settings, gmail=None) -> dict:
    gmail = gmail or GmailClient(config)
    with exclusive(db, 2):
        with db.session() as session:
            # A prior process dying after claim creates uncertainty, never a retry.
            for old in session.scalars(select(Outbox).where(Outbox.state == "sending")):
                old.state = "uncertain"
                old.last_error = "Previous sender stopped during delivery; reconcile manually"
                session.get(Outreach, old.outreach_id).status = "SEND_UNCERTAIN"
            row = session.scalar(
                select(Outbox)
                .where(Outbox.state == "pending")
                .order_by(Outbox.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not row:
                return {"status": "idle"}
            outreach = session.get(Outreach, row.outreach_id)
            if config.dry_run or not config.sending_enabled or sending_stopped(session):
                return {"status": "disabled"}
            try:
                validate_outreach(session, outreach)
                if outreach.status != "APPROVED" or outreach.approval_hash != snapshot(
                    session, outreach, config
                ):
                    raise Conflict("Approval no longer valid")
                contact = session.get(Contact, outreach.contact_id)
                if (
                    not config.allow_recruiter_delivery
                    and contact.email != config.test_recipient.lower()
                ):
                    raise Conflict("Only configured test recipient allowed")
                now = utcnow()
                sent_today = session.scalar(
                    select(func.count())
                    .select_from(Outreach)
                    .where(
                        Outreach.sent_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
                    )
                )
                if sent_today >= min(
                    config.daily_send_limit, get_search(session).max_emails_per_run
                ):
                    return {"status": "limit_reached"}
                recent = list(
                    session.scalars(
                        select(Outreach).where(
                            Outreach.id != outreach.id,
                            Outreach.sent_at
                            >= now
                            - timedelta(
                                days=max(config.company_cooldown_days, config.contact_cooldown_days)
                            ),
                        )
                    )
                )
                for previous in recent:
                    old_contact = session.get(Contact, previous.contact_id)
                    sent_at = (
                        previous.sent_at.replace(tzinfo=UTC)
                        if previous.sent_at.tzinfo is None
                        else previous.sent_at
                    )
                    if old_contact.email == contact.email and sent_at >= now - timedelta(
                        days=config.contact_cooldown_days
                    ):
                        raise Conflict("Contact cooldown active")
                    if old_contact.company_id == contact.company_id and sent_at >= now - timedelta(
                        days=config.company_cooldown_days
                    ):
                        raise Conflict("Company cooldown active")
                raw = raw_message(session, outreach, config, row.operation_key)
            except (ValueError, OSError) as exc:
                row.state, row.last_error = "blocked", str(exc)
                return {"status": "blocked", "reason": str(exc)}
            row.state, outreach.status = "sending", "SENDING"
            row.attempt_count += 1
            row_id, outreach_id = row.id, outreach.id
            audit(session, "outreach", outreach.id, "send_attempt", operation=row.operation_key)
        # Claim is committed BEFORE the external side effect.
        try:
            result = gmail.send(raw)
            if not result.get("id"):
                raise ValueError("Gmail did not return a message ID")
        except Exception as exc:
            with db.session() as session:
                row = session.get(Outbox, row_id)
                row.state, row.last_error = "uncertain", type(exc).__name__
                session.get(Outreach, outreach_id).status = "SEND_UNCERTAIN"
                audit(
                    session,
                    "outreach",
                    outreach_id,
                    "send_uncertain",
                    error_type=type(exc).__name__,
                )
            return {"status": "SEND_UNCERTAIN"}
        with db.session() as session:
            outreach = session.get(Outreach, outreach_id)
            outreach.status = "SENT"
            outreach.gmail_message_id = result["id"]
            outreach.gmail_thread_id = result.get("threadId", "")
            outreach.sent_at = utcnow()
            session.get(Outbox, row_id).state = "sent"
            audit(session, "outreach", outreach_id, "sent", gmail_message_id=result["id"])
        return {"status": "SENT", "gmail_message_id": result["id"]}


def make_draft(session: Session, outreach: Outreach) -> dict:
    editable(outreach)
    candidate = required(session, Candidate, outreach.candidate_id)
    job = required(session, Job, outreach.job_id)
    draft = compose(candidate.profile, job.data)
    outreach.subject, outreach.body, outreach.status = (
        draft["subject"],
        draft["body"],
        "DRAFT_READY",
    )
    outreach.approval_hash = ""
    audit(
        session,
        "outreach",
        outreach.id,
        "drafted",
        grounding=draft["grounding"],
        prompt_version=draft["prompt_version"],
    )
    return draft
