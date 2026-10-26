from contextlib import contextmanager
from datetime import datetime
from typing import TypeVar

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from job_outreach.domain import utcnow


class Base(DeclarativeBase):
    pass


T = TypeVar("T", bound=Base)


def required(session: Session, model: type[T], entity_id: int) -> T:
    row = session.get(model, entity_id)
    if row is None:
        raise ValueError(f"Missing {model.__name__} record")
    return row


class Record(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Candidate(Record):
    __tablename__ = "candidate_profiles"
    name: Mapped[str] = mapped_column(default="")
    email: Mapped[str] = mapped_column(default="")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Resume(Record):
    __tablename__ = "resumes"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    file_path: Mapped[str]
    content_hash: Mapped[str]
    extracted_text: Mapped[str]
    version: Mapped[int]
    __table_args__ = (
        UniqueConstraint("candidate_id", "content_hash"),
        UniqueConstraint("candidate_id", "version"),
    )


class Search(Record):
    __tablename__ = "search_profiles"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"), unique=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class Company(Record):
    __tablename__ = "companies"
    name: Mapped[str]
    domain: Mapped[str] = mapped_column(default="")
    careers_url: Mapped[str] = mapped_column(default="")
    __table_args__ = (UniqueConstraint("name", "domain"),)


class Job(Record):
    __tablename__ = "jobs"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str]
    external_id: Mapped[str]
    url_key: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="open")
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("source", "external_id"),
        Index("ix_job_company", "company_id"),
    )


class Contact(Record):
    __tablename__ = "contacts"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    email: Mapped[str]
    contact_type: Mapped[str] = mapped_column(default="UNVERIFIED")
    source_url: Mapped[str]
    evidence: Mapped[str]
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("job_id", "email"),)


class Match(Record):
    __tablename__ = "job_matches"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    score: Mapped[float]
    result: Mapped[dict] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(default="lexical-v1")
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", "resume_id"),)


class Outreach(Record):
    __tablename__ = "outreach"
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidate_profiles.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    subject: Mapped[str] = mapped_column(default="")
    body: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="CONTACT_FOUND")
    approval_hash: Mapped[str] = mapped_column(default="")
    gmail_draft_id: Mapped[str] = mapped_column(default="")
    gmail_message_id: Mapped[str] = mapped_column(default="")
    gmail_thread_id: Mapped[str] = mapped_column(default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("candidate_id", "job_id"),)


class Outbox(Record):
    __tablename__ = "outbox"
    outreach_id: Mapped[int] = mapped_column(ForeignKey("outreach.id"), unique=True)
    operation_key: Mapped[str] = mapped_column(unique=True)
    state: Mapped[str] = mapped_column(default="pending")
    attempt_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DiscoveryRun(Record):
    __tablename__ = "discovery_runs"
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(default="running")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)


class Audit(Record):
    __tablename__ = "audit_events"
    entity_type: Mapped[str]
    entity_id: Mapped[int]
    event_type: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Suppressed(Record):
    __tablename__ = "suppressed_contacts"
    email: Mapped[str] = mapped_column(unique=True)
    reason: Mapped[str]


class Setting(Record):
    __tablename__ = "runtime_settings"
    key: Mapped[str] = mapped_column(unique=True)
    value: Mapped[dict] = mapped_column(JSON)


class Database:
    def __init__(self, url: str):
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
            pool_pre_ping=True,
        )
        if url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.sessions.begin() as session:
            yield session


def audit(session: Session, kind: str, entity_id: int, event: str, **details):
    session.add(Audit(entity_type=kind, entity_id=entity_id, event_type=event, details=details))
