# Implementation plan

1. Foundation: typed configuration, SQLAlchemy tables, migration, authenticated API,
   local dashboard, Compose, and tests.
2. Discovery: bounded HTTP clients, three public board adapters, UTC freshness,
   conservative deduplication, source reports, scheduler and durable checkpoints.
3. Review: versioned resume ingestion, manual verified facts, deterministic matching,
   optional structured LLM assessments, contact evidence, editable grounded drafts.
4. Delivery: encrypted local Gmail OAuth, correct MIME attachments, approval snapshots,
   transactional outbox, single-attempt delivery and explicit uncertain-send recovery.
5. Verification: mocked external services, API workflow tests, local startup,
   lint/type checks and documented external-account prerequisites.

## Architecture decisions

- Modular monolith. PostgreSQL is the supported deployment database; SQLite is only
  for isolated tests and an explicitly selected local preview.
- FastAPI and Streamlit communicate over an authenticated local API. No public bind
  by default. One scheduler and one sender process; sends require explicit enqueue.
- Use a durable outbox and pessimistic row locking on PostgreSQL. Never retry a
  request after its delivery outcome becomes ambiguous.
- Dates, contact authorization, approval and recipient checks stay deterministic.
- No global search provider or company boards are enabled without configuration.
- Resume facts require review before outreach. Automatic extraction is a convenience,
  and never constitutes verification. Attach PDF resumes for delivery.
- No email goes to a real recruiter during setup or tests. First real send must use
  an explicitly configured test recipient. General delivery is a separate switch.
