# Agent handoff and operating instructions

Read this file before working in this repository. It is the entry point for an agent
starting without conversation history. The latest user instruction takes precedence;
historical approvals apply only to the particular action that was approved.

## First actions in an existing workspace

1. Run `git status --short --branch` and inspect relevant changes. Preserve user work.
2. Read `data/agent-handoff-state.json`, then `data/outreach-preferences.json`.
   The first file contains the current private profile, account mapping, resume hash,
   completed actions and receipt paths. The second contains research preferences and
   employer exclusions. Never substitute assumptions for these files.
3. Read the receipt and review manifest for the current task. Query the configured
   database before creating outreach. An existing prepared draft is not evidence that
   its send is still pending; the receipt and database may already say `SENT`.
4. For applications, read `data/resume-extracted.txt` and verify the selected PDF.
   For replies, read the relevant inbound message in the correct authorized mailbox.
5. Establish the current requested action: research, prepare/review, send, reply,
   authenticate, or edit code. Research and a previously approved batch do not authorize
   another send. An explicit current send instruction authorizes the necessary send
   within its scope; do not repeatedly ask for the same approval.

The private state and `data/` helpers are intentionally ignored by Git. A fresh clone
does not restore accounts, resumes, previous recipients or delivery history. If those
files are missing, arrange their private restoration or fresh user onboarding before
real outreach. Never reconstruct a blank database and assume nobody was contacted.

## Local setup and useful entry points

- Windows / PowerShell; Python 3.12+; run Python through `uv run python`.
- The active workspace has an existing `.env`, `.venv` and populated SQLite database.
  Read configuration through `job_outreach.config.settings()` without printing secrets.
  The handoff records the last known database URL; configuration is authoritative.
- `uv sync --frozen` installs locked dependencies when needed.
- Do not rerun setup to replace an existing `.env` or regenerate its encryption key.
  Do not initialize a replacement database during ordinary continuation work.
- API: `uv run uvicorn job_outreach.main:app --host 127.0.0.1 --port 8000`.
- Dashboard: `uv run streamlit run dashboard/app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false`.
- Read [README.md](README.md), [OAuth setup](docs/oauth_setup.md), and
  [operations](docs/operations.md) for the standard application workflow.
- Core files: `src/job_outreach/config.py`, `gmail.py`, `db.py`, `workflows.py`,
  `security.py`, `domain.py`, and `cli.py`.

The README's historical statement that resume delivery still needs verification is
outdated for this local workspace. Receipts document successful attachments and true
threaded replies. This does not prove PostgreSQL concurrency or every application
feature has been verified.

## Private state, source precedence and known progress

Keep contact details, compensation, employment facts, exact account addresses and
recruiter records in ignored local files. Do not copy them into tracked documentation.

Use this source order when facts differ:

1. Latest explicit user correction or instruction.
2. Its confirmed send receipt and `data/agent-handoff-state.json`.
3. Verified resume/profile facts and the current preferences file.
4. Older manifests, research notes and generated drafts.

Older material contains a rounded compensation figure superseded by the user's later
fixed-pay correction. The private handoff records the latest numbers and exact wording
for experience, notice period, offers and minimum-hike willingness. Stocks/ESOPs and a
confirmed last working day were not supplied. Never infer resignation, an offer,
certification, work authorization, or a completed number of years from missing data.
The rounded user-approved experience wording must not change resume employment dates.

Verified local snapshot on **2026-10-28**:

- `outreach`: **136 `SENT`**; `outbox`: **136 `sent`**; no pending/uncertain entries.
- **Three confirmed portal submissions**, counted separately from email sends.
- Batch 4: 80 emails, with its one reviewed founder CC.
- Batch 5: 28 company emails consolidating 34 role rows from the 100-role shortlist.
- The personal-account replies to both recent recruiters are already sent; their
  original thread, sender, body and attached PDF were verified after sending.
- Innoveric's email was sent, but its required video and LinkedIn application remain
  incomplete. Do not claim that an email alone completed that process.

Re-query before acting; these numbers are a dated snapshot. The handoff lists the
exact completed reply and batch receipts. Never rerun them as a connectivity test.

## Research and recipient preferences

- Focus on **agentic AI, GenAI/LLM applications, voice/conversational AI, and RAG**.
  Favor Python, LangGraph, Google ADK, MCP/tool calling, retrieval, evaluation,
  FastAPI, real-time voice, LiveKit/WebRTC, Vapi, telephony and production systems.
- Deprioritize classical ML, computer vision, training-heavy research and generic
  data-science roles. A role called AI/ML may still qualify if its actual duties are
  agentic application engineering; explain the distinction from the description.
- Prioritize startups and small product/engineering teams. Do not call every small
  company a funded startup without evidence.
