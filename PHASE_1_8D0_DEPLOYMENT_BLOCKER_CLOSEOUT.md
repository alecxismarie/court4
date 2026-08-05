# Court4 Phase 1.8D0 deployment blocker closeout

Date: 2026-08-05

## 1. Executive summary

Database isolation, guarded restore/migration, storage admission controls, and a
true real-video browser analysis are implemented and evidenced. Engineering checks
are green. Deployment remains blocked by real Brevo inbox/link proof, a mixed
unreviewed repository, unresolved orphan/legacy storage disposition, insufficient
host build reserve and no source-current image, and unprovisioned staging services.

## 2. Repository checkpoint status

**OPEN.** Branch `main` at `1a85dca`; no staged files. The worktree contains intended
D0/release source plus unknown landing/brand/auth assets and a developer capture
utility. `web/.env.local` is historically tracked (public localhost values, no
secret) and must be untracked. `git diff --check` passes, but there is no reviewed staged diff or
checkpoint. See `REPOSITORY_RELEASE_CLASSIFICATION.md`. Building is prohibited.

## 3. Database incident root cause

A validation container inherited the root primary URL. Test cleanup trusted an
environment label and truncated primary rows. The unsafe assumptions were inherited
configuration and no live identity assertion immediately before destructive SQL.

## 4. Database guard implementation

**CLOSED.** The guard requires test environment, explicit opt-in, exact expected
host/user, approved exact/prefixed database name, and live DB/user identity. Test
fixtures no longer inherit the root URL. E2E preflights a test-only identity endpoint;
migrations use a guarded wrapper; restores require distinct source/target. Refusal
tests cover all requested negative cases without credential disclosure.

## 5. Backup and restore evidence

**CLOSED.** Fresh dump: 107,125 bytes, SHA-256
`3DC5330D08C40B6DD013FC0FF8CD69F9F1DB37C1A4A9E139DAB80A7CB0E4B167`.
Guarded restore `court4_validation_restore_20260805_d0` reached revision
`0006_auth_onboarding`; counts and `/ready` matched. Primary counts before/after:
users 7, videos 3, analyses 3, runs 3, artifacts 663, events 12, idempotency 3,
selections 0, sessions 7, tokens 6. Only the disposable target was removed.

## 6. Real Brevo delivery evidence

**NOT TESTED — OPEN CRITICAL BLOCKER.** Adapter tests pass and a local key is set, but
no approved real inbox/session was available; frontend URL and deployment allowlist
are not final. No message was sent and no receipt/link/alignment claim is made. See
`BREVO_REAL_DELIVERY_REPORT.md`.

## 7. Real video-analysis E2E evidence

**CLOSED for one conservative CPU job.** The unmocked browser flow processed a
61.2-second, 640x368 sample (SHA-256 `841D992D...EC4FB`) through upload, court
detection, ~195-second tracking, selection, analytics, artifacts, refresh, histories,
relogin, and second-user 404. Analysis `7de6f35d28124d96b2298b3e4b985ec6`
completed with 317 artifacts. Evidence was honestly UNSUITABLE, so Match IQ and Play
History contribution were suppressed. See `REAL_ANALYSIS_E2E_REPORT.md`.

## 8. Storage reconciliation results

**OPEN.** All 663 registered rows were valid: no missing, duplicate, checksum/size,
unsafe-path, availability, or cross-owner issue. There were 9,131 unregistered files
among 9,833 files, 39 legacy `job.json` files, and one empty abandoned upload. They
need reviewed disposition; none were deleted. DB/FS byte totals were
134,180,714/976,901,098.

## 9. Storage capacity and cleanup controls

**CLOSED / ACCEPTED FOR STAGING.** Warning/hard-stop thresholds are 10/5 GiB; upload
reservation is 2x maximum and concurrency is one. Rejections occur before staging
with typed 429/507. Cleanup is manual, dry-run default, exact-confirmation, capped,
`_uploads`-only, and quarantine-not-delete. Tests cover all requested states.

## 10. Host disk and Docker results

