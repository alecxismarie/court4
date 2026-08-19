# Court4 Current-State Audit

> **HISTORICAL RESULT — 2026-08-14.** This document preserves the audit evidence and
> verdict as observed on that date. The current 2026-08-19 verified source result is
> recorded in `PRIVATE_STAGING_RELEASE_CLOSEOUT.md`; do not treat the historical
> "not deployable today" statement below as the post-closeout verdict.

**Audit date:** 2026-08-14
**Scope:** repository, configuration, running local Docker services, safe PostgreSQL inspection, source review, and safe frontend validation. No secrets, production configuration, application data, or Docker resources were changed.

## Executive verdict

Court4 is a capable local/private-alpha candidate with a real account system, PostgreSQL-backed ownership model, local video-analysis pipeline, and a verified healthy local runtime. It is **not deployable today** and is not ready to send to a friend through a real staging URL.

The core distinction is code versus operations:

- Authentication, verified-route gating, account recovery, session controls, upload safeguards, ownership filtering, and a historical real browser-to-CV run are implemented.
- The local API and PostgreSQL service are healthy.
- The release state is not reviewable yet: 31 tracked files are modified and one document is untracked.
- No staging infrastructure, source-provenance image, complete inbox/link proof, object-storage lifecycle, or deployed monitoring/backup system exists.
- The visible Remember Me checkbox is disabled and has no backend session policy. It is not a functional feature.

**DEPLOYABLE NOW: NO.**

## Current truth

### Git and repository

| Item | Current state |
| --- | --- |
| Branch / upstream | `main` / `origin/main` |
| Committed HEAD | `864ffc0fa68a0388358b9858b6e394fde212bd25` (`feat: close phase 1.8d0 deployment blockers`) |
| Ahead / behind | 0 / 0 |
| Worktree | Dirty: 31 modified tracked files, 752 additions and 128 deletions; no staged files |
| Untracked file | `LOCAL_AUTH_EMAIL_CONFIGURATION.md` |
| Whitespace check | `git diff --check` passes |
| Environment files | Root `.env` and `web/.env.local` are ignored; neither is tracked |
| Tracked source | 458 files; generated build/cache/media files are ignored |

The old `web/.env.local` tracking problem is resolved. The current auth/email/Docker/test work is nevertheless not a reviewed release checkpoint.

### Running local services — verified 2026-08-14

| Service | State | Evidence |
| --- | --- | --- |
| `court4-postgres-1` | Running / healthy | Docker healthcheck healthy; port 55433 published |
| `court4-api-1` | Running | Port 8000 published |
| API health | Pass | `GET /health` returned 200 / `{"status":"ok"}` |
| API readiness | Pass | `GET /ready` returned 200 / database and storage `ok` |
| Migration | At head | API Alembic reports `0006_auth_onboarding (head)` |

The API image/container was created about eight days before this audit and has no recorded source provenance. Because the checkout has uncommitted changes, this healthy container must **not** be assumed to run the exact current worktree.

### Safe primary database inspection — verified 2026-08-14

The running database is `court4`, connected as user `court4`, at migration revision `0006_auth_onboarding`.

| Record type | Count |
| --- | ---: |
| Users / verified users | 10 / 2 |
| Refresh sessions / active sessions | 13 / 6 |
| Account tokens | 14 |
| Videos / analyses / runs | 3 / 3 / 3 |
| Artifacts | 663 |
| Analysis-state events | 12 |
| Idempotency records | 3 |

Since the 2026-08-05 closeout, users increased 7→10, sessions 7→13, and tokens 6→14. Videos, analyses, runs, artifacts, events, and idempotency records are unchanged. This is consistent with subsequent account activity rather than media-persistence corruption, but it confirms the primary local database continued to be used after the prior checkpoint.

## Phase status

