# Approved Platform Implementation Roadmap

## Phase 1.8A — Platform Foundation

Scope: repository audit, permanent personal-account model, schema, auth direction,
authorization, provenance, write safety, storage/lifecycle, migration, deployment,
security plan, and ADRs.

Non-goals: all runtime changes, auth implementation, database, object storage,
workers, deployment.

Acceptance: this document set is coherent, code references exist, and only
documentation changes.

## Phase 1.8B — Persistence and Write Safety

Implementation status (2026-07-30): complete. Clean-schema, concurrency,
import, API/history, backup/restore, and 199-test validation gates passed.
Phase 1.8C is now unblocked but was not started by this phase.

Dependencies: 1.8A decisions; PostgreSQL/migration tooling; auth subject/session
integration spike; retention/consent owners assigned.

Scope:

- PostgreSQL and migrations;
- repository interfaces and transactional implementations;
- durable users (identity-ready), profiles, uploads, analyses, runs, artifact/storage
  metadata, events, idempotency, provenance;
- state-transition and concurrency enforcement;
- current synchronous executor adapted to run records;
- controlled filesystem import, reconciliation, backup and restore.

Non-goals: login UI/credentials, ownership enforcement from a real session, private
object storage, general queue/worker, billing.

Risks: dual source of truth, schema overreach, incorrect legacy inference, long
transactions around video work.

Acceptance:

- DB is authoritative for new metadata;
- parallel command tests prove no duplicate active run/lost update;
- crash/retry scenarios are idempotent;
- every new run/artifact has required provenance/checksum metadata;
- histories rebuild from DB with unchanged evidence semantics;
- migration dry-run is repeatable and rollback documented;
- verified backup restore.

Migrations: expand core schema once, seed policy/version reference data if used, no
production legacy import in schema migration. Rollback: app compatibility window,
database backup, read-only legacy archive.

### Phase 1.8B kickoff: spike cleanup and quarantine

The Phase 1.8B0 migration is executable evidence only and must not enter production
migration history. Generate the production schema and migration lineage cleanly.
Preserve and adapt the validated concurrency tests, but do not leave `spike/` as a
second apparently active persistence layer. Before production persistence becomes
authoritative, delete the provisional code or clearly quarantine it as archived
evidence. When Phase 1.8B is complete, runtime code must not import from `spike/`,
and CI must run the concurrency invariants against production persistence.

- [x] Generate clean production migrations.
- [x] Port validated constraints and transaction patterns.
- [x] Port concurrency regression tests.
- [x] Remove or archive the provisional spike migration.
- [x] Remove or quarantine provisional spike models and services.
- [x] Confirm no production runtime imports from `spike/`.
- [x] Confirm no dual persistence path appears active.
- [x] Confirm the production PostgreSQL test suite passes all spike invariants.

## Phase 1.8C — Authentication and Authorization

### Phase 1.8C.1 private-alpha remediation status (2026-08-03)

The security and product-boundary remediation is implemented: development-only
routers are absent in production, registration is explicitly controlled, the
provider-neutral Resend adapter is present, public claims/legal routes are corrected,
and the covered backend/frontend/browser suites pass. The private-alpha gate remains
closed because the stable Next.js dependency tree has three high production audit
findings, live provider delivery has not been evidenced, and the complete required
real browser matrix is not yet implemented. Do not begin Phase 1.8D or 1.8E as a way
to bypass these gate failures. See the root `PRIVATE_ALPHA_RELEASE_GATE.md` and
`PHASE_1_8C_1_VALIDATION_REPORT.md`.

Dependencies: 1.8B ownership schema; managed-auth spike/provider ADR; email service;
approved account-state and alpha policies.

Scope:

- email/password registration, verification, login/logout, forgot/reset/change
  password, sessions/current user;
- local identity mapping;
- approved-email alpha registration policy;
- owner filters on every player resource/history/artifact;
- account state, admin capabilities, internal/debug isolation;
- security/audit events and authorization test matrix.

Non-goals: Google/Apple implementation, sharing, organizations, subscriptions.

Risks: SSR cookie/token leakage, user enumeration, IDOR, duplicate provider identity.

Acceptance: every matrix cell is tested; unverified users cannot upload; non-owner
gets hiding 404; logout/reset revocation works; no tokens in browser storage/logs;
admin content access is explicit and audited.

Migrations: auth identity/session/token/registration tables or provider mappings.
Rollback: disable registration, preserve users/resources, revoke sessions, retain
provider/local reconciliation.

## Phase 1.8D — Storage and Data Lifecycle

