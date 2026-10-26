# Operations

- Keep the API and dashboard on loopback. Streamlit is a trusted local client; the dashboard
  has no separate login. Do not publish its port or run with untrusted local users.
- Keep `.env`, `data/credentials.json`, tokens and resumes private. Enable disk encryption.
  Back up PostgreSQL and the resume directory together; store CREDENTIAL_KEY separately.
- No real credentials are included in this repository. Local setup generates API/encryption keys.
- Start exactly one scheduler. PostgreSQL advisory locks also prevent a second active scheduler.
- Discovery persists successful boards independently. Rerun after a failure; unique constraints
  prevent duplicate jobs. No closed-state inference is currently made from absent jobs.
- API approval and queueing are transactional. Delivery is an explicit one-operation CLI command.
  Default daily limit is 5 UTC-day sends; contact/company cooldown defaults are 30/7 days.
- Global stop prevents future calls once checked. An already in-flight Gmail call cannot be
  recalled. To deliberately clear global stop, a local administrator can set the
  `runtime_settings` row `sending_shutdown` value to `{"disabled":false}` after reviewing pending
  outbox entries. There is intentionally no one-click dashboard resume.
- A blocked outbox entry is not retried automatically. Correct the cause and inspect the record;
  administrative recovery must not alter any sending/sent/uncertain operation into pending.
- SEND_UNCERTAIN must remain blocked until a unique sent message is found. Authorize read scope
  separately, then use Reconcile in the UI. Never reset or delete an uncertain outbox entry to
  force a retry. If reconciliation finds nothing, verify sent mail manually and keep it blocked.
- Gmail OAuth refresh failure requires reauthorization. Refresh is safe to retry; sending isn't.
- Updating an email clears approval. Profile/contact/sender changes invalidate queued snapshots.
- Gmail preview drafts may differ after local edits; the approved local snapshot drives delivery.
  Avoid manually sending preview drafts outside the app if you intend to use app delivery.
- Do not run setup again against an existing `.env`; edit local settings then restart processes.
- Use `docker compose down` to stop services. Do not add `-v` unless you intend to delete data.
