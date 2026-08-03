# Court4

Court4 is an upload-first pickleball performance analytics platform. Players will eventually upload a recorded match, confirm the court, select which tracked player they are, and receive movement and positioning analytics.

The MVP is pickleball-only. The code keeps generic video utilities and detector adapters separate from pickleball court geometry, but it does not implement a multi-sport plugin framework.

## Current Scope

Phase 0.1 established the foundation:

- FastAPI with `GET /health`
- Pydantic Settings
- Structured JSON logging
- OpenCV video inspection
- Metadata extraction
- Sampled-frame generation
- JSON reports
- pytest, Ruff, mypy, Docker, and Makefile tooling

Phase 0.2 added manual court calibration:

- Regulation pickleball court geometry in feet
- Manual four-corner calibration
- Image-to-court and court-to-image homographies
- Calibration JSON reports
- Verification overlays
- Normalized top-down court image

Phase 0.3 added local player tracking:

- Person tracking backend interface
- Optional Ultralytics YOLO plus ByteTrack backend
- Controlled JSONL backend for offline tests and validation
- Court filtering from calibrated homography
- Incremental observation JSONL writing
- Track summaries and eligibility rules
- Player-selection contact sheet
- Annotated tracking video
- Manual selection of one eligible track ID

Phase 0.4 adds foundational selected-player movement analytics:

- Total distance travelled in feet and meters
- Average movement per second
- Court-position timeline JSON
- Top-down trajectory PNG with start and end markers
- Top-down heatmap PNG
- Kitchen, transition-zone, and baseline-area occupancy
- Factual movement summary JSON

Phase 0.5 adds the first backend analysis API:

- Versioned REST endpoints under `/api/v1`
- Multipart video upload with synchronous inspection
- Filesystem-backed `job.json` state
- Sampled-frame and artifact retrieval
- API court calibration, controlled/optional detector tracking, player selection, and analytics generation
- Structured expected API errors

Phase 1.0A adds the frontend foundation and upload workflow:

- Next.js App Router frontend in `web/`
- TypeScript strict mode, Tailwind, TanStack Query, React Hook Form, Zod, and Lucide
- Dashboard, upload, recent matches, match details, and calibration placeholder routes
- Typed browser API client for analysis creation, job retrieval, sampled frames, and artifact URLs
- Upload progress, upload validation, normalized API errors, local recent-analysis storage, loading states, and empty states
- Backend CORS configuration for local frontend development

Phase 1.0B adds automatic court detection and the first end-to-end frontend workflow:

- OpenCV-based court-line inspection across sampled frames
- Automatic outer-corner estimation with `detected`, `low_confidence`, and `failed` outcomes
- Automatic calibration artifact generation when confidence is high enough
- Manual calibration requirement state when automatic detection is uncertain or fails
- Match-details actions for court detection, tracking, player selection, and analytics generation
- Player-selection artifact display with eligible track selection
- Simple analytics result page with factual metrics, trajectory, and heatmap artifacts

Phase 1.1 adds deterministic Match IQ:

- Rule-based Match IQ engine under `app/services/match_iq`
- Evidence-backed movement insights generated only from existing analytics metrics
- Persisted `analytics/match_iq.json` saved alongside analytics output
- Backward-compatible analytics responses where legacy analyses can return `match_iq: null`
- Frontend Match IQ summary, insight cards, focus area, limitations, and rule evidence

Phase 1.2 adds shareable performance cards:

- Instagram Story, Instagram/Facebook portrait, and square formats
- PNG export from persisted analytics and Match IQ data
- Native device sharing when the browser supports it
- Optional heatmap or trajectory artifact and optional results link
- No direct Facebook or Instagram posting integration

Phase 1.3 adds a player-centered workspace:

- Primary navigation for Dashboard, Player, Upload Match, Analysis History, Play History, and Settings
- Returning-player dashboard with latest Match IQ, factual activity totals, and recent matches
- Evidence-aware progress snapshot with explicit qualified-report and duration context
- Browser-local Player profile used for dashboard greeting and share-card defaults
- State-aware matches list with human-readable statuses and available actions only
- Mobile navigation that keeps all primary routes reachable

Phase 1.7A separates persisted recording history from evidence-qualified player
history:

- `/analyses` shows every persisted analysis, including processing, limited,
  unsuitable, failed, incomplete, and legacy results
- `/play-history` uses only analyses included by versioned `play-history-v1`
- Read-only `GET /api/v1/analyses` and `GET /api/v1/play-history` projections
- Included-only observation and movement totals with explicit duration denominators
- Honest provisional, excluded, not-evaluated, and insufficient-history states
- Player-facing observed-change evaluation and earlier-versus-recent graphs built only
  from comparable, qualified reports
- Separate versioned contribution, comparability, trend, interpretation, grouping, and
  aggregation decisions
- Safe redirects from `/matches` to `/analyses` and `/performance` to `/play-history`
- No rankings, unsupported coaching claims, Active Play data, or changed source analytics

Phase 1.8 defines the personal-account platform foundation before shared deployment:

- PostgreSQL-backed users, ownership, analyses, processing attempts, provenance, and
  artifact metadata are designed in `docs/platform/`
- Email/password is the permanent first authentication model; Google and Apple are
  future-compatible providers
- Private-alpha access is a temporary approved-registration policy, not invite-token
  or magic-link-only identity
