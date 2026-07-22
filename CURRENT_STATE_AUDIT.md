# Court4 Current State Audit

Date: 2026-07-22

## 1. Executive Verdict

Court4 is an MVP-quality local analysis workflow. The current repo supports the intended consumer path:

Upload match -> inspect video -> recognize court -> find players -> select yourself -> generate analytics -> view Match IQ -> export a share card.

Overall readiness: CONTROLLED DEMO READY.

The controlled fixture workflow is stable and well covered by tests. Real-video player detection is validated on local videos with CPU-only YOLO/ByteTrack, but remains limited by generic person detection, fragmented identities, and camera-dependent eligibility.

Do not start a history/progress feature phase before accepting the remaining real-video limitations or improving track continuity.

## 2. Repository And Working Tree

The repository has one committed baseline, `3aa0acf Implement Court4 analysis workflow`, and a large dirty working tree containing the Phase 1.0C through Phase 1.3 work plus recent hardening.

Important working-tree state:

| Area | Status | Notes |
| --- | --- | --- |
| Backend source | PARTIAL | Many modified files are uncommitted. Backend validation passes after formatter cleanup. |
| Frontend source | PARTIAL | Many modified and untracked files are uncommitted. Frontend validation passes with required env vars. |
| Match IQ files | COMPLETE | `app/schemas/match_iq.py`, `app/services/match_iq/`, and tests are untracked relative to the single commit. |
| Share-card files | COMPLETE | Share-card model, renderer, panel, tests, and artifact proxy route are untracked relative to the single commit. |
| Player workspace files | PARTIAL | Dashboard/performance/player/settings workspace files are untracked or modified. Storage is browser-local only. |
| YOLO model file | PARTIAL | `models/yolo11n.pt` exists locally, is ignored by Git, and is mounted by Docker Compose when present. The file is still a local prerequisite, not a committed artifact. |
| Generated data | EXPERIMENTAL | `data/output/` contains local smoke and real-video artifacts ignored by git. |

Phase 1.3A updates:

- Added `REAL_VIDEO_RELIABILITY_REPORT.md`.
- Added interactive manual calibration frontend, typed calibration API client support, and browser tests.
- Added canonical detector model path handling, Docker Compose model mount, and explicit `lap` detector dependency.
- Reconciled CLI/API Match IQ persistence.
- Added maintained Playwright E2E smoke tests.
- Generated local real-video validation artifacts under ignored `data/output/phase13a-*`.

## 3. Feature Inventory

Status values are one of COMPLETE, PARTIAL, EXPERIMENTAL, PLACEHOLDER, BROKEN, or NOT IMPLEMENTED.

