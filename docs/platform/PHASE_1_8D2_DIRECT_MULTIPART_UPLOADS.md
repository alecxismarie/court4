# Phase 1.8D2 direct multipart uploads

## Architecture

In S3 mode the browser sends only authenticated JSON control requests to Court4. It uploads
8 MiB `File.slice()` blobs directly to the private, owner-scoped source key using short-lived
SigV4 `upload_part` URLs. Three parts may run concurrently and each part receives at most three
attempts. No bucket credential, list permission, download URL, or reusable provider permission is
returned to the client.

PostgreSQL stores the upload session and its lifecycle. Provider completion first validates the
object's exact byte size, content type, upload-session metadata, and declared-size metadata. The
session then enters `verifying`. Court4 streams the object through SHA-256 in 8 MiB chunks, checks
an optional client digest if one was supplied, and performs a provider-side self-copy to attach the
verified `court4-sha256` metadata. Multipart ETags are retained only as provider part receipts and
are never content identity.

Only verified objects enter the existing owner- and sport-scoped duplicate reservation. The
existing analysis workflow materializes the source in a temporary processing workspace, inspects
it, preserves Pickleball/Padel isolation, and reuses the already-verified source object rather than
uploading it again. Failed, aborted, and expired sessions do not create analyses.

Local storage mode explicitly answers `transport=proxy`; the established streamed API upload is
then used for local development. S3 mode never silently falls back to proxy transport.

## Bucket CORS

The bucket remains private. Configure one CORS rule per deployment tier, replacing the example
origins with the exact Court4 web origins:

```json
[
  {
    "AllowedOrigins": [
      "https://staging.example-court4.invalid",
      "https://app.example-court4.invalid"
    ],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 900
  }
]
```

Do not use wildcard production origins. `PUT` and `ETag` exposure are required for multipart part
uploads and completion receipts. The browser does not need bucket `GET`, `POST`, `DELETE`, or
listing access. Court4 API CORS is separate and remains controlled by
`PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS`.

Before rollout, verify the configured S3 endpoint is HTTPS and browser-reachable from both web
origins, a preflight `OPTIONS` request permits `PUT`, and a test part response exposes `ETag`. If
the Railway bucket cannot apply this CORS contract, direct browser multipart upload is blocked;
do not make the bucket public or introduce wildcard origins.

## Configuration

The existing S3 variables remain authoritative. Phase 1.8D2 adds optional tuning variables whose
defaults support the current 1 GiB maximum:

```text
PICKLEBALL_AI_DIRECT_UPLOAD_PART_SIZE_BYTES=8388608
PICKLEBALL_AI_DIRECT_UPLOAD_MAX_CONCURRENCY=3
PICKLEBALL_AI_DIRECT_UPLOAD_PART_MAX_ATTEMPTS=3
PICKLEBALL_AI_DIRECT_UPLOAD_PRESIGN_TTL_SECONDS=900
PICKLEBALL_AI_DIRECT_UPLOAD_SESSION_TTL_SECONDS=21600
PICKLEBALL_AI_DIRECT_UPLOAD_VERIFICATION_LEASE_SECONDS=1800
PICKLEBALL_AI_DIRECT_UPLOAD_CHECKSUM_CHUNK_SIZE_BYTES=8388608
```

Do not increase `PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES`; it remains 1073741824. Keep
`BALL_TRACKING_ENABLED=false`, the S3 bucket private, and the legacy API volume mounted.

## Expired-session reconciliation

`python -m scripts.reconcile_multipart_uploads` is dry-run only by default. It selects only exact
PostgreSQL sessions in `initiated`, `uploading`, or `expired` state whose individual expiry has
passed. Apply mode requires both `--apply` and
`--confirm abort-expired-court4-multipart-sessions`, and refuses scopes above `--max-sessions`
(default 100). It calls provider abort for each exact key/upload ID and records the session as
aborted. It never lists the bucket, deletes objects, removes prefixes, or touches verifying,
analyzing, completed, or failed sessions.

## Deployment and acceptance sequence

1. Back up PostgreSQL; retain every Railway volume and existing S3 object.
2. Apply migration `0010_direct_multipart` and verify downgrade/re-upgrade in an isolated copy.
3. Apply the restrictive bucket CORS rule and validate preflight plus exposed `ETag` from the
   staging web origin.
4. Deploy `court4-api` with the existing S3 credentials and the defaults above. Do not change the
   storage backend, upload maximum, rate limits, volume mounts, or ball-tracking flag.
5. Verify `/ready`, then deploy the web build pointing at that API.
6. Upload a small Pickleball video; confirm direct part requests target S3, verification completes,
   and the existing analysis flow opens.
7. Upload the 680.6 MB / 4m55s Pickleball video; confirm no video request body targets Court4 API,
   progress reaches 100%, finalization completes, and an analysis is created.
8. Upload Padel; confirm inspection-only behavior and no Pickleball Match IQ/calibration path.
9. Retry an exact duplicate; confirm the existing-analysis response and explicit reanalysis option.
10. Interrupt an upload; confirm bounded part retries, a specific error/cancel state, provider abort,
    and no analysis row.
11. With a second owner, attempt status, part refresh, completion, and abort against the first
    session; every request must be concealed as not found.
12. Confirm the private source object and PostgreSQL locator/checksum exist, while responses contain
    no credentials or permanent provider URL. Run the reconciliation command without `--apply` and
    review its dry-run output.
