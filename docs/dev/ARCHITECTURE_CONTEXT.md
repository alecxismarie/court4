# Court4 Architecture Context

This document orients a coding agent to the current repository. Code, migrations, tests, git diff, and persisted state outrank this summary when they disagree. Read `AGENTS.md` and `docs/dev/CURRENT_TASK.md` before changing anything.

## System boundary

Court4 is an upload-first, evidence-first sports video analytics system. Pickleball is the supported analysis path. Padel exists as a durable sport identity and an experimental inspection path, with Pickleball interpretation disabled. The normal workflow is request-driven and currently runs through the API service; the repository has queue-ready run/stage records but no general background-worker architecture.

The trusted flow is:

> private video → CV/structured evidence → verified court evidence → deterministic analytics → deterministic Match IQ

Planned semantic Court Vision models, generative AI interpretation, Padel feature parity, subscriptions, Stripe, and Play Billing are not current production behavior.

## Stack

### Backend

- Python 3.12, FastAPI, Pydantic/Pydantic Settings, Uvicorn.
- PostgreSQL through SQLAlchemy 2 and Alembic; Psycopg is the driver.
- OpenCV and NumPy for inspection, calibration, visualization, and deterministic vision utilities.
- Optional Ultralytics YOLO with integrated ByteTrack for person detection/association. A pinned `yolo11n.pt` artifact is checksum-verified when that backend is constructed.
- Boto3 for the S3-compatible storage adapter; a local private-object adapter supports development and tests.
- Pytest, Ruff, and mypy provide backend validation.

### Frontend

- Next.js 16 App Router, React 19, and strict TypeScript.
- TanStack Query for server state and identity-scoped private caches.
- Zod for API payload validation, React Hook Form for forms, Tailwind CSS for styling, and Lucide for icons.
- Vitest/Testing Library for component tests and Playwright for browser flows.
- The browser talks to versioned FastAPI endpoints under `/api/v1`; Next route handlers proxy selected authentication/share operations.

## Durable authority and repository boundary

PostgreSQL is the durable metadata source of truth. It stores users, refresh sessions/account tokens, upload sessions, uploaded-video identity and state, analyses, attempts/runs, optional stage executions, state events, artifact registrations and provenance, calibration verification, player selection, idempotency, consent, and lifecycle records. JSONB payloads retain versioned domain reports/state while relational keys and constraints enforce ownership and lifecycle relationships. Video and artifact bytes do not belong in PostgreSQL.

`AnalysisJobRepository` is the boundary used by workflow services. It combines owner-scoped PostgreSQL operations with the configured private object store and a local processing workspace. Callers should not bypass it to discover artifacts or infer ownership from paths.

Analysis History and Play History/Progress are rebuildable, owner-scoped projections over durable analyses and registered artifacts. They are not independently editable source tables.

## Authentication and ownership

The implemented identity model is email/password with Argon2 hashing, email verification, password reset/change, access tokens, rotating hashed refresh sessions, session listing/revocation, and optional private-alpha registration policy. Verified identity is required for uploads and other protected operations according to endpoint policy.

The current authentication rate limiter is process-local, not a distributed product-wide quota across replicas. Rate limiting remains an architectural and security invariant; any future distributed enforcement must maintain or strengthen the existing protection.

API dependencies resolve the authenticated user before constructing `AnalysisWorkflowService`, `DirectUploadService`, or `HistoryProjectionService` with that user's ID. Persistence queries and composite ownership constraints scope videos, analyses, artifacts, stage executions, selections, uploads, and lifecycle operations to the owner. Cross-owner resources are concealed as unavailable rather than disclosed.

Critical invariant: owner isolation must remain intact from API authorization through database queries, provider keys, workspaces, caches, artifacts, deletion, and history projections. Never trust an analysis ID, object key, or frontend cache key as proof of ownership.

## Object storage and processing workspaces

`app.persistence.object_storage` provides local and S3-compatible private-object adapters. Provider keys are derived from owner and analysis identity, validated against traversal, and registered in PostgreSQL with logical keys, size, checksum, content type, state, and provenance. Artifact reads authorize through PostgreSQL before materializing or returning bytes.

With S3 configured, each repository request creates a unique owner-prefixed directory under `processing_workspace_root`. Required source/artifacts are downloaded into that workspace; generated outputs are checksum-verified and uploaded before PostgreSQL points to them; teardown removes the request workspace on success or failure. Capacity reservations and quarantine-style cleanup protect this bounded scratch space.

Critical invariants:

- The repository-managed workspace is authoritative for S3-backed workflow processing.
- Legacy `/app/data/output` paths must not be reintroduced for S3 workflow writes.
- Production application disk is scratch, not durable authority. Local filesystem persistence is a development adapter and legacy import source.
- Registered exact provider keys, never an untrusted prefix listing, drive deletion.
- A database commit must not advertise an artifact whose durable upload/integrity check failed.

## Direct and resumable uploads

The current scalable upload path reserves an owner-scoped `upload_sessions` row and a single private source key. The API returns short-lived presigned URLs for browser-to-S3 multipart parts. The browser records part ETags, can renew expired part URLs, discover/recover unfinished sessions, reconcile provider parts, resume, complete, or abort.