- Phase 1.8B–1.8E implement persistence, authentication/authorization, private
  storage/data lifecycle, and deployment operations in that order
- Private-alpha evidence collection and readiness review precede Phase 1.9 advanced
  match intelligence

Phase 1.8C-B adds provider-neutral account security:

- opaque, hashed, single-use email-verification and password-reset tokens;
- verification enforcement for uploads and Analyze Again;
- safe forgot/reset and authenticated password-change flows;
- active-session listing, individual revocation, and revoke-all controls;
- Court4-owned email templates with a development-only inspectable sink.

See
[Phase 1.8C-B account security](docs/platform/PHASE_1_8C_B_ACCOUNT_SECURITY.md).
Implementation validation is recorded in
[the Phase 1.8C-B validation report](docs/platform/PHASE_1_8C_B_VALIDATION_REPORT.md).

Exact duplicate upload hardening detects byte-identical videos within the current
owner's history, returns a typed duplicate response, and lets the user open the
existing analysis or explicitly analyze the video again. See
[Exact Duplicate Video Detection](docs/platform/EXACT_DUPLICATE_VIDEO_DETECTION.md).

Phase 1.3A hardens real-video workflow reliability:

- Interactive frontend manual calibration for automatic court-detection fallback
- Canonical `COURT4_DETECTOR_MODEL_PATH` support with Docker Compose model mounting
- Typed missing-model errors for the Ultralytics path
- CLI/API Match IQ persistence parity
- Maintained Playwright browser smoke tests for happy path, manual calibration, and missing-model recovery
- Local real-video YOLO validation remains CPU-only and limited by generic person tracking quality

Phase 1.3B adds real-video track continuity and candidate review:

- Deterministic player candidates built from one or more raw track fragments
- Stable candidate IDs, quality labels, warnings, and early/middle/late previews
- Candidate selection, rejection/restore, manual merge/undo, and persisted review state
- Candidate-based analytics with fragment lineage and no artificial gap jumps
- Recording-suitability guidance, including a recoverable vertical-video path
- Ranked visual player cards; raw track IDs are confined to technical details

Phase 1.6A.1 adds an internal calibration-readiness surface:

- Read-only `GET /api/v1/internal/calibration-readiness` summary over persisted
  manifests, reports, integrity hashes, and governance settings
- Development-only `/internal/calibration` dashboard, deliberately absent from
  player navigation
- Versioned engineering governance verdicts with explicit blockers, warnings,
  satisfied criteria, and recommended evidence-collection actions
- Typed missing, invalid, and stale source states
- Active Play shadow-review coverage that reports unreviewed denominators as
  `NOT_REVIEWED`, never as a zero-error result
- No inference, annotation, policy mutation, threshold approval, or player-facing
  analytics changes

See `CALIBRATION_READINESS_DASHBOARD_DESIGN.md`,
`CALIBRATION_READINESS_POLICY.md`, and `PHASE_1_6A_1_REPORT.md`.

The Evidence UX polish pass refines the player-facing analytics page without changing
analytics or evidence policy:

- Video Quality → Observation Coverage → Movement Measurements → Evidence
  Confidence → Movement Insight → Observed Court Position → Movement Maps →
  Limitations and Video Guidance
- Plain-language video failures and recovery guidance with internal reason codes
  kept out of the player view
- Coverage derived only from persisted video and reliable-observation durations,
  with explicit unavailable and legacy states
- Separate, connected Video, Tracking, Measurement, Interpretation, and
  Recommendation confidence stages
- Measurement-only map labels, clear trajectory marker legends, and grouped
  limitations

See `EVIDENCE_UX_POLISH_PLAN.md`, `EVIDENCE_UX_COPY_GUIDE.md`, and
`EVIDENCE_UX_POLISH_REPORT.md`.

Phase 1.4 adds insight integrity and recording-quality gates:

- Typed `EXCELLENT`, `GOOD`, `LIMITED`, and `UNSUITABLE` recording quality
- Persisted upload preflight and post-tracking analysis readiness
- Centralized initial engineering thresholds for orientation, resolution, FPS,
  duration, calibration, candidates, visibility, tracked time, gaps, and fragments
- Separate recording, tracking, measurement, interpretation, and recommendation confidence
- Deterministic `NORMAL`, `CAUTIOUS`, `MEASUREMENT_ONLY`, and
  `INSUFFICIENT_EVIDENCE` Match IQ gates
- Evidence-led insight cards with observation, evidence, confidence, interpretation,
  limitations, and next-review action
- Suppression of interpretation/advice for weak evidence and normal Match IQ for
  unsuitable evidence
- Disabled timeline-half rules that could reconnect movement across unobserved gaps

Phase 1.6A adds a shadow-only Active Play framework:

- Deterministic `LIKELY_ACTIVE`, `LIKELY_IDLE`, and `UNKNOWN` window estimates
- Gap-safe, time-based motion features with typed coverage, reasons, limitations,
  confidence, lineage, and `active-play-v1`
- Conservative interval merging and versioned filesystem artifacts
- Internal debug-only API access; no frontend or player-facing analytics changes
- Partial-interval calibration labels and raw-duration metrics
- No rally, point, serve, shot, scoring, ball, or tactical detection

