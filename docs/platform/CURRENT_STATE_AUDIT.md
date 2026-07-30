# Current-State Architecture Audit

This audit is grounded in application code as of commit `9107e34`. README claims are
used only as supporting context.

## Request and processing flow

`POST /api/v1/analyses` in `app/api/v1/analyses.py::upload_video` passes a multipart
`UploadFile` to `AnalysisWorkflowService.create_analysis`.

`create_analysis` in `app/services/jobs/workflow.py`:

1. generates `uuid4().hex` as `analysis_id`;
2. streams the request in configured chunks to
   `data/output/_uploads/{analysis_id}/source.{ext}`;
3. enforces filename extension, optional MIME type, non-empty input, and the
   `max_upload_size_bytes` ceiling;
4. calls `inspect_video` synchronously while the request remains open;
5. moves the source to `{analysis_id}/uploads/source.{ext}`;
6. writes `{analysis_id}/job.json`;
7. returns a job already in `processing/inspected`, or persists
   `failed/uploaded` when inspection fails.

The upload ID and analysis ID are currently the same concept. There is no distinct
upload record, processing attempt, idempotency key, owner, or request lock.

## Current job and stage model

`app/schemas/jobs.py::AnalysisJob` contains:

- identity: `analysis_id`;
- state: `status`, `current_stage`, five completion booleans, error;
- source path and artifact list;
- court-detection and evidence-readiness snapshots;
- `created_at` and `updated_at`.

Statuses are `pending`, `processing`, `completed`, and `failed`. Stages are
`uploaded`, `inspected`, `calibrated`, `tracked`, `player_selected`, and `analyzed`.
`pending` is defined but upload creation persists directly to `processing` after
inspection. There are no cancel, retry, deletion, lease, attempt, or supersession
states. A failed downstream mutation updates the whole job to `failed`; later
requests are not protected by a formal transition table.

Synchronous mutations are:

- manual calibration and automatic court detection;
- tracking;
- candidate generation, selection, rejection, restoration, merge, and unmerge;
- legacy track selection;
- analytics generation;
- debug Active Play generation.

These operations perform CPU/video work in the API process. There is no queue,
worker claim, lease, timeout recovery, or duplicate-command protection.

## Persistence and paths

`app/services/jobs/repository.py::AnalysisJobRepository` treats
`PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR` (default `data/output`) as the source of truth.
It writes `job.json` directly with `Path.write_text`; it does not use a temporary
file, file lock, compare-and-set, or transaction. `list_job_ids` scans directories
containing `job.json`.

Current layout:

```text
data/output/{analysis_id}/
  job.json
  uploads/source.{ext}
  metadata.json
  frames/frame_*.jpg
  calibrations/{calibration_id}/...
  tracking/tracking.json
  tracking/observations.jsonl
  tracking/tracked_players.mp4
  tracking/player_candidates.json
  tracking/player_candidates/{candidate_id}/...
  analytics/analytics.json
  analytics/match_iq.json
  analytics/*.png
  active_play/active_play.json
  active_play/features.jsonl
  active_play/windows.jsonl
```

Artifacts are discovered by recursively scanning all files except `job.json`.
`AnalysisArtifact` stores relative path, generated API URL, MIME type, and size; it
does not store a durable ID, checksum, creation time, owner, lifecycle status, or
storage version. Artifact retrieval validates the analysis ID and rejects absolute
or parent-relative paths. The model path is separately constrained to the configured
model directory.

Write behavior is inconsistent:

- `job.json`, tracking, selection, analytics, and Match IQ use direct writes;
- candidate collections use a temporary file plus replace in one code path;
- Active Play builds a temporary directory then renames it;
- OpenCV image/video output is written directly.

Concurrent writes can lose updates or expose partial groups of artifacts.

## Reports, versions, and integrity

Existing explicit versions include:

| Concern | Runtime symbol | Current value |
| --- | --- | --- |
| Recording quality | `RECORDING_QUALITY_POLICY_VERSION` | `recording-quality-v1` |
| Movement analytics | `ANALYTICS_SCHEMA_VERSION` | `movement-analytics-v1` |
| Match IQ | `MATCH_IQ_ENGINE_VERSION` | `match-iq-rules-v2` |
| Candidates | `CANDIDATE_SCHEMA_VERSION` | `3` |
| Active Play schema/policy | `ACTIVE_PLAY_SCHEMA_VERSION`, `ACTIVE_PLAY_POLICY_VERSION` | `1`, `active-play-v1` |
| Contribution | `PLAY_HISTORY_POLICY_VERSION` | `play-history-v1` |
| Comparability | `COMPARABILITY_POLICY_VERSION` | `play-history-comparability-v1` |
| Trend/interpretation | `TREND_POLICY_VERSION`, `INTERPRETATION_POLICY_VERSION` | `play-history-trend-v1`, `play-history-interpretation-v1` |
| Grouping/aggregation | `GROUPING_POLICY_VERSION`, `AGGREGATION_POLICY_VERSION` | `play-history-grouping-v1`, `play-history-aggregation-v1` |
| Calibration manifest | `CALIBRATION_MANIFEST_SCHEMA_VERSION` | `2` |
| Readiness | `READINESS_POLICY_VERSION` | `calibration-readiness-v1` |

The calibration subsystem records SHA-256 values for manifests, reports, policies,
and disagreements. Active Play records SHA-256 values for source tracking,
observations, and candidates. The general `AnalysisJob`, source video, tracking,
analytics, Match IQ, and most artifacts do not have a unified provenance envelope.
Detector provenance is a string such as
`ultralytics-bytetrack:{model filename}`, not a content digest.

