# Court4 Phase 1.8A: Platform Foundation

Status: approved architecture for implementation planning

Scope: documentation only

Decision date: 2026-07-29

## Outcome

Court4 will become a personal-account sports analytics platform with PostgreSQL as
the durable metadata source of truth, private blob storage behind a provider-neutral
storage interface, and a single owner for every uploaded video and analysis.
Analysis History and Play History remain rebuildable, user-scoped projections over
durable analyses and their evidence records.

This phase does not change application behavior. It defines the contracts for:

- Phase 1.8B: persistence, state transitions, provenance, idempotency, migration;
- Phase 1.8C: email/password authentication, sessions, ownership enforcement;
- Phase 1.8D: private storage, upload lifecycle, retention, deletion, quotas;
- Phase 1.8E: production hardening, deployment, monitoring, and recovery.

## Permanent product boundary

One `User` represents one personal Court4 account. There are no organizations,
workspaces, team tenants, or shared accounts. A source video can depict several
people without granting them ownership. During private alpha, the uploader is the
only owner and analysis subject.

Private-alpha admission is a removable registration policy, not an identity model.
The permanent identity direction is verified email/password, with Google and Apple
as later identity providers.

## Authoritative decisions

1. PostgreSQL owns resource identity, ownership, lifecycle state, provenance, and
   artifact metadata.
2. A logical `Analysis` has one or more immutable `AnalysisRun` records. Reprocessing
   creates a run; it never overwrites prior evidence.
3. `UploadedVideo.owner_user_id` and `Analysis.owner_user_id` are required and must
   match. This invariant is enforced in the service and transaction boundary; a
   composite foreign key is included in the schema.
4. Blob bytes are addressed through `StorageObject`; application paths are not
   durable production identifiers.
5. Histories are computed projections. They are not independently editable tables.
6. Every mutating command accepts an idempotency key. State changes are transactional,
   version-checked, and recorded as append-only events.
7. Managed authentication is preferred, while Court4 retains a provider-neutral local
   user and identity mapping.
8. Consent for required platform terms is separate from optional product/model
   improvement consent.
9. The application filesystem is scratch space only in production.
10. Shared matches, billing, and background queue execution are deferred without
    blocking their future addition.

## Document map

- [Current state](CURRENT_STATE_AUDIT.md)
- [Relational data model](DATA_MODEL.md)
- [Authentication direction](AUTHENTICATION_DIRECTION.md)
- [Authorization matrix](AUTHORIZATION_MATRIX.md)
- [Concurrency and idempotency](CONCURRENCY_AND_IDEMPOTENCY.md)
- [Provenance and reprocessing](PROVENANCE_AND_REPROCESSING.md)
- [Storage, retention, and deletion](STORAGE_AND_DATA_LIFECYCLE.md)
- [Consent and data use](CONSENT_AND_DATA_USE.md)
- [Migration plan](MIGRATION_PLAN.md)
- [API impact assessment](API_IMPACT_ASSESSMENT.md)
- [Deployment architecture](DEPLOYMENT_ARCHITECTURE.md)
- [Security hardening plan](SECURITY_HARDENING_PLAN.md)
- [Implementation roadmap](IMPLEMENTATION_ROADMAP.md)
- [Architecture decisions](../adr/README.md)

## Phase 1.8B entry conditions

Phase 1.8B may start when:

- PostgreSQL hosting and migration tooling are selected;
- the managed-auth integration spike confirms the stable external subject and session
  claims that Phase 1.8C will consume;
- product approves the initial upload/analysis state names;
- product and legal owners are assigned for the consent and retention decisions;
- an export of local development analyses is preserved before migration work.

The unresolved provider and policy choices do not change the core schema. The verdict
is **READY WITH CONDITIONS** for Phase 1.8B.

## Validation record

- 29 Markdown files were created under `docs/` (14 platform files, one ADR index,
  and 14 numbered ADRs), totaling 2,151 lines at validation time.
- Every relative Markdown link target exists.
- Markdown code fences are balanced; trailing whitespace and mojibake checks pass.
- Every explicitly cited repository file and core symbol exists.
- All documented existing route families were verified against the live OpenAPI
  document.
- `git diff --check` passes.
- Application source, API contracts, dependencies, migrations, and runtime
  configuration were not modified. README received only a 13-line roadmap note.
- Full runtime tests were intentionally not rerun after the documentation changes.
  Immediately before this phase, the unchanged baseline passed 165 backend tests,
  backend lint/type checks, 103 frontend tests, 22 browser tests, TypeScript checks,
  and the production frontend build.
- Pre-existing untracked `build/` and `court4.egg-info/` packaging artifacts remain
  untouched and are not Phase 1.8A deliverables.