Still out of scope: auth, databases, cloud storage, background workers, ball tracking, pose estimation, scoring, shot classification, coaching, face recognition, biometric identification, player comparison, opponent analysis, and real-time processing.

Shadow Active Play is not part of the normal player workflow. After tracking exists,
developers may generate or retrieve it with:

```text
POST /api/v1/analyses/{analysis_id}/debug/active-play
GET  /api/v1/analyses/{analysis_id}/debug/active-play
```

The output is an unvalidated activity estimate and must not be described as rally
detection. See `ACTIVE_PLAY_DESIGN.md` and `ACTIVE_PLAY_CALIBRATION_GUIDE.md`.

## Project Structure

```text
app/
  api/                         FastAPI routers
  api/v1/                      Versioned analysis workflow API
  config/                      Runtime settings
  core/                        Structured logging
  schemas/                     Pydantic schemas
  services/court_detection/    Automatic sampled-frame court detection
  services/detection/          Detector/backend interfaces
  services/jobs/               Filesystem-backed job workflow services
  services/recording_quality/  Two-stage recording and evidence assessment
  services/tracking/           Tracking backends and errors
  services/candidates/         Candidate generation, association, and review persistence
  services/video/              Video inspection, tracking, and selection services
  services/analytics/          Selected-player movement analytics and images
  services/active_play/        Internal shadow motion windows and interval policy
  services/match_iq/           Deterministic movement-insight rules
  sports/pickleball/           Pickleball calibration, geometry, landmarks
scripts/
  inspect_video.py
  calibrate_court.py
  track_players.py
  select_player.py
  analyze_match.py
tests/
data/input/
data/output/
web/                           Next.js frontend
  app/                         App Router pages
  components/                  Frontend UI components
  lib/                         Env, API client, local storage, workspace aggregation, share cards
  test/                        Frontend test helpers
```

## Setup

Use Python 3.12.

```bash
python -m venv .venv
source .venv/bin/activate
make install
```

On Windows PowerShell:

```powershell
# Install Python 3.12 first if needed:
winget install --id Python.Python.3.12 -e

# Verify this is a real Python install, not a WindowsApps alias.
where.exe python
python --version

# If where.exe points at WindowsApps, use a real python.org install path instead.
$pythonCandidates = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "C:\Program Files\Python312\python.exe",
  "C:\Program Files (x86)\Python312\python.exe"
)
$env:COURT4_PYTHON = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $env:COURT4_PYTHON) { throw "Install Python 3.12 from python.org or winget first." }
& $env:COURT4_PYTHON --version

& $env:COURT4_PYTHON -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation for the current shell, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

The optional real detector backend needs Ultralytics plus ByteTrack's `lap`
dependency:

```bash
python -m pip install -e ".[detector]"
```

Court4 does not commit YOLO weights. Place a local model file under `models/`
or set `COURT4_DETECTOR_MODEL_PATH` to another path:

```powershell
New-Item -ItemType Directory -Force models | Out-Null
$env:COURT4_DETECTOR_MODEL_PATH = "models/yolo11n.pt"
```

Frontend setup:

```powershell
cd web
copy .env.example .env.local
npm.cmd install
npm.cmd run dev
```

The default frontend expects the API at `http://127.0.0.1:8000`. On Windows/WSL setups, this avoids `localhost` resolving to the wrong loopback listener.

## Configuration

Settings use the existing `PICKLEBALL_AI_` prefix for backward compatibility.
`COURT4_DETECTOR_MODEL_PATH` is the canonical detector weight path and takes
precedence over the legacy `PICKLEBALL_AI_DETECTOR_MODEL_PATH`.

| Variable | Default |
| --- | --- |
| `PICKLEBALL_AI_INPUT_DIR` | `data/input` |
| `PICKLEBALL_AI_OUTPUT_DIR` | `data/output` |
| `PICKLEBALL_AI_DEFAULT_SAMPLE_INTERVAL_SECONDS` | `30` |
| `PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES` | `1073741824` |
| `PICKLEBALL_AI_SUPPORTED_EXTENSIONS` | `.mp4,.mov,.avi,.mkv` |
| `PICKLEBALL_AI_LOGGING_LEVEL` | `INFO` |
| `PICKLEBALL_AI_CALIBRATION_OUTPUT_DIR` | `data/output` |
| `PICKLEBALL_AI_CALIBRATION_TOP_DOWN_WIDTH_PIXELS` | `1000` |
| `PICKLEBALL_AI_NUMERIC_VALIDATION_TOLERANCE` | `0.000001` |
| `PICKLEBALL_AI_MIN_CALIBRATION_POLYGON_AREA_PIXELS` | `1000` |
| `PICKLEBALL_AI_COURT_DETECTION_CALIBRATION_ID` | `auto-court-detection` |
| `PICKLEBALL_AI_COURT_DETECTION_MIN_CONFIDENCE` | `0.72` |
| `PICKLEBALL_AI_COURT_DETECTION_LOW_CONFIDENCE_THRESHOLD` | `0.25` |
| `PICKLEBALL_AI_TRANSITION_AREA_DEPTH_FEET` | `8` |
| `PICKLEBALL_AI_TRACKING_OUTPUT_DIR` | `data/output` |
| `COURT4_DETECTOR_MODEL_PATH` | `models/yolo11n.pt` |
| `PICKLEBALL_AI_DETECTOR_MODEL_PATH` | `models/yolo11n.pt` |
| `PICKLEBALL_AI_DETECTOR_CONFIDENCE_THRESHOLD` | `0.35` |
| `PICKLEBALL_AI_DETECTOR_IMAGE_SIZE` | `640` |
| `PICKLEBALL_AI_FRAME_PROCESSING_INTERVAL` | `1` |
| `PICKLEBALL_AI_COURT_INCLUSION_MARGIN_FEET` | `3` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_TRACK_DURATION_SECONDS` | `1` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_OBSERVATION_COUNT` | `3` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_INSIDE_EXTENDED_RATIO` | `0.6` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_INSIDE_COURT_RATIO` | `0.6` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_COURT_MOVEMENT_RATE_FEET_PER_SECOND` | `1.2` |
| `PICKLEBALL_AI_MAX_SELECTABLE_PLAYER_TRACKS` | `4` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_AVERAGE_CONFIDENCE` | `0.4` |
| `PICKLEBALL_AI_ANNOTATED_VIDEO_CODEC` | `mp4v` |
| `PICKLEBALL_AI_ANNOTATED_VIDEO_FPS` | `10` |
| `PICKLEBALL_AI_ANALYTICS_OUTPUT_DIR` | `data/output` |
| `PICKLEBALL_AI_ANALYTICS_IMAGE_WIDTH_PIXELS` | `1000` |
| `PICKLEBALL_AI_API_BASE_PATH` | `/api/v1` |
| `PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR` | `data/output` |
| `PICKLEBALL_AI_UPLOAD_CHUNK_SIZE_BYTES` | `1048576` |
| `PICKLEBALL_AI_DEFAULT_TRACKING_BACKEND` | `controlled-json` |
| `PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` |