| Feature | Status | Evidence |
| --- | --- | --- |
| Health endpoint | COMPLETE | `GET /health` returns `{"status":"ok"}`. |
| API docs | COMPLETE | `GET /docs` returns HTTP 200. |
| Multipart video upload | COMPLETE | API validates extension, content type, empty uploads, size limit, and safe filenames. |
| Video inspection | COMPLETE | OpenCV metadata extraction and sampled frames are persisted under `data/output/<analysis_id>/`. |
| Artifact retrieval | COMPLETE | Backend validates relative artifact paths and serves images inline. Traversal is rejected. |
| Manual calibration backend | COMPLETE | `POST /api/v1/analyses/{id}/calibration` writes calibration reports and artifacts. |
| Manual calibration frontend | COMPLETE | `/matches/{id}/calibrate` supports sampled-frame selection, four corner clicks/taps, validation, submit, verification/top-down artifact display, and continue-to-tracking. |
| Automatic court recognition | PARTIAL | Deterministic OpenCV heuristic exists, has synthetic tests, and persists detection state. Real videos can still over-detect the court boundary. |
| Controlled JSON tracking backend | COMPLETE | Deterministic fixture backend is covered by pytest and full API workflow tests. |
| Ultralytics YOLO plus ByteTrack backend | EXPERIMENTAL | Adapter runs with local `models/yolo11n.pt`; two local real-video clips were validated offline with Docker `--network none`. Landscape demo clip produced selectable candidates; vertical clip did not. |
| Player filtering and selection | PARTIAL | Eligible cards are filtered by inside-court ratio, extended-court ratio, movement rate, confidence, and top-candidate cap. The raw tracking report can still contain many non-player track IDs. |
| Player preview images | COMPLETE | Per-track preview images are generated/backfilled for eligible tracks and shown in the UI. |
| Movement analytics | COMPLETE | Distance, average movement, timeline, average court position, zone occupancy, heatmap, and trajectory are persisted. |
| Deterministic Match IQ via API | COMPLETE | Rule engine persists `analytics/match_iq.json`; legacy analytics without Match IQ return `match_iq: null`. |
| Deterministic Match IQ via CLI | COMPLETE | `scripts/analyze_match.py` uses shared Match IQ persistence, writes `match_iq.json`, and reuses existing analytics deterministically. |
| Analytics results page | COMPLETE | Shows factual metrics, Match IQ, insight evidence, focus, limitations, heatmap, trajectory, and share-card panel. |
| Shareable performance cards | COMPLETE | Supports Story, portrait, square formats, PNG download, native share where browser-supported, optional heatmap/trajectory, and optional current results URL. |
| Public results links | PARTIAL | Share-card data can include the current URL, but there is no public hosting, auth boundary, or stable share token. |
| Dashboard workspace | PARTIAL | Local dashboard summarizes remembered browser-local analyses and latest Match IQ. No account or cross-device history. |
| Matches list | PARTIAL | Browser-local recent analysis IDs are listed with state-aware actions. Backend has no list-all endpoint. |
| Performance workspace | PARTIAL | Shows factual cumulative local totals and recent Match IQ summaries. Future progress is intentionally not implemented. |
| Player profile | PARTIAL | Browser-local display name, dominant hand, experience, and location fields. No auth, sync, identity verification, or history. |
| Settings page | PLACEHOLDER | Reserved for application preferences; currently only explains the profile boundary. |
| Branded logo/favicon | COMPLETE | User-provided Court4 logo is used in app shell and favicon assets. |
| Authentication and accounts | NOT IMPLEMENTED | No auth, sessions, user IDs, or access control. |
| Database persistence | NOT IMPLEMENTED | Persistence is local JSON/filesystem only. |
| Background workers | NOT IMPLEMENTED | Long-running work is synchronous request/response. |
| Ball tracking | NOT IMPLEMENTED | No ball detection, speed, placement, rallies, shots, scoring, or serve analysis. |
| LLM coaching | NOT IMPLEMENTED | Match IQ is deterministic and does not use an LLM. |

## 4. Architecture

Backend:

- FastAPI app in `app/main.py`.
- Top-level health route in `app/api/routes.py`.
- Versioned analysis routes in `app/api/v1/analyses.py` under `/api/v1`.
- Filesystem workflow orchestration in `app/services/jobs/workflow.py`.
- Local repository abstraction in `app/services/jobs/repository.py`.
- Pickleball geometry/calibration in `app/sports/pickleball/`.
- Detection adapters in `app/services/tracking/`.
- Movement analytics in `app/services/analytics/`.
- Deterministic Match IQ rules in `app/services/match_iq/`.

Frontend:

- Next.js App Router in `web/app`.
- Main shell/navigation in `web/components/app-shell.tsx`.
- Typed API contracts in `web/lib/api/types.ts` using Zod.
- API functions in `web/lib/api/analyses.ts`.
- Browser-local recent analysis storage in `web/lib/recent-analyses.ts`.
- Browser-local player profile in `web/lib/player-profile.ts`.
- Share-card derivation and canvas rendering in `web/lib/share-card.ts` and `web/lib/share-card-renderer.ts`.

Route inventory:

| Route | Status | Description |
| --- | --- | --- |
| `/` | PARTIAL | Player workspace dashboard using local storage plus fetched analysis details. |
| `/matches` | PARTIAL | Browser-local recent matches list. |
| `/matches/upload` | COMPLETE | Upload UI and validation. |
| `/matches/{analysisId}` | COMPLETE | Workflow detail route: court recognition, tracking, selection, analytics action. |
| `/matches/{analysisId}/analytics` | COMPLETE | Analytics, Match IQ, images, and share cards. |
| `/matches/{analysisId}/calibrate` | COMPLETE | Interactive manual calibration fallback with point validation and artifact review. |
| `/performance` | PARTIAL | Factual local snapshot; progress comparisons are not implemented. |
| `/player` | PARTIAL | Browser-local player profile. |
| `/settings` | PLACEHOLDER | Reserved for app-level preferences. |
| `/api/share-artifact/{analysisId}/{artifactPath}` | COMPLETE | Allows only `analytics/*.png` to be proxied for share-card canvas loading. |

## 5. Persistence Model

Backend persistence is local filesystem JSON under `data/output/<analysis_id>/`.

Typical persisted structure:

