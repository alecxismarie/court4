# Phase 1.8C.1 private-alpha remediation plan

Status date: 2026-08-03. This phase is restricted to the private-alpha release boundary; Phase 1.8D storage and Phase 1.8E deployment work have not started.

| Blocker | Remediation | Evidence | Status |
|---|---|---|---|
| Development/internal routes | Mount calibration readiness, development email inspection, and Active Play debug routers only in development/test; remove the player-facing internal page | Production OpenAPI and direct 404 tests | Closed |
| Open registration | Add explicit global toggle and normalized email allowlist; production requires an explicit fail-closed choice | `tests/test_release_controls.py` plus auth suite | Closed |
| Unsupported/vulnerable frontend | Upgrade Next 14/React 18 to current stable Next 16.2.12/React 19.2.8 and migrate route/config/lint contracts | Build, TypeScript, ESLint and unit tests pass | Partially closed; npm reports 3 high transitive findings with no fixed stable Next release |
| No production email adapter | Add provider-neutral Resend HTTP adapter and production configuration validation | Mocked success/failure/throttle tests | Partially closed; real sandbox/domain delivery is not validated |
| Broken browser authentication | Provision, verify and log in unique test users through the real test API; use isolated per-test login cookies | 23/23 Playwright tests pass | Closed for covered suite; required real analysis/cross-owner browser matrix remains incomplete |
| Misleading public presentation | Remove invented metrics/partners/prices; label stores, social and newsletter states; correct journey | Landing tests and manual source audit | Closed |
| Missing legal routes | Add draft private-alpha Privacy and Terms pages and live links | Legal and landing tests; production build route list | Closed, pending counsel review |
| Docker incident | Inventory first, remove only unused Court4 images, prune dangling build cache, preserve all volumes | 53.73 GB cache reclaimed internally; runbook and successful image build | Closed locally with WSL compaction follow-up |
| Interrupted engineering gate | Repeat static, database, migration, build, runtime and browser checks | `PHASE_1_8C_1_VALIDATION_REPORT.md` | Completed, with blockers above |

The release gate is not complete until the production dependency audit is free of high findings, real provider delivery is evidenced, and the remaining critical browser workflows run without API mocks.