Frontend variables live in `web/.env.local`:

| Variable | Default |
| --- | --- |
| `NEXT_PUBLIC_COURT4_API_URL` | `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES` | `1073741824` |
| `NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS` | `.mp4,.mov,.avi,.mkv` |

## API

```bash
make run
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

OpenAPI docs are available at:

```text
http://localhost:8000/docs
```

The Phase 0.5 API is synchronous and filesystem-backed. Each successful upload creates:

```text
data/output/<analysis_id>/
  job.json
  metadata.json
  uploads/source.<ext>
  frames/
```

`job.json` tracks `status`, `current_stage`, timestamps, failure details, stage-completion flags, available artifact paths, and optional automatic court-detection metadata:

```json
{
  "court_detection_status": "detected",
  "court_detection_confidence": 0.91,
  "court_detection_selected_frame": "frames/frame_000001.jpg",
  "court_detection_detected_corners": {
    "near_left": {"x": 80.0, "y": 760.0},
    "near_right": {"x": 720.0, "y": 760.0},
    "far_right": {"x": 600.0, "y": 120.0},
    "far_left": {"x": 200.0, "y": 120.0}
  }
}
```

Older jobs without these fields remain valid and return `null` values in the API payload.

Endpoint overview:

```text
POST /api/v1/analyses
GET  /api/v1/analyses/{analysis_id}
GET  /api/v1/analyses/{analysis_id}/frames
GET  /api/v1/analyses/{analysis_id}/artifacts/{artifact_path}
POST /api/v1/analyses/{analysis_id}/court-detection
POST /api/v1/analyses/{analysis_id}/calibration
POST /api/v1/analyses/{analysis_id}/tracking
GET  /api/v1/analyses/{analysis_id}/player-candidates
POST /api/v1/analyses/{analysis_id}/player-candidates/generate
POST /api/v1/analyses/{analysis_id}/player-candidates/{candidate_id}/select
POST /api/v1/analyses/{analysis_id}/player-candidates/{candidate_id}/reject
POST /api/v1/analyses/{analysis_id}/player-candidates/{candidate_id}/restore
POST /api/v1/analyses/{analysis_id}/player-candidates/merge
POST /api/v1/analyses/{analysis_id}/player-candidates/unmerge
GET  /api/v1/analyses/{analysis_id}/players
POST /api/v1/analyses/{analysis_id}/players/select
POST /api/v1/analyses/{analysis_id}/analytics
GET  /api/v1/analyses/{analysis_id}/analytics
```

Complete API workflow:

```bash
curl -F "file=@data/input/match.avi;type=video/x-msvideo" \
  http://localhost:8000/api/v1/analyses

curl http://localhost:8000/api/v1/analyses/<analysis_id>

curl http://localhost:8000/api/v1/analyses/<analysis_id>/frames

curl -X POST http://localhost:8000/api/v1/analyses/<analysis_id>/court-detection
```

Automatic court detection returns one of:

- `detected`: calibration artifacts were saved automatically.
- `low_confidence`: Court4 found a candidate, but confidence is below the save threshold.
- `failed`: Court4 could not find a usable court candidate.

If the result is `low_confidence` or `failed`, `manual_calibration_required` is true and callers should use the existing manual calibration endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/analyses/<analysis_id>/calibration \
  -H "Content-Type: application/json" \
  -d '{
    "calibration_id": "manual-court-calibration",
    "source_frame": "frames/frame_000001.jpg",
    "near_left": {"x": 120, "y": 680},
    "near_right": {"x": 1780, "y": 690},
    "far_right": {"x": 1320, "y": 220},
    "far_left": {"x": 580, "y": 215}
  }'
```