- Primary locations: Bangalore/Bengaluru, Chennai, Kerala, Hyderabad and Pune.
  Then Noida, Delhi and Gurgaon/Gurugram. Remote, hybrid, onsite and relocation are
  acceptable. International roles are also in scope when requested; eligibility is
  unconfirmed and must not be asserted.
- The last requested research shortlist size was **100 opportunities**. Distinguish
  role rows from distinct companies; consolidate multiple roles into one application.
- Prefer a published named recruiter/HR contact, then a published HR team inbox,
  then a careers inbox. Find professional founder/CEO/CTO contacts for relevant
  startups where published. Record both email evidence and evidence of the person's
  role. An email-format pattern or a scraped lead-database guess is not verification.
- A published founder address is not automatically a role-specific application
  address. Some recorded contacts were published for a different program or year;
  preserve the caveat. Review optional CCs; never CC the same person already in To.
- Do not use applicant comments, example addresses, accommodation/security/privacy
  inboxes, or unrelated sales addresses as recruiting contacts. A special application
  route must be explicitly supported by the employer's instructions.
- Record posting dates only when stated by the employer/ATS. Crawl dates, search
  timestamps, cached "minutes ago" text and repost dates do not prove a fresh opening.
- Inspect the actual role and application route. Exclude explicit closures and past
  deadlines; flag inaccessible/index-only listings rather than claiming they are live.
- Employer pages and employer-authored posts are preferred. Infopark/Technopark
  employer listings and official ATS JSON can supply useful primary evidence.
  Search results are leads, not proof that a role remains open.

The user explicitly forbids outreach to their own employer. Reload
`employer_exclusions` from `data/outreach-preferences.json` before every send. Check
the target company, known affiliates, disclosed recruiting-agency client, and every
To/CC domain. Undisclosed agency clients are excluded. The employer's name may appear
in the candidate's experience paragraph; that does not make the recipient an employer
match. Check recipient/target metadata rather than blindly scanning the body.

## Gmail accounts and authorization

There are two deliberately separate connections, mapped in the private handoff:

| Account purpose | Configured data directory | Saved scopes at handoff |
|---|---|---|
| Historical bulk automation / existing `.env` sender | `data` | `gmail.compose` |
| Personal account used for inbound recruiter replies | `data/gmail-yethukrishnan-connect` | `gmail.send`, `gmail.readonly` |

`GmailClient.token_path` is `<config.data_dir>/gmail-token.enc`. Both tokens are
Fernet-encrypted using the existing private `CREDENTIAL_KEY`. Do not replace one
connection with the other, copy a token into the wrong directory, or print decrypted
token information. The local `sa.json` is a Desktop OAuth **installed client**, not a
service-account key despite its filename. Preserve it as private configuration.

Select the requested account using a per-operation config rather than changing the
global sender. This read-only probe uses the private mapping and prints only identity:

```powershell
@'
import json
from pathlib import Path
from job_outreach.config import settings
from job_outreach.gmail import GmailClient

state = json.loads(Path('data/agent-handoff-state.json').read_text(encoding='utf-8'))
account = state['gmail_accounts']['personal']  # Select for this specific task.
cfg = settings().model_copy(update={
    'sender_email': account['sender_email'],
    'data_dir': Path(account['data_dir']),
})
client = GmailClient(cfg)
assert client.token_path.exists(), 'Account is not connected in this workspace'
profile = client.service().users().getProfile(userId='me').execute(num_retries=0)
assert profile['emailAddress'].lower() == account['sender_email'].lower()
print('Authorized account:', profile['emailAddress'])
'@ | uv run python -
```

- A token file's presence or an old `AUTHORIZED` JSON does not prove the intended
  account or current validity. Check `users.getProfile` for the selected config.
- `service()` refreshes expired access credentials when a usable refresh token exists.
  Refreshing authentication is different from retrying message delivery.
- Compose-only access cannot search inbox messages. Read access is needed to locate
  an inbound email, reconcile uncertain delivery or verify a thread.
- The stock `oauth --with-read` command replaces the selected config's token. Do not
  run it on the default account to connect the second account.
- For a genuinely missing/expired grant, use the Desktop local-server OAuth flow
  with the required scopes, account hint and a separate token directory. Verify the
  returned account before saving its credentials. The existing ignored
  `data/authorize_connect_account.py` illustrates this account-specific flow.
- Adding an account to Google Cloud's test-user list is not completed OAuth consent.
  Wait for Google's successful callback and account verification. The user may need
  to choose the account and allow access in the browser. Never ask for their password.
- OAuth URLs have an ephemeral localhost callback, state and PKCE challenge. Give the
  user the current live URL when needed; do not reuse an expired historical link or
  terminate its listener while the user is completing consent.
