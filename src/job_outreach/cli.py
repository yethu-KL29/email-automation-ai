import argparse
import asyncio
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from job_outreach.config import settings
from job_outreach.db import Database
from job_outreach.gmail import GmailClient
from job_outreach.workflows import deliver_one, discover


def main():
    parser = argparse.ArgumentParser(description="Job Outreach local operations")
    parser.add_argument(
        "command", choices=["setup", "init-preview", "oauth", "discover", "send-once", "scheduler"]
    )
    parser.add_argument("--preview", action="store_true")
    parser.add_argument(
        "--with-read",
        action="store_true",
        help="Separately authorize mailbox read for reconciliation",
    )
    args = parser.parse_args()
    if args.command == "setup":
        path = Path(".env")
        if path.exists():
            raise SystemExit(".env already exists; edit it locally (not overwritten)")
        template = Path(".env.example").read_text(encoding="utf-8")
        template = template.replace("API_TOKEN=", "API_TOKEN=" + secrets.token_urlsafe(32), 1)
        template = template.replace(
            "CREDENTIAL_KEY=", "CREDENTIAL_KEY=" + Fernet.generate_key().decode(), 1
        )
        if args.preview:
            template = template.replace(
                "postgresql+psycopg://outreach:outreach@localhost:5432/outreach",
                "sqlite:///data/preview.db",
            )
        Path("data").mkdir(exist_ok=True)
        path.write_text(template, encoding="utf-8")
        print("Created .env with local credentials. Keep .env private.")
        return
    config = settings()
    db = Database(config.database_url)
    if args.command == "init-preview":
        if not config.database_url.startswith("sqlite"):
            raise SystemExit("Use uv run alembic upgrade head for PostgreSQL")
        config.data_dir.mkdir(exist_ok=True, parents=True)
        from alembic.config import Config

        from alembic import command

        command.upgrade(Config("alembic.ini"), "head")
        print("Local SQLite preview initialized. PostgreSQL is required for deployment.")
    elif args.command == "oauth":
        GmailClient(config).authorize(read=args.with_read)
        print("Gmail authorized; encrypted token saved locally. Sending settings unchanged.")
    elif args.command == "discover":
        print(json.dumps(asyncio.run(discover(db, config))))
    elif args.command == "send-once":
        print(json.dumps(deliver_one(db, config)))
    elif args.command == "scheduler":
        from job_outreach.scheduling import serve

        serve(db, config)


if __name__ == "__main__":
    main()