Use the saved calibration ID from either automatic detection or manual calibration when starting tracking:

```bash
curl -X POST http://localhost:8000/api/v1/analyses/<analysis_id>/tracking \
  -H "Content-Type: application/json" \
  -d '{
    "calibration_id": "auto-court-detection",
    "backend": "controlled-json",
    "detections_jsonl": "uploads/detections.jsonl",
    "frame_interval": 1
  }'

curl http://localhost:8000/api/v1/analyses/<analysis_id>/players

curl -X POST http://localhost:8000/api/v1/analyses/<analysis_id>/players/select \
  -H "Content-Type: application/json" \
  -d '{"track_id": 1}'

# Preferred Phase 1.3B flow:
curl http://localhost:8000/api/v1/analyses/<analysis_id>/player-candidates

curl -X POST \
  http://localhost:8000/api/v1/analyses/<analysis_id>/player-candidates/<candidate_id>/select

curl -X POST http://localhost:8000/api/v1/analyses/<analysis_id>/analytics

curl http://localhost:8000/api/v1/analyses/<analysis_id>/analytics
curl -O http://localhost:8000/api/v1/analyses/<analysis_id>/artifacts/analytics/heatmap.png
```

For the controlled tracking backend, `detections_jsonl` must be an artifact-relative path inside the analysis directory. API callers cannot reference arbitrary filesystem paths.

Uploads are limited by `PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES`, accepted extensions use `PICKLEBALL_AI_SUPPORTED_EXTENSIONS`, and files are streamed in chunks of `PICKLEBALL_AI_UPLOAD_CHUNK_SIZE_BYTES`.

Artifact retrieval is restricted to files inside the requested analysis directory. Path traversal is rejected, missing files return 404, and content types are inferred from artifact filenames.

## Frontend

Run the backend first, then start the frontend from `web/`:

```powershell
npm.cmd run dev
```

Open:

```text
http://localhost:3000
```

Frontend routes:

```text
GET /                         Player dashboard with latest Match IQ and activity summary
GET /performance              Factual current performance snapshot
GET /matches                  State-aware recent matches stored in browser localStorage
GET /matches/upload           Match video upload
GET /matches/{analysis_id}    Job status, sampled frames, and workflow actions
GET /matches/{analysis_id}/calibrate  Manual four-corner calibration fallback
GET /matches/{analysis_id}/analytics  Analytics, Match IQ, and share-card export
GET /player                   Browser-local player profile
GET /settings                 Application and technical settings boundary
```

The match details page now drives the first end-to-end flow:

```text
Upload match
Detect Court
Start player tracking
Select This is me
Generate My Analytics
View analytics results
```

If automatic court detection returns `low_confidence` or `failed`, the page shows a `Calibrate Manually` action that opens the interactive calibration fallback.

The manual calibration page lets the user select a sampled frame, mark four
visible outer court corners, undo/reset points, review the order, submit to the
backend, and inspect the returned verification and top-down artifacts. The
player-facing point order is `far left`, `far right`, `near right`, `near left`;
the frontend maps those points to the backend contract order `near_left`,
`near_right`, `far_right`, `far_left`.

The Dashboard is a returning-player snapshot. It shows total and completed reports,
the number of reports available for progress comparisons, the latest completed
analysis, the latest verified movement insight, and the current progress answer. It
links to both history surfaces without exposing report-level eligibility decisions.

Analysis History (`/analyses`) reads persisted jobs from the backend rather than the
browser-local recent-ID cache. Every persisted analysis remains visible and reopenable
regardless of contribution status.

Play History (`/play-history`) uses the centralized backend policy described in
`PLAY_HISTORY_CONTRIBUTION_POLICY.md`. Only included analyses affect reliable
observation time, qualified movement time, the qualified zone summary, or verified
Match IQ summaries. Three comparable reports establish an initial baseline only. Four
or more may form deterministic non-overlapping earlier and recent groups. Movement
pace is normalized by qualified tracked duration, and court-zone percentages are
duration weighted. Graphs expose dates, report counts, qualified duration,
aggregation method, and provisional state. Missing aggregates are unavailable, not
zero. Observed changes are descriptive and do not automatically mean better or worse
performance. Report quality, processing, and contribution decisions remain on
Analysis History.

The Player page stores a minimal profile in browser `localStorage` only. Supported
fields are display name, profile photo, dominant hand, experience level, and optional
home club or location. Profile photos accept JPEG, PNG, or WebP up to 1 MB and appear
in the Dashboard header with an initials fallback. Text values are trimmed,
length-limited, sanitized for angle brackets, and can be cleared. This is not an
account system and does not sync across devices. The Settings
page is reserved for application and technical preferences, not sports identity fields.

The shared workspace aggregation utility in `web/lib/workspace-data.ts` defines a
completed match as a completed job with `analytics_completed` and a loaded analytics
payload. It sorts deterministically by persisted analytics/job timestamps, counts
completed Match IQ reports, derives the latest Match IQ, formats distance and tracked
time, and avoids mutating API payloads.

Mobile navigation uses the same primary route set as desktop navigation. All six routes
remain visible and keyboard-accessible at narrow widths; there is no separate conflicting
navigation model.

## Video Inspection

```bash
python -m scripts.inspect_video \
  --input data/input/match.mp4 \
  --analysis-id example-analysis
```

