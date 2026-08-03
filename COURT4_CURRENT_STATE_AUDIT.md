# Court4 Current-State Audit

**Audit date:** 2026-08-01
**Repository snapshot:** current working tree based on commit `3d18c56` plus substantial uncommitted Phase 1.8C, landing-page, and profile changes
**Scope:** audit and planning only; no runtime, schema, migration, test, or feature changes
**Method:** direct source, migration, configuration, calibration-data, documentation, and test review plus the validation recorded in Section 12

This document supersedes the conclusions in the root `CURRENT_STATE_AUDIT.md` and `docs/platform/CURRENT_STATE_AUDIT.md`. Those files describe pre-PostgreSQL or pre-authentication states and are now historical evidence, not the current architecture.

## 1. Executive summary

Court4 is a credible local product prototype with a substantially production-shaped metadata and account foundation. A user can register, verify an email in the development flow, log in, recover a password, rotate and revoke sessions, upload a video, progress through calibration and player selection, receive evidence-gated movement analysis, and revisit owner-scoped Analysis History and Play History. PostgreSQL is authoritative for users, sessions, uploaded-video metadata, analyses, runs, artifacts, idempotency, state events, and player selections. The authentication lifecycle, transaction model, duplicate isolation, and evidence-honesty work are the strongest parts of the system.

It is not a production system and is not yet a safe private-alpha system. Uploaded video and artifact bytes remain on one local filesystem; failed and duplicate uploads can leave staging files; there is no retention, user deletion, durable email delivery, real production email adapter, shared rate limiter, worker queue, monitoring, backup policy, or disaster-recovery procedure. The internal calibration endpoint is unauthenticated, Active Play debug mutation is available to any authenticated owner for their own analysis, and registration is open rather than restricted to approved alpha users. The locked Next.js 14.2.35 tree produced four high-severity production audit findings and is on an obsolete release line. The public landing page contains unsupported usage statistics, partner-club offers, automated recording/QR claims, and “every point” analysis claims that do not match runtime behavior.

The intelligence is useful but narrow. Court4 directly observes video metadata, detections, selected-player positions, tracking continuity, and recording/evidence diagnostics. It estimates calibrated player movement, distance, time, zones, and trajectory. It does not observe the ball, shots, serves, rallies, score, outcomes, opponent intent, or tactics. Match IQ v2 generally preserves this boundary and suppresses normal insights when evidence is weak. Active Play remains shadow-only. Play History remains provisional because match format and camera placement are not persisted as comparison dimensions.

The calibration dataset has only two partially reviewed real samples, no fully reviewed sample, no holdout, no reviewed Active Play intervals, no identity/continuity labels, and no outdoor or singles coverage. It is collecting evidence, not validated for private-alpha analytical claims or broad marketing claims.

The shortest safe sequence is a narrow alpha-boundary remediation pass, followed by object storage/data lifecycle, then deployment/worker/operations hardening. Calibration collection should continue in parallel but must not be confused with validation.

## 2. Final current-state verdict

Court4 is a strong development-stage system with several production-shaped foundations, but its current release boundary is not suitable for external private-alpha users. This is not because the core workflow is absent; it is because security exposure, vulnerable dependencies, local media lifecycle, operational fragility, misleading public claims, and a broken authenticated browser-test contract are still unresolved.

Readiness by audience:

| Audience | Assessment | Reason |
|---|---|---|
| Local developer | Ready with limitations | Repeatable app/database setup and broad automated coverage; detector weights and Docker resources remain environment-dependent. |
| Internal technical demo | Ready with limitations | Core controlled workflow is demonstrable on one machine with known videos and an operator. |
| Design-partner review without real uploads | Ready with limitations | Product shape and evidence UX are reviewable if landing claims are qualified and internal routes are not exposed. |
| Controlled private alpha with personal match video | Not ready | Security boundary, email, vulnerable Next.js line, local media lifecycle, deletion/retention, and deployment operations are incomplete. |
| Public beta or production | Not ready | Adds scale, privacy/legal, observability, queueing, abuse, backup, and validation requirements. |
| Google Play-connected product | Not ready | No Android deliverable exists and the backend does not meet public mobile-service operations, privacy, account-deletion, or release-security gates. |

## 3. Completed capabilities

### Product and workflow

- Upload-first analysis with typed upload states, recording preflight, exact duplicate detection, idempotency, and explicit “Analyze Again” behavior in `app/services/jobs/workflow.py`, `app/persistence/service.py`, and `web/components/upload-dropzone.tsx`.
- Court recognition plus manual four-point calibration fallback in `app/cv`, `app/services/jobs/workflow.py`, and `web/components/manual-calibration-workspace.tsx`.
- Player detection, track construction, candidate association, quality evaluation, exclusion/merge review, persistent player selection, and owner-scoped workflow routes.
- Movement analytics covering observed duration, continuity-safe distance, movement pace, zones, trajectory, heatmap, gaps, and fragments in `app/analytics`.
- Evidence-aware Match IQ v2 with explicit confidence dimensions, limitations, measurement-only mode, and unsupported-domain suppression in `app/match_iq` and `web/components/analytics-details.tsx`.
- Analysis History and Play History with persisted records, inclusion explanations, qualified-duration weighting, missing-value preservation, provisional comparison, and legacy redirects.
- Active Play shadow calculation and a deterministic calibration-readiness dashboard, both correctly treated as internal evidence tools in documentation, though route protection is incomplete.

### Accounts and isolation

