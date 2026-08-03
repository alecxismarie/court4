# Phase 1.8C.1 validation report

Validation date: 2026-08-03. Verdict: **NOT READY FOR PRIVATE ALPHA**.

## Exact validation evidence

| Area | Command | Result |
|---|---|---|
| Backend lint | `ruff check .` | Pass: `All checks passed!` |
| Backend format | `ruff format --check .` | Pass: 160 files formatted |
| Backend types | `mypy app tests` | Pass: no issues in 142 source files |
| Backend suite | `python -m pytest -q` | Pass: 224 passed, 10 skipped; 230.7 s; one Starlette warning recommending `httpx2` |
| Migrations | `alembic upgrade head`; `alembic downgrade base`; `alembic upgrade head`; `alembic check` | Pass through revisions 0001–0005; no new upgrade operations |
| Frontend unit | `npm.cmd test -- --run` | Pass: 35 files, 157 tests; Vite CJS API deprecation warning |
| Frontend lint | `npm.cmd run lint` | Pass |
| Frontend types | `npm.cmd run typecheck` | Pass |
| Frontend production | `npm.cmd run build` | Pass: Next 16.2.12, 22 pages including `/privacy` and `/terms` |
| Browser | `npm.cmd run e2e` | Pass: 23/23, 48.1 s, one worker; mobile smoke included |
| Production audit | `npm.cmd audit --omit=dev` | **Fail: 3 high** (`next/node_modules/postcss <=8.5.17`, `sharp <0.35.0`) |
| Outdated inventory | `npm.cmd outdated` | Reported optional major upgrades and two patch updates; no newer stable Next listed |
| Docker build | `docker build --tag court4:phase18c1 .` | Final source pass: 719.4 s, 306.56 kB context; final image about 9.26 GB |
| Production-like runtime | isolated `docker run` with production environment, secure cookie, exact HTTPS origin, bootstrap/sink off, registration off, Resend config | Startup pass; `/health` 200, `/ready` 200, OpenAPI has 33 paths and zero internal/development/debug paths; calibration/email-sink/Active Play GET+POST all 404; registration 403 `REGISTRATION_CLOSED` |
| Route regression | `python -m pytest tests/test_release_controls.py -q` within full suite | Production OpenAPI excludes calibration, email-sink and Active Play debug paths; direct routes return 404 |

The final image was rebuilt after the Active Play router split and the production-like route probes were repeated against that exact tag.

## Dependency audit

The app moved from unsupported Next 14.2.35/React 18 to stable Next 16.2.12/React 19.2.8. The current registry still resolves Next 16.2.12 with nested PostCSS 8.4.31 and Sharp 0.34.5. npm identifies three high advisories and offers only a destructive downgrade (`next@9.3.3`) through `--force`; no override, ignore or preview/canary release was used. This is blocking under the explicit zero-high acceptance rule.

## Email evidence

The Resend HTTP adapter preserves the provider-neutral interface. Mock transport tests cover accepted delivery IDs and 429 failure; configuration tests cover production fail-closed behavior. No real key or verified sender domain was available, so sandbox/test-domain delivery, delivered verification/reset links, password/security notifications, invalid live credentials and provider dashboard status were not proven. This is blocking.

## Browser coverage boundary

The suite creates a unique user through real registration, reads only that user's development sink, consumes the real verification token, logs in per test through isolated cookie jars, restores/revokes sessions, and uses the real PostgreSQL auth service. The 23 passing tests cover protected navigation, logout, mobile navigation, upload UI, duplicate/Analyze Again UI behavior, court/player/result/history presentations, manual calibration, profile photo and evidence states. The analysis workflow responses are controlled Playwright API mocks; the suite does not yet execute real video processing, all account-security/recovery actions, cross-owner API/artifact denial, or token expiry as browser workflows. Backend and component tests cover those contracts, but that does not satisfy the requested all-real browser matrix.

## Failure classification

| Failure | Classification | Layer / severity | Resolution |
|---|---|---|---|
| Original 22 tests stopped at login | TEST_FIXTURE_FAILURE | Test auth boundary | Replaced stale unauthenticated assumptions with real register/verify/login fixture |
| Next 16 rejected image URL containing a query string | REAL_FUNCTIONAL_REGRESSION | Frontend / HIGH | Removed the invalid logo query suffix; full build/browser regression passes |
| Parallel workers hit registration/login limits | TEST_FIXTURE_FAILURE | Test isolation | Unique worker users, one worker, test-only higher limits |
| Reused rotated refresh cookie revoked its family | TEST_FIXTURE_FAILURE | Test cookie state | Fresh isolated login context per test |
| Last tests redirected after refresh 429 | ENVIRONMENT_FAILURE | Test configuration | Raised only the disposable test refresh allowance; production default unchanged |
| PostgreSQL initially unhealthy after Docker interruption | ENVIRONMENT_FAILURE | Local operations | Preserved volume and waited for crash recovery/readiness |
| Two backend suites collided on one test DB | ENVIRONMENT_FAILURE | Validation orchestration | Confirmed processes stopped; single isolated rerun passed |
| Court confidence copy assertion no longer matched redesigned UI | TEST_FIXTURE_FAILURE | Browser assertion | Asserted accessible region/heading and visible confidence value |

No unresolved genuine functional regression remains in the covered suite.

## Public-claim classification

Invented usage/recommendation figures and fictional partner/rate/discount claims were `UNSUPPORTED` and removed. QR scanning, automatic recording and every-point analysis were `MISLEADING` for current behavior and replaced by the real upload/review/select/analyze journey. Store, social and partner concepts are `VERIFIED PLANNED`/`CONCEPT` and explicitly labeled coming later. Newsletter collection is visibly unavailable and accepts no email. Legal/support links resolve.

## Git and environment

The inspected Phase 1.8B/C baseline was explicitly staged without environments, databases, media, artifacts, caches, logs or `node_modules`, reviewed, and committed as `bd14ea1`. Generated frontend logs, Playwright results and artifacts are ignored. `web/scripts/capture-landing.mjs` remains an unrelated untracked developer utility and is not staged. No completion tag is created because this gate fails.

Docker root cause, exact cleanup and final measurements are in `DOCKER_DISK_RUNBOOK.md`. Host free space was 11,830,042,624 bytes before and 10,402,066,432 after the final large image/build operations; 53.73 GB was reclaimed inside Docker's WSL disk but the VHD was not compacted.

## Release blockers

1. Three high production dependency findings remain.
2. Real Resend delivery is not validated.
3. The entire required critical browser matrix is not real end-to-end; key analysis paths remain mocked.

Therefore the repository must not be promoted or tagged complete.
