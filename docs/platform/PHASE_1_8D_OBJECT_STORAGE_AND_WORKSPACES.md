# Phase 1.8D: Object Storage and Processing Workspaces

## Audited legacy lifecycle

Before this phase the authenticated `POST /api/v1/analyses` endpoint accepted one multipart
`UploadFile`. The API reserved twice the configured maximum upload size against
`analysis_output_dir`, streamed the request in configured chunks to
`_uploads/{analysis_id}/source.{ext}`, enforced the byte limit while streaming, and calculated
SHA-256 in the same pass. Extension and declared media type were validated before the write;
OpenCV then validated readability, actual size, metadata, and sampled frames.

PostgreSQL reserved the owner-scoped video/analysis and idempotency record after hashing. An
owner-and-sport-scoped SHA-256 lookup under a PostgreSQL advisory lock implemented exact
duplicate detection. `reanalyze=true` deliberately allowed another analysis; retries with the
same idempotency key and fingerprint returned the original result. The source was moved to
`{analysis_id}/uploads/source.{ext}` even when inspection failed. `_uploads` was removed in a
`finally` block, with a dry-run-first quarantine command for abandoned staging directories.

`AnalysisJobRepository` treated PostgreSQL as job and ownership authority, but discovered
artifact bytes by recursively walking `{analysis_output_dir}/{analysis_id}`. It registered
relative local keys, SHA-256, media type, size, kind, run, and stage-attempt provenance.
Artifact API responses exposed only authenticated Court4 proxy URLs. The artifact route checked
the owner through PostgreSQL, rejected traversal, required a current registered artifact, and
served a local `FileResponse`; unregistered or missing bytes returned 404.

All analysis stages were coupled to real paths. OpenCV video inspection, player tracking,
candidate appearance extraction, court calibration, ball visualization, and video writing use
seekable local files. History reads registered JSON artifacts through the repository. Pickleball
ball evidence writes under `ball/attempt-NNNN/`, and PostgreSQL enforces the matching immutable
stage attempt. The Padel API uses the same upload/inspection lifecycle but sport policy blocks
Pickleball calibration, tracking, Match IQ, active play, and history interpretation. The separate
Padel inspection CLI also accepts and writes explicit local paths.

The database already had `storage_provider` and `storage_key` on uploaded videos and artifacts,
but runtime registration hardcoded `local`. `UploadedVideo.storage_key`, artifact rows, and the
job payload's `source_video` contained relative local paths. Frontend upload code assumed a
single authenticated multipart request with progress and idempotency headers; frontend artifact
code assumed Court4 API URLs, not public bucket URLs. Tests directly created files below analysis
directories and therefore encoded local-backend compatibility.

`/app/data/output` was configured as the durable byte root in staging. `/app/data` also contains
the mounted persistent volume. There was no object-store completion state, no workspace
materialization, and no cleanup of an analysis directory because it was the durable library.
Failure recovery depended on PostgreSQL idempotency and retained local bytes. Process crashes
could leave `_uploads`; operator cleanup quarantined rather than deleted them.

## Chosen architecture

Phase 1.8D uses the smallest production-sensible first step:

```text
authenticated browser multipart upload
  -> Court4 API bounded workspace (stream + SHA-256 + size enforcement)
  -> PostgreSQL owner/idempotency/duplicate reservation
  -> OpenCV inspection using a seekable local path
  -> private S3-compatible bucket (verified source + durable artifacts)
  -> PostgreSQL provider locator and logical artifact metadata
  -> request workspace cleanup
```

This deliberately keeps browser-to-API upload for now. It preserves the existing checksum and
duplicate transaction boundary and avoids an unsafe frontend/completion rewrite. Direct,
multipart presigned upload remains the next scaling step; it requires explicit upload reservation
and completion endpoints, server-side completion verification, expiry, and abandoned multipart
reconciliation.

## Storage contract and privacy

`ObjectStorage` provides ready, put, download, stat, exists, and delete operations. The local
adapter remains the default and needs no Railway credentials. The S3 adapter uses SigV4 and
configurable `auto`, `virtual`, or `path` addressing, never sets a public ACL, never returns raw
bucket URLs, and never logs credentials or provider exception text. Every upload stores a
Court4 SHA-256 metadata value; `HEAD` size/checksum metadata and downloaded bytes are verified.

PostgreSQL remains authoritative for owner, sport, analysis/run/stage state, idempotency,
checksum, logical artifact identity, current-version selection, and provenance. Object existence
alone never creates or completes an analysis. A new `analysis_artifacts.logical_key` separates
the stable Court4 API path from the provider key. The migration copies legacy local keys
verbatim. Existing local records are read from `local_storage_root` and copied into a temporary
workspace when S3 mode is active; no legacy files are moved, deleted, or reinterpreted as S3.

The bucket remains private. All current downloads are authorized and proxied by the existing
owner-scoped Court4 artifact endpoint. Signed downloads are intentionally deferred.

## Object keys

Source objects are immutable and scoped to one owner and analysis:

```text
users/{owner_uuid}/analyses/{analysis_id}/source/video.{validated_extension}
```

Durable artifacts use their validated logical path plus a SHA-256 version component:

```text
users/{owner_uuid}/analyses/{analysis_id}/artifacts/
  {logical_parent}/versions/{sha256}/{filename}
```

