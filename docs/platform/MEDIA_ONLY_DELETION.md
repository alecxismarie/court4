# Media-only source deletion

## Pre-change audit

The starting worktree contains the uncommitted upload-session fix in uploads.py,
the multipart reconciliation script, upload API/dropzone and their tests, plus its
audit report. These changes must remain intact. No commit/push or Railway mutation
is authorized.

Analysis references UploadedVideo through an owner-composite RESTRICT foreign key.
Runs, selections and artifacts also use RESTRICT, not cascading analytical deletion.
UploadedVideo retains SHA-256, provider/key, original filename, byte count and JSON
metadata. Source artifacts have separate provider/key and logical path records;
legacy local keys are relative to the analysis directory. Artifact state already
supports deleted, but UploadedVideo.state only supports pending/available/failed.

Analysis History projects persisted job metadata and independent analytics and
Match IQ JSON. Play History and Progress are versioned read-time projections of
those same reports, quality, selections and timestamps; they are not computed from
the source bytes. Their existing contribution inputs must not change. Frames,
tracking, candidate previews, analytics and Match IQ are independent artifacts.
Duplicate detection joins immutable owner/checksum metadata to Analysis, without
checking physical source availability.

Simply deleting S3 bytes is unsafe: load_job materializes all available artifacts,
and save_job can upload workspace source bytes again. Several GET handlers can
regenerate candidate/preview evidence. These need media-state guards and read-only
retained-results paths, in addition to a deletion endpoint. No existing media-only
deletion service exists. ObjectStorage.delete already supports S3 and local bytes.

Plan: extend UploadedVideo's existing state constraint with deleting/deleted through
a new migration; preserve provenance and analysis timestamps. Commit deletion intent
before provider IO; finalize deleted only after success. Retry the same intent after
provider/DB/process failure. Coordinate source-dependent operations and deletion
with a PostgreSQL analysis lock, and reject writes to deleted media. No analysis,
run, contribution policy or derived evidence is deleted. No major architectural
conflict prevents these semantics.

## Implemented semantics

`DELETE /api/v1/analyses/{analysis_id}/source-video` requires the existing VerifiedUser
dependency and owner-scoped analysis lookup. Success is 204. Unknown/other-owner
analyses remain 404; unauthenticated requests remain 401. Incomplete Pickleball
analysis is rejected. Padel's successful inspection is its supported terminal
product step, and may release its media without enabling Pickleball interpretation.
An associated direct-upload session must be completed. No upload state is changed.

The endpoint deletes only the UploadedVideo's exact provider locator, plus its
source-file workspace copy. S3 uses the existing ObjectStorage.delete operation;
local/legacy paths use LocalObjectStorage rooted in the validated analysis directory.
No bucket listing, prefix deletion, public URL, credentials or broad deletion API
is exposed. No analytical row is deleted. Source artifact rows become `deleted`
while retaining their locators, hashes, sizes and provenance. Derived artifacts
remain available.

The existing UploadedVideo state machine now includes `deleting` and `deleted`.
Deletion intent and its timestamp commit before storage IO. Provider failure returns
a sanitized 503, leaving explicit retryable `deleting` state, never a false success.
After provider success, finalization records `deleted` and its timestamp. Missing
objects are idempotent; if database finalization fails after storage deletion, a
repeat DELETE finishes the same durable intent. No source is restored or substituted.
An unfinished deletion needs a user retry; there is no new automatic deletion worker.

PostgreSQL shared analysis locks cover workflow operations, repository writes and
artifact materialization; deletion takes the matching exclusive lock. Deletion
and materialization wait for contention to clear; other busy workflow operations
retain their typed 409. These
are session locks on autocommit connections, so there is no long idle transaction
around video processing or provider IO. Connection cleanup releases the lock, and
deletion intent survives process failure. Writes are also fenced by video state
in the repository and persistence service. A defensive shared-video check refuses
deletion if legacy data references one UploadedVideo from multiple analyses; normal
uploads and explicit reuploads create distinct video records.

