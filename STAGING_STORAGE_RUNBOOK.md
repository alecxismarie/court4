# Staging persistent-storage runbook

Court4 uses PostgreSQL as metadata authority and local filesystem storage for bytes. Mount a persistent volume at `/app/data`; `/app/data/output` must survive application replacement and restart. Do not place it in a disposable container layer.

## Data that must persist

- original videos under each analysis upload directory;
- frames, calibration results, tracking data, player candidates, annotated outputs;
- analytics JSON, heatmaps, trajectories, movement/Match IQ artifacts and share assets;
- legacy files required by existing database metadata;
- `_uploads` only while uploads are active; stale entries require reviewed cleanup.

`job.json` is not runtime authority. PostgreSQL artifact records and owner relationships are authoritative. Relative paths are normalized beneath the configured root; missing registered files return 404 and unregistered files are not exposed.

## Private staging capacity

Configure 512 MiB maximum per upload for staging (overriding the 1 GiB application
default), at most five allowlisted test users, and an operational limit of three
retained analyses per account. Provision at least a 50 GiB persistent data volume;
keep PostgreSQL, images/build cache, logs, and backups on separately budgeted space.

- The application warns below 10 GiB and rejects before staging an upload when free
  space after reservations would be below 5 GiB.
- Reserve two times the configured maximum upload for source and temporary/artifact
  overhead; allow one active reservation. A second request returns typed 429 and a
  capacity rejection returns typed 507 without leaving a staging directory.
- Permit one active processing request operationally on the single backend.
- Enforce `.mp4,.mov,.avi,.mkv` at the application and ingress; set ingress body limit and timeout consistently with 512 MiB.
- Never delete bytes solely because they are not recognized without a reviewed DB/filesystem reconciliation.

The audited local root contained 9,833 files using 976,901,098 bytes. All 663
registered artifacts matched; 9,131 unregistered/legacy-generated files require an
owner decision before copying or cleanup. See `STORAGE_RECONCILIATION_RUNBOOK.md`.

## Operations

Monitor free bytes, inode/file count, growth rate, largest analyses, `_uploads` age,
failed cleanup warnings, and reconciliation. Completed analyses are retained until an
approved deletion policy exists. Failed-analysis directories and orphan files are
review-only; never infer deletion from absence of metadata.

`python scripts/storage_cleanup.py` is dry-run by default and scopes work only to
expired `_uploads`. Apply mode requires the exact confirmation
`quarantine-expired-court4-uploads`, file and byte caps, and moves entries beneath
`_quarantine/uploads`; it does not delete them. Reconcile and back up before any later
quarantine purge, and record operator, scope, counts, bytes, and disposition.
