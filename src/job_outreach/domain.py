import hashlib
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field, HttpUrl


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_date(value: str | int | None) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (float, int)):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def freshness(posted: datetime | None, now: datetime | None = None, hours: int = 24) -> str:
    now = now or utcnow()
    if posted is None:
        return "POSTING_DATE_UNKNOWN"
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    age = now - posted
    if age < timedelta(0):
        return "POSTING_DATE_UNKNOWN"
    return "VERIFIED_RECENT" if age <= timedelta(hours=hours) else "VERIFIED_OLDER"


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    query = sorted(
        (k, v)
        for k, v in parse_qsl(p.query)
        if not k.startswith("utm_") and k not in {"gh_src", "source", "ref"}
    )
    return urlunsplit(
        (p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(query), "")
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class JobData(BaseModel):
    source: str
    external_id: str
    company: str
    company_domain: str = ""
    title: str
    canonical_url: HttpUrl
    apply_url: HttpUrl
    description: str = Field(default="", max_length=200000)
    location: str = ""
    remote_policy: str = "unknown"
    employment_type: str = ""
    salary: str = ""
    posting_date: datetime | None = None
    date_confidence: str = "unknown"
    raw: dict = {}


class CandidateProfile(BaseModel):
    name: str = ""
    email: str = ""
    skills: list[str] = []
    facts: list[str] = []
    experience_years: float | None = Field(default=None, ge=0, le=70)
    signature: str = ""
    work_authorization: str = "unknown"
    verified: bool = False


class SearchProfile(BaseModel):
    roles: list[str] = ["AI Engineer", "Generative AI Engineer", "LLM Engineer"]
    positive_keywords: list[str] = []
    negative_keywords: list[str] = []
    locations: list[str] = []
    work_arrangements: list[str] = []
    minimum_score: float = Field(default=30, ge=0, le=100)
    max_age_hours: int = Field(default=24, ge=1, le=8760)
    excluded_companies: list[str] = []
    preferred_companies: list[str] = []
    salary_preferences: str = ""
    min_experience: float | None = Field(default=None, ge=0)
    max_experience: float | None = Field(default=None, ge=0)
    max_drafts_per_run: int = Field(default=5, ge=1, le=50)
    max_emails_per_run: int = Field(default=5, ge=1, le=50)
    enabled: bool = True


def match_job(profile: dict, job: JobData, search: SearchProfile) -> dict:
    text = (job.title + " " + job.description).lower()
    reasons = []
    unknowns = ["Required experience and work authorization need manual review"]
    if search.roles and not any(role.lower() in job.title.lower() for role in search.roles):
        reasons.append("Title outside target roles")
    if job.company.lower() in [v.lower() for v in search.excluded_companies]:
        reasons.append("Excluded company")
    if any(k.lower() in text for k in search.negative_keywords):
        reasons.append("Excluded keyword")
    if search.locations and not any(
        loc.lower() in job.location.lower() for loc in search.locations
    ):
        unknowns.append("Location eligibility needs review")
    if search.work_arrangements and job.remote_policy not in search.work_arrangements:
        unknowns.append("Work arrangement needs review")
    skills = profile.get("skills", [])
    matched = [s for s in skills if re.search(r"(?<!\w)" + re.escape(s.lower()) + r"(?!\w)", text)]
    skills_score = len(matched) / max(len(skills), 1)
    role_score = 0 if "Title outside target roles" in reasons else 1
    # Conservative lexical baseline: unassessed rubric components contribute zero.
    breakdown = {
        "skills": round(35 * skills_score, 2),
        "projects": 0,
        "role": 20 * role_score,
        "domain": 0,
        "location": 0,
    }
    return {
        "score": round(sum(breakdown.values()), 2),
        "score_breakdown": breakdown,
        "eligible": not reasons,
        "matched_skills": matched,
        "rejections": reasons,
        "uncertainties": unknowns,
        "method": "lexical-v1",
        "prompt_version": None,
    }