Output:

```text
data/output/<analysis_id>/
  metadata.json
  frames/
    frame_000001.jpg
```

## Court Calibration

Court coordinates use feet:

```text
Origin: near-left outer court corner
X-axis: court width, left to right
Y-axis: court length, near baseline to far baseline

near-left:  (0, 0)
near-right: (20, 0)
far-right:  (20, 44)
far-left:   (0, 44)
```

Regulation dimensions:

- width: 20 feet
- length: 44 feet
- net: y = 22 feet
- near kitchen line: y = 15 feet
- far kitchen line: y = 29 feet

Calibration requires corner order: `near-left`, `near-right`, `far-right`, `far-left`.

## Automatic Court Detection

The backend endpoint `POST /api/v1/analyses/{analysis_id}/court-detection` requires an inspected analysis. It reads the sampled frame artifacts, searches for visible court-line boundaries, estimates the ordered outer corners, and reuses the existing calibration pipeline to save:

```text
data/output/<analysis_id>/calibrations/auto-court-detection/
  calibration.json
  verification.jpg
  top_down.jpg
```

The service returns `detected` only when confidence meets `PICKLEBALL_AI_COURT_DETECTION_MIN_CONFIDENCE`. Lower-confidence candidates return `low_confidence`; missing or unusable candidates return `failed`. Both fallback outcomes set `manual_calibration_required` on the analysis job so callers can route the user to manual calibration.

The detection outcome, confidence, selected frame, and detected corners are persisted in `job.json` so they remain available after refresh and after later tracking, player-selection, and analytics updates.

Manual calibration CLI:

```bash
python -m scripts.calibrate_court \
  --input data/output/example-analysis/frames/frame_000001.jpg \
  --analysis-id example-analysis \
  --calibration-id example-calibration \
  --near-left 120,680 \
  --near-right 1780,690 \
  --far-right 1320,220 \
  --far-left 580,215
```

Output:

```text
data/output/<analysis_id>/calibrations/<calibration_id>/
  calibration.json
  verification.jpg
  top_down.jpg
```

The corner reprojection error checks the homography math, not whether the selected physical lines are correct. Use `verification.jpg` for human confirmation.

## Player Tracking

The production detector path is an optional Ultralytics YOLO model with integrated ByteTrack. The model is loaded once per analysis, only class `person` is accepted from YOLO, and weights must exist locally. Court4 does not silently download weights. If the configured model path is missing, API tracking returns `detector_model_missing` with this user-facing message:

```text
Player detection is not available because the detector model is missing.
```

Example real-model command:

```bash
python -m scripts.track_players \
  --input data/input/match.mp4 \
  --calibration data/output/example-analysis/calibrations/example-calibration/calibration.json \
  --analysis-id example-analysis \
  --model-path models/yolo11n.pt \
  --confidence-threshold 0.35 \
  --frame-interval 1
```

Offline controlled-detection command:

```bash
python -m scripts.track_players \
  --input data/input/synthetic_match.avi \
  --calibration data/output/example-analysis/calibrations/example-calibration/calibration.json \
  --analysis-id example-analysis \
  --detections-jsonl data/input/controlled_detections.jsonl
```

`--detections-jsonl` expects one detection per line:

```json
{"frame_index":0,"track_id":1,"bounding_box":{"x1":100,"y1":200,"x2":180,"y2":420},"confidence":0.91}
```

This fixture backend is for deterministic tests and validation. It does not prove real-world detector quality.

Tracking output:

```text
data/output/<analysis_id>/tracking/
  tracking.json
  observations.jsonl
  player_candidates.json
  player_candidates/<candidate_id>/{crop,frame}_{1,2,3}.jpg
  player_selection.jpg
  tracked_players.mp4
```

`observations.jsonl` is incremental and machine-readable. Each line contains frame index, timestamp, track ID, bounding box, confidence, bottom-center image ground point, mapped court position, court-filter flags, and interpolation status.

The bottom-center bounding-box point is only a proxy for foot placement. It is not pose estimation.

## Court Filtering

Each detection is mapped through the calibration using the bottom-center point.

Flags:

- `inside_court`: mapped point is within the 20 by 44 foot court.
- `inside_extended_court`: mapped point is within the court plus configurable margin.
- `excluded_from_player_tracks`: true when outside the extended court.

The margin allows for players stepping past sidelines or baselines and imperfect boxes. Spectators are still written to `observations.jsonl` for debugging, but they are not eligible if they mostly fall outside the extended court.

## Track Eligibility

A track is eligible for manual selection only if it satisfies all configured rules:

- minimum observation count
- minimum duration
- minimum ratio inside the extended court
- minimum average confidence

Rejected tracks include deterministic reasons such as:

- `insufficient_observations`
- `insufficient_duration`
- `mostly_outside_court`
- `mostly_outside_detected_court`
- `limited_court_movement`
- `low_average_confidence`
- `outside_top_player_candidates`

Eligible tracks are ordered deterministically by movement distance, movement rate, duration, confidence, and track ID, then capped by `PICKLEBALL_AI_MAX_SELECTABLE_PLAYER_TRACKS`. Court4 does not assume exactly four players. Singles and doubles both remain possible because the cap is a maximum, not an expected player count.