- `job.json`
- `metadata.json`
- `uploads/source.<ext>`
- `frames/frame_*.jpg`
- `calibrations/<calibration_id>/calibration.json`
- `calibrations/<calibration_id>/verification.jpg`
- `calibrations/<calibration_id>/top_down.jpg`
- `tracking/tracking.json`
- `tracking/observations.jsonl`
- `tracking/player_selection.jpg`
- `tracking/tracked_players.mp4`
- `tracking/player_previews/track_<id>.jpg`
- `analytics/analytics.json`
- `analytics/movement_summary.json`
- `analytics/timeline.json`
- `analytics/trajectory.png`
- `analytics/heatmap.png`
- `analytics/match_iq.json`

Backward compatibility:

- Legacy jobs without court-detection fields load with null optional values.
- Legacy analytics without `analytics/match_iq.json` return `match_iq: null`.

Known persistence limitations:

- No database.
- No locking around concurrent writes.
- `GET /players` can mutate legacy tracking reports by refreshing eligibility metrics and preview paths.
- No user isolation. Any local caller with an analysis ID can request artifacts.
- No retention policy or cleanup strategy.

## 6. Match IQ Audit

Match IQ status: COMPLETE for API-generated and CLI-generated analytics.

Metrics used by rules:

- `distance.total_distance_feet`
- `distance.average_movement_feet_per_second`
- `timeline_observation_count`
- `zone_occupancy.tracked_time_seconds`
- `zone_occupancy.kitchen.percentage`
- `zone_occupancy.transition_zone.percentage`
- `zone_occupancy.baseline_area.percentage`
- `timeline.positions`

Implemented rule IDs:

- `positioning-high-baseline-v1`
- `positioning-high-kitchen-v1`
- `positioning-high-transition-v1`
- `positioning-low-transition-v1`
- `positioning-balanced-zones-v1`
- `positioning-primary-zone-v1`
- `movement-short-total-distance-v1`
- `movement-measured-distance-v1`
- `timeline-first-half-higher-distance-v1`
- `timeline-second-half-higher-distance-v1`

Safety assessment:

- Rules only use persisted movement analytics and timeline data.
- Each insight includes rule ID, evidence metric, value, and threshold.
- No LLM is used.
- No claims are made about shots, serves, tactics, reaction time, fatigue, opponent pressure, scoring, or improvement versus previous matches.

CLI/API parity:

- Both paths use shared Match IQ persistence helpers.
- CLI writes missing `analytics/match_iq.json` for existing analytics and remains deterministic on repeat runs.

Representative local Match IQ sample from `data/output/dc4b4effac81444da71bd848a51ed590/analytics/match_iq.json`:

```json
{
  "analysis_id": "dc4b4effac81444da71bd848a51ed590",
  "status": "generated",
  "summary": "Match IQ found 3 movement observations. Top signal: Court4 measured 57.0% of tracked time in the kitchen.",
  "insights": [
    {
      "id": "kitchen-occupancy",
      "rule_id": "positioning-high-kitchen-v1",
      "statement": "Court4 measured 57.0% of tracked time in the kitchen.",
      "evidence": "zone_occupancy.kitchen.percentage = 57.0%, threshold >= 55.0%"
    },
    {
      "id": "measured-movement",
      "rule_id": "movement-measured-distance-v1",
      "statement": "Court4 measured 43.6 ft over 13.0 seconds, averaging 3.35 ft/s.",
      "evidence": "distance.total_distance_feet = 43.6 ft; average_movement = 3.35 ft/s; tracked_time = 13.0 sec"
    },
    {
      "id": "first-half-distance",
      "rule_id": "timeline-first-half-higher-distance-v1",
      "statement": "The first half covered 32.8 ft, compared with 10.8 ft in the other half.",
      "evidence": "larger half >= 1.25x other half and delta >= 5.0 ft"
    }
  ],
  "focus": "Focus area: positioning mix"
}
```

## 7. Real-Model Tracking Audit

Real-model status: EXPERIMENTAL, validated for a controlled local demonstration.

Local model state:

- `models/yolo11n.pt` exists locally.
- The file is untracked and ignored by `models/*`.
- `COURT4_DETECTOR_MODEL_PATH` is the canonical model variable and takes precedence over the legacy prefixed setting.
- Docker Compose mounts `./models:/app/models:ro` and sets `COURT4_DETECTOR_MODEL_PATH=/app/models/yolo11n.pt`.
- The detector extra now includes Ultralytics plus `lap`, avoiding ByteTrack runtime autoinstall.

Representative real-model local output:

- Analysis: `phase13a-landscape-yolo-repro-20260722`
- `track_count`: 161
- Eligible IDs after filtering: `[1, 141, 146, 192]`
- Processing: 1,836 frames, 168.62 seconds, CPU only, Docker `--network none`
- Result: PASS WITH LIMITATION

