# Court4 MVP v1.0 End-to-End Smoke Test Report

Date: 2026-07-22  
Verdict: PASS with documented limitations

## Summary

The MVP v1.0 workflow completed end to end through the browser: upload, inspection, court recognition, persisted court state after refresh, player tracking, player selection and reselection, analytics generation, refresh/direct URL persistence, invalid upload validation, difficult-video manual fallback, legacy-job compatibility, mobile layout, backend outage, and backend recovery.

No application defects were fixed during this smoke pass. The only fixes made while testing were to the ignored CDP smoke helper under `data/output/mvp-smoke/`.

## Environment

- OS: Microsoft Windows NT 10.0.19045.0
- Docker: Docker version 29.6.1, build 8900f1d
- Backend image: `court4:local`, Python 3.12.13
- Backend URL: `http://127.0.0.1:8000`
- Frontend: Next.js 14.2.35, Node v24.11.0, npm 11.11.0
- Frontend URL: `http://127.0.0.1:3000`
- Browser smoke: Chrome `150.0.7871.181`
- Edge installed: `150.0.4078.83`, not separately executed
- Local Python: unavailable; `python` resolves to the WindowsApps shim and cannot run

## Services Started

Backend:

```powershell
docker run --rm -d -p 8000:8000 -v "${PWD}\data:/app/data" court4:local
```

Frontend:

```powershell
$env:NEXT_PUBLIC_COURT4_API_URL='http://127.0.0.1:8000'; npm.cmd run dev -- --hostname 127.0.0.1 --port 3000
```

Backend outage/recovery used:

```powershell
docker stop b4b50ca7ca7d
docker run --rm -d -p 8000:8000 -v "${PWD}\data:/app/data" court4:local
```

## Test Assets

| Purpose | Asset | Size | Video metadata |
| --- | --- | ---: | --- |
| Happy path | `data/input/phase05_api_smoke_match.avi` | 312,134 bytes | 1.5s, 800x900 |
| Invalid upload | `data/input/phase03_detections.jsonl` | 1,355 bytes | Unsupported upload type |
| Difficult/no-court path | `data/input/sample_validation.avi` | 13,066 bytes | 3.0s, 64x48 |

For player tracking, the smoke generated controlled detections at:

`data/output/e0181ca44566416ba7acc4540f4d106e/uploads/detections.jsonl`

This intentionally used the `controlled-json` tracking backend to avoid depending on local YOLO/model weights during MVP smoke validation.

## Browser Smoke Results

Evidence files:

- Full result: `data/output/mvp-smoke/frontend-smoke-full-result.json`
- Outage result: `data/output/mvp-smoke/frontend-smoke-outage-result.json`
- Recovery result: `data/output/mvp-smoke/frontend-smoke-recovery-result.json`
- Screenshots: `data/output/mvp-smoke/screenshots/`
- Final happy-path analysis: `data/output/e0181ca44566416ba7acc4540f4d106e/`
- Difficult-video analysis: `data/output/5d0c03a719f2408da95d4bdbfc96ee34/`
- Legacy job: `data/output/legacy-smoke-1784690887682/`

| Area | Result |
| --- | --- |
| Dashboard and upload page | Passed |
| Valid video upload and duplicate-click prevention | Passed |
| Inspection and sampled frame display | Passed |
| Court recognition | Passed, persisted `detected` with confidence `0.9799871723242003` |
| Refresh after court recognition | Passed |
| Player tracking | Passed, 2 eligible players |
| Raw track IDs hidden from consumer cards | Passed |
| Player selection and reselection | Passed, selected Player 1 then Player 2 |
| Analytics generation | Passed |
| Analytics metrics match API payload | Passed |
| Analytics placeholder/no fake coaching narrative | Passed |
| Analytics artifact URLs | Passed, heatmap 200 and trajectory 200 |
| Refresh after analytics | Passed |
| Dashboard reopen and direct match/analytics URLs | Passed |
| Mobile 390x844 responsive smoke | Passed, no horizontal overflow |
| Mobile technical details disclosure | Passed |
| Invalid upload type | Passed, remained on upload page with supported-extension message |
| Difficult video fallback | Passed, `failed` court detection and manual calibration CTA |
| Legacy job missing new persisted court fields | Passed, no fake confidence shown and optional fields null |
| Backend outage UI | Passed, friendly unavailable message, retry visible, details collapsed |
| Backend recovery UI | Passed, match and analytics routes loaded after restart |

