# Public job source integrations

Each source implements `JobSource.fetch()` and produces Pydantic-validated `JobData`.
Provider hosts are fixed in code; board names accept only letters, digits, underscores
and hyphens. No arbitrary website fetches or redirects are allowed.

| Source | Public GET API | Date treatment |
|---|---|---|
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true` | `publishedAt` is last publication, not necessarily original creation |
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | `updated_at` is never interpreted as publication |
| Lever | `https://api.lever.co/v0/postings/{board}?mode=json&skip=0&limit=100` | Unknown when no documented publication field exists |

Responses are bounded to 32 MB, requests to 20 seconds, retries to 3 for transient safe GETs.
Connections are bounded to 3. Boards of a given provider are serialized with a pause.
Lever pagination caps at 20 pages and reports a failure rather than silently completing
a truncated run. Ashby unlisted postings are ignored. Errors are reported per board;
successful boards commit independently, so rerunning a partial failure is safe.

Deduplication uses stable source identifiers and hashes of canonical application URLs,
preserving requisition query parameters. Similar titles alone never merge distinct jobs.
Unknown/future dates cannot satisfy strict recent filtering. A timestamp without timezone
is treated as unknown. Freshness is computed in UTC at display time.

Configured domains must be verified against the employer website. Only recruiting-style
inboxes explicitly published in the job text and matching that domain are automatically
classified as official inboxes. Other emails require user verification with evidence.
An address missing from the published text is never manufactured.

Sources provide discovery, not a guarantee that a role is still accepting applications.
Confirm the employer's application page before outreach. Current runs update seen jobs;
absence from a later board response is not yet used to infer closure.

Official docs verified while implementing:
- [Ashby public API](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- [Lever Postings API](https://github.com/lever/postings-api)
