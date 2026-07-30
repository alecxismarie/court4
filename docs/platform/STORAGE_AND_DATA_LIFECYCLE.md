# Storage, Retention, and Deletion

## Storage interface

Application services depend on:

```text
reserve(key, media_type, expected_size) -> upload capability
complete(reservation, checksum, size, provider_version) -> object metadata
open_read(object_id) -> stream
create_download(object_id, ttl, disposition) -> URL or proxy descriptor
delete(object_id, expected_version) -> deletion result
stat(object_id) -> provider metadata
```

Local development implements the contract with a configured root and atomic
same-volume rename. Production implements it with private object storage. Domain
code receives `StorageObject` IDs, never arbitrary filesystem paths or provider
credentials.

## Object keys

Recommended immutable patterns:

```text
u/{user_uuid}/v/{video_uuid}/source/{storage_uuid}
u/{user_uuid}/a/{analysis_uuid}/r/{run_uuid}/{category}/{artifact_uuid}
u/{user_uuid}/profile/{storage_uuid}
tmp/{reservation_uuid}/{random_nonce}
```

UUIDs are opaque and keys contain no email, original filename, display name, or
analysis title. Guess resistance does not replace authorization. Bucket/container
access is private and public ACLs are disabled.

## Upload direction

For private alpha, prefer direct multipart upload using short-lived, single-object,
size/content-type-scoped credentials:

1. authenticated API reserves `UploadedVideo` and `StorageObject`;
2. client uploads parts directly and may resume;
3. client calls completion with the idempotency key;
4. API verifies provider metadata, size, checksum strategy, and ownership;
5. inspection downloads/streams to bounded scratch space.

This avoids routing 1 GiB through FastAPI and supports future mobile clients.
API-proxied uploads remain the local-development and migration compatibility path.
Temporary credentials must restrict bucket, exact key, expiry, method, maximum size,
and multipart ID.

Downloads are authorized by FastAPI/Next.js before issuing a short-lived signed URL.
Use API proxying for small sensitive JSON or when response transformation is needed;
use signed downloads for videos and large artifacts. Never persist signed URLs.

No vendor is selected in Phase 1.8A. Required capabilities are private buckets,
multipart/resumable upload, conditional/versioned delete, lifecycle policies,
server-side encryption, checksums/metadata, access logs, and tested backup/export.

## Metadata and isolation

`storage_objects` records provider, bucket, immutable key/version, category, owner,
relations, MIME, size, SHA-256, ETag, timestamps, retention, deletion state, and
encryption key reference. Ownership in the key is defense in depth; authorization
uses database ownership.

Separate production and non-production accounts/buckets. Test fixtures and current
`data/output` never enter the production bucket automatically.

## Proposed retention defaults

These are product defaults for approval, not legal conclusions:

| Data | Proposed lifecycle |
| --- | --- |
| Initiated/incomplete upload | expire after 24 hours |
| Abandoned multipart upload | abort after 24 hours; reconcile metadata within 7 days |
| Validation-failed source | retain 7 days for owner retry/support, then purge |
| Failed analysis artifacts | quarantine 7 days; owner-visible safe evidence may follow normal retention |
| Successful raw source video | owner-controlled; default 30 days after completed analysis, warn before expiry |
| Generated reports/artifacts | retain while analysis exists |
| Deleted analysis | hide immediately; purge artifacts within 30 days |
| Deleted video | hide immediately; purge after dependent-analysis decision and cooling period |
| Verification token | 24 hours or provider standard, single use |
| Password reset token | 1 hour, single use; invalidate on password change |
| Expired/revoked session ledger | hard-delete after 90 days unless security hold |
| Account deletion | 14-day cancellation window, then active-store purge within 30 days |
| Operational audit events | 12 months proposed; security/product approval required |
| Database/object backups | 35 days proposed, encrypted and access-controlled |

Raw-video retention must be configurable without changing analysis evidence
retention. If reprocessing requires an expired raw video, the product explains that
re-upload is required.

## Delete semantics

### Delete one analysis

Set `deletion_pending`, remove it immediately from histories, cancel/deny active
runs, enqueue an auditable cleanup request, delete all run artifacts, reconcile
storage, then tombstone/hard-delete metadata according to audit policy. The source
video remains if another analysis or explicit owner retention references it.

### Delete one video

Show dependent analyses. The chosen product rule must be either: reject until those
analyses are deleted, or delete source bytes while retaining completed derived
analyses. Recommendation: allow source deletion and retain completed results, but
disable reprocessing and record `source_deleted_at`.

### Delete all history

This is a batch of owner-scoped analysis deletion requests, not deletion of a
history table. It does not silently delete profile/account or source videos unless
the UI explicitly includes them.

### Delete account

Recent re-authentication → `deletion_pending` → revoke sessions → block new work →
cancel active runs → enumerate all resources → delete private blobs → purge or
tombstone metadata → reconcile zero remaining accessible objects → mark completed.
Billing cancellation, email tombstoning, and re-registration policy are later
product decisions.

### Consent withdrawal

Withdraw optional future-use permission prospectively, remove resources from
debug/calibration/evaluation/training datasets, and start any promised derivative
cleanup. Required platform processing may continue only for the user's requested
service under the approved terms. Withdrawal does not imply account deletion unless
the UI offers a combined action.

## Holds, backups, and cleanup

Legal/product/security holds are explicit records with reason, scope, approver, and
expiry; they are never inferred. A hold may delay hard deletion but must not make
content normally accessible.

Deletion completion distinguishes active data from backups. Backup copies expire by
rotation and must not be restored into active service without replaying deletion
tombstones. Restore drills verify that deleted users remain deleted.

An asynchronous cleanup mechanism is required in Phase 1.8D even though general
analysis workers are deferred. Until then, deletion may be an operator-run
idempotent command with the same state machine and reconciliation report.

## Product/legal decisions

Approve raw video duration, cooling periods, backup duration, support access,
deletion SLA, source-delete dependency behavior, re-registration after deletion,
security/audit retention, jurisdiction/data location, and consequences of optional
consent withdrawal.