The raw tracking report can still contain spectators and background people because YOLO is a generic person detector. The frontend selection UI shows only tracks marked `eligible_for_selection`; rejected tracks remain in collapsed technical details for auditability.

## Player-Candidate Review

Player detection is not player identification. Raw IDs are local to one analysis
and can switch. Court4 deterministically groups plausible non-overlapping fragments
into reviewable candidates, while blocking overlap, opposite-side, and impossible-
movement associations.

The primary frontend shows candidate crops, tracked duration, quality, warnings,
selection, rejection, manual merge, and undo. Raw IDs remain in collapsed technical
details. Review state is persisted in `player_candidates.json`; legacy raw-track
selection and the CLI remain backward compatible:

```bash
python -m scripts.select_player \
  --tracking-report data/output/example-analysis/tracking/tracking.json \
  --track-id 2
```

Candidate selection persists `selected_player_candidate_id` plus its technical
source fragment IDs. Analytics use the candidate and never add movement between
fragments or across long gaps. A selection is not a real-world or biometric identity.

## Movement Analytics

Analytics run after calibration, tracking, and manual player selection. The analytics CLI reads:

- `data/output/<analysis_id>/tracking/tracking.json`
- `data/output/<analysis_id>/tracking/observations.jsonl`
- `data/output/<analysis_id>/calibrations/<calibration_id>/calibration.json`

Run:

```bash
python -m scripts.analyze_match \
  --analysis-id example-analysis
```

Optional:

```bash
python -m scripts.analyze_match \
  --analysis-id example-analysis \
  --output-dir data/output
```

Output:

```text
data/output/<analysis_id>/analytics/
  analytics.json
  match_iq.json
  movement_summary.json
  timeline.json
  trajectory.png
  heatmap.png
```

`analytics.json` is the top-level report with selected candidate lineage, technical
source fragments, observed and unobserved duration, continuity warnings, distance,
average court position, zone occupancy, and artifact names. `match_iq.json` is the
persisted deterministic Match IQ report generated from movement analytics.
`movement_summary.json` is a compact factual summary for the selected player.
`timeline.json` contains timestamped court positions. `trajectory.png` and
`heatmap.png` preserve regulation court proportions in a top-down view.

The CLI and API use the same deterministic Match IQ persistence helpers. If analytics already exist, the CLI loads the stored reports and writes a missing `match_iq.json` without duplicating rule logic.

Zone occupancy uses the configured `PICKLEBALL_AI_TRANSITION_AREA_DEPTH_FEET` value. Observations outside the regulation court are ignored for timeline, distance, heatmap, trajectory, and zone occupancy.

## Match IQ and Share Cards

Match IQ is deterministic and rule-based. It may use only metrics already produced by
the analytics pipeline. Every new insight separates observation, evidence, five
confidence dimensions, cautious interpretation, limitations, and a review action.
Limited evidence produces measurement-only output; unsuitable evidence produces an
insufficient-evidence report with normal insight cards suppressed. Rule IDs and reason
codes remain available in persisted technical data but are hidden from normal user views.

Share cards are generated in the browser from persisted analytics and Match IQ data.
Supported formats are Instagram Story, Instagram/Facebook portrait, and square post.
Cards may include player display name, match date, total distance, zone occupancy,
Match IQ summary, one or two Match IQ insights, one focus recommendation, Court4
branding, an optional heatmap or trajectory artifact, and an optional results link.
They do not include the original video, other-player images, track IDs, internal
thresholds, raw JSON, or unsupported statistics.

## Annotated Video

`tracked_players.mp4` shows:

- court polygon
- bounding boxes
- raw tracker IDs from the backend
- mapped ground-contact points
- excluded labels for off-court detections

The output preserves source aspect ratio. It records only processed frames and uses the configured output FPS and codec.

## Camera Guidance

- Place the camera behind or diagonally behind the baseline.
- Keep the full court visible and the camera stable.
- Prefer landscape orientation.
- Record at 720p minimum; 1080p is recommended.
- Capture enough continuous gameplay; usable tracked time matters more than total duration.
- Avoid severe obstruction and keep spectators away from the court boundary where possible.
- Use the same camera framing for calibration and tracking.

## Known Current Limitations

- Real-world performance depends on the chosen model, camera angle, lighting, occlusion, and spectators.
- Track IDs can switch during overlap or missed detections.
- Candidate association is conservative and can leave duplicate visible-player,
  spectator, or high-fragment candidates for manual review.
- ByteTrack is used through the optional Ultralytics backend; tests use controlled track IDs.
- No player identity recognition, face recognition, or team assignment exists.
- Automatic court detection is a deterministic local heuristic; real-world confidence depends on line visibility, camera angle, lighting, occlusion, and background clutter.
- Manual court calibration remains the fallback when automatic detection is uncertain or fails.
- Analytics accuracy currently depends on tracking accuracy.
- Distance and zone occupancy use consecutive valid in-court court positions only.
- No trajectory smoothing, interpolation, ball tracking, shot detection, rally detection, or coaching advice exists.
- API processing is synchronous; long videos block the request until each step completes.
- API job persistence is local JSON on disk; there is no database, queue, auth, or multi-user isolation yet.
- Frontend recent matches are stored only in the current browser's localStorage.
- Player profile data is browser-local only; there is no authentication or cross-device synchronization.
- Play History provides provisional long-term observed-change comparisons, not
  outcome-validated performance evaluation. AI coaching, public profiles,
  authentication, and cross-device profile synchronization remain unavailable.
