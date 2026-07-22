# Court4 Real-Video Reliability Report

Date: 2026-07-22

## Environment

- Workspace: `C:\Users\Ryzen 7 PRO\court4`
- Backend runtime: Docker image `court4:phase-1-3a`
- Frontend runtime: Next.js under `web/`
- Detector execution: CPU only
- CUDA status: `torch.cuda.is_available() == False`, `torch.cuda.device_count() == 0`
- Real-model validation was run with Docker `--network none` after rebuilding detector dependencies.

## Detector Configuration

- Backend: `UltralyticsByteTrackBackend`
- Model: `ultralytics-bytetrack:yolo11n.pt`
- Model path: canonical `COURT4_DETECTOR_MODEL_PATH`
- Local validation path: `/app/models/yolo11n.pt`
- Accepted detector class: YOLO class `0` (`person`)
- Tracker: Ultralytics ByteTrack (`bytetrack.yaml`) with `persist=True`
- Frame interval: `1`
- Confidence threshold: `0.35`
- Image size: `640`
- Court inclusion margin: `3.0 ft`
- Selection eligibility uses observation count, duration, inside-court ratio, inside-extended-court ratio, average confidence, court movement rate, deterministic ordering, and a max selectable-track cap.

## Model Availability

- Local model file: `models/yolo11n.pt`
- Size: `5,613,764 bytes`
- SHA256: `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`
- Git status: ignored by `models/*`; weights are not committed.
- Docker Compose mounts `./models:/app/models:ro` and sets `COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt`.
- Missing weights return typed API error `detector_model_missing` with user-facing copy: `Player detection is not available because the detector model is missing.`

## Test Videos

| Video | Source analysis | Duration | Resolution | Environment | Scenario | Camera | Visible players |
| --- | --- | ---: | --- | --- | --- | --- | ---: |
| `source.mp4` | `dc4b4effac81444da71bd848a51ed590` | 61.2 s | 640x368 | Indoor | Doubles match | Behind near baseline | 4 |
| `source.mp4` | `f54693f1003849fdb456247322925258` | 14.4 s | 720x1280 | Indoor | Drill/singles-like point | Behind near baseline, vertical social clip with text overlay | 2 |

Duplicate uploads `7a693b3f4ab74002a5692cf1eb4b2697` and `b1723142bfec4959a4821980a1cd85bb` have the same SHA prefix as the landscape clip (`841D992DCA4A1D29`) and were treated as duplicate local copies, not separate unique videos.

## Real-Model Results

| Video | Scenario | Expected players | Eligible tracks | Tracking quality | Processing time | Result | Limitations |
| --- | --- | ---: | ---: | --- | ---: | --- | --- |
| Landscape 61.2 s indoor doubles | Doubles | 4 | 4 | Raw detector created 161 tracks, but eligibility reduced selection candidates to track IDs `1,141,146,192`. Candidate previews were generated for all eligible tracks. | 168.62 s | PASS WITH LIMITATION | Track identities are fragmented; candidates cover 8.53-16.17 s each, not the full 61.2 s. Raw report still contains spectators/background people for audit. Duplicate-player fragments are possible without labeled ground truth. |
| Vertical 14.4 s indoor drill | Drill | 2 | 0 | Detector produced 2 tracks, but both were rejected. One track was mostly outside detected court and had no measured court movement; the other was below movement-rate threshold. | 45.49 s | FAIL | No player could be selected. Short duration, vertical framing, overlay text, and calibration perspective make this unsuitable for a reliable selectable-player workflow today. |

Compact metrics:

| Run ID | Frames | Raw tracks | Observation rows | Eligible IDs | Avg FPS |
| --- | ---: | ---: | ---: | --- | ---: |
| `phase13a-landscape-yolo-repro-20260722` | 1,836 | 161 | 12,152 | `1,141,146,192` | 10.89 |
| `phase13a-vertical-yolo-repro-20260722` | 432 | 2 | 842 | none | 9.50 |

Eligible landscape track details:

| Track ID | Observations | Duration | Avg confidence | Court distance | Movement rate | Inside extended ratio |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 358 | 12.03 s | 0.832 | 30.28 ft | 2.52 ft/s | 0.830 |
| 141 | 455 | 16.17 s | 0.701 | 43.62 ft | 2.70 ft/s | 0.859 |
| 146 | 257 | 8.53 s | 0.863 | 31.79 ft | 3.73 ft/s | 0.755 |
| 192 | 348 | 11.57 s | 0.852 | 34.36 ft | 2.97 ft/s | 0.707 |