- Email/password registration and login, Argon2id password hashing, short-lived HS256 access tokens, opaque hashed refresh tokens, rotation, family reuse detection, and session revocation in `app/auth` and `app/api/v1/auth.py`.
- Hashed, expiring, single-use verification and reset tokens with row locking and refresh-session revocation on password reset/change.
- HttpOnly refresh cookie with a narrow path, `SameSite=Lax`, Secure-cookie enforcement in staging/production, and exact-Origin checks on cookie-mutating endpoints.
- Owner scoping across uploads, analyses, runs, artifacts, histories, player selections, and duplicate lookup. Cross-owner resources are hidden as not found.
- Account-scoped browser profile keys prevent one account’s display name/photo from appearing in another account in the same browser. This is implemented in `web/lib/player-profile.ts`, but the profile remains browser-local rather than server-persisted.

### Persistence and integrity

- PostgreSQL models for `User`, `RefreshSession`, `AccountToken`, `UploadedVideo`, `Analysis`, `AnalysisRun`, `AnalysisStateEvent`, `IdempotencyRecord`, `AnalysisArtifact`, and `PlayerSelection` in `app/persistence/models.py`.
- Five reversible Alembic revisions from `0001_phase_1_8b` through `0005_account_security`.
- Separation of logical analysis from attempts/runs, owner-aware foreign keys, run provenance, leases, versions, attempt counts, checksums, unique active-run constraints, and optimistic row versions.
- Transactional idempotency and duplicate handling plus production-concurrency tests for the major race cases.
- PostgreSQL is authoritative for metadata through `app/persistence/runtime.py`; the former filesystem repository is now a compatibility facade rather than the metadata authority.

## 4. Product readiness

| Workflow | Classification | Evidence and limitation |
|---|---|---|
| Register | READY WITH LIMITATIONS | `POST /api/v1/auth/register` creates an account and verification token. It is open registration, not an invite/approved-email private-alpha boundary, and duplicate registration can reveal account existence. |
| Verify email | READY WITH LIMITATIONS | Hashed one-time token flow exists. Development sink works; no production provider adapter or durable outbox exists. |
| Login/logout | READY WITH LIMITATIONS | Access/refresh flow and cookie protections are strong. Already-issued access tokens remain valid for their short lifetime after revocation. |
| Forgot/reset password | READY WITH LIMITATIONS | Generic forgot response, expiring token, password reset, and session revocation are implemented. Delivery has the same production-email limitation. |
| Session management | READY WITH LIMITATIONS | List/revoke/revoke-all UI and API exist. Device labels are user-agent approximations; no security-event history is exposed. |
| First-time onboarding | READY WITH LIMITATIONS | First login collects a display name and shows new-versus-returning copy. Name/photo live only in account-keyed browser storage and do not follow the user to another device. |
| Upload guidance | READY WITH LIMITATIONS | Clear camera, landscape, resolution, stability, and continuous-play guidance is present. Validation is extension/size/MIME plus OpenCV readability, not malware/content scanning. |
| Upload video | READY WITH LIMITATIONS | Verified users can upload one file up to 1 GiB through the API. It is synchronous, local-disk, and lacks resumability, quota, cancellation, and robust cleanup. |
| Duplicate handling | READY WITH LIMITATIONS | Exact SHA-based lookup is owner-scoped and does not leak another owner’s upload. Duplicate and idempotent staging files can be orphaned. |
| Court detection/manual calibration | READY WITH LIMITATIONS | Automatic and manual paths are understandable and tested; real-angle coverage is extremely small. |
| Discover/select player | READY WITH LIMITATIONS | Candidate review, exclusion, merge, and selection exist. Reliability is not validated across diverse real matches and identity continuity labels are absent. |
| Understand observations | READY WITH LIMITATIONS | Results separate recording, calibration, tracking, measurement, and interpretation confidence and expose limitations. Some technical/internal terminology remains. |
| Match IQ | READY WITH LIMITATIONS | Evidence-qualified descriptive movement insights are safe; tactical/coaching conclusions are not supported. |
| Analysis History | READY | Owner-scoped persistence, status, limitations, and links are coherent. Media availability still depends on one filesystem. |
| Play History | READY WITH LIMITATIONS | Missing values are not converted to zero and comparisons are provisional. Comparability lacks persisted match-format/camera dimensions and real-world validation. |
| Share card | READY WITH LIMITATIONS | Browser-generated/downloaded card works for the user. It is not durable server storage or a public share service. |
| Internal calibration UI | INTERNAL ONLY | Hidden from public navigation but its backend readiness endpoint is unauthenticated and therefore not truly internal. |
| Active Play | INTERNAL ONLY | Shadow/debug outputs only; must not affect user metrics. Authenticated owners can currently trigger debug processing on their own records. |
| Account deletion/export | NOT IMPLEMENTED | No user-facing deletion, export, consent, retention, or erasure workflow. |
| Public landing page | UNSAFE | It presents unsupported scale statistics, partner offers, automated court QR recording, every-point analysis, and store-like experiences as current or near-current capabilities. |

New users can complete the account and analysis flow in the intended development environment, but a production user cannot reliably receive email until a provider adapter is implemented. Error handling is generally typed and understandable in the workflow UI, but not all backend failures have player-specific recovery guidance. Mobile layouts are explicitly styled and several mobile evidence views have tests, yet the current browser suite no longer reaches protected content because it does not authenticate.

## 5. Intelligence maturity

### Evidence hierarchy

