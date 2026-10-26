import csv
import hmac
import io
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from job_outreach.config import Settings, settings
from job_outreach.db import (
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
)
from job_outreach.domain import CandidateProfile, SearchProfile, freshness, parse_date, utcnow
from job_outreach.gmail import GmailClient
from job_outreach.resumes import MAX_BYTES, extract_resume, store_resume, suggest_profile
from job_outreach.security import normalize_email, validate_public_url
from job_outreach.workflows import (
    Conflict,
    boards,
    discover,
    editable,
    find_contacts,
    get_search,
    make_draft,
    queue_send,
    raw_message,
    run_matches,
    singleton,
    snapshot,
    validate_outreach,
)


class NewOutreach(BaseModel):
    job_id: int
    contact_id: int
    resume_id: int


class DraftEdit(BaseModel):
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=15000)


class ContactVerification(BaseModel):
    source_url: str
    evidence: str = Field(min_length=15, max_length=2000)
    contact_type: str = "HIRING_TEAM"


class BoardConfig(BaseModel):
    source: str = Field(pattern="^(ashby|greenhouse|lever)$")
    board: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    company: str = Field(min_length=1, max_length=200)
    domain: str = Field(default="", pattern=r"^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$|^$")
    enabled: bool = True


def record(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings()
    app = FastAPI(
        title="Job Outreach", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    db = Database(config.database_url)
    app.state.db = db
    app.state.config = config

    @app.exception_handler(Conflict)
    async def conflict_handler(_, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_handler(_, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def duplicate_handler(_, exc):
        return JSONResponse(
            status_code=409,
            content={"detail": "Record already exists or has conflicting references"},
        )

    def auth(request: Request):
        expected = config.api_token.get_secret_value()
        if len(expected) < 24:
            raise HTTPException(503, "Run setup to configure a strong API_TOKEN")
        if not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + expected):
            raise HTTPException(
                401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"}
            )

    def session():
        with db.session() as s:
            yield s

    def get(s, model, entity_id):
        row = s.get(model, entity_id)
        if row is None:
            raise HTTPException(404, "Record not found")
        return row

    @app.get("/api/v1/health")
    def health():
        try:
            with db.session() as s:
                s.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception:
            return JSONResponse(status_code=503, content={"status": "database_unavailable"})

    protected = [Depends(auth)]

    @app.get("/api/v1/profile", dependencies=protected)
    def profile(s=Depends(session)):
        return singleton(s).profile

    @app.put("/api/v1/profile", dependencies=protected)
    def update_profile(value: CandidateProfile, s=Depends(session)):
        candidate = singleton(s)
        if value.email:
            value.email = normalize_email(value.email)
        candidate.name, candidate.email = value.name, value.email
        candidate.profile = value.model_dump()
        audit(s, "candidate", candidate.id, "profile_reviewed", verified=value.verified)
        return candidate.profile

    @app.post("/api/v1/resumes", status_code=201, dependencies=protected)
    async def upload(file: UploadFile = File(...), s=Depends(session)):
        data = await file.read(MAX_BYTES + 1)
        suffix = Path(file.filename or "").suffix.lower()
        extracted = extract_resume(data, suffix)
        path, content_hash = store_resume(data, suffix, config.data_dir / "resumes")
        candidate = singleton(s)
        existing = s.scalar(
            select(Resume).where(
                Resume.candidate_id == candidate.id, Resume.content_hash == content_hash
            )
        )
        if existing:
            return {"id": existing.id, "version": existing.version, "duplicate": True}
        version = (
            s.scalar(select(func.max(Resume.version)).where(Resume.candidate_id == candidate.id))
            or 0
        ) + 1
        resume = Resume(
            candidate_id=candidate.id,
            file_path=str(path),
            content_hash=content_hash,
            extracted_text=extracted,
            version=version,
        )
        s.add(resume)
        s.flush()
        candidate.profile = {**(candidate.profile or suggest_profile(extracted)), "verified": False}
        audit(s, "resume", resume.id, "uploaded", version=version)
        return {
            "id": resume.id,
            "version": version,
            "extracted_text": extracted,
            "profile": candidate.profile,
        }

    @app.get("/api/v1/resumes", dependencies=protected)
    def resumes(s=Depends(session)):
        return [
            {
                "id": r.id,
                "version": r.version,
                "format": Path(r.file_path).suffix,
                "created_at": r.created_at,
            }
            for r in s.scalars(select(Resume).order_by(Resume.version.desc()))
        ]

    @app.get("/api/v1/search", dependencies=protected)
    def search(s=Depends(session)):
        return get_search(s)

    @app.put("/api/v1/search", dependencies=protected)
    def update_search(value: SearchProfile, s=Depends(session)):
        candidate = singleton(s)
        row = s.scalar(select(Search).where(Search.candidate_id == candidate.id))
        if row:
            row.preferences = value.model_dump()
        else:
            s.add(Search(candidate_id=candidate.id, preferences=value.model_dump()))
        return value

    @app.get("/api/v1/sources", dependencies=protected)
    def sources(s=Depends(session)):
        return boards(s, config)

    @app.put("/api/v1/sources", dependencies=protected)
    def update_sources(value: list[BoardConfig], s=Depends(session)):
        if len(value) > 30:
            raise ValueError("At most 30 boards per run")
        keys = [(b.source, b.board) for b in value]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate board configuration")
        row = s.scalar(select(Setting).where(Setting.key == "source_boards"))
        data = {"boards": [v.model_dump() for v in value]}
        if row:
            row.value = data
        else:
            s.add(Setting(key="source_boards", value=data))
        return data["boards"]

    @app.post("/api/v1/discovery/run", dependencies=protected)
    async def discovery_run():
        return await discover(db, config)

    @app.get("/api/v1/discovery/runs", dependencies=protected)
    def runs(limit: int = Query(50, ge=1, le=200), s=Depends(session)):
        return [
            record(r)
            for r in s.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(limit))
        ]

    @app.get("/api/v1/jobs", dependencies=protected)
    def jobs(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        freshness_filter: str = "",
        q: str = "",
        s=Depends(session),
    ):
        query = select(Job).order_by(Job.id.desc())
        if q:
            query = query.where(Job.title.ilike("%" + q[:100] + "%"))
        items = [
            {
                **record(j),
                "freshness": freshness(
                    parse_date(j.data.get("posting_date")), hours=get_search(s).max_age_hours
                ),
            }
            for j in s.scalars(query)
        ]
        if freshness_filter:
            items = [j for j in items if j["freshness"] == freshness_filter]
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/v1/jobs/{job_id}", dependencies=protected)
    def job_detail(job_id: int, s=Depends(session)):
        return record(get(s, Job, job_id))

    @app.post("/api/v1/matches/run", dependencies=protected)
    def matching(s=Depends(session)):
        return run_matches(s)

    @app.get("/api/v1/matches", dependencies=protected)
    def matches(limit: int = Query(200, ge=1, le=1000), s=Depends(session)):
        return [
            record(m) for m in s.scalars(select(Match).order_by(Match.score.desc()).limit(limit))
        ]

    @app.post("/api/v1/matches/assess", dependencies=protected)
    async def assess():
        from job_outreach.matching import assess_matches

        return await assess_matches(db, config)

    @app.post("/api/v1/jobs/{job_id}/contacts", dependencies=protected)
    def discover_contacts(job_id: int, s=Depends(session)):
        return find_contacts(s, get(s, Job, job_id))

    @app.get("/api/v1/contacts", dependencies=protected)
    def contacts(
        job_id: int | None = None, limit: int = Query(200, ge=1, le=1000), s=Depends(session)
    ):
        query = select(Contact)
        if job_id is not None:
            query = query.where(Contact.job_id == job_id)
        return [record(c) for c in s.scalars(query.limit(limit))]

    @app.post("/api/v1/contacts/{contact_id}/verify", dependencies=protected)
    def verify_contact(contact_id: int, value: ContactVerification, s=Depends(session)):
        contact = get(s, Contact, contact_id)
        validate_public_url(value.source_url, resolve=False)
        if contact.email.lower() not in value.evidence.lower():
            raise ValueError("Evidence must include the explicitly published email address")
        if value.contact_type not in {"NAMED_RECRUITER", "HIRING_TEAM", "OFFICIAL_CAREERS_INBOX"}:
            raise ValueError("Invalid verified contact type")
        contact.source_url, contact.evidence = value.source_url, value.evidence
        contact.contact_type, contact.verified_at = value.contact_type, utcnow()
        audit(s, "contact", contact.id, "user_verified")
        return record(contact)

    @app.post("/api/v1/outreach", status_code=201, dependencies=protected)
    def new_outreach(value: NewOutreach, s=Depends(session)):
        candidate = singleton(s)
        job, contact, resume = (
            get(s, Job, value.job_id),
            get(s, Contact, value.contact_id),
            get(s, Resume, value.resume_id),
        )
        if contact.job_id != job.id or resume.candidate_id != candidate.id:
            raise Conflict("Contact or resume does not belong to this application")
        if (
            s.scalar(
                select(func.count())
                .select_from(Outreach)
                .where(Outreach.status.in_(["CONTACT_FOUND", "DRAFT_READY"]))
            )
            >= get_search(s).max_drafts_per_run
        ):
            raise Conflict("Draft review queue limit reached")
        row = Outreach(
            candidate_id=candidate.id, job_id=job.id, contact_id=contact.id, resume_id=resume.id
        )
        s.add(row)
        s.flush()
        return record(row)

    @app.get("/api/v1/outreach", dependencies=protected)
    def outreach_list(limit: int = Query(200, ge=1, le=1000), s=Depends(session)):
        return [
            {**record(o), "recipient": s.get(Contact, o.contact_id).email}
            for o in s.scalars(select(Outreach).order_by(Outreach.id.desc()).limit(limit))
        ]

    @app.post("/api/v1/outreach/{outreach_id}/draft", dependencies=protected)
    def draft(outreach_id: int, s=Depends(session)):
        return make_draft(s, get(s, Outreach, outreach_id))

    @app.patch("/api/v1/outreach/{outreach_id}", dependencies=protected)
    def edit(outreach_id: int, value: DraftEdit, s=Depends(session)):
        row = get(s, Outreach, outreach_id)
        editable(row)
        row.subject, row.body, row.status, row.approval_hash = (
            value.subject,
            value.body,
            "DRAFT_READY",
            "",
        )
        audit(s, "outreach", row.id, "edited")
        return record(row)

    @app.post("/api/v1/outreach/{outreach_id}/approve", dependencies=protected)
    def approve(outreach_id: int, s=Depends(session)):
        row = get(s, Outreach, outreach_id)
        editable(row)
        if row.status != "DRAFT_READY":
            raise Conflict("Prepare and review a draft first")
        validate_outreach(s, row)
        row.status, row.approval_hash = "APPROVED", snapshot(s, row, config)
        audit(s, "outreach", row.id, "approved", snapshot=row.approval_hash)
        return record(row)

    @app.post("/api/v1/outreach/{outreach_id}/reject", dependencies=protected)
    def reject(outreach_id: int, s=Depends(session)):
        row = get(s, Outreach, outreach_id)
        editable(row)
        row.status, row.approval_hash = "REJECTED", ""
        audit(s, "outreach", row.id, "rejected")
        return record(row)

    @app.post("/api/v1/outreach/{outreach_id}/send", dependencies=protected)
    def send(outreach_id: int, s=Depends(session)):
        return queue_send(s, get(s, Outreach, outreach_id), config)

    @app.post("/api/v1/outreach/{outreach_id}/gmail-draft", dependencies=protected)
    def gmail_draft(outreach_id: int, s=Depends(session)):
        row = get(s, Outreach, outreach_id)
        editable(row)
        validate_outreach(s, row)
        if config.dry_run:
            return {"dry_run": True, "message": "No Gmail draft created"}
        if row.gmail_draft_id:
            raise Conflict("A Gmail draft already exists; review it in Gmail")
        result = GmailClient(config).create_draft(raw_message(s, row, config, str(uuid4())))
        row.gmail_draft_id = result["id"]
        audit(s, "outreach", row.id, "gmail_draft_created")
        return {"gmail_draft_id": row.gmail_draft_id}

    @app.post("/api/v1/outreach/{outreach_id}/reconcile", dependencies=protected)
    def reconcile(outreach_id: int, s=Depends(session)):
        row = get(s, Outreach, outreach_id)
        if row.status != "SEND_UNCERTAIN":
            raise Conflict("Only uncertain sends can be reconciled")
        operation = s.scalar(select(Outbox).where(Outbox.outreach_id == row.id))
        result = GmailClient(config).reconcile(operation.operation_key)
        if not result:
            return {
                "status": "SEND_UNCERTAIN",
                "message": "No unique sent message found; retry remains blocked",
            }
        row.status, row.gmail_message_id = "SENT", result["id"]
        row.gmail_thread_id, row.sent_at = result.get("threadId", ""), utcnow()
        operation.state = "sent"
        audit(s, "outreach", row.id, "reconciled_sent")
        return record(row)

    @app.post("/api/v1/sending/stop", dependencies=protected)
    def stop(s=Depends(session)):
        row = s.scalar(select(Setting).where(Setting.key == "sending_shutdown"))
        if row:
            row.value = {"disabled": True}
        else:
            s.add(Setting(key="sending_shutdown", value={"disabled": True}))
        audit(s, "settings", 0, "sending_stopped")
        return {"disabled": True}

    @app.post("/api/v1/suppression", dependencies=protected)
    def suppress(email: str, reason: str = "User opted out", s=Depends(session)):
        s.add(Suppressed(email=normalize_email(email), reason=reason[:500]))
        return {"suppressed": True}

    @app.get("/api/v1/export", dependencies=protected)
    def export(s=Depends(session)):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["company", "title", "location", "apply_url", "posting_date"])
        for job in s.scalars(select(Job).limit(10000)):
            values = [
                str(job.data.get(k, ""))
                for k in ["company", "title", "location", "apply_url", "posting_date"]
            ]
            writer.writerow(
                ["'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values]
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=jobs.csv"},
        )

    @app.get("/api/v1/stats", dependencies=protected)
    def stats(s=Depends(session)):
        statuses = dict(
            s.execute(select(Outreach.status, func.count()).group_by(Outreach.status)).all()
        )
        jobs = list(s.scalars(select(Job)))
        return {
            "jobs": len(jobs),
            "verified_recent": sum(
                freshness(parse_date(j.data.get("posting_date"))) == "VERIFIED_RECENT" for j in jobs
            ),
            "verified_contacts": s.scalar(
                select(func.count()).select_from(Contact).where(Contact.verified_at.is_not(None))
            ),
            "matches": s.scalar(select(func.count()).select_from(Match)),
            "pipeline": statuses,
            "dry_run": config.dry_run,
            "sending_enabled": config.sending_enabled,
        }

    # Authenticated OpenAPI is useful locally without exposing sensitive actions publicly.
    @app.get("/api/v1/openapi.json", dependencies=protected)
    def schema():
        return JSONResponse(jsonable_encoder(app.openapi()))

    return app


app = create_app()
