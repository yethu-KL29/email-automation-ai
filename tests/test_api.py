import pymupdf
from fastapi.testclient import TestClient

from job_outreach.config import Settings
from job_outreach.db import Base, Company, Job
from job_outreach.domain import JobData, canonical_url, digest
from job_outreach.main import create_app


def make_client(tmp_path):
    config = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_token="test-secret-at-least-32-characters",
        data_dir=tmp_path,
        _env_file=None,
    )
    app = create_app(config)
    Base.metadata.create_all(app.state.db.engine)
    return app, TestClient(
        app, headers={"Authorization": "Bearer test-secret-at-least-32-characters"}
    )


def seed_job(app):
    data = JobData(
        source="ashby",
        external_id="1",
        company="Acme",
        company_domain="example.com",
        title="AI Engineer",
        description="Python. Contact careers@example.com for this role.",
        canonical_url="https://example.com/jobs/1",
        apply_url="https://example.com/jobs/1",
    )
    with app.state.db.session() as s:
        company = Company(name="Acme", domain="example.com")
        s.add(company)
        s.flush()
        job = Job(
            company_id=company.id,
            source=data.source,
            external_id=data.external_id,
            url_key=digest(canonical_url(str(data.apply_url))),
            title=data.title,
            data=data.model_dump(mode="json"),
        )
        s.add(job)
        s.flush()
        return job.id


def test_authentication_and_resume_workflow(tmp_path):
    app, client = make_client(tmp_path)
    assert TestClient(app).get("/api/v1/jobs").status_code == 401
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), "Candidate built Python services")
        pdf = doc.tobytes()
    upload = client.post("/api/v1/resumes", files={"file": ("resume.pdf", pdf, "application/pdf")})
    assert upload.status_code == 201, upload.text
    profile = {
        "name": "Candidate",
        "email": "candidate@example.com",
        "facts": ["Built Python services"],
        "skills": ["Python"],
        "verified": True,
    }
    assert client.put("/api/v1/profile", json=profile).status_code == 200
    job_id = seed_job(app)
    assert client.post("/api/v1/matches/run").status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/contacts").status_code == 200
    contacts = client.get("/api/v1/contacts").json()
    assert contacts[0]["contact_type"] == "OFFICIAL_CAREERS_INBOX"
    response = client.post(
        "/api/v1/outreach",
        json={"job_id": job_id, "contact_id": contacts[0]["id"], "resume_id": upload.json()["id"]},
    )
    assert response.status_code == 201, response.text
    outreach_id = response.json()["id"]
    assert client.post(f"/api/v1/outreach/{outreach_id}/send").status_code == 409
    assert client.post(f"/api/v1/outreach/{outreach_id}/draft").status_code == 200
    assert client.post(f"/api/v1/outreach/{outreach_id}/approve").status_code == 200
    # Default dry run never calls Gmail and cannot claim SENT.
    response = client.post(f"/api/v1/outreach/{outreach_id}/send")
    assert response.status_code == 200, response.text
    assert response.json()["dry_run"] is True
    assert client.get("/api/v1/outreach").json()[0]["status"] == "APPROVED"
    # Editing always invalidates approval.
    assert (
        client.patch(
            f"/api/v1/outreach/{outreach_id}", json={"subject": "Updated", "body": "Changed"}
        ).status_code
        == 200
    )
    assert client.post(f"/api/v1/outreach/{outreach_id}/send").status_code == 409


def test_missing_contact_stays_missing(tmp_path):
    app, client = make_client(tmp_path)
    job_id = seed_job(app)
    with app.state.db.session() as s:
        job = s.get(Job, job_id)
        job.data = {**job.data, "description": "Apply using the portal"}
    response = client.post(f"/api/v1/jobs/{job_id}/contacts")
    assert response.json()["status"] == "NOT_FOUND"
    assert client.get("/api/v1/contacts").json() == []
