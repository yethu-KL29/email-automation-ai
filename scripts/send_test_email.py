"""Explicit single-message connectivity test; does not enable recruiter delivery."""

import json
from uuid import uuid4

from job_outreach.config import settings
from job_outreach.domain import utcnow
from job_outreach.gmail import GmailClient, build_text_message
from job_outreach.security import normalize_email


def main():
    config = settings()
    if not config.sender_email or not config.test_recipient:
        raise SystemExit("Set SENDER_EMAIL and TEST_RECIPIENT in .env first.")
    client = GmailClient(config)
    if not client.token_path.exists():
        if not config.oauth_client_file.exists():
            raise SystemExit(
                "Not sent: Gmail OAuth client is missing. Save your Google Cloud Desktop "
                "OAuth client JSON to data/credentials.json, then rerun this command. "
                "See docs/oauth_setup.md. Do not share your Gmail password."
            )
        client.authorize()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    receipt = config.data_dir / "hi-test-send.json"
    sender = normalize_email(config.sender_email)
    recipient = normalize_email(config.test_recipient)
    operation = str(uuid4())
    state = {
        "operation": operation,
        "from": sender,
        "to": recipient,
        "subject": "HI",
        "body": "HI",
        "started_at": utcnow().isoformat(),
        "status": "SENDING",
    }
    raw = build_text_message(sender, recipient, "HI", "HI", operation)
    # Exclusive file creation blocks repeated sends, including ambiguous prior attempts.
    try:
        with receipt.open("x", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
    except FileExistsError:
        raise SystemExit(
            "Test operation already exists. Inspect data/hi-test-send.json; no resend attempted."
        )
    try:
        result = client.send(raw)
        if not result.get("id"):
            raise ValueError("Gmail did not return a sent message ID")
    except Exception as exc:
        state.update(status="SEND_UNCERTAIN", error_type=type(exc).__name__)
        receipt.write_text(json.dumps(state, indent=2), encoding="utf-8")
        raise SystemExit(
            "Send outcome uncertain or failed. Inspect Gmail Sent before any retry. No automatic retry."
        ) from None
    state.update(
        status="SENT", gmail_message_id=result["id"], gmail_thread_id=result.get("threadId", "")
    )
    receipt.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Gmail confirmed sending HI from {sender} to {recipient}. Message ID: {result['id']}")


if __name__ == "__main__":
    main()
