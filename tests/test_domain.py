from datetime import UTC, datetime, timedelta

import pytest

from job_outreach.domain import JobData, SearchProfile, canonical_url, freshness, match_job
from job_outreach.security import validate_public_url


def test_unknown_date_is_not_recent():
    now = datetime.now(UTC)
    assert freshness(None, now) == "POSTING_DATE_UNKNOWN"
    assert freshness(now - timedelta(hours=23), now) == "VERIFIED_RECENT"
    assert freshness(now - timedelta(hours=25), now) == "VERIFIED_OLDER"
    assert freshness(now + timedelta(days=2), now) == "POSTING_DATE_UNKNOWN"


def test_url_dedup_keeps_distinct_requisitions():
    assert (
        canonical_url("https://jobs.example/a?utm_source=x&id=1") == "https://jobs.example/a?id=1"
    )
    assert canonical_url("https://jobs.example/a?id=1") != canonical_url(
        "https://jobs.example/a?id=2"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "https://169.254.169.254/",
        "file:///etc/passwd",
        "https://user:pass@example.com/",
        "https://[::1]/",
    ],
)
def test_ssrf_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url, resolve=False)


def test_matching_unknown_experience_and_missing_skills():
    job = JobData(
        source="ashby",
        external_id="1",
        company="Acme",
        title="AI Engineer",
        canonical_url="https://example.com/1",
        apply_url="https://example.com/1",
        description="Python and Kubernetes",
    )
    result = match_job(
        {"skills": ["Python"], "facts": ["Built Python services"]}, job, SearchProfile()
    )
    assert "Python" in result["matched_skills"]
    assert "experience" in " ".join(result["uncertainties"]).lower()
    assert result["eligible"]
