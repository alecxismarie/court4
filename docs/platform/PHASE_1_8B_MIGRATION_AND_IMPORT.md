# Phase 1.8B Migration and Import

## Clean migration

Production uses root `alembic.ini` and `app/persistence/alembic`. The spike has
its own `spike/alembic.ini`, is excluded from package discovery, and remains only
as quarantined evidence.

Required release rehearsal:

1. Back up the target database and record its identity.
2. Run `alembic upgrade head` against an empty production-shaped database.
3. Run schema drift comparison and the full production PostgreSQL tests.
4. Run `alembic downgrade base`, then `alembic upgrade head`.
5. Re-run tests and record the exact revision.

Schema migrations never scan or import filesystem records.

## Existing local data inventory

The read-only inventory of `data/output` on 2026-07-30 found:

- 58 top-level directories;
- 39 readable `job.json` records;
- 19 completed/analyzed records classified as valuable;
- 20 incomplete records (10 calibrated, 8 inspected, 2 player-selected);
- 19 non-analysis validation/tool directories;
- zero malformed jobs, duplicate IDs, or missing referenced artifacts among the
  39 readable records;
- approximately 398,430,045 bytes below job directories.

No record contains a reliable owner identity. The inventory therefore did not
import or claim any record.

## Import command

`python -m scripts.legacy_persistence` supports `inventory`, `dry-run`, and
`import`. Dry-run/import require an explicit source, environment, owner UUID, and
owner identity. Import additionally requires
`PICKLEBALL_AI_LEGACY_IMPORT_ENABLED=true`.

The environment argument must exactly match runtime configuration. Import is
idempotent by preserved analysis ID, does not delete or rename source files, does
not infer owners, skips malformed records, and registers checksums for all
artifact bytes except `job.json`. Re-running reports existing IDs separately.

## Rollback and recovery

Before cutover, rollback is application rollback plus database restore; legacy
source remains read-only. After new writes begin, do not downgrade destructively.
Roll the application forward or restore the database and reconcile local orphan
bytes by checksum. Never revive `job.json` as an authority.
