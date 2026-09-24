# Phase 1.8D3: resilient long uploads and session recovery

## Scope and incident evidence

This phase follows `AUTH_REFRESH_401_OBSERVABILITY.md` and the September 24
long-upload audit. The reproduced 950,238,652-byte upload reached S3 with 112 of
114 parts (933,461,436 bytes); parts 3 and 19 were absent. No completion request
occurred. A later cancellation met expired access authentication and
`auth_refresh_rejected reason=cookie_missing`. Reauthentication lost the browser
context while the durable owner session continued occupying its admission slot.
There was no evidence of an API crash or processing-workspace exhaustion.

The exact event that triggered that historical cancellation was not captured.
The implementation addresses the demonstrated missing safeguards without
claiming that every aspect of the old cancellation is proven.

## Architecture

Keep direct browser-to-S3 multipart transfer, existing part sizing, concurrency,
attempt bound, 1 GiB limit, owner admission, and session lifetime. Add:

* A per-part **inactivity** watchdog, default 60 seconds, configurable through
  `PICKLEBALL_AI_DIRECT_UPLOAD_PART_INACTIVITY_SECONDS` (10–300 seconds). Only
  increasing upload progress resets it. No total-duration cutoff is imposed on
  a part that continues progressing. A stalled XHR is aborted and consumes one
  existing bounded attempt. Retry backoff remains bounded.
* Expiry-aware part URLs: request a new URL before a missing/expired/near-expiry
  URL is used, and after a storage authorization rejection. URL renewal does not
  extend the upload session lifetime or change the 15-minute URL lifetime.
* Recoverable client/network/auth errors stop sibling transfers but do not
  automatically DELETE the durable session. Explicit user cancellation uses
  the existing authenticated, owner-scoped abort operation.
* Owner-only discovery and S3 reconciliation. Confirmed parts seed progress;
  only missing parts transfer. In-flight bytes reset on retry, avoiding double
  counting. A lost PUT response can be recovered through S3 ListParts.

The API adds `GET /api/v1/uploads/recoverable`,
`GET /api/v1/uploads/{id}/recovery`, and
`POST /api/v1/uploads/{id}/resume`. The latter checks file identity and size.
Each request requires a verified authenticated owner. Foreign session IDs return
404 before storage access. Reconciliation holds the existing session row lock;
completion/abort keep their existing state fences and idempotency. S3 part
pagination is bounded and part numbers/sizes are checked against the session.
Discovery itself does not expire, delete, abort, or rewrite stored sessions.

No migration: the existing JSON client metadata stores a reserved
`court4_file_identity` value. Caller metadata cannot override it. Existing
requests without an identity retain their old idempotency fingerprint.

## Safe file reselection

Browsers cannot silently reopen a local file after reload. New uploads hash every
byte before initiation, using fixed 8 MiB chunks and bounded memory. The identity
is `sha256-chunks-v1:` followed by SHA256 of:

1. UTF-8 `court4-file-v1\n`;
2. the concatenated binary SHA256 digests of each 8 MiB chunk (last may be smaller);
3. UTF-8 newline followed by the decimal file size.

Resume checks the same identity and declared size before issuing more part
URLs. Renaming the identical file is safe; matching name/size alone is not
accepted. The API verifies the completed object against this identity before
analysis, in addition to its existing full SHA256, metadata, and media checks.
This currently adds a bounded-memory object read to server verification and a
local browser read before uploading/resuming; neither raises upload limits.

Legacy sessions without this identity remain discoverable. If all parts exist,
the owner can finalize without the local file. If parts are missing, resumption
fails closed; the UI explains that explicit cancellation is available. This
includes the historical 112/114-part session if it still exists. The phase does
not delete it or pretend to have verified a legacy file identity.

## Authentication architecture and manual configuration

The two staging `*.up.railway.app` hosts are separate sites. The observed Safari
cookie absence is addressed using a **narrow same-origin auth proxy** in the
existing Next.js Node server. An owned registrable domain was not supplied.
This avoids an extra service or a general upload proxy.

Browser auth requests now use `/api/v1/auth/...` on the web origin. An allowlisted
route handler forwards only supported auth operations to one server-configured
API origin. Set-Cookie values, including rotation/deletion and all attributes,
are returned unchanged. The API's host-only cookie therefore belongs to the
web response host and is first-party during refresh. HttpOnly, Secure, SameSite,
Path, token lifetimes, rotation, origin validation and API rate limits are not
weakened. Access tokens remain in browser memory. Video bytes still go directly
to S3, and other API calls retain their current API origin and credentialed CORS.

The proxy bounds JSON request size, rejects redirects and caller-selected
targets, disables caching, preserves the browser's actual Origin, and requires
an exact configured web Origin for mutations. It does not trust caller-supplied
forwarded-IP headers or log credentials. Production configuration fails closed
without HTTPS origins. It does not expose development email routes.