Job reads project source availability from UploadedVideo without changing saved
analysis payloads, timestamps, run versions or selections. Results loading excludes
the removed source, and deleted-media candidate/player reads use retained evidence
without regenerating it. Source-dependent mutations and source-artifact requests
return `source_video_unavailable` (409). Completed analytics/Match IQ GET remains
available. Reuploading bytes is a separate existing upload operation: checksum
duplicate detection still finds the retained analysis, and explicit reanalysis of
a newly uploaded recording retains its existing behavior.

Analysis History and Play History are retained. Their versioned policy inputs are
unchanged: no match is removed or reclassified solely because media is gone. The
five-match regression compares the entire History and Play History responses,
including Progress, before/after removing match-2 (the third match), as well as the
full analytics/Match IQ response and independent frame evidence.

The completed match details page offers Delete video with deliberate confirmation,
Keep video, pending, error/retry and durable Source video deleted states. The copy
distinguishes the original recording from analysis and Progress retention. No success
state appears until backend confirmation. Source-dependent workflow controls are
hidden after deletion; the completed report link and evidence remain.

## Schema

New migration: `0011_source_media`, file `0011_source_media_lifecycle.py`, revising
`0010_direct_multipart`. It only extends `ck_video_state`; no historical migration
was edited. Existing available/pending/failed rows remain valid. Downgrade/re-upgrade
is supported before deletion records exist. Downgrade deliberately refuses once
deleting/deleted records exist rather than relabeling missing media as available.
Alembic metadata drift and round-trip tests cover this behavior.

## Exact files for this feature

- `app/api/v1/analyses.py`
- `app/persistence/errors.py`
- `app/persistence/models.py`
- `app/persistence/service.py`
- `app/persistence/alembic/versions/0011_source_media_lifecycle.py`
- `app/schemas/jobs.py`
- `app/services/jobs/repository.py`
- `app/services/jobs/workflow.py`
- `app/services/jobs/media_guard.py`
- `app/services/jobs/source_media.py`
- `tests/test_source_media.py`
- `tests/test_object_storage.py` (use real persistence in the provider-failure fixture,
  since repository writes now acquire a database lock)
- `web/lib/api/types.ts`
- `web/lib/api/source-media.ts`
- `web/components/match-details.tsx`
- `web/components/source-video-controls.tsx`
- `web/components/source-video-controls.test.tsx`
- `web/test/factories.ts`
- `web/e2e/source-media.spec.ts`
- This report.

The seven previously changed multipart implementation/test files and its audit
report were not edited for this feature. No commit, push, Railway change or staging
data mutation is authorized or performed. Storage limits, authentication, CORS,
registration, private bucket policy, Padel isolation and disabled ball tracking
are unchanged. The upload-finalization crash limitations recorded in the previous
audit remain outside this media-only feature.

## Validation results

- Full backend: `pytest --tb=short` in the isolated Compose test database:
  **390 passed, 10 skipped**, 437.40 seconds. Includes all **10 media-deletion
  cases** and **28 direct-multipart cases**. One existing Starlette/httpx
  deprecation warning. The first full run exposed an empty persistence test stub;
  that fixture now uses real persistence and the full rerun passed.
- Frontend: `npm test`: **217 passed in 41 files**. The three deletion UI cases
  also passed again after final JSX formatting.
- `npm run typecheck` and `npm run lint`: passed, including the new browser spec.
- `npm run build`: passed (Next 16.3.0, 22 static pages).
- Ruff check/format for the feature files: passed. `mypy app scripts`: passed,
  166 source files.
- Migration upgrade, downgrade/re-upgrade with existing records, no Alembic
  metadata drift, and refusal to downgrade deletion records: passed in the
  media-deletion suite. These were local tests, not a staging migration.
- Playwright Chrome: **21 passed across rate-limit-safe batches**: 10 Progress
  integrity, 10 workflow, and 1 new deletion/confirmation/retry/refresh case.
- `git diff --check`: passed. Reviewed the combined tracked diff and all new
  feature files; no credentials, environment values, generated artifacts,
  storage/authentication policy changes or unrelated files were introduced.
- Final worktree: **18 modified tracked files and 10 untracked files**, comprising
  the original 7 multipart files + its audit, and the 20 files listed above.
  No files staged; no commit or push. Generated `next-env.d.ts` changes returned
  to their starting contents after the E2E run.

