# Court4 Current State Audit

Date: 2026-07-28

## 1. Executive Verdict

Court4 is an MVP-quality local analysis workflow. The current repo supports the intended consumer path:

Upload match -> inspect video -> recognize court -> find players -> select yourself -> generate analytics -> view Match IQ -> export a share card.

Overall readiness: CONTROLLED DEMO READY.

Phase 1.7A adds separate player-facing Analysis History and Play History. Analysis
History lists every persisted job from the local filesystem; Play History uses only
analyses included by deterministic `play-history-v1`. The projection exposes honest
excluded, provisional, and legacy/not-evaluated states. The Progress Integrity Pass
adds separate versioned comparability, trend, interpretation, grouping, and
aggregation decisions. It can display provisional, neutral observed-change
comparisons after four comparable reports; it does not claim genuine performance
improvement. The local workspace still has no account or user-isolation boundary.

Phase 1.6A.1 adds an internal, read-only calibration-readiness projection and
development route. The current two-sample dataset is honestly classified
`COLLECTING_EVIDENCE`: it has one development and one validation sample, no holdout,
no fully reviewed samples, no reviewed Active Play intervals, and no current-schema
Active Play sample. One artifact set is legacy-compatible and one is partial.

The source, policy, reviewer-label, holdout-simulation, and deterministic repeat-hash
checks are current. The dashboard does not run inference, alter labels or thresholds,
enable Active Play, or appear in primary player navigation. Active Play remains
shadow-only and unvalidated.

The player-facing analytics page now follows an evidence-to-insight narrative. It
explains video suitability in plain language, shows observation coverage only
when persisted durations support it, keeps five confidence dimensions separate,
describes suppressed Match IQ as an evidence limitation, renames Zone Occupancy to
Observed Court Position, labels maps as measurements, and groups limitations.

This UX pass changed no backend schemas, analytics calculations, Match IQ gates,
confidence calculations, thresholds, persisted artifacts, reviewer labels, or Active
Play visibility.

Player-facing copy consistently uses “video.” Internal `recording_*` schema, policy,
and persistence identifiers remain unchanged for backward compatibility.

The controlled fixture workflow is stable and well covered by tests. Phase 1.3B
adds stable visual player candidates, persisted manual review, candidate analytics,
and a selectable LIMITED vertical-video result. Real-video detection remains limited
by generic person detection, duplicate candidates, fragmentation, and camera quality.

Do not add evaluative performance, tactics, or coaching intelligence before collecting
match context and validating outcome-linked metrics. Current comparisons remain
provisional because match format and camera placement are not persisted.

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

Phase 1.3B updates:

- Added the typed, schema-versioned player-candidate domain and deterministic
  fragment association with centralized safety thresholds.
- Added persisted candidate selection, rejection/restore, manual merge/undo,
  representative artifacts, and legacy raw-selection compatibility.
- Replaced primary raw-ID selection with ranked visual candidate cards.
- Updated analytics to combine selected candidate fragments without counting
  overlap, long gaps, or cross-fragment endpoint jumps.