| Layer | Current capability | Maturity |
|---|---|---|
| Direct observations | Video metadata, decoded frames, court lines/points, person detections, track fragments, selected candidate, timestamps, gaps, recording diagnostics | Useful but detector/calibration dependent |
| Measurements | Estimated court position, observed duration, continuity-safe movement distance/pace, zone occupancy, trajectory/heatmap, fragment/gap counts | Player-safe when evidence gates pass and wording says estimated |
| Evidence quality | Recording suitability, calibration confidence, tracking quality, measurement confidence, interpretation confidence, limitation codes | Strong product design; weak real-data calibration |
| Interpretations | Dominant/largest observed zone and cautious descriptive movement patterns | Narrow and acceptable only behind current gates |
| Recommendations | Review trajectory/heatmap, collect clearer/longer evidence | Safe process guidance, not coaching |
| Coaching claims | Shot selection, tactics, positioning intent, opponent exploitation, outcome advice | Not supported and should remain suppressed |
| Historical trends | Duration-weighted qualified movement and zone comparisons | Provisional; comparability metadata and external validation are incomplete |
| Active Play | Shadow estimates, currently 100% `UNKNOWN` on both calibration samples | Internal only |

Match IQ v2’s defaults correctly state that shots, serves, rallies, ball, opponent, scoring, outcome, tactics, and intent are unavailable. Insufficient evidence suppresses insights. Limited recording, fragmentation/gaps, or too little observed time reduces output to measurement-only. This is a meaningful strength.

The current tracker can support review of estimated movement coverage for selected players under constrained camera conditions. It cannot support “real coaching” in the ordinary sense. Ball tracking is required before the product can credibly reason about shots, serves, rallies, score progression, or shot-context positioning. Rally segmentation is not justified until ball/serve/rally labels and active-play intervals exist at useful scale. Player-tracking and calibration evidence should be expanded before adding those intelligence layers.

No current result should claim improvement, causality, tactical error, or likely future performance. Active Play must remain excluded from player-facing totals. Play History comparisons should remain explicitly provisional and neutral.

**Intelligence maturity:** evidence-aware movement measurement prototype; not a validated coaching system.

## 6. Calibration and dataset readiness

Source: `calibration/manifest.v2.json` and `calibration/calibration-results.json`.

| Dimension | Current state |
|---|---|
| Total samples | 2 |
| Development / validation / holdout | 1 / 1 / 0 |
| Fully reviewed | 0 |
| Partially reviewed | 2 |
| Complete current-schema artifact chains | 0 |
| Legacy-compatible chain | 1 |
| Partial chain | 1 |
| Reviewed Active Play intervals | 0 |
| Reviewed Active Play duration | 0 seconds |
| Stable real-player identity labels | 0 |
| Candidate identity mappings | 0 |
| Tracking continuity intervals | 0 |
| Camera placement | Baseline only |
| Indoor / outdoor | 2 / 0 |
| Doubles / singles / unknown | 1 / 0 / 1 |
| Orientation/resolution | One 640×368 landscape, one 720×1280 vertical |
| Lighting labels | Both not reviewed |
| Stability/distance labels | Not reviewed |
| Active Play result | 100% `UNKNOWN` on both samples |
| False-active / false-idle | Numerically zero only because no reviewed interval denominator exists; not evidence of accuracy |
| Threshold simulations | Two exploratory analyses; validation excluded |
| Unresolved disagreements | 2; both incomplete annotations requiring manual review |

The landscape sample’s artifact chain is legacy-compatible, including older candidate and Match IQ schemas. The vertical sample lacks analytics, timeline, and Match IQ outputs and also contains legacy candidate data. A short-edge threshold experiment showed a regression on the sole development sample. The minimum-tracked-time experiment had no affected development sample and excluded validation; it cannot set policy. Policy review and error budgets are not frozen.

The dataset status is **collecting evidence**. It is insufficient for threshold policy, private-alpha analytical validation, confidence calibration, false-active/false-idle claims, generalization, or broad public claims. Automated test volume does not change that conclusion.

## 7. Platform and security readiness

| Control or issue | Assessment | Release classification |
|---|---|---|
| PostgreSQL metadata authority | Clean current authority with migrations and constraints | ACCEPTABLE AS IS |
| Owner scoping/cross-user denial | Consistently enforced in service/API queries and tested | ACCEPTABLE AS IS |
| Password storage | Argon2id with rehash support | ACCEPTABLE AS IS |
| Access tokens | Short-lived HS256 bearer tokens held in frontend memory | ACCEPTABLE FOR ALPHA; key rotation/issuer/audience policy needed later |
| Refresh rotation/reuse detection | Hashed opaque tokens, family locking and revocation | ACCEPTABLE AS IS |
| Verification/reset/session revocation | Strong single-use and locking model | ACCEPTABLE AS IS |
| CSRF | Exact Origin validation on refresh/logout/password/session cookie actions; `SameSite=Lax` cookie | ACCEPTABLE AS IS for the current split-origin design |
| CORS | Exact configured origins; wildcard rejected; credentialed restricted methods | ACCEPTABLE AS IS if production values are correct |
| Artifact authorization | Owner metadata check precedes local file access | ACCEPTABLE AS IS |
| Duplicate privacy | Checksum lookup is owner-scoped | ACCEPTABLE AS IS |
| Bootstrap safety | Disabled by default and rejected outside development/test | ACCEPTABLE AS IS |
| Registration policy | Open registration; roadmap describes approved-email alpha | BLOCKER FOR PRIVATE ALPHA |
| Internal calibration endpoint | `GET /api/v1/internal/calibration-readiness` has no auth/role guard | BLOCKER FOR PRIVATE ALPHA |
| Active Play debug routes | Any authenticated owner can invoke debug shadow processing for own analysis | BLOCKER FOR PRIVATE ALPHA |
| Authorization roles | No admin/internal role or service identity | BLOCKER FOR PRIVATE ALPHA for internal tools |
| Account enumeration | Registration’s conflict response distinguishes an existing email | BLOCKER FOR PUBLIC BETA |
| Rate limiting | Process-local in-memory limiter only; no upload/analysis/global shared enforcement | BLOCKER FOR PUBLIC BETA; acceptable only behind a strict single-instance alpha gateway |
| Production email | Provider-neutral interface exists, but provider mode intentionally raises because no adapter is installed | BLOCKER FOR PRIVATE ALPHA |
| Email durability | Synchronous send, caught failure, no durable outbox/retry | BLOCKER FOR PUBLIC BETA |
| Secrets | Production validation rejects default access secret and insecure refresh cookie, but Compose uses local static credentials and no secret manager | BLOCKER FOR PUBLIC BETA |
| Frontend dependencies | Locked Next.js 14.2.35; `npm audit --omit=dev` reports 4 high-severity findings and no fix on the installed line | BLOCKER FOR PRIVATE ALPHA |
| Backend dependencies | Broad version ranges and no Python lock; `pip-audit` was unavailable | BLOCKER FOR PUBLIC BETA |
| Container hardening | Runs as root, includes dev/test/detector tooling, no image healthcheck or SBOM/signing/scanning | BLOCKER FOR PUBLIC BETA; BLOCKER FOR GOOGLE PLAY-connected production |
| API docs | FastAPI documentation remains public by default | NON-BLOCKING FOR CONTROLLED ALPHA if network-restricted; otherwise restrict |
| Security audit trail | No account/security event ledger | BLOCKER FOR PUBLIC BETA |
| Account deletion/export | Absent | BLOCKER FOR PRIVATE ALPHA when accepting personal video; BLOCKER FOR GOOGLE PLAY |

