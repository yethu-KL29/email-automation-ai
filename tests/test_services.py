import base64
from email import policy
from email.parser import BytesParser

import httpx
import pytest

from job_outreach.composer import compose, validate_grounding
from job_outreach.discovery import BoardSource
from job_outreach.gmail import build_message
from job_outreach.resumes import extract_resume


@pytest.mark.asyncio
async def test_ashby_and_greenhouse_dates():
    def handler(request):
        if "ashby" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": "1",
                            "title": "AI Engineer",
                            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                            "applyUrl": "https://jobs.ashbyhq.com/acme/1/apply",
                            "publishedAt": "2026-10-25T04:00:00Z",
                            "descriptionPlain": "Python",
                            "isListed": True,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 2,
                        "title": "Engineer",
                        "absolute_url": "https://boards.greenhouse.io/acme/2",
                        "updated_at": "2026-10-25T04:00:00Z",
                        "content": "<p>Python</p>",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ashby = await BoardSource(
            {"source": "ashby", "board": "acme", "company": "Acme"}, client
        ).fetch()
        gh = await BoardSource(
            {"source": "greenhouse", "board": "acme", "company": "Acme"}, client
        ).fetch()
    assert ashby[0].posting_date is not None
    assert gh[0].posting_date is None
    assert gh[0].description == "Python"


@pytest.mark.asyncio
async def test_provider_malformed_response():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"jobs": "wrong"}))
    ) as client:
        with pytest.raises(ValueError):
            await BoardSource({"source": "ashby", "board": "acme"}, client).fetch()


@pytest.mark.asyncio
async def test_ashby_null_compensation():
    payload = {
        "jobs": [
            {
                "title": "Engineer",
                "jobUrl": "https://example.com/1",
                "applyUrl": "https://example.com/1",
                "compensation": {"compensationTierSummary": None},
            }
        ]
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))
    ) as client:
        jobs = await BoardSource({"source": "ashby", "board": "acme"}, client).fetch()
    assert jobs[0].salary == ""


def test_docx_extract_and_invalid_file():
    from io import BytesIO

    from docx import Document

    doc = Document()
    doc.add_paragraph("Built Python services")
    stream = BytesIO()
    doc.save(stream)
    assert "Built Python services" in extract_resume(stream.getvalue(), ".docx")
    with pytest.raises(ValueError):
        extract_resume(b"fake", ".pdf")


def test_mime_attachment_and_headers():
    raw = build_message(
        "sender@example.com",
        "Candidate",
        "recruiter@example.com",
        "Role",
        "Hello",
        b"%PDF-1.4 resume",
        "resume.pdf",
        "operation-1",
    )
    msg = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
    assert msg["To"] == "recruiter@example.com"
    attachment = list(msg.iter_attachments())[0]
    assert attachment.get_payload(decode=True) == b"%PDF-1.4 resume"
    assert attachment.get_filename() == "resume.pdf"
    with pytest.raises(ValueError):
        build_message(
            "sender@example.com",
            "Candidate",
            "recruiter@example.com",
            "Role\nBcc:bad@example.com",
            "Hello",
            b"pdf",
            "resume.pdf",
            "op",
        )


def test_composer_uses_only_verified_facts():
    profile = {
        "verified": True,
        "name": "Candidate",
        "facts": ["Built Python services"],
        "signature": "Candidate",
    }
    draft = compose(profile, {"title": "AI Engineer", "company": "Acme"})
    assert "Built Python services" in draft["body"]
    assert "10 years" not in draft["body"]
    with pytest.raises(ValueError):
        validate_grounding(["Managed 100 people"], profile)
    with pytest.raises(ValueError):
        compose({**profile, "verified": False}, {"title": "AI Engineer", "company": "Acme"})
