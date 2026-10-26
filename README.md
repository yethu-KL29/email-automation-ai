# Job Discovery & Recruiter Outreach

A local Python application for discovering public job postings, reviewing resume facts,
matching roles, finding published recruiting email addresses, and approving Gmail outreach.
FastAPI API, Streamlit dashboard, SQLAlchemy/Alembic persistence, separate scheduler,
and a transactional delivery outbox. Sending and external Gmail draft creation default to dry run.

## Quick local preview (Windows / PowerShell)

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

```powershell
uv sync --frozen
uv run python -m job_outreach.cli setup --preview
uv run python -m job_outreach.cli init-preview
uv run uvicorn job_outreach.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from this same directory:

```powershell
uv run streamlit run dashboard/app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
```

Open http://127.0.0.1:8501. Setup generates a private `.env` with an API token and encryption
key. An existing `.env` is never overwritten. The preview uses SQLite, a single API process,
and no real email. Use PostgreSQL for deployment and cross-process locking.

## PostgreSQL / Docker

Install Docker Desktop and start its engine. For a fresh checkout:

```powershell
uv sync --frozen
uv run python -m job_outreach.cli setup
```

Set `POSTGRES_PASSWORD` in `.env` to a strong URL-safe password. Then:

```powershell
docker compose up --build -d
```

The migration service runs before the API. API and dashboard ports bind only to localhost.
Compose uses PostgreSQL 16 with the pgvector extension available. The current embedding cache
uses JSON and cosine computation in Python; vector indexing is not yet enabled.
The local preview database is separate from PostgreSQL; data is not migrated automatically.

For an existing PostgreSQL installation, set `DATABASE_URL` in `.env`, then run:

```powershell
uv run alembic upgrade head
uv run uvicorn job_outreach.main:app --host 127.0.0.1 --port 8000
```

## Using the workflow

1. **Resume & profile:** upload a text PDF or DOCX (10 MB / 50 PDF pages max). Review
   extracted text and correct your profile. Enter verified experience/achievement statements,
   skills and signature. Confirm review. A new resume upload clears verification.
2. **Search & sources:** set roles, locations, keywords and limits. Add company boards
   you want to search. Example configuration (these are real public boards, not job fixtures):

   ```json
   [
     {"source":"ashby","board":"openai","company":"OpenAI","domain":"openai.com","enabled":true},
     {"source":"greenhouse","board":"anthropic","company":"Anthropic","domain":"anthropic.com","enabled":true}
   ]
   ```

3. **Overview:** run discovery and basic matching. Optional AI assessment requires
   `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`; optionally set `EMBEDDING_MODEL`.
   That action sends verified facts and job descriptions to the configured provider.
   It is bounded by `LLM_CALLS_PER_RUN`. No model is selected on your behalf.
4. **Jobs:** review posting freshness, match evidence and uncertainties. Find published
   recruiting contacts. Verify unverified contacts against the actual published evidence.
   No contact means use the linked application portal.
5. **Draft review:** create an application with a selected PDF resume version; generate and
   edit its email. Save edits, review recipient/content/resume and approve. Editing clears
   approval. Profile/contact/sender changes invalidate the approval snapshot.
6. With default settings, send is a **dry run**: it neither queues nor sends a message.
   Connect Gmail and follow [OAuth setup](docs/oauth_setup.md) for the first authorized test.

## Your details needed

See [onboarding checklist](docs/onboarding.md). Do not paste keys, Gmail passwords, tokens,
or the contents of `.env` into chat. Gmail uses browser OAuth, never your Gmail password.

## Scheduling and sending

```powershell
uv run python -m job_outreach.cli scheduler
```

Runs discovery daily at `SCHEDULE_HOUR` in `TIMEZONE` (default Asia/Kolkata). Launch exactly
one scheduler. PostgreSQL advisory locks prevent concurrent discovery and duplicate scheduler
processes. Enable the optional Compose service with `docker compose --profile schedule up -d`.
SQLite preview locking only protects one process and is not suitable for this deployment.

Sending is deliberately separate from discovery. The API queues an approved operation;
this command processes at most one queued operation:

```powershell
uv run python -m job_outreach.cli send-once
```

Global stop in the dashboard blocks future attempts. In-flight network calls cannot be recalled.
See [operations](docs/operations.md) for recovery, shutdown and backups.

## Verification

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/job_outreach
uv run python scripts/smoke_sources.py
```

The last command performs real GET requests to OpenAI's Ashby and Anthropic's Greenhouse boards.
It saves no jobs and sends no email. Other tests mock external services.
See [verification evidence and limitations](docs/verification.md).

## Scope and limits

This is a working initial vertical slice, not completion of every feature in `context.md`.
Basic matching is conservative lexical scoring (up to 55/100; unknown rubric components
contribute zero), followed by optional cached semantic/LLM assessment. Evidence validation
checks citation existence; the user must judge relevance and factual accuracy.
There is no restricted-site scraping, global search-engine discovery, employer-page crawler,
authorized enrichment connector, automated reply monitoring, OCR or automatic follow-up.
Salary/experience preferences are stored for review; unstructured qualifications and regional
work eligibility require human review. Missing information never counts as a confirmed failure.
LLM integration supports OpenAI-compatible endpoints; other native provider protocols and Azure
deployment URL conventions need their own adapter. Email writing currently uses a grounded,
editable template. The provider interface is available for further composition work.

Gmail OAuth and plain-text test delivery have been verified with authorized personal accounts.
Resume-attachment delivery and PostgreSQL concurrency still need verification with your account
and infrastructure. Do not expose this single-user application directly to the internet.