User filenames, emails, display names, and arbitrary path components never enter provider keys.
Ball evidence retains `ball/attempt-NNNN/` in the logical parent, so attempts cannot overwrite
one another. Content-addressed artifact versions prevent retries from overwriting historical
bytes even when a canonical logical artifact changes.

## Durable and temporary policy

The source video and every artifact registered by the existing repository are durable. This
includes sampled review frames, metadata, court calibration evidence, tracking reports and
user-facing media, analytics, Match IQ/active-play reports, and attempt-versioned ball evidence.
The repository does not upload unregistered detector caches or the `_uploads` staging tree.
Ball-pipeline internal temporary visualization directories retain their existing cleanup.

In S3 mode every API dependency creates a unique `court4-{owner}-*` workspace. Processing calls
materialize current registered objects before existing path-based stages run, and newly generated
durable outputs are uploaded and verified before PostgreSQL points at them. Dependency teardown
removes the complete workspace on success and failure. A capacity reservation covers all
materialized objects plus one additional source-sized output allowance, and the existing active
limit bounds concurrent materialization.

The upload admission reservation now measures `processing_workspace_root`, not the durable
object library. Upload-size policy remains `max_upload_size_bytes`; S3 capacity/provider errors
are separate from local workspace free-space and concurrency errors. The warning and hard-stop
thresholds were not lowered or removed.

A process crash may leave a workspace. `python -m scripts.workspace_cleanup` is dry-run by
default, considers only `court4-*` directories older than 24 hours, and never touches unrelated
paths. Apply mode requires `--confirm quarantine-expired-court4-workspaces` and file/byte caps;
it moves candidates to `_quarantine/workspaces` instead of deleting them. Schedule a reviewed
dry run and quarantine after crashes. Railway currently does not expose bucket lifecycle
configuration, so review provider objects with no committed PostgreSQL locator operationally;
do not delete registered objects based only on a bucket listing. Automated S3 orphan deletion
remains deferred until Court4 has an owner-scoped, auditable reconciliation state machine.

## Configuration

Local development defaults:

```text
STORAGE_BACKEND=local
PICKLEBALL_AI_LOCAL_STORAGE_ROOT=data/output
STORAGE_PROCESSING_WORKSPACE_ROOT=data/workspace
```

For `court4-api` on Railway:

```text
STORAGE_BACKEND=s3
STORAGE_PROCESSING_WORKSPACE_ROOT=/tmp/court4-workspaces
STORAGE_S3_ENDPOINT=${{<bucket-service-name>.ENDPOINT}}
STORAGE_S3_REGION=${{<bucket-service-name>.REGION}}
STORAGE_S3_BUCKET=${{<bucket-service-name>.BUCKET}}
STORAGE_S3_ADDRESSING_STYLE=auto
STORAGE_S3_ACCESS_KEY_ID=${{<bucket-service-name>.ACCESS_KEY_ID}}
STORAGE_S3_SECRET_ACCESS_KEY=${{<bucket-service-name>.SECRET_ACCESS_KEY}}
```

Replace `<bucket-service-name>` with the bucket's actual Railway service name or use the bucket
Credentials tab's auto-inject action, then map the injected values to the Court4 names above.
Use `BUCKET`, not `RAILWAY_BUCKET_NAME`. Railway documents buckets as private and documents
`BUCKET`, `ENDPOINT`, `REGION`, `ACCESS_KEY_ID`, and `SECRET_ACCESS_KEY` as referenceable bucket
variables: <https://docs.railway.com/storage-buckets>. Railway reference syntax is documented at
<https://docs.railway.com/variables>.

New Railway buckets normally use virtual-hosted URLs and `auto` is the correct default. If the
bucket Credentials tab says this older bucket requires path-style URLs, set
`STORAGE_S3_ADDRESSING_STYLE=path`.

Keep `PICKLEBALL_AI_LOCAL_STORAGE_ROOT=/app/data/output` while legacy files remain there. Do not
remove the API volume. Keep the existing upload-size, reservation multiplier, warning/hard-stop,
and active concurrency settings. `BALL_TRACKING_ENABLED=false` remains mandatory.

## Deployment and recovery

1. Back up PostgreSQL and retain the API volume.
2. Deploy the schema migration before enabling S3 writes.
3. Add bucket reference variables to `court4-api`; seal credentials if desired.
4. Set the backend and workspace variables, review the staged Railway changes, then deploy.
5. Verify `/ready`, one small Pickleball upload, one Padel inspection-only upload, duplicate retry,
   authenticated artifact download, and cross-owner denial.
6. Verify the source/artifact rows use provider `s3` and that no bucket URL is returned publicly.
7. Keep legacy reconciliation read-only. Migration of legacy bytes is a later explicit operation.

If object upload or verification fails, the analysis is not reported as successfully persisted.
The client can retry using its idempotency key. If a process exits after an object write but
before the PostgreSQL transaction, the provider object is an owner/analysis-scoped orphan and is
handled by reviewed reconciliation; it does not become visible merely by existing.

The 0009 downgrade is supported while all artifact rows remain local. It intentionally refuses
to drop logical locators after non-local artifact rows exist, because that would make S3 provider
keys look like public logical paths on a later re-upgrade.
