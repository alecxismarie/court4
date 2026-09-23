# Phase 1.8D2 upload-stuck audit

## Read-only evidence, before changes

Audited local/deployed revision `d8a43c786b814e9c9c26cd4299e7b178d7121982`.
Railway staging PostgreSQL was queried inside an explicitly READ ONLY transaction;
S3 was queried with ListParts for the exact database key/upload ID. No API status
GET was used: that endpoint can mutate expiry and schedule verification.

- Session: `e6a5755e-f054-4251-afbe-9cc6d00150d8`.
- Status: `initiated`; declared size: 713,687,532 bytes.
- Created/last updated: 2026-08-31 16:13:14.721917 UTC.
- Expires: 2026-08-31 22:13:14.721917 UTC; database confirms past expiry.
- No verification start or failure reason; this was the only returned session.
- S3 multipart still open: 52 parts, 436,207,616 bytes; listing not truncated.
- Actual settings: S3, active limit 1, TTL 21,600 seconds. Migration: `0010_direct_multipart`.

## Root cause and admission algorithm

`app/services/uploads.py:DirectUploadService.initiate` emits the exact message
"Another upload is already active. Try again after it completes." as
`upload_capacity_busy`, HTTP 429. After validating metadata it acquires an
owner/idempotency-key PostgreSQL transaction advisory lock and returns an existing
matching session if present. For a new key it takes a GLOBAL capacity advisory
lock and counts ALL owners' initiated/uploading/completing/verifying/analyzing
rows. It does not filter expiry or reconcile before counting.

The observed expired row therefore deterministically consumes the sole slot,
including for other owners. The six-hour TTL alone cannot release it. Expiry is
only applied when accessing that same session or replaying its original key.
Reset/new file/refresh loses that key. No scheduled reconciliation was found in
the repository. The manual reconciliation script covers expired multipart states,
but merely having the script does not run cleanup. Restart preserves this blocker
in PostgreSQL. This is not evidence of local-volume exhaustion.

The interruption that left the original upload incomplete is not established by
these observations (browser disappearance/network/provider failure are possible).
The cause of the persistent subsequent admission failure IS established.

## Frontend audit

- Pending Cancel aborts the controller; once a session ID is known, caught part
  failures attempt DELETE. Initiation response loss happens outside this catch.
- Idle Reset only clears local form/key/progress/error; it cannot abort an old
  server session. Selecting another file is disabled while pending; afterwards
  it generates a new key without cleaning up a previous session.
- Network/part failures after initiation attempt abort, but abort ignores HTTP
  failure responses. Other concurrent part workers are not canceled on failure.
- No unload/unmount cleanup or durable browser session/key recovery was found.
  Browser cleanup cannot be the authoritative fallback.
- onMutate initializes progress to zero before admission; onError leaves it
  visible. Thus the screenshot shows an unsuccessful new attempt, not the old
  upload's actual byte count (S3 has 52 parts).
- Same-file retry within the mounted form preserves the key and can reuse an
  active session (re-uploading parts). An aborted/failed/expired response is
  polled and errors, without rotating the key. Reset/file change/refresh uses a
  new key and hits the occupied capacity.
- The busy message has no actionable recovery time or cancellation path.

## Safest scoped corrective design

Serialize admission per owner in PostgreSQL; row-lock existing sessions and
expired multipart candidates. Abort the exact provider multipart while holding
the row lock before releasing its admission slot. Fail closed on provider errors;
retain a retryable record. Use the same locked abort path for reconciliation and
explicit cancellation so completion cannot race provider abort. Preserve TTL,
size limit, checksum, privacy, sport separation and live-upload busy behavior.

Cancel sibling part transfers on failure, bound cleanup requests, distinguish
confirmed terminal cleanup from ambiguous failures for retry keys, and hide stale
progress after errors. New initiation provides authoritative recovery after TTL
without relying on browser cleanup. No schema change is required.

`completing` crash recovery and unattended `verifying`/`analyzing` recovery are
separate lifecycle gaps: they must not be expired as if they were multipart
transfers. GET can restart verification after its lease, but not completing.
This audit does not establish such a state in staging.

## Implemented behavior (working tree; staging unchanged)

- Admission uses an owner-scoped PostgreSQL transaction lock, counts only that
  owner's live sessions, and reconciles their expired multipart sessions first.
  A live session still returns 429. Two workers/new keys cannot both win.
- Expiration aborts the exact S3 multipart, records `expired` and an `aborted_at`
  cleanup receipt, then flushes before counting capacity (autoflush is disabled).
  Cleaned expired records are not repeatedly sent to the provider. Provider errors
  return a sanitized 503 and preserve retryable state; they do not admit a second
  upload. Provider unavailability remains an operational dependency.