Storage tests use the existing fake S3 implementation and real local files. No
live Railway bucket deletion was performed. Browser tests use real isolated
authentication with mocked analysis/deletion responses; backend tests separately
exercise persistence and storage ordering.

The combined browser run reached the configured authentication rate limit after
the ten Progress cases. Subsequent specs were run in smaller batches after the
window expired; authentication limits were not changed. The new deletion spec's
alert locator was scoped to its dialog to avoid Next's separate route announcer.

## Final P1 materialization race correction

The pre-commit review found that `resolve_artifact` checked source availability
without a shared media lock. An S3 download could capture bytes before deletion,
then write or rename them into a workspace after DELETE had succeeded. Direct
bulk materialization also lacked its own locking boundary.

`resolve_artifact`, `load_job` and bulk materialization now acquire the existing
owner/analysis PostgreSQL shared advisory lock before reading durable state and
hold it through cache checks, local copying, provider download, integrity checks
and final file installation. Deletion waits for that same lock exclusively.
Waiting retries release the database connection between attempts, so waiters do
not exhaust the pool needed by the lock holder's persistence transactions. No new
lock namespace, migration or frontend change was introduced.

If materialization wins, deletion waits for it to finish, then commits deletion
intent, removes the provider source and exact local source copies, and finalizes
`deleted`. If deletion wins, materialization waits and reads durable state only
after acquiring the lock. An explicit source request receives the existing
`source_video_unavailable` conflict without provider access; bulk result loading
excludes the source and continues serving retained evidence.

S3 request repositories have separate owner-prefixed workspaces. Cleanup now
removes the exact source logical path and its matching `.court4-download` file
from the current workspace, configured legacy root, and owner-prefixed directories
directly under the configured processing root. It excludes symlink directories
and does not recursively delete directories, other matches, other owners, derived
artifacts or unrelated temporary files. Cleanup errors retain retryable `deleting`
state instead of claiming success. This covers the configured local filesystem;
it is not a mechanism for erasing files on separate hosts or arbitrary external
copies. Durable state still rejects reanalysis through every repository.

Lock order remains media advisory lock, then short persistence transactions, with
no row lock held while awaiting the advisory lock. Nested shared operations reuse
the repository's context-local lock. Exclusive upgrades are rejected, and release
runs in `finally` with connection invalidation if unlock fails. The audited paths
do not acquire multiple analysis locks or nest different repositories' locks.

Eight event-controlled regression cases exercise both orderings, individual/bulk
materialization and shared/separate workspaces. They pause before the local write
or provider deletion and observe a failed PostgreSQL lock acquisition before
releasing the first operation; no sleep-based ordering assertion is used. Each
case checks source absence, durable deletion, reanalysis rejection, unchanged
analysis payload/version/timestamp, results, History and Progress. An additional
case checks exact cleanup in an abandoned owner workspace while preserving other
matches, owners, derived evidence and unrelated temporary files. The legacy-local
test also verifies removal of an already materialized copy.

Validation of the P1 correction:

- Deterministic concurrency tests: **8 passed**, 10 deselected, 27.85 seconds.
- Full backend suite against the isolated Compose test database: **399 passed,
  10 skipped**, 454.71 seconds. The skips remain the optional PostgreSQL spike
  cases. One existing Starlette/httpx deprecation warning.
- Separate focused media-deletion and multipart regression run: **47 passed**
  (19 media-deletion cases and 28 multipart cases), 94.48 seconds, same warning.
- Ruff lint and formatting checks: passed for all three affected Python files.
- `mypy app scripts`: passed, 166 source files.
- No frontend files changed, so no frontend rerun was needed for this correction.
- SHA-256 comparison confirms all seven multipart implementation/test files are
  byte-for-byte identical to their contents at the start of this correction.
- The correction changes only `app/services/jobs/repository.py`,
  `app/services/jobs/source_media.py`, `tests/test_source_media.py` and this report.
  The media-only lifecycle, provenance, retained analysis and Progress semantics
  remain intact. No new migration, configuration or credential changes.
- Final diff/whitespace review passed, with no unrelated changes or secrets added.
  Final Git status remains **18 modified tracked files and 10 untracked files**;
  nothing staged. No reset, revert, commit, push, deployment or Railway mutation.
