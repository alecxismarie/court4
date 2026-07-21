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

Still out of scope: auth, databases, cloud storage, background workers, ball tracking, pose estimation, scoring, shot classification, coaching, face recognition, biometric identification, player comparison, opponent analysis, and real-time processing.

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
  services/tracking/           Tracking backends and errors
  services/video/              Video inspection, tracking, and selection services
  services/analytics/          Selected-player movement analytics and images
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
  lib/                         Env, API client, storage helpers
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
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The optional real detector backend needs Ultralytics:

```bash
python -m pip install -e ".[detector]"
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
| `PICKLEBALL_AI_DETECTOR_MODEL_PATH` | `models/yolo11n.pt` |
| `PICKLEBALL_AI_DETECTOR_CONFIDENCE_THRESHOLD` | `0.35` |
| `PICKLEBALL_AI_DETECTOR_IMAGE_SIZE` | `640` |
| `PICKLEBALL_AI_FRAME_PROCESSING_INTERVAL` | `1` |
| `PICKLEBALL_AI_COURT_INCLUSION_MARGIN_FEET` | `3` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_TRACK_DURATION_SECONDS` | `1` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_OBSERVATION_COUNT` | `3` |
| `PICKLEBALL_AI_MIN_ELIGIBLE_INSIDE_EXTENDED_RATIO` | `0.6` |
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

`job.json` tracks `status`, `current_stage`, timestamps, failure details, stage-completion flags, and available artifact paths.

Endpoint overview:

```text
POST /api/v1/analyses
GET  /api/v1/analyses/{analysis_id}
GET  /api/v1/analyses/{analysis_id}/frames
GET  /api/v1/analyses/{analysis_id}/artifacts/{artifact_path}
POST /api/v1/analyses/{analysis_id}/court-detection
POST /api/v1/analyses/{analysis_id}/calibration
POST /api/v1/analyses/{analysis_id}/tracking
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
GET /                         Dashboard and local recent matches
GET /matches                  Recent matches stored in browser localStorage
GET /matches/upload           Match video upload
GET /matches/{analysis_id}    Job status, sampled frames, and workflow actions
GET /matches/{analysis_id}/calibrate
GET /matches/{analysis_id}/analytics
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

If automatic court detection returns `low_confidence` or `failed`, the page shows a `Calibrate Manually` action and keeps the existing manual calibration route as the fallback. The manual route is still intentionally lightweight; it preserves the fallback entry point while automatic detection is the primary flow.

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

The production detector path is an optional Ultralytics YOLO model with integrated ByteTrack. The model is loaded once per analysis, only class `person` is used, and weights must exist locally. Court4 does not silently download weights.

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
- `low_average_confidence`

Court4 does not assume exactly four players. Singles and doubles must both remain possible later.

## Manual Player Selection

Player detection is not player identification. Track IDs are local to one analysis and can switch.

Use `player_selection.jpg` to inspect representative crops, then select one eligible track:

```bash
python -m scripts.select_player \
  --tracking-report data/output/example-analysis/tracking/tracking.json \
  --track-id 2
```

This updates `tracking.json` with `selected_player_track_id` and preserves `observations.jsonl`. The selection is not a real-world identity and is not persisted outside the local analysis report.

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
  movement_summary.json
  timeline.json
  trajectory.png
  heatmap.png
```

`analytics.json` is the top-level report with source paths, selected track ID, distance metrics, average court position, zone occupancy, and artifact names. `movement_summary.json` is a compact factual summary for the selected player. `timeline.json` contains timestamped court positions. `trajectory.png` and `heatmap.png` preserve regulation court proportions in a top-down view.

Zone occupancy uses the configured `PICKLEBALL_AI_TRANSITION_AREA_DEPTH_FEET` value. Observations outside the regulation court are ignored for timeline, distance, heatmap, trajectory, and zone occupancy.

## Annotated Video

`tracked_players.mp4` shows:

- court polygon
- bounding boxes
- stable track IDs from the backend
- mapped ground-contact points
- excluded labels for off-court detections

The output preserves source aspect ratio. It records only processed frames and uses the configured output FPS and codec.

## Camera Guidance

- Keep the camera fixed.
- Make the full court visible.
- Avoid severe obstruction.
- Prefer elevated or baseline-oriented views.
- Keep spectators away from the court boundary where possible.
- Use the same camera framing for calibration and tracking.

## Known Current Limitations

- Real-world performance depends on the chosen model, camera angle, lighting, occlusion, and spectators.
- Track IDs can switch during overlap or missed detections.
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
- The frontend manual calibration page is still a fallback entry point rather than a polished interactive corner-marking tool.
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

The default Docker image does not install Ultralytics or include model weights. Use controlled JSONL detections for offline validation, or extend the image/install optional dependencies and mount a local model file for real inference.

Run the API with Docker:

```bash
docker build -t court4:local .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" court4:local
```

## Validation Commands

Default offline validation:

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy app scripts tests
docker build -t court4:local .
cd web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
$env:NEXT_PUBLIC_COURT4_API_URL="http://127.0.0.1:8000"
npm.cmd run build
```

Optional real-model validation should only be reported when a local model file and optional detector dependencies are actually available.

## Recommended Next Phase

Phase 1.1 - Shareable Performance Cards.

That phase should add shareable summaries based on factual analytics outputs without adding ball tracking, scoring, or AI coaching.
