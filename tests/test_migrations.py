from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_fresh_install_migration_and_repeat(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "jobs",
        "outreach",
        "outbox",
        "resumes",
        "suppressed_contacts",
        "audit_events",
    } <= tables
    command.check(config)
    engine.dispose()