The frontend dependency result is independently consistent with Next.js’s current support/security guidance: Next.js 14 is no longer the maintained target and current security releases direct users to supported 15.x or 16.x versions. The repository must upgrade and repeat the full frontend/browser matrix rather than attempting to waive the audit.

Authentication materially improved the platform, but it did not by itself make the public boundary secure.

## 8. Storage and lifecycle readiness

### Current byte locations

- Uploaded source video: local `data/output/...` paths through `LocalStorage` and workflow/repository compatibility code.
- Generated JSON, contact sheets, annotated video, analytics, Match IQ, and calibration artifacts: local analysis directories; metadata/checksums are registered in PostgreSQL.
- Upload staging: `data/output/_uploads/{analysis_id}/source.<ext>`.
- Temporary/test files: system or pytest temporary directories plus workflow staging.
- Share cards: generated and downloaded in the browser, not durably stored server-side.
- Profile photo/name: account-keyed browser `localStorage`, not backend/object storage.
- Legacy outputs: inventory/import tooling exists; legacy files remain a migration/operations concern.

### Lifecycle findings

`AnalysisWorkflowService.create_analysis` writes a staging file before the outer cleanup path. `_cleanup_staging_dir` calls `rmdir()` but does not remove files. Duplicate return, idempotency replay/conflict, empty upload, and some pre-reservation failures can therefore leave source files or directories. There is no orphan sweeper or DB-to-object reconciliation job.

There is no implemented retention policy, quota, erasure workflow, account deletion, consent record, legal hold, backup policy, restore drill, storage encryption policy, signed object access, resumable direct upload, malware scanning, or lifecycle transition. PostgreSQL backup cannot recover missing video/artifact bytes.

Answers to the required storage questions:

- **Container restart:** yes only when the same durable host mount/volume remains attached. An ephemeral production container can lose bytes while PostgreSQL still references them.
- **More than one backend instance:** not reliably. Instances need a shared filesystem and careful placement; otherwise a request can reach an instance without the analysis bytes.
- **Cross-device access:** analyses can be queried from another device when it reaches the same backend/filesystem, but profile name/photo do not follow the account and artifact availability is host-dependent.
- **Reliable deletion:** no. No complete user/data graph erasure process exists.
- **Failed-upload cleanup:** no; concrete staging-orphan paths exist.
- **Highest-priority platform blocker:** object storage plus lifecycle is the largest architectural blocker after the narrow security/product remediation pass.
- **Content deduplication:** owner-scoped exact duplicate detection is sufficient now. Cross-owner physical deduplication should be deferred because it adds privacy, reference-count, erasure, and side-channel complexity.
- **Local storage for alpha:** acceptable only for an operator-controlled, single-host, very small design trial with explicit consent, manual retention/deletion, encrypted durable disk, backup, and no availability promise. The current implementation does not yet supply those operational controls, so it is not acceptable as-is.

**Phase 1.8D readiness:** architecture is ready to begin object-storage work without redesigning the domain model, but Phase 1.8D should start only after the narrow alpha-boundary remediation gate. Its scope must include lifecycle and reconciliation, not merely replacing paths with bucket keys.

## 9. Deployment readiness

### Infrastructure findings

- `Dockerfile` uses `python:3.12-slim`, installs `.[dev,detector]`, copies tests/calibration data, and runs as root.
- `docker-compose.yml` provides API and PostgreSQL plus spike/test profiles, but no frontend service, worker, reverse proxy/TLS, resource limits, restart policy, secrets, backup, or monitoring.
- API startup runs migrations and Uvicorn in one container. Multiple replicas could all attempt migration startup.
- `/health` is unconditional process liveness. `/ready` checks only PostgreSQL; it does not check storage writability/capacity, detector availability, migrations, email provider, or worker capacity.
- Production settings correctly reject the default access secret, insecure refresh cookie, development email sink, and non-HTTPS frontend URL. This is good fail-closed behavior.
- All CPU/video processing is synchronous in API workers. There is no queue, worker isolation, admission control, cancellation, lease recovery loop, per-user quota, or resource-aware scheduler.
- The configured maximum upload is 1 GiB through the application server. No reverse-proxy/body-timeout policy is defined.
- Structured logs, correlation IDs, metrics, traces, alerts, security-event retention, SLOs, dashboards, backup automation, restore drills, rollback procedure, and disaster recovery are absent.

