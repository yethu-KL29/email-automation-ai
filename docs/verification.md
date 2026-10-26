# Verification evidence

Executed on 2026-10-25 and rechecked on 2026-10-26, Windows, Python 3.12.12, uv 0.11.29.

- Automated tests: 26 passing. Isolated SQLite databases and mocked Gmail/HTTP responses.
- Domain: unknown/older/future posting dates, conservative URL identities, private-URL
  rejection, lexical matching uncertainties, cosine ranking and evidence validation.
- Services: Ashby/Greenhouse normalization, malformed responses, null compensation regression,
  DOCX extraction, invalid PDF, exact MIME attachment bytes, header injection, grounded drafts.
- API: authorization, resume/profile workflow, contact evidence, missing contacts, draft/edit/
  approve/dry-run flow and invalidation of approval on edits.
- Delivery: returned Gmail identifiers persisted, duplicate attempts prevented, ambiguous
  timeout never retried, interrupted sender becomes uncertain, shutdown and changed-profile
  checks prevent sending, overlapping-run guard.
- Migration: fresh SQLite install, repeated upgrade, schema consistency check.
- Ruff lint and format checks; mypy against application source.
- Live GET-only smoke: OpenAI Ashby 793 jobs, all with publication timestamps; Anthropic
  Greenhouse 682 jobs, all with unknown publication date. Counts change with live boards.
  No live jobs were added to the user's empty preview database by this smoke test.
- Local API `/api/v1/health`: `{"status":"ok"}`.
- Browser inspection: Streamlit overview renders, including preview-mode banner, navigation,
  statistics, discovery/matching controls. This is not a full browser workflow test.
- Live Gmail OAuth and one-message HI tests succeeded with two separately authorized personal
  accounts. Gmail returned sent-message IDs. These were explicitly requested manual tests,
  with no attachments; resume-attachment delivery has not been tested against live Gmail.

## Not yet verified or implemented

- Docker is not installed here, so image build/Compose startup and PostgreSQL transaction,
  row-lock and advisory-lock behavior have not been exercised on PostgreSQL.
- Gmail authorization requires each user's own Google Cloud OAuth client and account.
  Real application emails and live resume-attachment delivery have not been tested.
- No configured LLM key: real model/embedding requests have not been executed. Structured
  evidence and cosine math are unit-tested; provider reliability/calibration needs real examples.
- The test suite is a starting regression suite, not comprehensive coverage of all 22 categories
  or every acceptance criterion in context.md. OAuth refresh-error tests, provider retry/pagination
  edge cases, and multi-process PostgreSQL races need additional coverage before production.
- Search-engine/employer-page discovery, pgvector indexing, bulk approval, automated replies,
  advanced eligibility extraction and state tracking beyond delivery remain future work.
- FastAPI's installed TestClient dependency emits a Starlette/httpx deprecation warning; tests pass.
