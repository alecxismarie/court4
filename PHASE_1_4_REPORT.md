# Court4 Phase 1.4 — Implementation Report

## Outcome

Phase 1.4 implements evidence-quality assessment and Match IQ abstention without adding
AI coaching, ball/rally detection, Player History, authentication, databases, or cloud
infrastructure.

## Implemented

- Added `INSIGHT_INTEGRITY_DESIGN.md` and `RECORDING_STANDARD.md`.
- Added a centralized typed recording-quality service with `EXCELLENT`, `GOOD`,
  `LIMITED`, and `UNSUITABLE`.
- Added upload preflight for format, orientation, resolution, FPS, and duration.
- Added analysis readiness for calibration, people/candidates, candidate quality,
  player visibility, tracked duration, gaps, and fragments.
- Persisted preflight in `metadata.json`/`job.json`; persisted readiness in
  `player_candidates.json`/`job.json`; exposed both in typed API responses.
- Refactored Match IQ to separate recording, tracking, measurement, interpretation, and
  recommendation confidence.
- Added deterministic normal, cautious, measurement-only, and insufficient-evidence
  gates.
- Suppressed interpretation/actions for measurement-only output and all normal insight
  cards for unsuitable evidence.
- Disabled first-half/second-half distance rules because the persisted timeline cannot
  prove continuity across fragments.
- Updated upload guidance, workflow readiness cards, evidence-led insight cards,
  concise dashboard/match states, and retry actions.
- Kept legacy jobs, analytics, candidate collections, and Match IQ reports readable.

## Real-video validation without inference rerun

Existing YOLO/ByteTrack and candidate artifacts were reused. No expensive inference was
rerun.

| Recording | Upload preflight | Final quality | Warnings/failures | Insight eligibility | Confidence and limitations | Suppression |
| --- | --- | --- | --- | --- | --- | --- |
| Landscape `dc4…590` / repro tracking | `UNSUITABLE` | `UNSUITABLE` | 640×368 at 30 FPS for 61.2 s; short edge is below the 480-pixel blocking threshold. Existing repro has 161 detected raw tracks, 80 active candidates, 30 usable/strong candidates, including 5 `STRONG`. | No normal Match IQ, even though candidate evidence exists. | Recording `LOW`; interpretation and recommendation `NOT_AVAILABLE`. Generic person detection, low resolution, duplicates/spectators, and unlabeled identity remain limitations. | Appropriate: Phase 1.3 Match IQ output must not be promoted; Phase 1.4 suppresses it. |
| Vertical `f546…258` / repro tracking | `LIMITED` | `LIMITED` | 720×1280 at 30 FPS for 14.4 s; vertical framing. Best candidate is `USABLE`, 14.27 observed s, 410 frames, one fragment, 100% in-court, with vertical/limited-movement warnings. | Measurement-only after user selection; no completed selected-player analytics exists in the reused artifact. | Recording `LOW` due limitations; tracking is usable but interpretation/recommendation are unavailable at the measurement-only gate. Narrow view and limited spatial coverage remain limitations. | Appropriate: measurements may be shown after selection; interpretation and recommendations are suppressed. |

These classifications follow initial engineering thresholds. They are not a labeled
accuracy result. In particular, the landscape result demonstrates that candidate quality
does not override recording quality.

## Automated validation

- Docker image `court4:phase14` built successfully.
- Backend: Ruff check and format check passed; mypy passed over 80 source files; 95
  pytest tests passed with one upstream Starlette/httpx deprecation warning.
- Frontend: ESLint and TypeScript passed; 75 Vitest tests passed; the production build
  passed.
- Playwright: 7 scenarios passed, covering good, limited, unsuitable, fragmented,
  manual-review persistence, calibration fallback, and missing-model recovery.
- Runtime: `/health` and `/docs` both returned HTTP 200.

## Remaining risks

- Thresholds require labeled-video validation and may change.
- Generic person detection still includes spectators and cannot prove active play.
- Candidate association still has duplicate/identity risk.
- Calibration and movement error are not statistically calibrated.
- Existing Phase 1.3 Match IQ JSON remains on disk for legacy analyses; it is readable,
  but it does not acquire Phase 1.4 confidence unless regenerated through the new flow.

## Verdict

The Phase 1.4 integrity contract is implemented. Court4 now leads with measured evidence,
exposes evidence limits, and abstains when recording or tracking support is weak. It does
not provide tactical or causal coaching.
