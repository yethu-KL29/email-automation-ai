from unittest.mock import Mock

import pymupdf
import pytest
from sqlalchemy import select
from test_api import make_client, seed_job

from job_outreach.db import Outbox, Outreach
from job_outreach.workflows import Conflict, deliver_one, exclusive


def approved_application(tmp_path):
    app, client = make_client(tmp_path)
    app.state.config.sender_email = "candidate@example.com"
    app.state.config.sender_name = "Candidate"
    app.state.config.test_recipient = "careers@example.com"
    app.state.config.sending_enabled = True
    app.state.config.dry_run = False
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), "Built Python services")
        pdf = doc.tobytes()
    resume = client.post("/api/v1/resumes", files={"file": ("resume.pdf", pdf)}).json()
    client.put(
        "/api/v1/profile",
        json={"name": "Candidate", "facts": ["Built Python services"], "verified": True},
    )
    job_id = seed_job(app)
    client.post(f"/api/v1/jobs/{job_id}/contacts")
    contact = client.get("/api/v1/contacts").json()[0]
    outreach = client.post(
        "/api/v1/outreach",
        json={"job_id": job_id, "contact_id": contact["id"], "resume_id": resume["id"]},
    ).json()
    client.post(f"/api/v1/outreach/{outreach['id']}/draft")
    assert client.post(f"/api/v1/outreach/{outreach['id']}/approve").status_code == 200
    assert client.post(f"/api/v1/outreach/{outreach['id']}/send").status_code == 200
    return app, client, outreach["id"]


def test_ambiguous_delivery_never_retried(tmp_path):
    app, client, outreach_id = approved_application(tmp_path)
    gmail = Mock()
    gmail.send.side_effect = TimeoutError("uncertain")
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "SEND_UNCERTAIN"
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "idle"
    assert gmail.send.call_count == 1
    assert client.post(f"/api/v1/outreach/{outreach_id}/send").status_code == 409
    assert (
        client.patch(
            f"/api/v1/outreach/{outreach_id}", json={"subject": "Retry", "body": "Retry"}
        ).status_code
        == 409
    )


def test_success_persists_real_identifiers_and_deduplicates(tmp_path):
    app, client, outreach_id = approved_application(tmp_path)
    gmail = Mock()
    gmail.send.return_value = {"id": "mock-gmail-message", "threadId": "mock-thread"}
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "SENT"
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "idle"
    row = client.get("/api/v1/outreach").json()[0]
    assert row["gmail_message_id"] == "mock-gmail-message"
    assert row["gmail_thread_id"] == "mock-thread"
    assert row["sent_at"]
    assert client.post(f"/api/v1/outreach/{outreach_id}/send").status_code == 409


def test_shutdown_and_suppression_at_delivery(tmp_path):
    app, client, outreach_id = approved_application(tmp_path)
    gmail = Mock()
    client.post("/api/v1/sending/stop")
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "disabled"
    gmail.send.assert_not_called()


def test_changed_profile_blocks_already_queued_send(tmp_path):
    app, client, outreach_id = approved_application(tmp_path)
    client.put("/api/v1/profile", json={"facts": ["Different fact"], "verified": True})
    gmail = Mock()
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "blocked"
    gmail.send.assert_not_called()


def test_crash_during_send_is_uncertain(tmp_path):
    app, client, outreach_id = approved_application(tmp_path)
    with app.state.db.session() as s:
        s.scalar(select(Outbox)).state = "sending"
        s.get(Outreach, outreach_id).status = "SENDING"
    gmail = Mock()
    assert deliver_one(app.state.db, app.state.config, gmail)["status"] == "idle"
    assert client.get("/api/v1/outreach").json()[0]["status"] == "SEND_UNCERTAIN"
    gmail.send.assert_not_called()


def test_overlapping_runs_rejected(tmp_path):
    app, _ = make_client(tmp_path)
    with exclusive(app.state.db, 1):
        with pytest.raises(Conflict):
            with exclusive(app.state.db, 1):
                pass