**OPEN.** Free space fell from 6,700,752,896 to 3,894,087,680 bytes after real CV
evidence and 2,044,063,744 bytes after final frontend/browser output, below the 5 GiB
runtime stop and 20 GiB build reserve. Docker has 29.78
GB images and 32.78 GB cache (8.922 GB reclaimable). The old image is ~9.26 GB,
root-running, and lacks a healthcheck. No broad prune, volume, or user-data deletion
was performed.

## 11. Current-source image rebuild

**NOT TESTED — OPEN CRITICAL BLOCKER.** Skipped because both prerequisites failed:
reviewed commit and 20 GiB reserve. New-image source/build ID, contents, size/time,
runtime hardening, route exposure, and layer-secret checks cannot be claimed.

## 12. Backend validation

**CLOSED against current source.** Full PostgreSQL suite: 292 pass with one upstream
deprecation warning. Ruff and format pass across 170 files; Mypy passes 130 app/script
files. Guarded Alembic base-to-head, downgrade/base/re-upgrade, and drift check pass
at `0006_auth_onboarding`.

## 13. Frontend and browser validation

**CLOSED for executed gates.** Vitest 184/184; ESLint, TypeScript, and Next 16.3
production build pass (22 pages/routes); production npm audit reports zero. Standard
Playwright passes 29 scenarios with the explicitly gated real test omitted; real E2E
is separately evidenced. Mobile coverage is in the standard suite. No unexpected
post-login console errors were observed. The retained primary local API still returns
200 for `/health` and `/ready`, and the frontend returns 200 on port 3000. Database/
storage failure behavior, allowlist, mandatory verification, and route exposure are
covered by the passing backend/browser suites; the live low-disk path returned 507.

## 14. Staging infrastructure requirements

**DEFINED, NOT PROVISIONED.** One Linux host, 8 vCPU, 16 GiB RAM minimum (24–32
recommended), 100 GiB system disk, 50 GiB app disk, 20 GiB private PostgreSQL, 50 GiB
separate backups, 20 GiB pre-build reserve, TLS 1.2+, inbound 443, outbound Brevo 443,
and one upload/analysis at a time. CPU is supported; GPU optional. See infrastructure
requirements.

## 15. Secrets and configuration readiness

**OPEN.** The safe template covers all required variables. Root `.env`, media, builds,
and newly created local configs are ignored, but `web/.env.local` is historically
tracked and must be untracked at checkpoint. Its values are public localhost config,
not secrets. The configured Brevo/signing secret values were not found in source or
the frontend build. A new image-layer/log scan is impossible until image build. Use
the eventual platform secret manager.

## 16. Monitoring and provenance readiness

**DEFINED, NOT PROVISIONED.** Monitor availability, health/readiness, DB, disk/write,
upload/analysis failures and duration, Brevo failures, 5xx, restarts, backups, and
reconciliation. Record commit/build/environment/migration/pipeline/model/tracker/
configuration fingerprint. Provenance remains placeholder without checkpoint/image.

## 17. Remaining blockers

1. Complete real Brevo verification/resend/reset/security receipt and link use.
2. Review UNKNOWN files, untrack `web/.env.local`, and make a path-scoped checkpoint.
3. Decide keep/import/quarantine for 9,131 unregistered files and rerun reconciliation.
4. Reach 20 GiB free, then build/validate a hardened current-source image.
5. Provision HTTPS/DNS, disks, DB, secrets, backups, monitoring, and provenance; run
   staging smoke and rollback checks.

## 18. Non-blocking follow-ups

Approve legal text/retention policy, compact Docker Desktop's VHD in a maintenance
window if needed, evaluate smaller CPU/GPU images later, and implement full object
storage in Phase 1.8D. None overrides the critical gates.

## 19. Recommended deployment order

Review/checkpoint source; targeted disk maintenance; rebuild/scan; resolve storage;
provision private infrastructure; restore/migrate; mount reconciled bytes; deploy
behind HTTPS; enable allowlist; prove Brevo; run runtime/real-video smoke and rollback;
approve the release gate.

## 20. Final verdict

NOT READY FOR DEPLOYMENT
