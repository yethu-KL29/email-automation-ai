import base64
from email import policy
from email.parser import BytesParser

from job_outreach.gmail import build_text_message


def test_hi_message_has_no_attachment():
    raw = build_text_message(
        "sender@example.com", "recipient@example.com", "HI", "HI", "test-operation"
    )
    message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw))
    assert message["Subject"] == "HI"
    assert message["From"] == "sender@example.com"
    assert message["To"] == "recipient@example.com"
    assert message.get_content().strip() == "HI"
    assert list(message.iter_attachments()) == []