Full-run event summary: no runtime exceptions, no HTTP response errors, and `blockingErrorCount: 0`. The only full-run request failures were `net::ERR_ABORTED` events from normal browser navigation.

## Timings

Final full run generated at `2026-07-22T03:28:08.588Z`.

| Step | Time |
| --- | ---: |
| Upload + inspection | 498 ms |
| Court recognition | 729 ms |
| Player tracking | 1,534 ms |
| Analytics generation | 2,051 ms |
| Happy-path total | 4,812 ms |
| Difficult upload + court failure | 939 ms |

These timings are for tiny synthetic fixtures and should not be treated as production performance baselines.

## Visual QA

- Court verification image aligns with the synthetic court and labels corners correctly.
- Top-down court view renders and is nonblank.
- Player-selection artifact shows both controlled tracks with expected observation counts and confidence labels.
- Analytics heatmap and trajectory artifacts are nonblank and match the controlled synthetic movement path.
- Desktop workflow pages are readable without overlapping controls.
- Mobile smoke at 390px keeps text inside containers and exposes player technical details.
- Difficult-video fallback clearly presents manual calibration; the screenshot still shows sampled-frame placeholders because the failure state was captured as soon as the fallback appeared.

## Automated Validation

Backend:

```powershell
docker build -t court4:local .
docker run --rm -v "${PWD}:/app" -w /app court4:local python -m pytest
docker run --rm -v "${PWD}:/app" -w /app court4:local python -m ruff check .
docker run --rm -v "${PWD}:/app" -w /app court4:local python -m ruff format --check .
docker run --rm -v "${PWD}:/app" -w /app court4:local python -m mypy app scripts tests
curl.exe -i http://127.0.0.1:8000/health
curl.exe -I http://127.0.0.1:8000/docs
```

Results:

- Docker build passed.
- Pytest passed: 72 passed, 1 existing Starlette/httpx deprecation warning.
- Ruff check passed.
- Ruff format check passed: 64 files already formatted.
- Mypy passed: no issues in 64 source files.
- `/health` returned 200 with `{"status":"ok"}`.
- `/docs` returned 200.

Frontend:

```powershell
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
$env:NEXT_PUBLIC_COURT4_API_URL='http://127.0.0.1:8000'; npm.cmd run build
```

Results:

- Next lint passed with no warnings or errors.
- Typecheck passed.
- Vitest passed: 7 files, 31 tests.
- Production build passed.

E2E framework status:

- `@playwright/test` not installed in `web/node_modules`.
- `playwright` not installed in `web/node_modules`.
- No `playwright` binary in `web/node_modules/.bin`.
- No package scripts for Playwright/Cypress E2E.
- Browser smoke used a custom temporary CDP runner under ignored `data/output/mvp-smoke/`.

## Defects And Fixes

No product-code defects were found or fixed during this smoke pass.

Smoke helper fixes made during testing:

- Fixed CDP startup order.
- Decoded non-string WebSocket message payloads.
- Cleared CDP timeout timers after successful responses.
- Made assertions match current UI copy and CSS-transformed `innerText`.
- Waited for image loading before image assertions.
- Scoped mobile technical-details interaction to the selected player card.
- Wrote mode-specific result files.

These helper changes are in ignored smoke artifacts, not application source.

## Limitations

- Tracking used `controlled-json`; the smoke did not validate a real YOLO/Ultralytics model path.
- Fixtures are synthetic and very small; timings are not representative of real match videos.
- Browser smoke ran in Chrome only. Edge is installed but was not separately executed.
- No configured Playwright/Cypress E2E suite exists in the repo.
- Local Python is unavailable on this machine, so backend validation used Docker.
- Outage-mode request failures are expected `net::ERR_CONNECTION_REFUSED` entries caused by the backend being intentionally stopped.

## Changed Files

Tracked worktree changes present after the smoke:

```text
Dockerfile
README.md
MVP_SMOKE_TEST_REPORT.md
app/schemas/jobs.py
app/services/jobs/workflow.py
tests/test_api_workflow.py
web/app/page.tsx
web/components/analytics-details.test.tsx
web/components/analytics-details.tsx
web/components/job-status.test.tsx
web/components/job-status.tsx
web/components/match-details.test.tsx
web/components/match-details.tsx
web/components/workflow-actions.tsx
web/lib/api/client.ts
web/lib/api/types.ts
web/test/factories.ts
```

Smoke-only artifacts were written under ignored `data/output/`.
