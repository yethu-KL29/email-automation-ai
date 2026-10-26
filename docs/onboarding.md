# Details needed to personalize and connect your app

## Resume and candidate facts

- Current PDF resume path (PDF is required for email attachments); DOCX may also be ingested.
- Preferred version for each role, if you use multiple resumes.
- Full name, public contact email, phone/portfolio/LinkedIn links if desired in your signature.
- Target title, total experience if reliably known, skills, work authorization and notice period.
- A short list of verified achievements with numbers only where supported by your resume.
- Any qualifications or past employment details that must be corrected after extraction.

The dashboard lets you enter and verify these; extraction does not automatically verify facts.

## Job preferences

- Target role titles and keywords to include/exclude.
- Countries/cities, relocation preference, remote/hybrid/on-site and remote region restrictions.
- Desired seniority/experience, employment types, compensation currency/range.
- Companies to prioritize/exclude and a starter list of company career pages or ATS boards.
- Discovery timezone/time, minimum score, maximum drafts and daily send limit.

## Email and Gmail

- Sending Gmail address and display name.
- Signature and preferred tone. Optional portfolio links belong in your reviewed signature.
- An email address you own/control for the first explicitly authorized test.
- Google Cloud project with Gmail API enabled, OAuth consent setup, and a Desktop app OAuth
  client JSON stored locally at `data/credentials.json`.
- Local browser authorization. Do not share your password or OAuth token.
- Decision on optional mailbox read access for sent-message reconciliation. Default OAuth
  requests draft/send scope only.

Set `SENDER_EMAIL`, `SENDER_NAME`, and `TEST_RECIPIENT` in local `.env`.
Keep `DRY_RUN=true` and `SENDING_ENABLED=false` until ready for a reviewed test.

## Optional AI provider

- Provider name/base URL and chosen chat model; optionally an embedding model.
- An API key saved locally to `.env`, never pasted into chat.
- Acceptable per-run call budget (default 10 assessments; each may also need embeddings).
- Confirm you are comfortable sending reviewed resume facts and job text to that provider.

Basic discovery, matching, profile review and email templates work without an LLM key.