**Manual steps for the owner, after reviewing and authorizing deployment:**

1. On the **web service**, set these server-side variables:
   `COURT4_AUTH_PROXY_UPSTREAM=https://court4-api-staging.up.railway.app` and
   `COURT4_WEB_ORIGIN=https://court4-web-staging.up.railway.app`.
   These are bare origins, without `/dashboard` or `/api/v1`. Keep
   `NEXT_PUBLIC_COURT4_API_URL` pointing at the API for all non-auth operations.
2. Keep the API allowed frontend origin and `FRONTEND_BASE_URL` equal to the
   exact web origin. Preserve Secure=true, the existing cookie SameSite setting,
   host-only scope, `/api/v1/auth` Path, existing lifetimes and rate limits.
   No cookie Domain setting is required or introduced.
3. Confirm the existing storage principal permits `s3:ListMultipartUploadParts`
   on Court4's existing upload object prefix. Only if missing, authorize that
   narrowly scoped permission manually; do not broaden bucket visibility or
   disable ownership/storage safeguards.
4. After the separately authorized release, sign in once through the web UI.
   The old API-host cookie cannot be migrated by JavaScript. Verify, without
   exporting tokens, that the web-host cookie is accepted, refresh rotates it,
   logout clears it, and Safari can reload and recover an interrupted upload.
5. Exercise a representative long video, including a temporary network stall
   and reauthentication. Inspect sanitized observability events and final
   upload status. Do not change TTLs to manufacture expiry or delete live data.

**Rate-limit tradeoff:** backend limits remain enforced at their existing
values, but proxied requests can share a proxy egress IP and therefore a limit
bucket. Session IP display may also show the proxy. Do not solve this by
trusting arbitrary forwarded headers or raising limits. For broader traffic,
moving to same-site app/API hosts under an owned registrable domain with a
reviewed return to direct auth requests would avoid this pooling;
alternatively, a separately reviewed authenticated trusted-proxy identity design
is needed. This repository preparation makes no infrastructure changes.

## User experience and safety

The upload page checks for an existing owner session before offering a new
upload. It shows confirmed progress, original filename and clear actions:
Recoverable upload found, Resume upload, Cancel upload, Uploading,
Upload interrupted, and Finalizing. At authentication loss, `/upload-match`
shows Sign in again to continue instead of redirecting to the homepage.
Reauthentication remounts owner-scoped discovery. Changing accounts cannot
reuse the prior owner's UI state. No S3 identifiers, tokens, URLs, or provider
error bodies are shown in the UI.

Cancellation only clears the recovery UI after server confirmation. An uncertain
cancel retains the session context. Once completion has claimed the session,
cancel cannot interrupt verification/analysis. Completed result navigation
preserves existing duplicate-video behavior and history identifiers.

Existing pickleball, Padel isolation, history, Match IQ, source-media lifecycle,
local storage fallback, PostgreSQL persistence, authentication and admission
logic remain in place. `BALL_TRACKING_ENABLED=false` is unchanged; Padel Match
IQ remains unavailable.

## Limitations

* Browser/OS suspension can defer JavaScript timers; the watchdog acts when the
  browser can execute again. Reload recovery requires the original local file.
* Recovery is bounded by the existing six-hour session lifetime. Expired parts
  are not silently revived or given an extended authorization lifetime.
* The pre-existing server completion/verification worker architecture is retained.
  This phase is not a durable job-queue redesign; an API process interruption
  during an already claimed completion still needs operational reconciliation.
* File hashing adds local I/O and one server object read. Full-match analysis
  throughput is a separate capacity concern; this phase does not establish its
  maximum supported processing duration or change workspace/storage capacity.
* Browser acceptance on the deployed Safari origin needs a post-release check;
  local deterministic tests cannot prove external browser policy or live IAM.

## Validation

Validation uses local deterministic S3 fakes and the guarded local test database.
No live Railway/S3 operations, deployments, environment changes or user-data
deletions are part of implementation/testing.

| Check | Result |
| --- | --- |
| Full backend: `python -m pytest --tb=short -ra` | 431 passed, 10 optional PostgreSQL spike tests skipped, 536.42 seconds |
| Final focused backend: `pytest tests/test_direct_uploads.py tests/test_object_storage.py --tb=short -ra` | 58 passed, including final no-cache, invalid-receipt and expired-progress safeguards added during review |
| Full frontend: `npm test` | 242 passed across 44 files |
| Focused multipart/recovery/proxy/dropzone frontend | 42 passed |
| Ruff: `python -m ruff check .` | Passed |
| Formatting: `python -m ruff format --check .` | Passed |
| Backend types: `python -m mypy app scripts tests` | Exactly the five documented baseline errors in `tests/test_source_media.py:49,58,138,287,295`; no new errors |
| Frontend types: `npm run typecheck` | Passed, including the new browser recovery test |
| ESLint: `npm run lint` | Passed |
| Production frontend: `npm run build` | Passed; Node auth route included |
| Migration checks | No migration introduced; existing migration tests included in full backend suite |
| Whitespace: `git diff --check` | Passed |

