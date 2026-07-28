# Phase 1.7A History Implementation Report

## Verdict

Implemented for private-alpha validation. Analysis History and Play History are
separate routes and backend projections. Play History is governed by
`play-history-v1` and includes evidence-safe progress comparisons.

## Delivered

- `GET /api/v1/analyses?limit=100&offset=0`: bounded, newest-first persisted history.
- `GET /api/v1/play-history?recent_limit=5`: contribution counts, included-only
  observation and measurement totals, safe zone summary, verified Match IQ summaries,
  progress readiness, normalized earlier-versus-recent trend metrics, and play-style
  comparison.
- `/analyses` and `/play-history` player routes.
- `/matches` redirects to `/analyses`; `/performance` redirects to `/play-history`.
  Existing `/matches/{analysisId}` and nested report routes are unchanged.
- Player navigation is Dashboard, Player, Upload Match, Analysis History, Play History,
  and Settings. Active Play and internal calibration remain absent.
- The dashboard uses the history projections and no longer presents unqualified
  cumulative athletic totals.

## Safety and legacy behavior

All persisted job directories remain visible. Invalid legacy metadata is represented
as a legacy, not-evaluated entry. Included-only aggregation deduplicates IDs, preserves
duration context and zone denominators, excludes missing measurements, and never reads
Active Play artifacts.

No source analytics, Match IQ, confidence, recording-quality, calibration, tracking,
reviewer label, or Active Play calculation was changed. Progress comparisons are a
read-only projection over qualified source reports.

## Validation

Final validation completed on 2026-07-28:

- `python -m ruff check .` in the local Python 3.12 Court4 image: pass, 0 errors.
- `python -m ruff format --check .`: pass, 148 files already formatted.
- `python -m mypy app scripts tests`: pass, 0 issues in 113 source files.
- `python -m pytest`: pass, 164 tests; 1 existing Starlette/httpx TestClient
  deprecation warning.
- `npm.cmd run lint`: pass, 0 ESLint warnings or errors.
- `npm.cmd run typecheck`: pass.
- `npm.cmd test`: pass, 21 files and 98 Vitest tests; Vite CJS API deprecation
  warning.
- `npm.cmd run build`: pass; 12 static pages generated.
- `npm.cmd run e2e`: pass, 21 Playwright scenarios. Playwright reported the existing
  `NO_COLOR`/`FORCE_COLOR` notice and a slow-file suggestion.
- TestClient smoke checks: `/health` 200 with `{"status":"ok"}`, `/docs` 200,
  `/openapi.json` 200, and both history API paths present.

Final failures: 0.

## Known limitations

The repository has no authentication, account ownership, database, or cross-device
sync. The backend projection therefore represents the current local filesystem
workspace. Progress comparison requires at least three included reports from the same
source analysis version. Current movement and court-position metrics can describe
changes but cannot verify overall improvement without a validated outcome metric.
