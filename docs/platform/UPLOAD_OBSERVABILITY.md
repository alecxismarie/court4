# Direct multipart upload timing

This instrumentation changes no upload settings, hashing, authentication, retry decisions,
verification or inspection behavior. No migration or Railway variable is required.

## Collecting a real upload

Capture the browser console (preserve logs across navigation) and filter `court4_upload`.
Each entry is a JSON snapshot. Browser events are **not sent to the API or persisted**;
mobile testing requires browser remote inspection/console capture. There is no user-facing
debug dashboard. Preparation has a non-secret `run_id`; `session_bound` links that run to
the server-issued `upload_session_id`. Remove hyphens from the session UUID to match
`analysis_id` in API timing logs. Browser/server wall clocks can differ; durations use
monotonic clocks within each process.

## Browser events

- `preparation_start`, `preparation_end`: hash/identity preparation timestamps, bytes,
  successfully processed chunks, duration and bounded outcome. The root digest is included
  in duration; no hash value or filename is recorded.
- `session_bound`: links preparation to the durable upload session.
- `transfer_start`, `transfer_end`: total file bytes/parts, previously completed parts/bytes,
  newly completed bytes, completed-part count, duration, retries, successful URL renewals,
  maximum observed in-flight parts and effective Mbps. Transfer covers the part-worker
  window (including renewal, backoff and stalls), ending before the completion API call.
  Mbps uses **newly successful bytes** only, excluding previously completed parts and
  retransmitted/failed bytes. It is useful throughput, not physical link bandwidth.
- `part_start`, `part_end`: part number, attempt, bytes, timestamps, duration, active-part
  count and outcome. Attempt timing covers PUT/body transfer/response, excluding URL renewal.
- `part_retry`: an existing subsequent attempt actually begins; includes previous failure
  category. No extra retry is introduced.
- `part_stalled`: part/attempt and elapsed milliseconds since increasing progress (or send).
- `url_renewal_start`, `url_renewal_end`: part/attempt, duration, outcome and reason:
  `near_expiry`, `expired`, `authorization_rejection`, or `recovery_resume` (no cached URL).

Outcomes are `success`, `canceled`, `network`, `inactivity`, `storage_authorization`, `http`,
`missing_receipt`, or `other`. Logging is capped at 2,048 events per browser run and never
emits per-progress events. A failed transfer summary is a snapshot at first worker failure;
sibling abort/end events can follow. It is not reported as successful completion.

## API events

The existing JSON logger emits `upload_completion_received`, `upload_completion_accepted`,
`upload_verification_start`, `upload_verification_end`, `upload_session_completed` and
`upload_session_failed`. Accepted means the completion handler accepted the existing state
and scheduled background work when applicable; it does not mean verification succeeded.
Repeated idempotent requests may produce repeated received/accepted events.

`upload_phase_start` / `upload_phase_end` bracket `completion` (completion service call,
including multipart finalization and initial object metadata validation), `integrity` (existing file identity check),
`sha256`, `verified_metadata`, `source_materialization`, `inspection`, and
`artifact_persistence`. Phase duration includes IO already performed by that operation;
there are no additional S3 reads. Phase success means the operation returned normally;
the verification end outcome is authoritative for validation success. Missing optional
identity checks produce a near-zero integrity interval. Inspection/persistence timings
also apply to the existing proxy path sharing those operations.

Verification end includes duration and success/failure. An analyzing-session recovery skips
verification as before. Existing `verification_started_at` remains a lease timestamp and
is overwritten on entering analysis/recovery; do not treat it as immutable phase history.
`created_at`, `completed_at`, and session state retain their existing meanings.

## Limits and safety

These events cannot identify carrier congestion, radio quality, packet retransmission,
browser suspension, DNS/TLS timing or S3 internal latency independently. No client events
survive a closed tab unless its console was captured. Process termination may leave an
unmatched start event. Logging caps can truncate unusually retry-heavy runs. No historical
upload gains missing browser timings retroactively.

New fields contain only generated run/session/analysis identifiers, numeric metrics and
fixed event/reason/outcome categories. No credentials, headers, cookies, filenames, local
paths, object keys, ETags, hashes, file contents, request bodies, presigned URLs or arbitrary
exception text are logged. No progress UI or performance setting changes are included.