- If opening the browser is rejected by policy, explain the stated rejection and
  provide the live authorization link for the user to open. Do not evade the block
  through another shell or launcher. This happened during the second-account setup.

Authorization and token values must stay out of Git, logs, user-facing output and
handoff prose. A successful OAuth connection does not itself send a message.

## Reply in the original thread

The user specifically requested true replies from the personal account. A new message
with a `Re:` subject is **not** a reply in the original thread.

1. Use the mailbox containing the original message; verify the authenticated account.
2. Search narrowly by the exact recruiter address and company/topic. Retrieve the
   matching message, verify its sender/content, and choose the actual requested
   original. Do not guess a thread from another account. If selection is ambiguous,
   resolve it before sending.
3. Capture original Gmail message ID, Gmail `threadId`, RFC `Message-ID`, subject and
   existing `References`. Preserve identifiers exactly. Respect a meaningful original
   subject, including punctuation or emoji.
4. Prepare the same intended response with the selected sender in its signature.
   Set `In-Reply-To` to the original RFC `Message-ID`, append it to `References`, and
   use a matching reply subject. Set the API send body's **`threadId`** as well.
5. Reply only to the requested recruiter. Do not reply-all to a bulk mailing,
   undisclosed recipients, original BCCs, or unrelated recipients.
6. Check the thread and operation receipt for an existing reply from this account.
   A prior send from another account permits a second send only when the user
   explicitly requested it, as happened for the first personal-account reply.
7. After Gmail accepts the send, retrieve that sent message with read scope. Verify
   actual From/To, original thread ID, `In-Reply-To`, `References`, body and PDF bytes.
   Report verification honestly; API acceptance alone does not prove inbox delivery.

Ignored `data/reply_rohit_connect.py` and `data/reply_hcltech_murugan.py` demonstrate
the verified workflow. They contain frozen task-specific recipients, original IDs,
paths and assumptions. Inspect them as examples; never rerun a completed script or
copy it without reviewing every recipient, source, selector and receipt guard.

## Prepare, review, send and record

1. Ground the message in verified resume facts and the latest user corrections.
   The user prefers a direct application opening, not "I saw your post" or "I have
   seen this opportunity". Do not claim to have read an unavailable JD attachment.
2. Ask only for material missing facts such as offer status, a required compensation
   breakup or willingness to accept a hike. Carry forward confirmed preferences;
   do not invent a last working day or fabricate compliance with experience/certification
   requirements. For unsuitable senior roles, consider a clearly worded suitable-level
   enquiry rather than falsely claiming to meet the minimum.
3. Verify recipient provenance and company/client identity. Check all prior email
   recipients, company names/domains, portal confirmations and suppression entries.
   Dedupe To and CC, plus aliases/rebrands of already-contacted companies.
4. Verify the original PDF path and SHA-256 against the private handoff and selected
   `Resume` record. Check the actual decoded MIME attachment bytes and filename.
   "Resume attached" in the prose is not attachment verification.
5. Show the user the recipient/company list and exact message content before sending,
   using a full review artifact for batches. Include CCs, sender and attachment.
   When the current user has explicitly authorized sending within this scope, proceed
   without another redundant permission question. Changed scope needs its own basis.
6. Freeze the review and complete MIME previews. Bind approval to recipient, sender,
   subject, body, profile, verified contact and PDF hash. Profile/contact timestamps
   should be committed before computing approval snapshots; SQLite timestamp
   normalization previously caused mismatches when snapshots used uncommitted data.
7. Verify the selected Gmail account immediately before delivery. Keep an exclusive
   operation receipt, unique operation key and durable outbox state. Commit `sending`
   and attempt count **before** the external API call. Keep batch budgets explicit.
8. Send exactly once per operation with Google client **`num_retries=0`**. A timeout
   or ambiguous response may already have delivered the message. Mark it uncertain,
   stop, and reconcile before any further attempt.
9. On a returned Gmail message ID, record `SENT`/`sent`, message/thread IDs, timestamp,
   sender and PDF evidence in both DB/audit and the receipt. Persist acceptance before
   optional post-send checks so a verification failure cannot trigger a duplicate send.
10. Update review/CSV/shortlist statuses only after confirmed delivery. Preserve the
    original approved bytes in an approved backup before modifying a pinned manifest.
    For consolidated roles, label them company outreach sent rather than falsely
    claiming every separate portal application was completed.

`job_outreach.gmail.build_message()` supports a simple single-recipient message, not a complete
CC/thread-reply workflow. Build and validate full MIME explicitly when those are needed.
`EmailMessage(policy=policy.SMTP.clone(max_line_length=998))` was used successfully for
long subjects. Compare parsed/decoded headers and normalized body text, not raw folded
header strings; normalize CRLF versus LF in comparisons. Do not modify the resume.