Completion is server-controlled: provider metadata, declared size, content type, upload identity, and checksum/file identity are validated before the source becomes available and analysis inspection begins. Row versions, idempotency keys, request fingerprints, status transitions, expiry, cleanup records, and exact-duplicate lookup prevent competing finalization or accidental duplicate work. The local storage adapter intentionally does not offer direct multipart upload.

The older API-mediated upload/import code remains part of compatibility and local workflows, but private S3 upload architecture should not be redesigned back into routing large source bytes through FastAPI.

## Analysis and job lifecycle

`analyses` carries owner, sport, current state/stage, a versioned job payload, promoted run, lifecycle state, and optimistic row version. Normal stages are `uploaded → inspected → calibrated → tracked → player_selected → analyzed`, with failure/cancellation represented explicitly. `analysis_runs` add attempt number, source checksum, sport/court/pipeline/policy versions, configuration fingerprint, build provenance, leases, and terminal state. PostgreSQL constraints permit only one active run per analysis.

`analysis_stage_executions` supports independently retryable optional/shadow stages with separate attempt numbers, provenance, inputs/outputs, and state. This mechanism currently backs experimental ball evidence; it does not turn the primary workflow into a worker queue.

Workflow mutations run through media-operation locks plus PostgreSQL row-version checks. Lifecycle state fences reads/writes, and stale job snapshots fail rather than overwriting newer calibration, selection, artifacts, or deletion state.

## Inspection and sampled frames

Pickleball inspection validates the source, reads metadata with OpenCV, assesses upload suitability, and samples frames at a configured interval into the active repository workspace. Metadata and frame artifacts are then registered/durably stored. The frontend lists authorized sampled-frame artifacts for court review and manual calibration.

Sampled frames are evidence candidates, not automatic ground truth. Filenames encode a one-based source frame number. Nominal time can be derived from FPS for constant-rate media, but variable-rate timing needs stronger provenance.

## Court calibration

### Current automatic proposal

`app.services.court_detection.automatic` evaluates sampled images with an HSV/edge mask, morphology, contours, convex hulls, four-point approximation, and a shape/area/solidity score. It chooses the highest-scoring candidate across frames and passes four ordered outer corners into the same Pickleball homography code used by manual calibration. Its confidence measures proposal shape, not semantic alignment to the playable court.

### Manual correction

The user can select an authorized sampled frame and mark near-left, near-right, far-right, and far-left outer court corners. `app.sports.pickleball.calibration` validates image bounds/polygon geometry, builds image↔court homographies against the 20 × 44 ft template, and writes calibration JSON, a projected-line verification overlay, and top-down image into the repository workspace.

### Generated versus verified

A mathematically usable calibration is generated/unverified. Trusted court-based downstream measurements require a human confirmation record bound to the exact calibration ID and SHA-256 checksum. The review UI explicitly warns that recognition confidence does not verify floor alignment.

Saving a correction creates a new calibration ID, retires tracking/analytics/active-play registrations derived from the old mapping, clears verification, and requires a fresh review. Tracking and analytics reject an unverified or mismatched calibration.

Critical invariants:

- Calibration must be checksum-bound and verified before trusted court-based downstream measurements.
- Numerical round-trip/reprojection of the four fitting corners does not prove semantic correctness.
- Stale concurrent saves must not restore a replaced calibration or artifacts. Media-operation exclusion, analysis row versions, active calibration ID, and checksum comparisons enforce this boundary.

### Offline Court Vision work

The working tree contains an unfinished offline-only benchmark foundation: a 12-keypoint/eight-line annotation contract, existing-detector replay, independent point/line errors, accept/abstain/incorrect outcomes, grouping/leakage diagnostics, and deterministic JSON/Markdown reporting. The real manifest is empty, so no real accuracy result exists. This code is under `scripts/`, `calibration/court_vision/`, and focused tests; production detector/workflow code does not import it.

Semantic keypoint models, automatic line validation, multi-frame consensus, model training, and production integration remain planned work.

## Player tracking and identity review

The normal frontend workflow explicitly requests the Ultralytics tracking backend, even though the server default may remain `controlled-json`. When invoked, the Ultralytics adapter loads a checksum-verified YOLO model and uses ByteTrack. API health or readiness alone does not prove that the Ultralytics detector model is provisioned because startup model verification depends on the configured server default; an Ultralytics tracking request verifies the model before use. Controlled JSONL detection is retained for deterministic tests/offline validation. Tracking writes bounded observations incrementally, projects eligible foot points through the verified Pickleball calibration, filters to supported court geometry, produces summaries/previews, and records evidence limitations.

Candidate construction groups compatible raw track fragments with deterministic temporal, court-distance, and bounding-box evidence. Stable candidate IDs preserve lineage. The review flow supports selection, rejection/restore, and persisted manual “Same player” merge/undo. Analytics consume the selected candidate's fragment lineage and do not add artificial movement across unobserved gaps.

Candidate continuity is an identity-within-one-recording aid, not biometric identification or face recognition.

