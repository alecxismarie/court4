# Phase 1.8B Validation Report

Status: passed on 2026-07-30.

## Environment

- Image: `court4:local`, rebuilt from the current dependency manifest.
- Production-shaped database: PostgreSQL 16.14, isolated `court4_test` database
  on local port 55434.
- Historical spike database: isolated `court4_spike` on local port 55432,
  enabled only for the final no-skip regression run.
- Isolation: read committed.
- Timeouts: lock 5s, statement 10s, idle transaction 15s.

No development/production database or existing `data/output` record was mutated.

## Commands and results

| Validation | Result |
| --- | --- |
| `docker compose config` | Passed |
| `docker compose build api` | Passed; production dependencies installed |
| `docker compose --profile test up -d postgres-test` | Passed; healthy |
| `alembic upgrade head` | Passed from empty |
| `alembic downgrade base` | Passed |
| `alembic upgrade head` | Passed re-upgrade |
| `alembic check` | Passed; no new operations |
| `pytest -q tests/persistence` | 14 passed |
| Production concurrency A-J | 10 passed; 20 actors and 10 repetitions where required |
| `pytest -q` with production and quarantined spike PostgreSQL | 199 passed, 0 skipped |
| `ruff check app tests scripts` | Passed |
| `mypy app scripts` | Passed; 106 source files |
| Uvicorn startup | Passed |
| `GET /health` | 200 `{"status":"ok"}` |
| `GET /ready` | 200 `{"status":"ready","database":"ok"}` |
| Actual legacy `inventory` | Passed; 39 records, no writes |
| Actual legacy `dry-run` | Passed; zero imported |
| Synthetic import/re-run | Passed; preserved source, one resource, repeat reported existing |
| `pg_dump`/`pg_restore` rehearsal | Passed; restored revision `0001_phase_1_8b` |
| Runtime/spike import search | Passed; no `app` import from `spike` |
| Runtime `job.json` search | Passed; references limited to explicit legacy tooling/exclusion |
| `git diff --check` | Passed |

Frontend build/lint/typecheck was not run because existing response shapes were
unchanged. `Idempotency-Key` and `/ready` are additive backend contracts.

## Concurrency evidence

A-J cover same-key/same-payload contention, conflicting fingerprints, competing
run starts, independent owners, replay after a lost response, ordered
valid/invalid transitions, optimistic conflicts, stale recognition/replacement,
bootstrap fail-closed policy, and same-key reuse across owners. High-contention
cases use 20 threads, Sessions, transactions, and simultaneously held distinct
PostgreSQL backend PIDs. No Python lock enforces a domain invariant.

## Migration and recovery evidence

The finalized revision is an explicit immutable Alembic migration and imports no
runtime model metadata. Upgrade, downgrade, re-upgrade, and drift checks passed.
A temporary logical backup restored into a separately named database at the same
revision; the restore database and dump were then removed.

## Legacy evidence

The actual read-only scan found 58 directories: 39 valid records (19 valuable,
20 incomplete) and 19 non-analysis/tool directories. Actual dry-run imported
zero records. No owner was inferred. The synthetic integration test proved
explicit-owner import, duplicate behavior, checksums, and source preservation.

## Performance and warnings

`EXPLAIN` used `ix_analysis_owner_created` for owner history and
`uq_run_one_active` for active-run lookup. The synchronous CV executor remains
the dominant latency; database transactions do not span CV work or file
streaming. History still projects records in application code and should be
measured before larger cohorts.

One non-blocking upstream warning remains: FastAPI/Starlette reports that its
current `httpx` TestClient integration is deprecated in favor of `httpx2`.

## Verdict

All Phase 1.8B cutover gates passed. PostgreSQL is authoritative for production
runtime metadata. Authentication and public deployment remain prohibited until
Phase 1.8C and later gates pass.