- Added recording suitability and orientation metadata handling.
- Revalidated the preserved landscape and vertical CPU YOLO observations; see
  `TRACK_CONTINUITY_REPORT.md`.

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
| Ultralytics YOLO plus ByteTrack backend | EXPERIMENTAL | Adapter runs with local `models/yolo11n.pt`; preserved CPU runs cover landscape and vertical footage. Both now produce selectable candidates, with limitations. |
| Player-candidate generation | COMPLETE | Deterministic candidate IDs/grouping, typed quality/warnings, suitability, preview artifacts, and lazy legacy generation are implemented. Real grouping quality remains EXPERIMENTAL. |
| Candidate review and selection | COMPLETE | Visual selection, reject/restore, manual merge/undo, technical lineage, and refresh-safe persistence replace raw IDs in the primary UI. |
| Player preview images | COMPLETE | Up to three candidate crops and highlighted full frames are generated for sufficiently observed candidates. |
| Movement analytics | COMPLETE | Distance, average movement, timeline, court position, zones, heatmap, and trajectory use selected candidate fragments and preserve gap/lineage metadata. |
| Deterministic Match IQ via API | COMPLETE | Rule engine persists `analytics/match_iq.json`; legacy analytics without Match IQ return `match_iq: null`. |
| Deterministic Match IQ via CLI | COMPLETE | `scripts/analyze_match.py` uses shared Match IQ persistence, writes `match_iq.json`, and reuses existing analytics deterministically. |
| Analytics results page | COMPLETE | Shows factual metrics, Match IQ, insight evidence, focus, limitations, heatmap, trajectory, and share-card panel. |
| Shareable performance cards | COMPLETE | Supports Story, portrait, square formats, PNG download, native share where browser-supported, optional heatmap/trajectory, and optional current results URL. |
| Public results links | PARTIAL | Share-card data can include the current URL, but there is no public hosting, auth boundary, or stable share token. |
| Dashboard workspace | COMPLETE FOR PRIVATE ALPHA | Evidence-aware snapshot uses backend history projections and avoids unqualified cumulative totals. |
| Analysis History | COMPLETE FOR PRIVATE ALPHA | `/analyses` and `GET /api/v1/analyses` list every persisted job with status, quality, coverage, availability, contribution, limitation, and report link. |
| Play History | COMPLETE FOR PRIVATE ALPHA | `/play-history` and `GET /api/v1/play-history` separate contribution, comparability, trend, and interpretation decisions; use deterministic grouping, normalized pace, duration-weighted zones, neutral graphs, evidence context, and a supporting-report drill-down. Comparisons remain provisional and descriptive. |
| Legacy route redirects | COMPLETE | `/matches` redirects to `/analyses`; `/performance` redirects to `/play-history`; analysis deep links are unchanged. |
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
- Versioned history contribution, comparability, grouping, aggregation, trend, and
  interpretation policies in `app/services/history/`.

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
| `/performance` | COMPLETE REDIRECT | Redirects to `/play-history`. |
| `/analyses` | COMPLETE FOR PRIVATE ALPHA | Every persisted analysis with technical evidence and contribution context. |
| `/play-history` | COMPLETE FOR PRIVATE ALPHA | Neutral observed-change baseline/comparison view with evidence denominators and report drill-down. |
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
- Phase 1.3B candidates: 80 (5 STRONG, 25 USABLE, 50 UNCERTAIN)
- Processing: 1,836 frames, 168.62 seconds, CPU only, Docker `--network none`
- Candidate post-processing: 2.149 seconds build plus 11.343 seconds previews
- Result: CONTROLLED DEMO READY WITH REVIEW LIMITATIONS

Interpretation:

- The five STRONG representative crops are visibly on court; a seated sideline
  spectator was downgraded using factual court-position coverage.
- All four court-player appearances are available in the ranked review list, but
  duplicate visible-player and spectator candidates remain.
- The vertical real clip now produces one USABLE selectable candidate and one
  UNCERTAIN candidate. Suitability is LIMITED, not silently passed.
- This is still a generic person detector and must not be described as
  player-only detection or identity recognition.

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
| Docker build | COMPLETE | `docker build -t court4:local .` passed. |
| Pytest | COMPLETE | `86 passed, 1 warning in 10.56s`. Warning is the upstream Starlette/httpx TestClient deprecation. |
| Ruff check | COMPLETE | `All checks passed!` |
| Ruff format check | COMPLETE | `75 files already formatted`. |
| Mypy | COMPLETE | `Success: no issues found in 75 source files`. |
| Live `/health` | COMPLETE | HTTP 200 and `{"status":"ok"}` from `court4:local` on temporary port 18000. |
| Live `/docs` | COMPLETE | HTTP 200 with Swagger UI from `court4:local` on temporary port 18000. |

Frontend validation:

| Check | Result | Notes |
| --- | --- | --- |
| Lint | COMPLETE | `next lint` passed with no warnings or errors. |
| Typecheck | COMPLETE | `tsc --noEmit` passed. |
| Vitest | COMPLETE | `17 passed (17 files), 71 passed (71 tests)`. Vite CJS API deprecation warning only. |
| Production build | COMPLETE | Build passed with the documented `NEXT_PUBLIC_COURT4_*` variables. |
| Browser E2E | COMPLETE | `npm.cmd run e2e`: `5 passed (18.7s)` for happy path, fragmented candidate, manual review persistence, manual calibration, and missing-model recovery. |

Environment notes:

- Running `npm.cmd run build` without the required `NEXT_PUBLIC_COURT4_*` variables fails during prerender of `/matches/upload`.
- A stale concurrent Next dev server on port 3000 produced mixed `.next` artifacts and caused a missing vendor chunk in `next start`; stopping the dev server and rebuilding from a clean `.next` fixed it.
- Avoid running `next dev`, `next build`, and `next start` concurrently in the same `web/` directory.