| Environment | Verdict |
|---|---|
| Local development | READY WITH LIMITATIONS |
| Internal single-host demo | READY WITH LIMITATIONS |
| Controlled private alpha | NOT READY until remediation, object lifecycle, and minimum operations gates pass |
| Public beta | NOT READY |
| Public production | NOT READY |
| Google Play-connected backend | NOT READY |

The lack of a worker queue is not necessarily the first remediation item for a tiny single-host design trial, but it becomes a blocker as soon as concurrent real users, large uploads, or availability expectations are introduced. Before public beta, CPU work must move out of request-serving processes.

## 10. Frontend and UX readiness

### Strengths

- Routes cover landing, login/register, verification, recovery/reset, dashboard, upload, analysis workflow, manual calibration, player profile, Analysis History, My Progress, settings, and internal calibration.
- Protected navigation is centralized in `web/components/auth-gate.tsx`; access tokens remain memory-only and refresh is cookie-based.
- Dashboard new/returning copy is driven by account login/onboarding state: new users see “Welcome” plus upload guidance; returning users see “Welcome back” plus report guidance.
- Sidebar no longer exposes the player name above logout. Email is shown only in the account-security context where it is relevant.
- Profile data is keyed by authenticated user ID, preventing browser-local name/photo leakage across accounts.
- Upload instructions are concrete. Evidence UX has good empty, limited, unsuitable, and provisional states. Missing metrics are shown as unavailable rather than zero.
- Core controls use labels, roles, keyboard interaction, focus styles, and mobile layouts. Unit tests cover important accessibility semantics.

### Gaps and misleading content

- `web/lib/landing-content.ts` hardcodes `10K+ Matches Analyzed`, `5K+ Players Improving`, and `95% Would Recommend Court4` without repository evidence.
- The journey says users scan a Court4 QR code, Court4 records automatically, and AI analyzes every point/movement/position. The actual product is manual upload and does not segment points.
- Four named partner clubs, rates, and 20% discounts are presented in a partner-card treatment despite being planned/reference content.
- Store/merchandise and newsletter experiences look actionable before revealing they are planned or not stored.
- Terms and Privacy links are anchors/placeholders rather than substantive legal pages, including in signup consent copy.
- Social links are placeholders. Public claims of “real improvement,” strengths/opportunities, and becoming the best version of one’s game exceed the two-sample evidence base.
- The `/internal/calibration` route is absent from navigation but still build-visible and backed by an unauthenticated API.
- Some text output observed through PowerShell shows mojibake sequences for ellipsis/dot separators; confirm served UTF-8/browser rendering before release.
- The AuthGate introduction invalidated all 22 existing Playwright flows because their fixtures do not establish an authenticated account. This is a test-contract mismatch that hides real browser regressions until repaired.
- Browser console/error smoke could not be completed after the running Docker/API environment became unresponsive; do not infer console cleanliness from unit tests.

**Design-partner readiness:** the authenticated application is ready for guided design review using synthetic/preloaded data. The public landing page and external self-service flow are not ready for unsupervised design partners until claims, legal links, authentication E2E, and internal-route isolation are corrected.

## 11. Architecture quality

### Coherent foundations

- Domain ownership is explicit and carried through composite relationships and service queries.
- `UploadedVideo`, `Analysis`, and `AnalysisRun` have distinct responsibilities: immutable-ish source identity/metadata, logical user analysis, and execution attempt/provenance.
- Idempotency, exact duplicate policy, run leasing/versioning, state events, and artifact metadata are transactionally modeled.
- Account tokens and refresh sessions are separate, hashed, expiring models with appropriate indexes.
- Email composition/delivery has a provider-neutral boundary, making a real adapter possible without rewriting auth services.
- Storage has an interface and safe path-resolution implementation; database models already carry `storage_provider` and keys.

### Debt and boundary problems

- Metadata is PostgreSQL-authoritative while bytes are local-filesystem-authoritative. That split is intentional for transition but operationally unsafe until an object lifecycle/reconciliation layer is complete.
- `app/services/jobs/repository.py` remains a compatibility facade that scans filesystem artifacts and backfills registrations. It should be retired only after Phase 1.8D migration and reconciliation prove stable.
- HTTP request handlers synchronously perform heavy CV work despite run/lease concepts that anticipate background execution.
- Transaction boundaries cannot atomically cover filesystem writes; failure compensation is incomplete.
- Internal/admin authorization is missing even though internal/debug routes exist.
- Browser-local profile and recent-analysis conveniences create device-local secondary state. They are not metadata authority, but product copy should not imply cross-device persistence.
- `spike/` and `tests/spike/` remain in the repository. Runtime import quarantine was historically tested, but the optional spike suite requires a separate URL and was skipped in the current full run.
- Root and platform current-state audits are materially stale and contradict the runtime. Phase 1.8C roadmap text also promises approved-email registration, internal isolation, admin capabilities, and audit events that current code does not implement.
- Proposed data-lifecycle documentation contains consent/deletion/storage-object concepts not present in current models. It is design intent, not shipped behavior.

