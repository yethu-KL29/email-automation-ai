# Architecture

FastAPI handles authenticated single-user operations. Streamlit is a local client holding the
API token in process configuration. SQLAlchemy transactions persist profiles, resume versions,
companies, jobs, contacts, matches, outreach, outbox operations, audit events and suppression.
Alembic owns the initial schema. PostgreSQL is the deployment target; SQLite is a local preview.

Discovery fetches from fixed public ATS API hosts. One advisory lock prevents overlapping runs;
per-board commits provide checkpoints and deduplication makes reruns safe. A dedicated
APScheduler process schedules discovery and has its own lifetime advisory lock.

Resume bytes are stored by content hash separately from parsed text and editable profiles.
Only reviewed facts can be used in email templates. Every outreach references one immutable
resume record; its hash is rechecked before approval/delivery. DOCX is accepted for extraction,
but a PDF version must be selected for email delivery.

Matching starts with deterministic title/company/keyword checks and lexical overlap. Unknown
qualifications remain uncertainties. Optional AI assessment adds cached embeddings and exact
fact-index/job-quote references, validating structured output before persisting the weighted
35/25/20/10/10 rubric score. Scores are not hiring probabilities. Embedding caches use content
hashes including provider/model; they currently use JSON rather than a pgvector index.

Outreach moves from CONTACT_FOUND to DRAFT_READY to APPROVED to SENDING to SENT, with
REJECTED, SEND_UNCERTAIN and blocked outbox alternatives. Discovery/matching/no-contact stages
exist in their separate job/match/contact records. The current UI does not implement automated
reply, interview and closed-state tracking.

Approval binds content, recipient, sender, resume hash and reviewed profile. The send endpoint
only queues a unique operation. The sender validates policy again, commits SENDING, calls Gmail
once without library retries, and persists the returned Gmail message/thread IDs. Network failure
or a process dying after claim yields uncertainty; a later run cannot retry it. Optional sent-mail
reconciliation can confirm delivery by RFC Message-ID. No result does not imply non-delivery.

Security boundaries: local-only ports; Bearer token for sensitive API routes; encrypted OAuth
tokens; ignored secret files; suppression checks; conservative contact validation; no tools
available to LLMs; no external content can approve or enqueue email. Exact evidence existence
checks cannot prove that LLM interpretations are semantically correct—human review remains required.
Credentials in `.env` and resumes on disk need operating-system account protection and encrypted
storage/backups; OAuth encryption does not encrypt the entire resume database.