| Phase | Status | Evidence | Remaining blocker |
| --- | --- | --- | --- |
| 1.8A Platform foundation | COMPLETE | Platform configuration and boundaries exist | None identified |
| 1.8B Persistence | COMPLETE | PostgreSQL models, ownership constraints, duplicate/idempotency logic, migrations through `0006` | Operational deployment work |
| 1.8C Authentication/security | PARTIAL | Account lifecycle and security controls implemented | Functional Keep Me Signed In is absent |
| 1.8D Storage/data lifecycle | NOT STARTED | Local filesystem remains the only media backend | Object storage and retention/deletion lifecycle |
| 1.8D0 closeout | PARTIAL | Historical real video E2E and safeguards documented | Review/checkpoint and operational gates |
| 1.8E Deployment/operations | NOT STARTED | Templates/runbooks only | Staging, source-current image, monitoring, backups |

The active work is an uncommitted post-D0 remediation bundle touching auth, email, configuration, Docker, tests, and frontend verification behavior. It is not a completed deployable phase.

## Capability audit

| Capability | UI | Backend | Real implementation | Current evidence | Status |
| --- | --- | --- | --- | --- | --- |
| Landing, login, signup | Yes | Yes | Yes | Frontend tests/build pass | Ready locally |
| Private-alpha registration | Yes | Yes | Allowlist and explicit registration controls | Source reviewed; no staging config | Code-ready only |
| Email verification / resend | Yes | Yes | Hashed, expiring, single-use tokens; verified gate | Unit coverage and historical provider submissions | Inbox/link unverified |
| Password reset/change | Yes | Yes | Generic reset and session invalidation | Unit coverage and historical provider submissions | Inbox/link unverified |
| Sessions / logout / revoke-all | Yes | Yes | Rotating opaque refresh sessions and reuse detection | Source and frontend tests | Ready locally |
| Keep Me Signed In | Disabled checkbox | No separate policy | No | No two-policy tests | NOT IMPLEMENTED |
| Onboarding display name | Yes | Yes | Server completion; other profile fields browser-local | Frontend tests | Ready with limitation |
| Upload / duplicate detection | Yes | Yes | Size/extension/readability checks, checksum, idempotency, owner scope | Source and historical E2E | Ready locally |
| Processing / CV | Yes | Yes | Synchronous court detection, optional Ultralytics, artifacts | One historical unmocked run | Capacity-limited |
| Match IQ / analytics | Yes | Yes | Evidence-gated measurements/insights | Historical run honestly suppressed unsuitable Match IQ | Ready with limitation |
| Histories / artifacts | Yes | Yes | Owner-scoped persistence/proxied artifacts | Historical cross-user 404 evidence | Ready locally |
| Storage | N/A | Yes | Local filesystem only | `/ready` storage probe passes | Not production-ready |
| Email provider | N/A | Yes | Development, Resend, Brevo adapters | Local Brevo config and historical API 201s | Delivery unverified |
| Deployment / monitoring / backups | N/A | Partial | Runbooks/templates | Nothing provisioned | NOT READY |

## Authentication and email

The code implements registration, private-alpha control, mandatory verification, hashed verification/reset tokens, expiration, single-use consumption, session handoff, login/logout, refresh rotation, replay-family revocation, disabled-account handling, password change/reset, session revocation, owner enforcement, HttpOnly refresh cookies, secure-cookie validation for staging/production, exact configured CORS origins, and focused process-local rate limiting.

Refresh uses one configured policy (30 days by default). Every login receives that persistent-cookie policy. Therefore:

- Checked and unchecked Remember Me behavior does not exist.
- Browser restart preserves every current refresh session until expiry or revocation.
- Expired/revoked sessions fail refresh and require login.
- Cookie/security properties remain in place, but session-choice functionality is absent.

Email is provider-neutral. Local configuration selects Brevo and has local credentials/sender configuration without exposing values. Historical API logs show successful Brevo `201` submissions for verification, resend, password reset, and password-change messages. This proves **provider API submission**, not inbox receipt, sender alignment, rendering, link consumption, or a complete real recovery flow. Those remain release blockers.

## Analysis, storage, and real E2E evidence