There is no need to redesign the central domain before object storage. Phase 1.8D should preserve `UploadedVideo`, `Analysis`, `AnalysisRun`, owner scoping, and artifact records while replacing the byte transport/lifecycle and removing compatibility scans gradually.

## 12. Test and validation results

Validation was run on 2026-08-01 against the audited working tree. Backend commands used the current repository bind-mounted into the existing local image and an isolated `postgres-test` database. The attempted image rebuild timed out before producing a new image.

| Check | Result | Notes |
|---|---|---|
| Alembic upgrade → downgrade base → re-upgrade → `alembic check` | PASS | All five revisions cycled on isolated PostgreSQL; “No new upgrade operations detected.” |
| Full backend pytest | PASS | 219 passed, 10 skipped, 1 Starlette/httpx deprecation warning in 228.18s. |
| Optional/skipped backend tests | SKIPPED | Ten `tests/spike` cases require `COURT4_SPIKE_DATABASE_URL`; reported separately. |
| Production concurrency | PASS | Focused `tests/persistence/test_production_concurrency.py`: 12 passed. |
| Authentication, persistence, calibration, workflow | PASS within full suite | Included in the 219-pass run; no separate inflated count claimed. |
| Ruff | NOT COMPLETED | Docker became unresponsive while parallel validation was running. Historical Phase 1.8C report says pass, but that is not credited as a current run. |
| Mypy | NOT COMPLETED | Same environment failure; historical result not credited. |
| Backend dependency consistency | NOT COMPLETED | `pip check` was started in the unresponsive parallel Docker group; no reliable result returned. |
| Backend vulnerability scan | NOT RUN | `pip-audit` is not installed and Python dependencies are not locked. |
| Frontend Vitest | PASS | 34 files, 155 tests passed. Initial attempt collected none due full disk; the valid rerun passed after removing only generated E2E cache. |
| TypeScript | PASS | `tsc --noEmit`. |
| ESLint | PASS | No warnings or errors. |
| Next production build | PASS | Next.js 14.2.35; 22 pages/routes generated. Isolated build output was removed and Next’s automatic `tsconfig` formatting was reverted exactly. |
| Frontend production dependency audit | FAIL | `npm audit --omit=dev`: 4 high-severity vulnerabilities, primarily obsolete Next.js/embedded dependencies; no fix on current installed line. |
| Playwright browser suite | FAIL | 22/22 failed because new AuthGate redirects/blocks older unauthenticated mocked fixtures. This is a browser-test contract failure, not proof that every underlying feature is broken. |
| Live frontend HTTP | PASS | `http://127.0.0.1:3000/` returned HTTP 200 and HTML. |
| Live API `/health` and `/ready` | ENVIRONMENT-BLOCKED/FAIL | Both timed out after Docker engine/disk saturation. Earlier `docker compose ps` showed API up and PostgreSQL healthy, but no successful post-incident probe is claimed. |
| Browser console smoke | NOT COMPLETED | System Chrome launched, but the live page did not reach a stable rendered heading while API/Docker was unresponsive. |
| Critical browser E2E flow | NOT VALIDATED | The current suite cannot cross AuthGate. Backend tests cover register/verify/login/ownership/workflow pieces, and historical reports describe a live auth smoke, but no current full 16-step browser flow passed. |

The first backend run produced 219 setup errors because Compose’s env file set bootstrap auth off and overrode pytest’s `setdefault`. It was invalid runner configuration, not a code result. The suite was rerun with the documented test-only bootstrap identity and then passed. This failed attempt is disclosed to avoid hiding validation uncertainty.

The test estate is broad and valuable, but it currently has two quality gaps: browser fixtures are pre-authentication, and static/backend vulnerability checks are not independently reproducible without Docker and a Python lock/toolchain.

## 13. Private-alpha blockers

1. Protect or remove unauthenticated internal calibration and owner-accessible Active Play debug routes; add an explicit internal/admin authorization boundary.
2. Upgrade off Next.js 14.2.35, resolve the four high-severity production audit findings, and rerun unit, build, browser, and security scans.
3. Replace unsupported landing statistics, partner/store/QR/automatic-recording/every-point claims with truthful current-capability and invitation copy; provide real Terms and Privacy documents.
4. Implement an alpha admission policy (invite/approved email) rather than open public registration.
5. Implement and exercise a production email provider adapter. Define retry/delivery-failure operations at least sufficient for the alpha cohort.
6. Repair authenticated Playwright fixtures and pass the realistic register-through-cross-user-denial flow.
7. Complete object storage and lifecycle for personal video, including failed-upload cleanup, orphan reconciliation, retention, user deletion, and restore behavior—or constrain the first trial to a formally approved single-host exception with equivalent manual controls.
8. Restore reliable local deployment health, successful `/health` and `/ready` probes, and enough disk/resource headroom to run the release gate.
9. Establish explicit participant consent, privacy notice, deletion contact/process, and data-handling boundaries before accepting personal match footage.

## 14. Public-beta blockers

All private-alpha blockers plus:

- Queue/worker isolation, concurrency/admission control, cancellation, retry, and resource limits for CPU-heavy video work.
- Shared/distributed rate limiting for auth, upload, analysis, and abuse; perimeter controls and quotas.
- Durable transactional email outbox/retry and delivery monitoring.
- Account/security audit events, operational audit access, generic registration behavior, and stronger secret/key rotation.
- Object-store backup/versioning policy, PostgreSQL backup automation, restore drills, disaster recovery, rollback, and migration-run coordination.
- Structured logs, correlation IDs, metrics, traces, alerting, SLOs, on-call/runbooks, and log retention.
- Container non-root/minimal production stages, healthcheck, dependency locks, vulnerability scans, SBOM, image provenance/signing, and patch policy.
- Validated calibration/evidence dataset across camera placements, indoor/outdoor, singles/doubles, lighting, orientation, resolution, identities, and continuity.
- Formal legal/privacy/consent/retention/export/deletion policies and support process.
- Accessibility testing beyond component semantics, cross-browser/device matrix, load/soak tests, and failure-injection tests.

