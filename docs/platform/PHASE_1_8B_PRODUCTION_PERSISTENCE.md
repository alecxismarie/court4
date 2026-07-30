# Phase 1.8B Production Persistence

## Decision

PostgreSQL is the only authority for users, uploads, analyses, analysis runs,
workflow state, state events, idempotency, artifact metadata, provenance, and
player selection. Local storage remains the development/test byte provider. A
path or `job.json` file cannot create, list, authorize, or change a runtime
resource.

The existing HTTP response shapes and opaque analysis identifiers are retained.
There is no compatibility fallback: missing PostgreSQL configuration or a
disabled development/test bootstrap identity fails closed.

## Runtime boundaries

- `app.persistence` owns SQLAlchemy models, connections, typed failures,
  transactions, bootstrap policy, and local-storage path safety.
- `AnalysisJobRepository` is a compatibility façade. It serializes the existing
  `AnalysisJob` projection into `analyses.job_payload`, while explicit columns
  own state, stage, ownership, runs, and artifacts.
- CV algorithms produce files outside a database transaction. A short
  transaction then commits job state, artifact checksums/metadata, and events.
  Unregistered orphan bytes have no runtime authority.
- History enumeration is owner-scoped from PostgreSQL. Analytics bytes are
  loaded only through registered artifact metadata.
- `/health` is process liveness. `/ready` verifies PostgreSQL connectivity.

## Frozen states

Uploaded video: `pending`, `available`, `failed`.

Analysis: `pending`, `processing`, `completed`, `failed`, `cancelled`.

Analysis run: `queued`, `processing`, `completed`, `failed`, `cancelled`,
`stale`. `stale` is explicit so an expired lease is distinguishable from a
pipeline failure or user cancellation.

Only one run in `queued` or `processing` may exist per analysis. PostgreSQL
enforces this with a partial unique index. Terminal runs are immutable. A retry
creates a new run linked through `previous_run_id`.

`analyses.promoted_run_id` is the sole durable result-selection pointer. Starting
a retry does not promote it. Only a completed transition may change it.

## Ownership and identity

All player resources carry `owner_user_id`; composite foreign keys prevent an
analysis, artifact, or player selection from crossing owners. Phase 1.8B does
not implement authentication. Development and test may explicitly configure one
bootstrap UUID and identity label. Bootstrap is rejected in staging and
production, where mutations remain unavailable until Phase 1.8C supplies a real
subject.

## Idempotency and concurrency

Idempotency records are unique by `(owner_user_id, scope, key_hash)`. The raw key
is never stored. Reuse with the same request fingerprint resolves to the original
resource; reuse with another fingerprint returns a conflict. Optimistic row
versions guard competing run transitions. State and state-event writes share one
transaction.

The API accepts an optional `Idempotency-Key` header on upload. Requests without
one receive a server-generated one-shot key, preserving the existing client
contract.

`uploaded_videos.metadata_payload` is a non-null JSONB mapping. Both ORM-created
and direct database inserts default omitted metadata to `{}`; `NULL` has no
separate domain meaning. Revision `0003_metadata_payload_contract` backfills
legacy NULLs before enforcing this contract.

The web client supplies an idempotency key for every upload intent and reuses it
for retries. Separately, exact duplicate detection checks the uploaded SHA-256
checksum within the same owner's history. A new intent containing bytes already
uploaded by that owner returns the existing analysis; it does not create another
row unless the user explicitly chooses Analyze Again.

Concurrent identical uploads are serialized with an owner-and-checksum-scoped
PostgreSQL advisory lock. See
[Exact Duplicate Video Detection](EXACT_DUPLICATE_VIDEO_DETECTION.md) for the
response contract, privacy boundary, and byte-identical detection limit.

## Configuration

All settings use the `PICKLEBALL_AI_` prefix:

- `ENVIRONMENT`, `PERSISTENCE_BACKEND`, `DATABASE_URL`
- pool size, overflow, timeout, recycle, and pre-ping settings
- statement, lock, and idle-in-transaction timeout settings
- `LOCAL_STORAGE_ROOT`
- development/test bootstrap identity settings
- `LEGACY_IMPORT_ENABLED`

No setting selects filesystem metadata authority.

## Artifact inventory

The local provider registers source uploads, inspection metadata and sampled
frames, calibration reports/images, tracking reports/observations/video and
candidate previews, analytics JSON/images, Match IQ, and shadow Active Play
evidence. Each row stores a relative provider key, MIME type, byte size, SHA-256,
kind, owner, analysis, and producing run. Browser-generated share cards are not
backend artifacts and are not falsely registered. Unknown files and legacy
`job.json` remain invisible to runtime reads.

## Deferred work

Authentication/session identity, private object storage, queues/workers,
retention deletion, managed deployment, backup/restore operations, and public
exposure remain Phase 1.8C or later work.