Focused smoke validation:

| Smoke Path | Result | Notes |
| --- | --- | --- |
| Controlled full API workflow | COMPLETE | `test_full_controlled_api_workflow` and `test_full_controlled_api_workflow_with_automatic_court_detection`: `2 passed, 1 warning`. |
| Tracking eligibility and Match IQ rules | COMPLETE | `test_tracking_pipeline_outputs_and_eligibility` and `test_match_iq_generates_factual_evidence_backed_insights`: `2 passed`. |
| Real-model smoke | PARTIAL | Two unique local clips were post-processed from preserved CPU YOLO observations. Landscape is reviewable with duplicate/spectator candidates; vertical now has one USABLE candidate and a LIMITED warning. |
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

README is reconciled through Phase 1.3B for the local MVP workflow.

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
| Generic person detector tracks all people before filtering | HIGH | PARTIAL | Candidate quality/ranking and rejection help, but the review list can still contain spectator and duplicate candidates. |
| Fragment association can leave duplicates or build ambiguous long chains | HIGH | PARTIAL | Temporal overlap, side, speed, size, and appearance guards are deterministic; manual review and labeled evaluation remain necessary. |
| Model dependency requires a local untracked file | HIGH | PARTIAL | Compose now mounts `./models:/app/models:ro`, but `models/yolo11n.pt` must still be provided locally. |
| Synchronous API processing can time out on long videos | HIGH | PARTIAL | No queue, worker, cancellation, or progress polling beyond frontend pending states. |
| No auth or user isolation | HIGH | NOT IMPLEMENTED | Local-only MVP assumption. Unsafe for multi-user hosting. |
| Filesystem persistence has no locking | MEDIUM | PARTIAL | Concurrent requests can race on JSON/artifact writes. |
| CLI analytics Match IQ parity | MEDIUM | COMPLETE | CLI uses shared Match IQ persistence and writes/reuses `match_iq.json`. |
| Manual calibration UI missing | MEDIUM | COMPLETE | Interactive fallback route is implemented and tested. |
| Local history lacks account isolation | HIGH | PARTIAL | History now survives refresh through filesystem-backed list projections, but there is no auth, player ownership, database, or cross-device sync. |
| No browser E2E suite | MEDIUM | COMPLETE | Playwright suite covers controlled happy path, manual calibration fallback, and missing-model recovery. |
| Frontend build requires explicit public env vars | LOW | PARTIAL | Expected for Next, but missing `.env.local` causes build failure. |

## 13. Do Not Continue Before Fixing

Required before a real beta or a history/progress phase:

1. Reduce the real-video candidate-review load.
   - Landscape validation is demo-usable but still includes duplicate player and
     spectator candidates.
   - Far-court subjects remain fragmented and often USABLE rather than STRONG.
   - Do not claim player-only or identity detection.

2. Decide the expected operating envelope for real uploads.
   - Current validation supports a controlled real-match demonstration, not arbitrary public uploads.
   - Camera position, clip duration, visible full court, and spectator placement should be documented as demo requirements.

Recommended before the next feature phase:

1. Add a backend list endpoint if the workspace should become more than browser-local recent IDs.
2. Add write locking or idempotency protection around job state transitions.
3. Add an optional local real-model validation script that summarizes existing videos without committing weights or videos.

## 14. Phase 1.4 Integrity Update

Phase 1.4 now separates recording quality from candidate quality. Video inspection
persists upload preflight; calibration/tracking/candidate evidence persists analysis
readiness. Both are exposed in typed job and workflow responses with passed checks,
warnings, blocking failures, human guidance, and technical reason codes.

Match IQ now uses separate recording, tracking, measurement, interpretation, and
recommendation confidence. Limited evidence produces measurement-only output, and
unsuitable evidence suppresses normal insight cards. The unsupported observed-span
first/second-half rules are disabled because persisted timeline positions do not carry
fragment continuity.

The thresholds are initial engineering safeguards, not validated quality probabilities.
The real landscape recording is now `UNSUITABLE` because its 368-pixel short edge is
below the blocking resolution threshold. The vertical recording is `LIMITED`: it is
720p/30 FPS and long enough for preflight, but vertical framing, a merely `USABLE`
candidate, and limited tracked duration suppress interpretation and recommendations.