The initial focused frontend failures were old auth-origin/automatic-abort
expectations and incomplete recovery fixtures. The first full frontend run
also identified two pre-session progress expectations; those remain compatible,
while durable-session interruptions preserve progress. All were resolved.
The test database initially took longer than its startup health window to
finish crash recovery; tests ran after normal recovery completed, without
resetting its volume. The backend retains one dependency deprecation warning
about Starlette/HTTPX. The optional spike tests require a separate guarded
`COURT4_SPIKE_DATABASE_URL`, not a staging database.

The full browser run encountered the already documented fixture rate-limit
collision (see `MEDIA_ONLY_DELETION.md`): repeated login/signup from one local
IP produced 429s and cascading fixture failures. Rate limits were not changed.
Affected cases were rerun in paced batches: all 10 workflow cases, all 4 affected
verification cases, and all 5 affected history/profile/media/recovery cases
passed. Thus all **35 enabled browser cases passed** across the full run and
paced retries. One optional real-video CV case was skipped because no fixture
was supplied. The new browser recovery case also passed in the initial focused
3-case authentication/recovery run. It uses real local authentication and
controlled transfer responses; it verifies same-origin auth, a preserved 50%
snapshot across auth loss/reload, file reselection, one missing-part PUT and no
automatic DELETE. It does not claim a live Safari/S3 deployment test.

Final Git state: `main` at unchanged `ca6375d`, matching the locally recorded
`origin/main`; **19 modified tracked files and 9 untracked files**, all listed
below. Nothing staged, committed or pushed. Build-generated `next-env.d.ts`
matches its starting contents. Local test services were stopped after
validation; their volumes and data were retained.

## Changed files

| Area | Files |
| --- | --- |
| API contract and watchdog configuration | `app/api/v1/uploads.py`, `app/config/settings.py`, `app/schemas/uploads.py` |
| Reconciliation and file verification | `app/services/uploads.py`, `app/persistence/object_storage.py` |
| Backend coverage | `tests/test_direct_uploads.py`, `tests/test_object_storage.py` |
| Transfer and browser identity | `web/lib/api/analyses.ts`, `web/lib/api/types.ts`, `web/lib/file-identity.ts` |
| Recovery and sign-in UI | `web/app/upload-match/page.tsx`, `web/components/upload-recovery-workspace.tsx`, `web/components/upload-dropzone.tsx`, `web/components/auth-gate.tsx`, `web/components/auth-form.tsx` |
| Same-origin authentication | `web/lib/api/client.ts`, `web/lib/auth-proxy.ts`, `web/app/api/v1/auth/[...path]/route.ts`, `web/.env.example` |
| Frontend coverage | `web/lib/api/analyses.test.ts`, `web/lib/api/auth.test.ts`, `web/lib/auth-proxy.test.ts`, `web/lib/file-identity.test.ts`, `web/components/auth-gate.test.tsx`, `web/components/upload-recovery-workspace.test.tsx`, `web/e2e/upload-recovery.spec.ts`, `web/test/setup.ts` |
| Documentation | `docs/platform/PHASE_1_8D3_RESILIENT_UPLOADS.md` |

## Final security review

* Verified ownership precedes provider access on recovery, resume, part renewal,
  completion and cancellation. No caller supplies a storage key or provider
  upload identifier to recovery. Foreign sessions are concealed as 404 and
  discovery returns only the current owner. Recovery responses are `no-store`.
* Reconciliation accepts only in-range, unique part numbers, exact expected
  sizes and valid bounded receipts. Same-file validation covers all bytes;
  final server verification prevents accepting a mixed-content object.
* Existing completion/abort locks and terminal-state guards remain intact;
  concurrent completion reaches the provider once. Recovery does not relax
  admission, authorization, object metadata checks or deletion locks.
* Auth proxy targets and routes are fixed/allowlisted. It rejects cross-origin
  mutations and redirects, preserves cookie security and rotation, bounds
  request bodies, retains API rate limits and uses no credential cache.
* No new token/cookie/header/presigned-URL logging or browser persistence was
  introduced. S3 failures use sanitized messages. Transfer errors do not issue
  destructive cleanup; cancellation is explicit and owner-scoped.
* No production/staging storage, environment, infrastructure, feature flags,
  auth TTLs, upload limits, existing user data or unrelated features changed.
  Test values are synthetic and local. No migration, staging, commit or push.