Timestamps exist on jobs and several reports, but not every stage or artifact.
There is no software commit, build ID, configuration fingerprint, or immutable run
record spanning a completed analysis.

## Histories

`GET /api/v1/analyses` constructs Analysis History through
`HistoryProjectionService.analysis_history`. It calls `list_job_ids`, loads every
job, and combines job, analytics, Match IQ, and readiness artifacts.

`GET /api/v1/play-history` calls `HistoryProjectionService.play_history` over the
same repository. Contribution, comparability, grouping, aggregation, trend, and
interpretation are derived with separately versioned policies. Missing evidence is
not treated as zero, and mixed incompatible versions are not silently combined.

This projection design is correct. Its current flaw is scope: both histories scan
the one shared filesystem because there is no owner.

## API surface

The live OpenAPI document exposes 24 operations:

- public health: `GET /health`;
- analysis list/create, detail, frames, artifact, calibration, court detection,
  tracking, players, candidates, analytics;
- debug Active Play GET/POST nested under an analysis;
- `GET /api/v1/play-history`;
- `GET /api/v1/internal/calibration-readiness`.

There are no server endpoints for retry, cancel, delete, feedback, account, consent,
or admin operations. Frontend “retry” copy means the user may invoke a workflow step
again; it is not a durable retry command.

All operations are unauthenticated. CORS is not authorization: non-browser clients
can call the API, and the browser can use configured local origins.

## Frontend assumptions

`web/lib/api/analyses.ts` uses `XMLHttpRequest` for upload progress and direct
cross-origin fetch/XHR for all resources. `web/lib/api/client.ts` sends no
credentials or authorization header. API responses are validated with Zod.

`NEXT_PUBLIC_COURT4_API_URL` is mandatory. Upload size and extensions are public
build-time configuration. Recent analysis IDs and the player profile, including an
optimized profile image data URL, live in browser `localStorage`; they are not an
account source of truth.

The frontend defaults tracking requests to `ultralytics`, while backend
`Settings.default_tracking_backend` and `.env.example` say `controlled-json`.
The setting is not used to supply the frontend default. This is a documentation/
configuration mismatch.

## Runtime and deployment

`app/main.py` mounts all routers and exposes FastAPI docs by default. CORS permits
local port 3000 origins, GET/POST/OPTIONS, all request headers, and no credentialed
cookies.

Declared backend runtime is Python `>=3.12,<3.13`. `pyproject.toml` allows FastAPI
`>=0.111,<1.0`, NumPy `>=1.26,<3.0`, OpenCV headless `>=4.10,<5.0`,
Pydantic Settings `>=2.3,<3.0`, python-multipart `>=0.0.9,<1.0`, and Uvicorn
`>=0.30,<1.0`; detector extras allow Ultralytics `>=8.3,<9.0` and LAP
`>=0.5.12,<0.6`. There is no Python lock file.

The installed frontend tree observed during the audit contains Next.js `14.2.35`,
React/React DOM `18.3.1`, TanStack Query `5.101.3`, Zod `3.25.76`, TypeScript
`5.9.3`, Vitest `2.1.9`, and Playwright `1.41.2`; `web/package-lock.json` is the
frontend lock. Version ranges in `web/package.json` permit drift on a fresh install.

The local, untracked detector file observed on 2026-07-29 is
`models/yolo11n.pt`, 5,613,764 bytes, SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
That observation is development inventory, not durable model provenance or a
guarantee that another environment has identical weights.

The Docker image:

- installs production, development, and detector extras;
- copies tests and local calibration material;
- runs as root;
- has no image health check;
- has no pinned Python lock file.

Compose defines only the API, publishes port 8000, loads `.env.example`, bind-mounts
`data`, and mounts `models` read-only. It has no frontend, database, private storage,
TLS proxy, secret source, restart policy, resource limits, or backup job.

## Logging and development data

`app/core/logging.py::JsonFormatter` emits timestamp, level, logger, message,
exception, and arbitrary structured context. Workflow logs often include
`analysis_id` and errors. There is no `request_id`, `user_id`, `run_id`,
`idempotency_key`, or redaction policy.

The repository ignores `data/input/*`, `data/output/*`, and `models/*`, but the
working development environment contains extensive real-video-derived artifacts.
Tests use temporary directories and controlled JSON fixtures. Development data must
never be bulk-imported or copied into a production image without an explicit,
reviewed migration manifest.

## Runtime/documentation disagreements

- README accurately states that processing is synchronous and filesystem-backed.
- “Internal” and “debug-only” describe intent, not access control; both route groups
  are publicly mounted.
- `default_tracking_backend` suggests a backend-selected default, but the request
  schema requires a backend and the frontend independently chooses Ultralytics.
- `AnalysisArtifact.url` looks durable but is regenerated from current API base path
  and filesystem path.
- Browser-local recent IDs are no longer the only history source, but browser-local
  player profile remains separate from server histories.

## Correctness and deployment blockers

1. No identity, ownership, or authorization boundary.
2. Non-transactional concurrent filesystem writes.
3. No idempotency or processing-attempt model.
4. Synchronous, unmetered expensive operations and 1 GiB uploads.
5. Local files are the durable source of truth.
6. Internal/debug routes are exposed.
7. Incomplete provenance across pipeline outputs.
8. No deletion, retention, consent, or account lifecycle.
9. Production dependency and container hardening work remains.
