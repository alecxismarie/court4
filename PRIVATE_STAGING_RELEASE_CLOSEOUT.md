# Court4 private staging release closeout

Verified 2026-08-19 in preparation for a restricted HTTPS preview. This task did not
deploy services, alter DNS, configure cloud resources, or send real external email.

## Current verified result

Court4's reviewed source is ready to become the private-staging release checkpoint.
The exact deployable SHA is the commit containing this report and is recorded by the
release handoff after the commit is created. It is not a production tag.

The local backend image build was deliberately not attempted: drive C had 8.24 GiB
free versus the repository's required 20 GiB Docker build reserve. Dockerfile
`--check` and Compose configuration validation pass. Task 2 must build the exact
checkpoint SHA on a builder with adequate capacity; no old image is release proof.

## Baseline and worktree classification

Baseline: branch `main`, HEAD
`864ffc0fa68a0388358b9858b6e394fde212bd25`, tracking `origin/main` at `+0/-0`.
There were no staged changes. The pre-existing modified and untracked work was
reviewed and classified as follows:

- **A — auth/email/session:** `LOCAL_AUTH_EMAIL_CONFIGURATION.md`, auth API/service/
  schemas, authentication/Brevo/settings fixtures and tests, verification UI/tests,
  frontend auth API/client/context and tests, auth Playwright workflows/configuration,
  and auth smoke runners. These changes make delivery wording truthful, isolate test
  email, preserve refresh recovery, clear stale sessions, and support verification
  handoff.
- **B — Phase 1.9A0 evidence foundation:** migration `0007`, stage/calibration/ball
  schemas, persistence models/service, optional-stage repository metadata, ball/stage
  services, streaming frame source, offline feasibility validator, consent/evidence
  documentation, and `tests/test_stage_evidence_foundation.py`. These are isolated,
  internal foundations; they add no ball detection, interaction, event, analytics,
  route, or player-facing output.
- **C — release/configuration:** `.env.example`, `Dockerfile`, `docker-compose.yml`,
  settings, staging configuration, detector provisioning/integrity source and tests,
  `web/package-lock.json`, `web/next-env.d.ts`, and test/build runners. The generated
  Next declaration follows the repository's Next 16 agent rule and contains no local
  values.
- **D — documentation:** README, Brevo/local-auth/staging/current-state/pre-deploy/
  private-alpha reports, consent boundary, detector provenance, and this closeout.
  Historical verdicts remain labeled by date instead of being rewritten.
- **E — generated/runtime:** ignored root `.env`, `web/.env.local`, caches, logs,
  `.next*`, `node_modules`, test artifacts, model bytes, media, output artifacts,
  build output, and database/runtime material. None belongs in the checkpoint.
- **F — unrelated/uncertain:** none remained after review.

## Closeout changes

The disabled Remember Me control and its policy copy were removed. Forgot Password
is right-aligned in the same login row. Authentication duration, refresh rotation,
revocation, cookies, and session restoration are unchanged. A configurable session-
persistence choice remains a future enhancement.

The player model is pinned as
`ultralytics-yolo11n-assets-v8.3.0`, source
`https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt`, size
5,613,764 bytes, SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
The model binary remains ignored. Provisioning downloads only that versioned URL to
a temporary file, validates the digest, and atomically installs it. Ultralytics-
default API startup fails if bytes are missing/invalid, and explicit Ultralytics
analysis verifies again immediately before load. A fresh controlled remote download
and the existing ignored local artifact both matched the pin.

Test-mode settings now omit dotenv as a source when
`PICKLEBALL_AI_ENVIRONMENT=test`; automated tests cannot inherit real root email or
database configuration. Compose keeps the release registration throttle default of
5 while allowing an explicit isolated E2E-only override.

The production dependency advisory was removed by updating only the lockfile's
compatible transitive `nanoid` resolution from 3.3.16 to 3.3.18. No force, override,
Next downgrade, or preview package was used. Current `npm audit --omit=dev` reports
zero vulnerabilities across 26 production dependencies.

## Validation evidence

| Gate | Current result |
|---|---|
| Backend complete suite | PASS — 309 passed, 10 skipped; one Starlette/httpx deprecation warning |
| Quarantined persistence/concurrency spike | PASS separately — 10 passed against `court4_spike` |
| Phase 1.9A0 isolation | PASS — 14 passed |
| Ruff | PASS |
| Ruff format | PASS — 185 files |
| Mypy | PASS — 176 source files |
| Alembic clean rehearsal | PASS — base → `0007_stage_evidence` |
| Alembic rollback/re-upgrade | PASS — head → base → `0007_stage_evidence` |
| Alembic drift check | PASS — no new upgrade operations detected, before and after cycle |
| Frontend unit suite | PASS — 194 passed in 38 files |
| ESLint | PASS |
| TypeScript | PASS |
| Frontend production build | PASS — 22 static/dynamic routes generated with sanitized HTTPS public config |
| Auth/onboarding Playwright | PASS — 11 lifecycle/handoff workflows |
| Login desktop/mobile closeout | PASS — 1280×800 and 375×812, no persistence claim or overflow |
| Production dependency audit | PASS — 0 vulnerabilities |
| Dockerfile static build check | PASS — no warnings |
| Compose config | PASS |
| Current backend image build | DEFERRED — 8.24 GiB free is below the 20 GiB safety reserve |

The ten skips in the aggregate run were the quarantined PostgreSQL spike cases
because `COURT4_SPIKE_DATABASE_URL` was intentionally absent there; they were not
counted as aggregate passes. The same ten cases subsequently passed in a dedicated
run against the isolated `court4_spike` database. Model integrity and provisioning
have dedicated passing tests plus a fresh pinned-download proof.

The backend suite covers upload, exact duplicates, court detection/calibration,
player tracking/candidates/selection, movement analytics, evidence gating, Match IQ,
artifacts, Analysis History, Play History, concurrency, authentication/security, and
owner isolation. No new real-video evaluation was run because ignored footage was
not assumed to have consent for new evaluation. Historical controlled and real-video
evidence remains historical evidence, not a current-source image claim.

`BALL_TRACKING_ENABLED=false` remains the default and staging setting. No public API
invokes the Phase 1.9A0 shadow service, no existing product surface reads optional
ball artifacts, and optional-stage terminal state cannot change parent analysis
completion.

## Remaining staging-only work

1. Provision restricted staging and isolated PostgreSQL.
2. Configure persistent media/model volumes and provision the pinned model.
3. Configure secrets, exact HTTPS origins, registration allowlist, Brevo, DNS/TLS,
   commit/build identifiers, and storage thresholds.
4. Build and deploy the exact checkpoint SHA on a builder meeting the disk reserve.
5. Run migrations and prove health/readiness.
6. Perform separately authorized real Brevo verification/reset through the HTTPS
   origin.
7. Run one consent-cleared controlled real-video smoke, verify backup/restore, and
   approve the friend-facing link.

## Verdict

**CURRENT VERIFIED RESULT — READY FOR PRIVATE STAGING SOURCE CHECKPOINT.**

This is source readiness for Task 2, not public-production approval.