Dependencies: 1.8B storage metadata; 1.8C ownership; selected private storage;
approved retention/consent/deletion rules.

Scope:

- provider-neutral storage implementation;
- direct resumable uploads and completion verification;
- scratch-based processing and private signed/proxied downloads;
- retention, analysis/video/account deletion, orphan/failed upload cleanup;
- consent gates, quotas, storage reconciliation.

Non-goals: general analysis queue, cross-user sharing, model-training pipeline.

Risks: orphaned multipart uploads, DB/object inconsistency, signed URL leakage,
deletion promises that backups cannot meet.

Acceptance: no durable app-filesystem dependency; cross-user storage tests; resumable
large upload; hash verification; idempotent deletion; account purge reconciliation;
restore honors deletion tombstones.

Migrations: storage provider/key/version completion and consent/deletion data.
Rollback: compatibility proxy to old local development storage only outside
production; production object metadata remains authoritative.

## Phase 1.8E — Deployment and Operations

Pre-deployment checkpoint (2026-08-05): **blocked**. Automated backend/frontend gates, PostgreSQL migration/restore, exact-origin controls, secure cookies, private route isolation, and database/storage readiness probes pass. Remaining entry gates are real Brevo delivery/link evidence, a reviewed clean Git checkpoint, a source-current hardened Docker build with adequate disk reserve, local-storage reconciliation/capacity controls, and a real sample-video CV workflow. No deployment or Phase 1.8D object-storage work was started. See `PRE_DEPLOYMENT_READINESS_AUDIT.md` at the repository root.

Dependencies: 1.8B–D; patched dependencies; hosting and incident owners.

Scope:

- production configuration and secrets;
- hardened non-root minimal Docker image;
- health/readiness, resource limits, rate limits;
- logs, metrics, alerts, error tracking;
- CI security/release gates;
- backups, restore verification, deployment/rollback and incident runbooks;
- private-alpha environment and access controls.

Non-goals: Kubernetes, multi-region, automatic GPU fleet, public beta scaling.

Risks: synchronous compute exhaustion, video egress cost, insufficient observability.

Acceptance: clean security scans/audits, capacity limit verified, alerts tested,
restore and rollback drill passed, no internal/debug public route, launch checklist
approved.

Migrations: operational indexes/config only where measured. Rollback: previous
compatible image, forward-compatible schema, documented secret/config rollback.

### Phase 1.8D0 closeout status (2026-08-05)

Database isolation, guarded restore/migration, storage capacity/quarantine controls,
and one unmocked real-video browser workflow are **CLOSED**. Deployment is **NOT
READY**: Brevo inbox/link proof, a reviewed release checkpoint, disposition of
unregistered local files, 20 GiB build reserve and a source-current hardened image,
plus provisioned HTTPS infrastructure/secrets/monitoring are **OPEN**. The full Phase
1.8D object-storage lifecycle remains **DEFERRED**. See
`PHASE_1_8D0_DEPLOYMENT_BLOCKER_CLOSEOUT.md`.

## Private Alpha

Invite wording is avoided: users register with approved emails through the permanent
email/password flow. Alpha work collects real match evidence, validates upload
guidance and resource cost, exercises deletion/privacy/support, and reviews
calibration readiness and user behavior.

Exit requires product/model readiness review, resolved critical privacy/security
issues, observed cost limits, and evidence that account lifecycle works.

## Phase 1.9 — Advanced Match Intelligence

Begins only after private-alpha evidence. It may add evidence-backed intelligence
without bypassing contribution/comparability/version controls. Platform concerns are
not folded into analytics rules.

## Deferred work

Google/Apple identity, subscriptions (Free/Pro/Elite), plan quotas, shared matches,
participant grants, coaching result entities, general background queue/workers,
multi-sport schema extensions, and public-beta scale. Billing later attaches to
`users.id`; no plan logic is hard-coded in Phase 1.8.

## Open decisions and owners

| Decision | Needed by | Owner |
| --- | --- | --- |
| Managed auth/provider and region | 1.8C start | Engineering/security |
| PostgreSQL host and migration tool | 1.8B start | Engineering/operations |
| Retention/deletion values | 1.8D start | Product/legal/security |
| Consent wording and purpose boundaries | Before first alpha upload | Product/legal |
| Source deletion with retained derived results | 1.8D | Product/legal |
| Alpha admin/break-glass policy | 1.8C | Security/operations |
| Hosting/object storage and budget | 1.8D/E | Engineering/operations |
| Model evidence release criteria | Alpha exit | Product/analytics |