Metadata is PostgreSQL-backed; source video and artifacts are stored on the local filesystem. Processing is synchronous, not queue/worker-based. Admission control reserves storage, limits active uploads, returns typed 429/507 errors, and uses owner-scoped exact checksum duplicate detection. Temporary-upload cleanup and manual dry-run/quarantine tools exist.

`REAL_ANALYSIS_E2E_REPORT.md` records the strongest end-to-end evidence: browser upload through a disposable database, court detection, Ultralytics tracking, candidate selection, analytics, artifacts, refresh/relogin, history, and cross-user 404. The 61.2-second sample took about 3.5 minutes on CPU and was correctly marked unsuitable for Match IQ. This is real pipeline evidence, not a current live-staging result.

Object storage, resumable/direct upload, retention, account deletion/export, backup-aware media deletion, and durable orphan reconciliation remain unimplemented. `data/output` contains 9,838 ignored files totaling 976,901,178 bytes. The prior reconciliation recorded 9,131 unregistered files; that exact database-versus-filesystem count is historical rather than reverified in this audit.

## Validation and security

| Check | Result |
| --- | --- |
| Frontend Vitest | PASS — 193 tests in 38 files |
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 22 pages/routes |
| Docker/API health/readiness | PASS |
| Alembic current revision | PASS — `0006_auth_onboarding (head)` |
| Backend tests / Ruff / Mypy | UNVERIFIED this audit — sandbox Python access blocked; PostgreSQL tests destructively reset their isolated database |
| Playwright/browser suite | UNVERIFIED this audit |

The focused source scan found no common hard-coded private-key/API-token patterns outside ignored local configuration. Development/internal routers are included only in development/test. Current `npm audit --omit=dev` reports one high-severity transitive production finding: `nanoid@3.3.16`, through `next@16.3.0` and `postcss@8.5.23` (GHSA-2v37-7h3g-55p8). Resolve or formally risk-accept it before exposure.

## Documentation corrections

| Previous statement | Current truth | Required action |
| --- | --- | --- |
| `web/.env.local` was tracked | It is ignored and not tracked | Mark resolved in historical closeout docs |
| Three high production dependency findings | Current audit reports one high `nanoid` finding | Refresh security-gate evidence |
| 184 frontend tests | 193 currently pass | Update after review/commit |
| Real Brevo had not been submitted | Historical logs show successful provider API submissions | Distinguish submission from inbox/link proof |
| No real CV E2E | One restricted local browser-to-Ultralytics run exists | Keep its staging limitation explicit |

## Private-alpha readiness

**Can a friend sign up and use it? NO today.** There is no real staging URL and email inbox/link evidence is incomplete.

**Can a friend use the real analysis workflow? PARTIAL.** A real local pipeline has completed historically, but it is synchronous, CPU-heavy, dependent on local model/storage configuration, and not proven from a staging URL with a friend's match.

**Can Court4 safely be exposed through a real staging URL? NO.** It needs a reviewed release checkpoint, dependency resolution, source-current hardened image, private HTTPS infrastructure/secrets/backup/monitoring, real email link proof, and a staging smoke test.

## Smallest safe next move

1. Review the 31 changed files, resolve the disabled Remember Me product decision and the `nanoid` finding, run isolated backend/browser validation, and make a reviewed commit.
2. Decide whether legacy `data/output` content is excluded from staging or reconciled/quarantined; do not delete it casually.
3. Provision the smallest private HTTPS staging environment with a source-current image, isolated PostgreSQL, persistent storage, secret manager, backup/restore process, and basic monitoring.
4. Use that environment to prove Brevo inbox receipt/link consumption and one real browser-to-analysis workflow before inviting a friend.

Full Phase 1.8D object storage can remain deferred for a restricted alpha. Security/session correctness, source provenance, real email, ownership validation, backups, and deployment health cannot.

## Confidence

**HIGH** for repository, configuration, frontend validation, current Docker/API health, migration revision, and safe database counts.
**MEDIUM** for operational readiness: current container source provenance is unknown, backend/browser suites were not rerun, no staging infrastructure exists, and inbox/link delivery remains unverified.
