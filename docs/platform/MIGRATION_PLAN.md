# Filesystem-to-Platform Migration Plan

## Recommendation

Current local analyses remain development-only by default. Production starts empty.
If a specific design-partner analysis must move, import it through an explicit,
owner-selected command after that user exists and has accepted current terms. Do not
create a synthetic production “legacy user” that makes ownership ambiguous.

## One controlled ownership migration

Phase 1.8B introduces all durable identity placeholders (`users.id`), upload,
analysis, run, artifact, provenance, and state metadata together. Phase 1.8C later
attaches auth identities to those users. This avoids separate throwaway migrations
for persistence and ownership.

For pre-auth development/import testing, create an explicit
`migration_placeholder` user in non-production only. It cannot authenticate and
must be resolved to a real owner before any production import commit.

## Import stages

1. **Inventory (read-only):** scan `data/output`; classify valid, partial, malformed,
   manually created, fixture, and orphan directories.
2. **Export manifest:** record source root fingerprint, analysis ID, relative files,
   sizes, SHA-256 values, detected schemas/versions, timestamps, and validation
   errors. Exclude secrets and absolute paths from the durable report.
3. **Owner mapping:** require an explicit mapping from each selected analysis to one
   user; no inference from filenames.
4. **Dry run:** validate IDs against the current pattern, parse `job.json` and
   recognized reports, map stages/status, calculate storage plan, and produce a
   reconciliation report without writes.
5. **Import transaction:** preserve a valid current `analysis_id` UUID/identifier,
   create UploadedVideo, Analysis, initial legacy AnalysisRun, events, and reserved
   storage metadata; copy bytes to immutable keys; commit metadata only after hash
   verification.
6. **Reconcile:** compare file count, byte total, hashes, parsed report count,
   current run, history classification, and unresolved warnings.
7. **Cutover:** switch repository reads to PostgreSQL only after reconciliation.
8. **Archive:** make legacy roots read-only and retain for the rollback window; never
   dual-write indefinitely.

## Mapping rules

- Preserve current analysis IDs when valid and unique; otherwise assign a UUID and
  record `legacy_analysis_id`.
- One current analysis directory becomes one UploadedVideo, one Analysis, and one
  initial AnalysisRun.
- Preserve source and report timestamps when trustworthy; retain filesystem mtime
  only as `legacy_metadata`, never silently as creation time.
- Current relative paths become display/logical names only. New storage keys use
  opaque IDs.
- Compute source and artifact SHA-256 during import.
- Map `processing` jobs with no live executor to `failed` reason
  `legacy_stale_processing`, unless an operator explicitly resumes them as a new run.
- Missing versions remain `UNVERSIONED`/nullable with
  `legacy_missing_fields`; do not apply current versions retroactively.
- Current completion booleans help validate artifacts but do not override missing
  required files.

## Malformed and partial records

Import is fail-closed per analysis, not all-or-nothing for the batch. Each rejected
record has a stable reason and no partial durable row/object set. Unknown files are
listed and optionally imported as `legacy_unknown` artifacts only after review.
Test IDs, calibration datasets, validation runs, and manually generated detector
outputs are excluded by default.

## Dual-read/write and rollback

Recommended cutover:

- short compatibility period where the new repository can read DB first and legacy
  filesystem only for explicitly flagged imported IDs;
- no normal dual-write, because current JSON writes are not transactional and would
  create split authority;
- maintenance window for the final selected import;
- rollback by routing to the read-only legacy repository and dropping/ignoring the
  uncommitted new environment, never by copying partially imported objects back.

Once new writes are enabled, PostgreSQL is authoritative and rollback must restore
database/object-store backups as one reconciled recovery point.

## Import acceptance

- every imported Analysis has exactly one real owner and matching source owner;
- all copied objects match source hashes and byte counts;
- no absolute local path is persisted as a production key;
- history output matches expected legacy classification;
- unresolved provenance is explicit;
- dry-run and committed reconciliation reports are retained;
- rerunning the same manifest is idempotent.