Interpretation:

- The filter now limits selectable cards to plausible in-court candidates.
- The underlying tracker still sees many people in the video.
- This is expected for a generic person detector and should not be represented as "only detects players" yet.
- The vertical real clip `phase13a-vertical-yolo-repro-20260722` produced 2 raw tracks and 0 eligible tracks, so not every real local pickleball clip is usable yet.
- Better court masking, duplicate-fragment handling, and track continuity logic are needed.

## 8. Share Card Audit

Share-card status: COMPLETE for local export, PARTIAL for public sharing.

Implemented:

- Typed `ShareCardData`.
- Formats: Instagram Story 1080x1920, portrait 1080x1350, square 1080x1080.
- Data derives from persisted analytics and Match IQ.
- Optional heatmap or trajectory artifact.
- Optional display name from browser-local profile.
- PNG download through canvas export.
- Native Web Share when `navigator.share` and `navigator.canShare` support the payload.
- No direct Facebook or Instagram API posting.
- No original video, raw JSON, track IDs, or rule thresholds are included on the share card by default.

Limitations:

- Optional results link is only the current local route. There is no public hosted result or share token.
- Canvas rendering is covered by unit tests/mocks, not a browser E2E screenshot suite.
- Native sharing depends on browser/device support.

## 9. Validation Log

Backend validation:

| Check | Result | Notes |
| --- | --- | --- |
| Docker build | COMPLETE | `docker build -t court4:phase-1-3a .` passed. Final image includes detector dependencies and local model mount support. |
| Pytest | COMPLETE | `77 passed, 1 warning in 7.96s` inside the rebuilt image. Warning is Starlette/httpx deprecation from TestClient. |
| Ruff check | COMPLETE | `All checks passed!` |
| Ruff format check | COMPLETE | `70 files already formatted` after formatter cleanup. |
| Mypy | COMPLETE | `Success: no issues found in 70 source files`. |
| Live `/health` | COMPLETE | `{"status":"ok"}` from packaged Docker image on temporary port 8010. |
| Live `/docs` | COMPLETE | HTTP 200 from packaged Docker image on temporary port 8010. |

Frontend validation:

| Check | Result | Notes |
| --- | --- | --- |
| Lint | COMPLETE | `next lint` passed with no warnings or errors. |
| Typecheck | COMPLETE | `tsc --noEmit` passed. |
| Vitest | COMPLETE | `17 passed (17 files), 68 passed (68 tests)`. Vite CJS API deprecation warning only. |
| Production build | COMPLETE | Clean build passed with `NEXT_PUBLIC_COURT4_API_URL`, `NEXT_PUBLIC_COURT4_MAX_UPLOAD_BYTES`, and `NEXT_PUBLIC_COURT4_SUPPORTED_VIDEO_EXTENSIONS` set. |
| Browser E2E | COMPLETE | `npm.cmd run e2e`: `3 passed (20.0s)` for controlled happy path, manual calibration fallback, and missing-model recovery. |

Environment notes:

- Running `npm.cmd run build` without the required `NEXT_PUBLIC_COURT4_*` variables fails during prerender of `/matches/upload`.
- A stale concurrent Next dev server on port 3000 produced mixed `.next` artifacts and caused a missing vendor chunk in `next start`; stopping the dev server and rebuilding from a clean `.next` fixed it.
- Avoid running `next dev`, `next build`, and `next start` concurrently in the same `web/` directory.

Focused smoke validation:

| Smoke Path | Result | Notes |
| --- | --- | --- |
| Controlled full API workflow | COMPLETE | `test_full_controlled_api_workflow` and `test_full_controlled_api_workflow_with_automatic_court_detection`: `2 passed, 1 warning`. |
| Tracking eligibility and Match IQ rules | COMPLETE | `test_tracking_pipeline_outputs_and_eligibility` and `test_match_iq_generates_factual_evidence_backed_insights`: `2 passed`. |
| Real-model smoke | PARTIAL | Two unique local real-video clips were validated offline. Landscape clip passed with limitations; vertical clip failed to produce a selectable player. |
| Browser E2E smoke | COMPLETE | Maintained Playwright suite exists under `web/e2e/` and is run by `npm.cmd run e2e`. |

## 10. Test Coverage Audit

Strong coverage:

- Video inspection validation.
- Pickleball geometry and calibration.
- Automatic court detection on synthetic court videos.
- Controlled tracking backend.
- Player tracking artifacts, eligibility, preview image output, and selection errors.
- Full API workflow through controlled detections, player selection, analytics, Match IQ persistence, and artifact serving.
- Match IQ rule outputs and insufficient-data handling.
- Frontend API client, upload UI, match details, manual calibration fallback, workflow actions, analytics details, share-card panel, dashboard, recent matches, player profile, performance workspace, and app shell.
- Browser E2E smoke for controlled happy path, manual calibration fallback, and missing-model recovery.

Coverage gaps:

- No automated real YOLO/Ultralytics integration test.
- No real-world video fixture suite.
- No screenshot assertions for share cards or page layout.
- No concurrent request/write tests.
- No automated real YOLO test in default CI because it requires local weights and is slow.

## 11. Documentation Reconciliation

README is reconciled through Phase 1.3A for the local MVP workflow.

Updated in Phase 1.3A:

- Docker detector setup now documents installed detector dependencies, local untracked model weights, `COURT4_DETECTOR_MODEL_PATH`, and the Compose model mount.
- Manual calibration frontend is documented as an interactive fallback.
- CLI/API Match IQ parity is documented.
- Browser E2E command is documented.
- Recommended next phase was revised away from Player History until real-video track continuity improves.

Undocumented additions visible since the Phase 1.3 description:

- Per-track player preview image artifacts and UI card previews.
- Stricter selectable-player filtering based on inside-court ratio, court movement distance/rate, and top-candidate cap.
- Dockerfile now installs detector dependencies including `lap`.
- Local `models/yolo11n.pt` has been downloaded but remains ignored.
- Court4 logo and favicon assets were replaced/expanded from the provided logo.

## 12. Risk Register

| Risk | Severity | Status | Notes |
| --- | --- | --- | --- |
| Real-video court detection can over-fit the visible scene and include spectators | HIGH | PARTIAL | User-observed issue is mitigated by track eligibility filters, not solved at detection level. |
| Generic person detector tracks all people before filtering | HIGH | PARTIAL | UI hides ineligible tracks, but raw tracking report can contain many spectator IDs. |
| Model dependency requires a local untracked file | HIGH | PARTIAL | Compose now mounts `./models:/app/models:ro`, but `models/yolo11n.pt` must still be provided locally. |
| Synchronous API processing can time out on long videos | HIGH | PARTIAL | No queue, worker, cancellation, or progress polling beyond frontend pending states. |
| No auth or user isolation | HIGH | NOT IMPLEMENTED | Local-only MVP assumption. Unsafe for multi-user hosting. |
| Filesystem persistence has no locking | MEDIUM | PARTIAL | Concurrent requests can race on JSON/artifact writes. |
| CLI analytics Match IQ parity | MEDIUM | COMPLETE | CLI uses shared Match IQ persistence and writes/reuses `match_iq.json`. |
| Manual calibration UI missing | MEDIUM | COMPLETE | Interactive fallback route is implemented and tested. |
| Browser-local workspace can lose history | MEDIUM | PARTIAL | localStorage only; no backend list-all or account state. |
| No browser E2E suite | MEDIUM | COMPLETE | Playwright suite covers controlled happy path, manual calibration fallback, and missing-model recovery. |
| Frontend build requires explicit public env vars | LOW | PARTIAL | Expected for Next, but missing `.env.local` causes build failure. |

## 13. Do Not Continue Before Fixing

Required before a real beta or a history/progress phase:

1. Improve real-video track continuity and candidate review.
   - Landscape real-video validation is demo-usable but fragmented.
   - Vertical real-video validation produced no selectable players.
   - Do not claim reliable player-only detection until duplicate fragments, missed intervals, and spectator raw tracks are better handled or clearly accepted.

2. Decide the expected operating envelope for real uploads.
   - Current validation supports a controlled real-match demonstration, not arbitrary public uploads.
   - Camera position, clip duration, visible full court, and spectator placement should be documented as demo requirements.

Recommended before the next feature phase:

1. Add a backend list endpoint if the workspace should become more than browser-local recent IDs.
2. Add write locking or idempotency protection around job state transitions.
3. Add an optional local real-model validation script that summarizes existing videos without committing weights or videos.

## 14. Roadmap Recommendation

Recommended next phase: Phase 1.3B - Real-Video Track Continuity and Candidate Review.

Phase 1.4 Player History and Progress should wait until Court4 can reliably produce a selectable player track on the intended real-video operating envelope. Any future history phase must preserve the current Match IQ safety boundary: no unsupported coaching claims, no LLM-generated claims, no ball tracking, no shot/rally/score inference, and no comparison unless stored prior match data supports it.