## 15. Google Play blockers

All public-beta blockers plus:

- There is no Android application, Android build/signing pipeline, package identity, release track, device compatibility matrix, mobile telemetry/crash reporting, or store listing.
- Google Play Data safety disclosures, privacy-policy URL, in-app and web account deletion, data collection/retention mapping, and reviewer credentials/process are absent.
- Public HTTPS API deployment, mobile token/session threat model, certificate/network policy, backward-compatible API/versioning policy, and staged rollout/rollback are absent.
- Upload behavior must handle mobile networks, backgrounding, retries/resumption, bandwidth/storage constraints, and user cancellation without proxying a fragile 1 GiB synchronous request.
- Security dependency and backend operational gates must be continuously enforced, not one-time audit artifacts.

Google Play work should remain deferred until the web/backend private alpha proves product value and lifecycle/operations are stable.

## 16. Technical debt

- Stale current-state documents conflict with implemented PostgreSQL/auth behavior.
- Dirty working tree contains an entire uncommitted authentication/security/landing tranche, weakening release provenance and rollback clarity.
- Local-filesystem compatibility repository and recursive artifact discovery remain transitional.
- Synchronous CV inside the API process couples latency, memory, CPU, and request availability.
- No Python lock; frontend is pinned by lock but on an obsolete framework line.
- FastAPI/httpx test stack emits a deprecation warning.
- E2E fixtures do not model authenticated state.
- Optional spike suite is separate and skipped by default; spike code remains in-tree.
- Readiness checks only the database, not the full serving path.
- Account-scoped profile state is browser-local and not represented in backend models.
- Match format and camera placement are not persisted for Play History comparison.
- Artifact registration can depend on filesystem scans instead of explicit creation events.

## 17. Product risks

- Marketing credibility risk from fabricated/unsubstantiated scale, recommendation, partner, price, store, and automatic-recording claims.
- Users may interpret calibrated movement estimates as tactical coaching despite evidence copy.
- Failed email delivery can strand registration or recovery with no durable retry.
- Large synchronous uploads and analysis can feel frozen and can exhaust a single server.
- Browser-local player profile surprises users who switch device/browser.
- Provisional Play History can be overread as improvement without comparable conditions.
- Narrow real-video coverage may cause a polished but unreliable first experience for common camera setups.
- No deletion/export journey undermines trust for personal video.

## 18. Security risks

- Public unauthenticated internal calibration data and insufficient internal/debug authorization.
- Four high-severity `npm audit --omit=dev` findings on the production dependency tree; Next.js 14.2.35 is obsolete.
- Open registration conflicts with a controlled-alpha threat model.
- Process-local rate limiting is bypassed by scaling/restart and does not protect expensive workflow endpoints.
- Account enumeration at registration.
- Root/dev-heavy production container and missing supply-chain controls.
- Public API docs and debug-shaped routes expand discovery surface.
- Static symmetric access-token secret without documented rotation/issuer/audience/key versioning.
- No security event ledger, alerting, or incident response evidence.
- Access tokens remain valid until expiry after session revocation; acceptable only with the current short lifetime and explicit documentation.

## 19. Data/privacy risks

- Personal match video, derived trajectories, account identity, and analysis artifacts have no implemented consent/retention/deletion/export policy.
- Local disk and PostgreSQL can diverge; backup/restore does not cover the whole data product.
- Failed/duplicate/idempotent uploads can leave orphaned bytes.
- No documented encryption-at-rest, object access logging, key management, regional residency, or processor/subprocessor mapping.
- No reliable account-wide erasure or artifact reference reconciliation.
- Cross-owner logical isolation is strong, but physical cross-owner deduplication would create unnecessary side-channel/erasure risk and should not be added now.
- Browser-local profile photos can remain after server logout/account actions unless explicitly cleared by the user/browser lifecycle.
- Share exports can disclose personal images/measurements outside Court4; no share-consent guidance exists.

## 20. Recommended next move

### Narrow Phase 1.8C-C — Alpha boundary and truthfulness remediation

**Objective:** close the smallest set of release-boundary defects that would make Phase 1.8D safe to build and validate.

**Why now:** object storage should not carry unauthenticated internal routes, an obsolete vulnerable frontend, open alpha registration, misleading public claims, a missing production email path, and a browser suite that cannot authenticate into the next phase.

**Exact scope:**

- Internal/admin authorization and removal or isolation of debug mutation from public user APIs.
- Invite/approved-email admission for alpha.
- Upgrade Next.js to a supported security release; lock and audit the resulting dependency graph.
- Truthful landing copy and real Terms/Privacy destinations.
- One production email provider adapter plus delivery observability and an alpha recovery procedure.
- Authenticated Playwright fixtures and a passing realistic critical workflow including cross-user denial.
- Fix staging cleanup/orphan behavior that is independent of the object-store implementation.
- Release provenance: commit/review the Phase 1.8C work and update stale current-state documentation.

**Non-goals:** object storage, queue/worker architecture, new analytics, Active Play promotion, ball tracking, rally segmentation, Android/Google Play, public beta, new visual redesign.