- Explicit cancellation first commits an expired cancellation claim, then aborts
  the provider and records `aborted`. This fences completion even if the database
  connection or API dies during the provider call. New initiation can finish that
  interrupted cleanup. No schema changes or TTL reductions were made.
- Operator reconciliation rechecks status/expiry under a row lock BEFORE provider
  abort. A stale snapshot cannot abort a session that entered completion.
- Frontend part failure cancels sibling transfers and attempts a bounded DELETE;
  a non-2xx DELETE is not treated as confirmed cleanup. Confirmed terminal results
  get a fresh retry key; ambiguous failures retain their original key.
- Reset and file replacement retry abort for a known previous session and retain
  the form when cleanup cannot be confirmed. A session ID lost with the initiation
  response or browser refresh still relies on same-key retry or server expiration.
- Errors clear the stale progress display. Unmount cancellation is best effort;
  correctness does not depend on beforeunload. Busy errors now explain cancellation
  and the existing six-hour bound for abandoned transfers. Finalization is distinct.

Recovery is lazy and authoritative on the next initiation after expiry; this patch
does not introduce a scheduler. If no request arrives, the operator reconciliation
script is still needed to clean unused provider parts proactively.

## Files

- `app/services/uploads.py`: admission, expiry, owner scope, cancellation fencing.
- `scripts/reconcile_multipart_uploads.py`: locked provider/database reconciliation.
- `web/lib/api/analyses.ts`: transfer cancellation, cleanup confirmation, terminal errors.
- `web/components/upload-dropzone.tsx`: Reset/replacement recovery, retry keys, progress.
- `tests/test_direct_uploads.py`: PostgreSQL lifecycle/concurrency/reconciliation regressions.
- `web/lib/api/analyses.test.ts`, `web/components/upload-dropzone.test.tsx`: frontend regressions.
- This report. `upload-progress.tsx` was inspected; its caller now removes stale progress.

## Deployment and limitations

No Railway settings, staging database records, S3 objects, or bucket policies were
modified. Migration remains `0010_direct_multipart`; no migration is required.
The observed staging session remains stuck until the fix is deployed or an operator
performs scoped reconciliation. After deployment, its owner's next new initiation
can abort the expired multipart and obtain a new session without manual row deletion.

Deploy API and web after review. Avoid overlapping old/new API workers during the
cutover: they use different admission locks. All new workers use the same durable
owner lock. The old six-hour TTL, one-upload limit, 1 GiB ceiling, checksum checks,
private storage, authentication and sport isolation remain in force.

This is a fix for the confirmed abandoned multipart blocker, not a claim that
every finalization crash is recoverable. A crash leaving `completing` still requires
provider-aware recovery; unattended verifying/analyzing recovery still depends on
polling/lease retry. Those states were absent in the audited staging database and
are not force-expired by this change.

## Validation

- Baseline reproduction: mounted `d8a43c7:app/services/uploads.py` into the local
  test container and ran `pytest tests/test_direct_uploads.py -k
  abandoned_upload_recovers --tb=short`. Expected failure reproduced exactly:
  `upload_capacity_busy`, "Another upload is already active. Try again after it
  completes." Result: 1 failed, 27 deselected. No staging upload was initiated.
- Corrected full backend invocation: `docker compose --profile test run --rm`
  with read-only working-tree mounts for tests, scripts, web/scripts and Dockerfile;
  `api-test env -u FRONTEND_BASE_URL -u PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS
  pytest --tb=short`: **380 passed, 10 skipped**, 415.11 seconds. The skips are
  optional PostgreSQL spike tests requiring `COURT4_SPIKE_DATABASE_URL`. Production
  PostgreSQL persistence/migration tests ran against the isolated test database.
- Initial full backend attempt: 348 passed, 31 failed, 10 skipped. Its Compose
  browser-E2E origin (`localhost:3002`) conflicted with unit tests' canonical
  `localhost:3000`, and web/scripts plus Dockerfile were not mounted. Correcting
  only the test invocation resolved all 31 failures; application settings were
  not altered. A Starlette/httpx deprecation warning remains.
- `npm test` in web: **214 passed in 40 files**, 20.75 seconds.
- `npm run typecheck`, `npm run lint`, `npm run build`: passed. Production build
  generated 22 static pages. Build-generated changes to next-env.d.ts were restored.
- `mypy app scripts`: passed, 163 source files.
- Ruff lint and formatting checks on all changed Python files: passed.
- Final working-tree multipart rerun: `pytest tests/test_direct_uploads.py
  --tb=short`: **28 passed**, 38.08 seconds (same deprecation warning).
- Diff review: no credentials, new public storage access, authentication weakening,
  migration, ball-tracking enablement, sport-policy change, or upload-limit change.
  `git diff --check` passed. No commit, push, deployment, or staging cleanup performed.
