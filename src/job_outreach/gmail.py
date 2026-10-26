import base64
import json
from email.message import EmailMessage
from pathlib import Path

from cryptography.fernet import Fernet
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from job_outreach.config import Settings
from job_outreach.security import normalize_email

COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def build_text_message(sender: str, recipient: str, subject: str, body: str, operation: str) -> str:
    if any("\r" in v or "\n" in v for v in [sender, recipient, subject, operation]):
        raise ValueError("Header injection rejected")
    message = EmailMessage()
    message["From"] = normalize_email(sender)
    message["To"] = normalize_email(recipient)
    message["Subject"] = subject
    message["Message-ID"] = f"<{operation}@job-outreach.local>"
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def build_message(
    sender: str,
    name: str,
    recipient: str,
    subject: str,
    body: str,
    pdf: bytes,
    filename: str,
    operation: str,
) -> str:
    if any("\r" in v or "\n" in v for v in [sender, name, recipient, subject, filename, operation]):
        raise ValueError("Header injection rejected")
    from email.utils import formataddr

    message = EmailMessage()
    message["From"] = formataddr((name, normalize_email(sender)))
    message["To"] = normalize_email(recipient)
    message["Subject"] = subject
    message["Message-ID"] = f"<{operation}@job-outreach.local>"
    message.set_content(body)
    message.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


class GmailClient:
    def __init__(self, config: Settings):
        self.config = config

    @property
    def token_path(self) -> Path:
        return self.config.data_dir / "gmail-token.enc"

    def cipher(self):
        key = self.config.credential_key.get_secret_value()
        if not key:
            raise ValueError("CREDENTIAL_KEY is required; generate one with the setup command")
        return Fernet(key.encode())

    def save(self, credentials):
        self.config.data_dir.mkdir(exist_ok=True, parents=True)
        self.token_path.write_bytes(self.cipher().encrypt(credentials.to_json().encode()))

    def authorize(self, read: bool = False):
        scopes = [COMPOSE_SCOPE] + ([READ_SCOPE] if read else [])
        flow = InstalledAppFlow.from_client_secrets_file(str(self.config.oauth_client_file), scopes)
        credentials = flow.run_local_server(
            port=0, open_browser=True, access_type="offline", prompt="consent"
        )
        self.save(credentials)

    def service(self):
        if not self.token_path.exists():
            raise ValueError("Authorize Gmail first: uv run python -m job_outreach.cli oauth")
        info = json.loads(self.cipher().decrypt(self.token_path.read_bytes()))
        credentials = Credentials.from_authorized_user_info(info)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.save(credentials)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def create_draft(self, raw: str) -> dict:
        return (
            self.service()
            .users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute(num_retries=0)
        )

    def send(self, raw: str) -> dict:
        # Deliberately no Google client retries: timeout may mean delivery succeeded.
        service = self.service()
        account = service.users().getProfile(userId="me").execute(num_retries=0)
        if normalize_email(account["emailAddress"]) != normalize_email(self.config.sender_email):
            raise ValueError("Authorized Gmail account differs from configured sender")
        return (
            service.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=0)
        )

    def reconcile(self, operation: str) -> dict | None:
        service = self.service()
        result = (
            service.users()
            .messages()
            .list(
                userId="me", q=f"in:sent rfc822msgid:{operation}@job-outreach.local", maxResults=10
            )
            .execute(num_retries=0)
        )
        messages = result.get("messages", [])
        return messages[0] if len(messages) == 1 else None
