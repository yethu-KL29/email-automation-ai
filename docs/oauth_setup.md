# Gmail OAuth and the first test

1. Create or select a Google Cloud project. Enable the Gmail API.
2. Configure the OAuth consent screen. For a personal external app in Testing, add your own
   Gmail account as a test user. Organizational policies may require administrator approval.
3. Create an OAuth client of type **Desktop app**. Download its JSON to
   `data/credentials.json`. This directory is ignored by Git and Docker builds.
4. Set `SENDER_EMAIL`, `SENDER_NAME`, and an email you control as `TEST_RECIPIENT` in `.env`.
   Setup has generated `CREDENTIAL_KEY`; keep it private and backed up separately from tokens.
5. Run locally (not inside the container):

   ```powershell
   uv run python -m job_outreach.cli oauth
   ```

   Complete the Google browser flow with your sending account. The callback uses a local
   ephemeral port. Tokens are encrypted with Fernet in `data/gmail-token.enc` and refreshed
   when needed. Sending checks that the authorized account matches the configured sender.

The default scope is `gmail.compose`, which supports managing drafts and sending. The app
does not request read access during this flow. Inbox reading for reconciliation is a separate,
explicit opt-in:

```powershell
uv run python -m job_outreach.cli oauth --with-read
```

This adds `gmail.readonly`. Reauthorization replaces the locally encrypted token. Revocation
or consent expiry requires running the OAuth command again. Do not log token errors with
credential payloads or share token files.

## First test (manual, never an automated test)

Prepare a real reviewed draft addressed to `TEST_RECIPIENT`, with a published/contact source
you can verify, or use a separately prepared test record. Approve its recipient, body and PDF.
Set `DRY_RUN=false`, `SENDING_ENABLED=true`, leave `ALLOW_RECRUITER_DELIVERY=false`, then restart
the API so it reloads configuration. Queue the approved send and run:

```powershell
uv run python -m job_outreach.cli send-once
```

Confirm the test recipient received the exact approved content and resume version and the
application has a Gmail message ID. Real recruiter delivery requires deliberately setting
`ALLOW_RECRUITER_DELIVERY=true`, restarting the API and reviewing each application.

Gmail draft creation is a distinct action and never marks an application sent. Delivery uses
the locally approved snapshot; it does not send later edits made directly inside Gmail.
Do not manually send a Gmail preview draft and then queue the same application in this app.

Official references:
- [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Sending email](https://developers.google.com/workspace/gmail/api/guides/sending)
