# Private-alpha release gate

Status: **NOT READY** as of 2026-08-03.

| Gate | Result | Release impact |
|---|---|---|
| Repository checkpoint and generated-file exclusions | Pass | Baseline `bd14ea1`; remediation source/test checkpoint `b8ae24e` |
| Docker incident understood and safe cleanup complete | Pass with operational follow-up | Internal cache reclaimed; WSL VHD compaction still pending |
| Production internal/debug route absence | Pass | Calibration, development email, and Active Play debug routes absent and undiscoverable |
| Registration controlled and fail-closed | Pass | Explicit production choice plus allowlist requirement |
| Supported frontend framework | Pass | Stable Next.js 16.2.12 and React 19.2.8 |
| No high production dependency findings | **Fail** | `npm audit --omit=dev` reports 3 high transitive findings |
| Production email adapter exists | Pass | Resend adapter is provider-neutral and fails safely |
| Real provider delivery evidence | **Fail** | No approved API key/test domain was available |
| Backend/static/migration gates | Pass | Ruff, format, Mypy, 224-test suite and Alembic cycle pass |
| Frontend/build/browser covered suite | Pass | 157 unit tests, build, lint, typecheck and 23 Playwright tests pass |
| Entire required real browser workflow matrix | **Fail** | Analysis workflow tests still mock analysis APIs; cross-owner, recovery and several account workflows are verified below browser level, not as real E2E |
| Public claims and legal routes | Pass with counsel follow-up | Claims corrected; draft Privacy and Terms routes work |

Promotion requires: a stable dependency tree with zero high production findings; real Resend verification/reset/security delivery proof from the configured sender domain; and real PostgreSQL/filesystem browser coverage for the outstanding critical workflow matrix with console-error assertions.