## Analytics and Match IQ

Movement analytics are deterministic and Pickleball-specific. They compute selected-player observed duration, court-position timeline, gap-safe distance/pace, zone occupancy, trajectory, heatmap, and limitations from persisted tracking plus the verified homography. They do not infer ball contacts, rallies, shots, scores, or tactics.

Analysis readiness combines recording, calibration, people/candidate, selected-player, visibility, tracked-time, gap, and fragment signals. Match IQ is currently a versioned deterministic rule engine over persisted movement analytics and readiness evidence. Its gates are `NORMAL`, `CAUTIOUS`, `MEASUREMENT_ONLY`, and `INSUFFICIENT_EVIDENCE`; weak evidence lowers confidence, suppresses interpretation/recommendations, or returns no normal Match IQ. Reports retain metric evidence and limitations.

Generative AI Match IQ is future architecture. It must sit after verified evidence and deterministic analytics rather than becoming an event or geometry authority.

## History and Progress

Analysis History lists all live owner-scoped analyses, including incomplete, limited, unsuitable, failed, and legacy records. Play History applies versioned contribution policy and includes only evidence-qualified analyses; it records excluded, provisional, and not-evaluated states rather than silently dropping uncertainty.

Progress additionally uses versioned comparability, grouping, aggregation, trend, and interpretation policies. Earlier-versus-recent comparisons require enough comparable qualified evidence. Match IQ summaries exposed through History require generated reports with acceptable gates and verified calibration. Pending/deleted matches do not contribute.

History/Progress correctness depends on coverage across the full source. A report based on a partial observation window must not be represented as whole-video evidence.

## Data deletion

Media-only deletion removes the source video and retained playback-style video while preserving the completed structured report and required images/JSON, checksum duplicate identity, calibration/review evidence, and Progress contribution. It is intended for completed Pickleball analysis or completed Padel inspection where the report can remain useful without source media.

Whole-match deletion is a separate owner-scoped lifecycle. It first commits `deletion_pending`, excludes the match from normal access and History/Progress, uses registered exact artifact/source keys as a durable retry manifest, performs provider/local cleanup, then removes relational analysis content in dependency order while retaining minimal tombstone/control records needed to prevent resurrection and support idempotency. Partial provider failure remains retryable and is not reported as success.

Critical invariant: stale workflow/idempotency writes must not republish a deleted match or its artifacts.

## Sport isolation

`app.sports.config` marks Pickleball supported and Padel experimental. Padel currently disables automatic/manual court calibration, movement analytics, Match IQ, and Play History contribution. Its geometry is defined separately in metres and includes service-line/wall semantics that cannot be mapped onto Pickleball kitchen/transition rules.

Critical invariant: shared storage, video, tracking, and provenance infrastructure must not inject Pickleball geometry, zones, thresholds, rules, or conclusions into Padel.

Padel court calibration, reflection/wall handling, candidate validation, analytics, Match IQ, History, and Progress parity are future work.

## Experimental ball evidence

`app.services.ball_tracking` contains an internal, optional shadow stage with a deterministic OpenCV yellow/lime color-and-motion detector and a bounded temporal tracker. Attempts and artifacts are independently versioned under `ball/attempt-NNNN/`; outputs distinguish observed/interpolated/missing evidence and exclude contact, bounce, shot, rally, score, and coaching claims.

The stage is not scheduled by the primary workflow, has no player-facing API/UI, and is not consumed by trusted movement analytics, Match IQ, History, or Progress. Court projection is optional and allowed only with the exact verified calibration, where it remains an approximate plane projection rather than a 3D ball trajectory.

Critical invariants:

- `BALL_TRACKING_ENABLED=false` remains unchanged unless explicitly authorized.
- Experimental ball tracking must remain isolated from trusted analytics until representative validation supports integration.
- Existing private-alpha media is not automatically eligible for model evaluation or training; purpose-specific consent/provenance is required.

## Deployment and staging boundary

The repository contains Docker images/Compose services, health checks, Alembic migrations, strict staging/production setting validation, private S3 support, PostgreSQL configuration, and deployment guidance for a separate web service, API service, database, and private object store. Production-like environments require exact credentialed CORS/CSRF origins, secure refresh cookies, non-development secrets/email delivery, and HTTPS S3 endpoints.

Railway is the documented deployment target in platform guides, but repository code cannot prove current live service topology, variables, migrations, bucket lifecycle rules, backups, or staging validation. Treat those as external operational state and verify them directly before a release. Never change Railway variables or volumes without explicit authorization.

## Change checklist

Before implementation:

1. Read `AGENTS.md`, `docs/dev/CURRENT_TASK.md`, relevant platform docs, git status, and the current diff.
2. Identify whether the change touches ownership, lifecycle, persistence, storage, calibration verification, sport gates, or evidence claims.
3. Preserve repository-managed workspace use and registered artifact provenance.
4. Keep experimental/future features from being described or wired as trusted production behavior.
5. Run focused tests first; broaden only when touched scope justifies it.
6. Do not stage, commit, push, deploy, train models, change Railway state, or enable ball tracking unless explicitly requested.