## 15. Roadmap Recommendation

Recommended next phase: focused real-video continuity hardening with labeled
tracks, review-list reduction, and broader camera/lighting validation.

Player History and Progress should wait until Court4 can reliably produce a selectable
player track on the intended real-video operating envelope. Any future history phase
must preserve the Match IQ safety boundary: no unsupported coaching claims, no
LLM-generated claims, no ball tracking, no shot/rally/score inference, and no
comparison unless stored prior match data supports it.

## 16. Phase 1.5 Calibration Update

Court4 now has a strict, versioned real-video calibration manifest and structured human
review schema. The internal CLI reuses persisted artifacts, recomputes only inexpensive
Phase 1.4 policies in memory, measures quality/gate/candidate/insight outcomes, reports
stale or missing artifacts, and continues after individual sample failures.

The two existing real recordings are seeded without copying video files. Current
policy-consistency results are exact for both documented quality decisions:

- landscape: `UNSUITABLE` with `INSUFFICIENT_EVIDENCE` suppression;
- vertical: `LIMITED` with measurement-only eligibility.

These are two partially reviewed samples derived from existing reports, not independent
ground truth. Candidate schema artifacts and the landscape Match IQ artifact are legacy,
the vertical sample lacks selected-player analytics, and identity/measurement error is
not labeled. All percentages are provisional. Threshold simulations produced
regressions for both tested alternatives and did not change production policy.

The calibration tool remains CLI-only and internal. The next evidence milestone is a
larger, independently reviewed dataset with frame-level identity and continuity labels.

## 17. Phase 1.5A Dataset Expansion Update

The calibration manifest now accepts schema v1 and additive schema v2. Schema v2 adds
typed recording metadata, development/validation/holdout splits, stable real-player IDs,
candidate-fragment mappings, optional continuity intervals, and per-insight review
without requiring complete annotation.

Dataset management remains internal and CLI-based. Commands generate overwrite-safe
templates, validate one sample, summarize balance, list incomplete reviews, report
artifact readiness, show unresolved mappings, and identify pending insight review.
Generated reports cannot edit the manifest.

The two seed samples retain all existing labels. New identity, interval, and per-insight
fields remain explicitly unreviewed. Landscape is development and vertical is
validation; no holdout exists, so threshold findings remain exploratory and
provisional.

Artifact readiness is explicit. The landscape chain is `LEGACY_COMPATIBLE`; the vertical
chain is `PARTIAL`. Unversioned inspection, court, tracking, and analytics artifacts are
reported as unversioned rather than assigned invented versions.

The balance report identifies missing outdoor, singles, ideal-quality, diagonal,
distance, 1080p, stability, several obstruction, `EXCELLENT`, `GOOD`, and holdout
coverage. Actual collection, consent, independent review, and adjudication remain human
work.

## 18. Phase 1.6A Shadow Active Play Update

Court4 now has an isolated `active-play-v1` evidence stage. It derives time-based,
gap-safe motion windows from persisted tracking/candidate artifacts and emits only
`LIKELY_ACTIVE`, `LIKELY_IDLE`, or `UNKNOWN`. Every estimate includes confidence,
coverage, signals, deterministic reasons, limitations, source lineage, and policy
version. Adjacent windows merge only across continuous boundaries with the same state.

The stage persists `active_play/features.jsonl`, `windows.jsonl`, and
`active_play.json`. It is available only from the internal debug route and does not
alter job state, distance, zones, heatmaps, Match IQ, cards, dashboards, or frontend
contracts. Legacy analyses continue to load without an Active Play artifact.

The existing landscape and vertical tracking artifacts were evaluated without
inference. Both use legacy candidate schema v1 and lack current recording-readiness
evidence, so all 61.2 landscape seconds and all 14.4 vertical seconds abstain as
`UNKNOWN`. No human Active Play label was invented.

Calibration schema v2 now accepts partial interval reviews and reports raw seconds and
interval counts for agreement, false-active, false-idle, unknown, boundary error,
abstention, and coverage. Active Play threshold simulations exclude validation and
holdout samples and cannot mutate the production policy or reviewer labels.

Active Play remains shadow-only and unvalidated. Rally, point, serve, shot, ball,
scoring, and tactical detection remain not implemented. Player-facing activation
requires a balanced independently reviewed dataset, reviewed false-positive/negative
budgets, boundary and abstention targets, a frozen policy review, and complete
regression approval.