The default app is still **dry-run, sending disabled, recruiter delivery disabled**.
The default daily limit is five. Historical one-time batches used explicit user-approved
budgets and dedicated audited scripts while leaving persistent defaults unchanged.
Those completed exceptions do not authorize a general bypass of limits. For new work,
use the app's normal approval/configuration workflow or a narrowly scoped, explicitly
authorized operation with equivalent safeguards. Never silently enable a scheduler or
change persistent sending switches to make a one-time send work.

## Recovery and concurrency pitfalls

- Inspect `Outreach` and `Outbox` statuses before using a send worker. In particular,
  the generic worker treats leftover `sending` rows as uncertain. Never run it alongside
  a dedicated sender or use it to "check status" during another send.
- `exclusive()` provides cross-process advisory locks on PostgreSQL. Its SQLite lock
  is process-local only. Run one sender process at a time in the local SQLite workspace;
  receipt guards do not turn SQLite into safe cross-process scheduling.
- A runtime `sending_shutdown` entry or suppression must be respected. Do not clear
  shutdowns or delete suppression records just to complete a requested batch.
- Existing receipt files and `SENT`, `SENDING`, or `SEND_UNCERTAIN` states are duplicate
  guards. Never delete/reset them to force a retry. Use read-authorized reconciliation
  by RFC message ID/operation key and inspect the intended sender's Sent mailbox.
- A refresh failure can be reauthorized. A delivery timeout cannot be blindly retried.
- Review builders may be non-idempotent or reset statuses. Do not rerun historical
  preparation/reconciliation scripts merely to regenerate an HTML report.
- Changing a sender/profile invalidates approval snapshots. Do not reuse a snapshot
  computed for one Gmail account when sending from the other.
- Old JSON count summaries and research audits may predate later sends. SQL history
  and final send receipts take precedence. Global counts cover both accounts, not one
  mailbox. Keep portal submissions separate.
- Site `403`, JS-only HTML, cached search snippets and expired job redirects need
  different handling. Use primary evidence/ATS APIs when available; mark unresolved
  availability accurately. Never invent emails or replace a blocked form with a claim
  of successful submission. CAPTCHA/sign-in or mandatory demo requirements can leave
  a portal application incomplete even when an outreach email was sent.

## Read-only status check

Use configured SQLAlchemy models so the active database is selected correctly:

```powershell
@'
from sqlalchemy import select, func
from job_outreach.config import settings
from job_outreach.db import Database, Outreach, Outbox

db = Database(settings().database_url)
with db.session() as session:
    print('Outreach:', session.execute(
        select(Outreach.status, func.count()).group_by(Outreach.status)
    ).all())
    print('Outbox:', session.execute(
        select(Outbox.state, func.count()).group_by(Outbox.state)
    ).all())
'@ | uv run python -
```

Inspect receipt fields selectively. Do not dump `.env`, OAuth client JSON, decrypted
credentials or full mailbox contents into tool output. Scope inbox searches to the
requested recruiter/task and show only the metadata needed to confirm selection.

## Coding, verification and Git

- Read relevant source before adapting helper scripts. Use `rg` for search, batch
  independent read-only checks, and keep mutations/dependent operations sequential.
- In PowerShell, use literal paths for file operations and verify targets before
  recursive deletion or moves. Prefer Python here-strings for multiline data; avoid
  unsafe shell interpolation, backticks and command substitution.
- Keep API/dashboard services on loopback. Do not start background senders or scheduled
  work unless requested. For Windows background helpers, use hidden windows except
  where the user needs an interactive authorization window.
- Never commit `.env`, `sa.json`, OAuth client data, tokens, encryption keys, resumes,
  databases, recruiter lists, receipts, MIME previews, or private handoff/profile data.
  Preserve `.gitignore`; `data/` is intentionally excluded. A push cannot back up these
  local assets. Restoring tokens also requires the original private encryption key.
- For code changes, run appropriate checks from the README. Tests must not send real
  email or perform real OAuth. For documentation-only changes, check the diff, links,
  staged files and whitespace; a full application test run is not necessary.
- Stage only intended files. Inspect `git diff --cached --check` and staged paths
  before committing. Push only when the user requests it or already authorized it;
  use the existing remote/branch conventions and do not force-push.
- Update this guide and the ignored private handoff when durable workflow facts change.
  Refresh snapshot counts from the DB; do not turn a historical approval into a new
  authorization. In the final response, state what happened, what was verified, and
  any concrete incomplete requirement; do not claim delivery or application completion
  beyond the available evidence.