Manual-review notes:

- No labeled ground truth was available, so no precision, recall, or accuracy percentage is claimed.
- Landscape spectators are visible along both sides. They appear in raw tracking but are not surfaced as selectable player cards after filtering.
- Identity switches and duplicate fragments cannot be measured exactly without labeled player tracks. The short eligible durations on a 61.2 s clip show fragmentation remains.
- Bounding boxes outside the calibrated/extended court are preserved in `observations.jsonl` and marked with exclusion flags for audit.

## Manual Calibration Results

- Frontend route `/matches/{analysisId}/calibrate` now provides frame selection, four-point corner marking, numbered markers, undo/reset, client-side validation, backend submission, verification artifact display, top-down artifact display, and a continue-to-tracking action.
- Player-facing order: `far left`, `far right`, `near right`, `near left`.
- Backend contract order submitted by the frontend: `near_left`, `near_right`, `far_right`, `far_left`.
- Safety checks cover in-bounds points, distinct points, non-self-intersecting polygon, minimum polygon area, and duplicate-submission prevention.
- Unit test coverage includes coordinate scaling, valid submission order, undo/reset, and invalid polygon blocking.
- Browser E2E coverage includes automatic court failure fallback through manual calibration completion.

## Model Packaging and Docker Setup

- Added `COURT4_DETECTOR_MODEL_PATH` as the canonical model path while preserving `PICKLEBALL_AI_DETECTOR_MODEL_PATH`.
- Added detector model bind mount to Docker Compose: `./models:/app/models:ro`.
- Added `models/*` to `.gitignore`.
- Added `lap>=0.5.12,<0.6` to the detector extra after real validation exposed an Ultralytics runtime autoinstall attempt.
- Rebuilt `court4:phase-1-3a`; `lap 0.5.13` imports in the image.
- Final real-video validation used Docker `--network none`, proving the validated runtime did not need downloads.
- Final image model-load check also used Docker `--network none`: local `yolo11n.pt` loaded, `lap 0.5.13` imported, and CUDA was unavailable.

## CLI and API Parity

- API analytics and CLI analytics now use shared Match IQ persistence helpers.
- API continues to persist `analytics/match_iq.json` after analytics generation.
- CLI writes `match_iq.json` for new analytics and writes a missing Match IQ file when analytics already exist.
- Repeated CLI generation remains deterministic and backward compatible.
- Match IQ rules are not copied into the CLI.

## Browser E2E Results

Command:

```powershell
cd web
npm.cmd run e2e
```

Result:

```text
3 passed (20.0s)
```

Covered scenarios:

- Controlled happy path: dashboard -> upload -> court recognition -> tracking -> player selection -> analytics/Match IQ -> refresh -> share-card preview.
- Court failure fallback: automatic court recognition failure -> manual calibration -> verification/top-down artifacts -> continue to tracking.
- Detector model missing: typed error appears and the UI remains retryable.

## Defects Found and Fixed

- Frontend manual calibration was a placeholder; replaced with a usable calibrated-corner workflow.
- Missing detector weights now return a typed recoverable error instead of an unstructured failure.
- Canonical model path and Docker Compose model mount were added.
- Runtime tracker dependency `lap` was missing from the detector extra; added after an autoinstall attempt was observed.
- CLI analytics no longer diverges from API Match IQ persistence.
- Vitest excluded Playwright specs so unit tests remain unit-only.
- Playwright E2E now uses a maintained Node runner that starts/stops Next cleanly on Windows.
- Manual calibration overlay markers no longer intercept image clicks.

## Remaining Limitations

- Real YOLO/ByteTrack tracking remains experimental.
- Raw tracking can include spectators and background people; eligibility filtering controls selectable candidates but does not make YOLO player-specific.
- Track IDs fragment across occlusions and missed detections.
- Duplicate selectable fragments for the same real player are still possible.
- The vertical real clip failed to produce any selectable player.
- No labeled ground truth exists, so identity switches, missing-player intervals, and duplicate-track counts are manually reviewed, not scored.
- Processing is synchronous and CPU-only in the validated environment.
- Contact-sheet text can overlap on compact generated sheets; the main UI uses individual previews.

## Readiness Verdict

Ready for a controlled real-match demonstration

Evidence:

- Controlled backend, frontend unit, browser E2E, Docker, health, and docs validation pass.
- The landscape real match produced four selectable player candidates from a local YOLO model with networking disabled.
- The vertical real clip failed, and the landscape run still shows fragmented track identities. That prevents design-partner or external beta readiness without careful demo video selection and manual review.
