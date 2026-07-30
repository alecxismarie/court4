# API Impact Assessment

No API changes are made in Phase 1.8A. The following is the Phase 1.8B–1.8D impact
contract. Existing response fields should remain compatible where possible; new
account/resource fields are additive. Authentication failures use `401`; verified
non-owner resource requests use hiding `404`.

## Existing endpoints

All owner operations require an active, verified account unless noted.

| Method/path | Current behavior | Future behavior and ownership | Contract impact |
| --- | --- | --- | --- |
| `GET /health` | Process health | Anonymous liveness only; no dependency details | Preserve body; add separate protected readiness |
| `POST /api/v1/analyses` | Multipart upload + synchronous inspection + analysis creation | Owner-scoped command with idempotency and exact duplicate detection; `reanalyze=true` explicitly creates a new analysis | Add typed `DuplicateUploadResponse` (`200`); normal creation remains `201` |
| `GET /api/v1/analyses` | Lists every filesystem job | Query `owner_user_id`; derived Analysis History | Same shape initially; never admin-wide |
| `GET /api/v1/analyses/{id}` | Reads ID | Owner-filtered DB read | Hiding 404 |
| `GET .../{id}/frames` | Scans frame files | Current/selected run committed frame artifacts, owner-filtered | Artifact IDs may be additive |
| `GET .../{id}/artifacts/{path}` | Resolves relative local path | Compatibility resolver maps owner/run artifact; later canonical artifact-ID endpoint | Hiding 404; path route deprecated later |
| `POST .../{id}/calibration` | Synchronous mutation | Idempotent owner command on current active run | Add idempotency/stale-state errors |
| `POST .../{id}/court-detection` | Synchronous mutation | Idempotent owner command; queued/run-aware later | Same response where practical |
| `POST .../{id}/tracking` | Synchronous mutation | Owner-only; model options server-policy controlled | Do not permit arbitrary client model selection in production |
| `GET .../{id}/players` | Reads tracking | Owner/current committed run | Hiding 404 |
| candidate GET/generate/select/reject/restore/merge/unmerge | Reads or rewrites candidate JSON | Owner command, row-version/idempotency protected; review events durable | Add command IDs/version conflict |
| `POST .../{id}/players/select` | Legacy selection mutation | Owner-only compatibility endpoint | Deprecate after candidate flow migration |
| analytics GET/POST | Read/generate current analytics | Owner/current run; POST idempotent | Preserve evidence response |
| debug Active Play GET/POST | Publicly mounted analysis debug | Remove from player production router; admin/worker capability only | Public route returns 404 in production |
| `GET /api/v1/play-history` | Projects all filesystem jobs | Project only authenticated owner's analyses/runs | Response semantics preserved |
| `GET /api/v1/internal/calibration-readiness` | Publicly mounted read-only internal data | Admin `operations:read`, separate internal router/network | Anonymous/non-admin 404 |

The candidate endpoint paths are:

- `/player-candidates`;
- `/player-candidates/generate`;
- `/player-candidates/{candidate_id}/select`;
- `/player-candidates/{candidate_id}/reject`;
- `/player-candidates/{candidate_id}/restore`;
- `/player-candidates/merge`;
- `/player-candidates/unmerge`.

## New resource endpoints

Detailed API design belongs to implementation phases, but the platform needs:

- account: register, verify, session/login/logout, forgot/reset password,
  `GET/PATCH /me`, delete account;
- uploads: reserve, multipart/complete, metadata, delete;
- analyses: create from uploaded video, list runs, retry/reprocess, cancel, delete;
- artifacts: metadata and authorized download;
- feedback: create/list own submissions;
- consent: current agreements, accept, withdraw;
- admin: registration policy and user state, on a separately protected surface.

`POST /analyses` must eventually accept an `uploaded_video_id`; the legacy multipart
form remains only for a documented transition window.

## Response and compatibility rules

- Authentication does not change evidence fields or policy semantics.
- Resource IDs remain opaque strings; imported IDs are preserved.
- Add `uploaded_video_id`, `current_run_id`, version/provenance summary, and
  lifecycle fields additively before deprecating stage booleans.
- Return `409` for stale version/invalid transition/idempotency mismatch, `429` for
  rate/quota throttling, and `422` for semantic validation.
- Never return provider bucket/key, local path, token, credential, or internal
  failure traceback.
- Frontend adds a session-aware same-origin API layer or bearer propagation; direct
  cross-origin calls without credentials are retired.

## Missing current operations

There are no actual retry, cancel, delete, feedback, source-video, consent, or account
routes today. UI retry language re-invokes existing stage mutations. These operations
must be designed against the state machine rather than inferred from current copy.