- Manual calibration accuracy depends on the user selecting the true outer court corners.
- Legacy analyses remain viewable. Missing quality evidence is labeled unavailable and
  does not strengthen an insight.
- No interpolation is performed beyond native backend continuity.
- Severe lens distortion is not corrected.

## Developer Commands

```bash
make install
make test
make lint
make format
make format-check
make typecheck
make run
make inspect
make calibrate INPUT=... NEAR_LEFT=... NEAR_RIGHT=... FAR_RIGHT=... FAR_LEFT=...
make track INPUT=... CALIBRATION=... ANALYSIS_ID=...
make select-player TRACKING_REPORT=... TRACK_ID=...
make analyze ANALYSIS_ID=...
make docker-build
```

Frontend commands:

```powershell
cd web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run e2e
npm.cmd run build
npm.cmd run dev
```

## Docker

```bash
docker compose up --build
docker compose run --rm api python -m scripts.inspect_video --input data/input/match.mp4
docker compose run --rm api python -m scripts.calibrate_court --input ...
docker compose run --rm api python -m scripts.track_players --input ... --calibration ...
docker compose run --rm api python -m scripts.select_player --tracking-report ... --track-id ...
docker compose run --rm api python -m scripts.analyze_match --analysis-id ...
```

The Docker image installs the optional detector dependencies, including Ultralytics
and ByteTrack's `lap` dependency, but it does not include model weights. The
Compose service mounts `./models:/app/models:ro` and sets
`COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt`, so real tracking requires a
local untracked `models/yolo11n.pt` file on the host. Controlled JSONL detections
remain available for deterministic offline tests that do not require weights.

Run the API with Docker:

```bash
docker build -t court4:local .
docker run --rm -p 8000:8000 \
  -e COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt \
  -v "$PWD/data:/app/data" \
  -v "$PWD/models:/app/models:ro" \
  court4:local
```

Run backend validation through Docker without a local Python environment:

```powershell
docker compose build api
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .
docker compose run --rm api python -m ruff format --check .
docker compose run --rm api python -m mypy app scripts tests
```

## Real-Video Evidence Calibration

Phase 1.5 adds an internal, deterministic calibration workflow for the Phase 1.4
recording-quality and Match IQ evidence policies.

Validate the versioned seed manifest:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v1.json
```

Evaluate reusable artifacts and regenerate the reports:

```powershell
python -m scripts.calibrate_evidence evaluate calibration/manifest.v1.json
```

Outputs:

- `calibration-results.json`
- `CALIBRATION_REPORT.md`

The evaluator reuses persisted inspection, court, tracking, candidate, analytics, and
Match IQ artifacts. It does not rerun expensive inference by default, overwrite human
labels, mutate production thresholds, or expose calibration as a player-facing feature.
Threshold alternatives are simulated in memory and remain manual review inputs.

The seed dataset contains only the documented landscape and vertical recordings. All
metrics are provisional and do not constitute scientific validation. See
`CALIBRATION_GUIDE.md`, `PHASE_1_5_CALIBRATION_DESIGN.md`, and
`PHASE_1_5_REPORT.md`.

Phase 1.5A adds the backward-compatible `calibration/manifest.v2.json`, safe onboarding
templates, balance diagnostics, detailed identity/continuity/insight labels, explicit
artifact readiness, split-aware threshold simulation, and
`CALIBRATION_DISAGREEMENTS.md`.

```powershell
python -m scripts.calibrate_evidence summarize calibration/manifest.v2.json
python -m scripts.calibrate_evidence review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence artifact-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence evaluate calibration/manifest.v2.json
```

Actual recording collection and independent annotation remain human work. See
`DATASET_COLLECTION_GUIDE.md`, `ANNOTATION_GUIDE.md`, and
`PHASE_1_5A_DATASET_DESIGN.md`. Exact implementation and validation evidence is in
`PHASE_1_5A_REPORT.md`.

## Validation Commands

Default offline validation:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app scripts tests
docker build -t court4:local .

# In another shell while the API is running:
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/docs

cd web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run e2e
$env:NEXT_PUBLIC_COURT4_API_URL="http://127.0.0.1:8000"
npm.cmd run build
```

Optional real-model validation should only be reported when a local model file and optional detector dependencies are actually available. For a no-download runtime check in Docker, use `--network none` and mount the local model:

```powershell
docker run --rm --network none `
  -e COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt `
  -v "${PWD}/data:/app/data" `
  -v "${PWD}/models:/app/models:ro" `
  court4:local python -m scripts.track_players `
    --input /app/data/output/<analysis_id>/uploads/source.mp4 `
    --calibration /app/data/output/<analysis_id>/calibrations/auto-court-detection/calibration.json `
    --analysis-id real-model-validation `
    --output-dir /app/data/output `
    --model-path /app/models/yolo11n.pt `
    --frame-interval 1
```

## Recommended Next Phase

Expand the Phase 1.5 manifest with independently reviewed videos across camera,
orientation, lighting, obstruction, spectator, and player-size conditions. Add
frame-level player identity and continuity ground truth before claiming candidate
precision or tracking accuracy. Player History should remain deferred until the intended
real-upload operating envelope is measured and accepted.