**Dependencies:** supported Node/Next migration path, alpha admission decision, email provider credentials/sandbox, internal-role policy, legal copy owner.

**Acceptance criteria:** all private boundary routes require the correct role; alpha registration is restricted; email verification/recovery works through the selected provider; production dependency scan has no unresolved high/critical findings; current unit/static/build/browser gates pass; landing claims map to runtime/evidence; terms/privacy pages exist; duplicate/failed staging leaves no orphan; current-state docs match runtime.

**Risks:** Next major-version migration can change App Router behavior; email deliverability configuration may expose DNS/provider work; internal-role design can become overbuilt. Keep the pass narrow.

**Relative size:** MEDIUM.

## 21. Revised roadmap

| Order | Phase | Objective | Why now | Scope / non-goals | Acceptance signal | Size |
|---|---|---|---|---|---|---|
| 1 | 1.8C-C Alpha boundary remediation | Make the release boundary truthful, protected, supportable, and testable | Current blockers are orthogonal to storage and would contaminate later validation | Scope in Section 20; no new intelligence | Section 23 gate passes | MEDIUM |
| 2 | 1.8D Object storage and data lifecycle | Make video/artifact bytes durable, owner-authorized, reconcilable, retainable, and deletable | Local bytes are the largest remaining architecture blocker | Object provider, direct/resumable transfer as appropriate, explicit artifact creation, cleanup/reconciliation, retention/deletion, migration; no cross-owner dedup | Restart/multi-instance/delete/orphan/restore tests pass | LARGE |
| 3 | 1.8E-A Worker and workload isolation | Move CV out of request-serving processes | Real concurrent uploads otherwise threaten availability | Queue, worker, leases, retry/cancel, admission/resource controls; no new analytics | Failure/retry/concurrency/load gates pass | LARGE |
| 4 | 1.8E-B Deployment and operations | Deploy a recoverable, observable, patched single-region alpha service | Operations must exist before external footage | TLS/origins/secrets, minimal images, migrations, backups/restores, logs/metrics/alerts/runbooks/rollback | Staging release/restore/incident drills pass | LARGE |
| 5 | Controlled evidence-collection alpha | Collect consented diverse videos without broad analytical claims | Dataset is the binding constraint on intelligence | Small invite cohort, calibrated review labels, support loop; no growth marketing | Predefined sample/review/coverage/error budgets met | MEDIUM operational effort |
| 6 | Intelligence policy review | Decide which measurements/interpretations can graduate | Only after sufficient labeled holdout evidence | Thresholds, confidence calibration, Active Play decision; no ball intelligence by default | Frozen policy and holdout results | MEDIUM |
| 7 | Public-beta hardening | Scale, legal, accessibility, abuse, reliability | Only after private-alpha evidence and operations | Public controls and validation | Public-beta gate passes | LARGE |
| 8 | Mobile/Google Play discovery and build | Validate whether native mobile adds value and create a compliant client | Backend and product must be stable first | Android product, network/upload UX, store compliance | Internal/closed Play track passes | LARGE |

Calibration collection should run alongside Phases 1.8C-C through 1.8E using internal or explicitly consented material, but no threshold or marketing claim should graduate early.

## 22. Deferred work

- Ball tracking, shot classification, serve detection, rally segmentation, scoring, outcome inference, tactics, opponent modeling, and coaching recommendations.
- Promotion of Active Play into user metrics.
- Cross-owner physical content deduplication.
- Social/public sharing service, partner marketplace, club QR recording, automatic capture, store/merchandise, and newsletter infrastructure.
- Broad design-system overhaul unrelated to release blockers.
- Multi-region, Kubernetes, microservices, or complex event streaming before demonstrated load.
- Native Android/Google Play implementation before a stable controlled alpha.
- Advanced trend language such as improvement/decline until comparability and holdout evidence exist.
- Public APIs, third-party club integrations, and automated partner billing.

## 23. Exact acceptance gate for the next phase

Phase 1.8C-C is complete, and Phase 1.8D may begin, only when all of the following are evidenced in the repository and a reproducible validation report:

1. Every `/api/v1/internal/*` and debug mutation is absent from the public surface or requires an explicit tested internal/admin authorization policy; ordinary owners receive denial.
2. Private-alpha registration is invite/approved-email restricted, with no cross-account identity or resource disclosure.
3. Production verification, resend, forgot-password, and reset emails pass through a real provider sandbox/staging account; delivery failure is observable and recoverable.
4. Next.js is on a supported release line and production `npm audit` has no unresolved high/critical issue. Python dependencies are locked and a backend vulnerability scan is recorded.
5. Landing, signup, partner, store, statistics, recording, and intelligence copy describe only implemented and evidence-supported capabilities. Real Terms and Privacy pages are linked.
6. Duplicate, empty, oversized, idempotent replay/conflict, reservation failure, and interrupted upload tests prove staging bytes and directories are removed or reconciled.
7. Full backend tests, auth, persistence, 12-case concurrency, calibration, Ruff, Mypy, Alembic cycle/check, frontend tests, TypeScript, ESLint, production build, and browser suite all pass from a clean documented environment.
8. A browser/API critical flow passes: register, verify, login, upload, duplicate, analyze again, court detection, discovery, selection, completion, results, both histories, session management, logout, and cross-user denial.
9. `/health` and strengthened `/ready` pass in the release environment; a failed database/storage/provider dependency produces the intended readiness failure.
10. The working tree is release-reviewed/committed, stale audits are marked historical, and current docs, routes, migrations, tests, and frontend contracts agree.

NOT READY FOR PRIVATE ALPHA

COMPLETE A NARROW REMEDIATION PASS FIRST
