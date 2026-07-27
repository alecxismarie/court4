# Court4 Phase 1.6A — Shadow Active Play Framework

Date: 2026-07-27

## Implementation verdict

COMPLETE FOR INTERNAL SHADOW USE.

Court4 now produces deterministic, traceable estimates using only `LIKELY_ACTIVE`,
`LIKELY_IDLE`, and `UNKNOWN`. The feature is unvalidated, unavailable in the normal
player workflow, and does not claim rally, point, serve, shot, ball, score, or tactical
detection.

The contract is in `ACTIVE_PLAY_DESIGN.md`. Reviewer workflow and activation gates are
in `ACTIVE_PLAY_CALIBRATION_GUIDE.md`.

## Architecture and motion evidence

`app/services/active_play/` contains an immutable provisional policy, time-derived
feature construction, deterministic classification/merging, and atomic artifact
persistence. `app/schemas/active_play.py` contains the strict versioned contract.

Three-second windows derive:

- smoothed speed;
- time-based velocity and speed-change proxy;
- normalized movement intensity;
- direction-change frequency;
- stationary duration;
- elapsed tracked coverage;
- visible and reliably observed player counts;
- simultaneous movement duration;
- per-window gap severity;
- candidate continuity;
- low-movement kitchen safeguards.

Smoothing and derivatives never cross raw-track boundaries or observation gaps over
0.75 seconds. Coverage is elapsed time with enough reliable streams, not candidate
duration. All policy values in `policy.py` are provisional engineering thresholds.

## Policy and intervals

`LIKELY_ACTIVE` requires sufficient multi-player coverage, sustained movement, and
simultaneous movement. `LIKELY_IDLE` requires sufficient multi-player coverage and
sustained low activity; low movement near the kitchen abstains. Weak, stale,
unsuitable, short, fragmented, occluded, one-player-only, gap-heavy, or conflicting
evidence becomes `UNKNOWN`.

Reason codes are typed. Key positive reasons are
`SUSTAINED_MULTI_PLAYER_MOVEMENT`, `SIMULTANEOUS_MOVEMENT`,
`MEANINGFUL_DIRECTION_CHANGES`, `SUSTAINED_LOW_MOVEMENT`, and
`SUFFICIENT_TRACKED_COVERAGE`. Safeguards include
`INSUFFICIENT_TRACKED_COVERAGE`, `ONE_PLAYER_ONLY`, `SEVERE_TRACKING_GAPS`,
`STALE_SOURCE_ARTIFACT`, `SHORT_CONTEXT`,
`KITCHEN_LOW_MOVEMENT_SAFEGUARD`, and `CONFLICTING_EVIDENCE`.

Adjacent windows merge only when state and time boundary are compatible. Unknown
windows never bridge active windows. Merged confidence is the weaker value; coverage,
signals, reasons, limitations, candidate IDs, raw-track lineage, and source-window
count remain explicit. Short and rapidly changing intervals are retained.

## Persistence and API

Generation atomically persists:

- `active_play/features.jsonl`;
- `active_play/windows.jsonl`;
- `active_play/active_play.json`.

Reports include schema/policy version, source SHA-256 values, confidence, coverage,
reasons, limitations, and lineage. Matching sources and policy return the existing
artifact byte-for-byte; stale combinations fail rather than overwrite.

Only these internal debug routes expose the report:

- `POST /api/v1/analyses/{analysis_id}/debug/active-play`;
- `GET /api/v1/analyses/{analysis_id}/debug/active-play`.

Missing legacy artifacts return `active_play_not_ready` without breaking the analysis.
No database migration was needed. Normal analytics responses and job state do not
include Active Play.

## Calibration

Manifest schema v2 now supports partial Active Play intervals with reviewed
boundaries, expected state, boundary tolerance, Court4 state/boundaries, reviewer
confidence, false-active, false-idle, unknown-but-reviewable, uncertain human label,
and notes.

Reports include raw seconds and interval counts for reviewed duration,
likely-active/likely-idle agreement, false-active, false-idle, unknown, boundary
error, abstention, and coverage. Uncertain/unreviewed human labels stay out of
agreement denominators. Development-only simulations read persisted features;
validation and holdout samples are excluded. Policy and labels are never mutated.

## Existing sample results

Both samples were evaluated from existing tracking/candidate files with no inference:

| Sample | Windows | Source seconds | Active | Idle | Unknown | Readiness |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Landscape | 21 | 61.2 | 0.0 | 0.0 | 61.2 | Legacy candidate schema v1 |
| Vertical | 5 | 14.4 | 0.0 | 0.0 | 14.4 | Legacy candidate schema v1 |

Both reports are artifact-ready, but their evidence is not classification-ready.
Every window is `UNKNOWN` with `STALE_SOURCE_ARTIFACT`; vertical also has insufficient
reliable-player coverage. Human Active Play review remains zero seconds across zero
intervals. No label was invented.

## Regression protections

Tests cover smoothing, timestamps, velocity, speed change, direction changes,
stationary time, coverage, player reliability, simultaneous movement, gaps, active,
idle, abstention, kitchen/stationary safeguards, occlusion, one-player evidence,
merging, lineage, deterministic persistence, policy versioning, stale artifacts,
legacy analyses, unchanged analytics/Match IQ files, interval metrics, and holdout-safe
simulation.

Player-facing distance, heatmaps, zone percentages, Match IQ, share cards, summaries,
and frontend contracts were not changed. No frontend validation was run because no
frontend file or shared browser contract changed.

## Validation

Final results:

- `docker build -t court4:phase16a .` — PASS. Initial build: 334.7s; corrected cached
  build after adding `calibration/` to the image: 71.8s; exact final cached rebuild:
  6.4s.
- `docker run --rm court4:phase16a python -m pytest -q` — PASS, 139 tests.
- Focused Active Play/calibration/API suite — PASS, 44 tests.
- `ruff check app tests` — PASS.
- `ruff format --check app tests` — PASS, 88 files formatted.
- `mypy app` — PASS, 71 source files.
- `/health` — HTTP 200, `{"status":"ok"}`.
- `/docs` — HTTP 200.
- Calibration v1 validation — PASS, schema 1, 2 samples.
- Calibration v2 validation — PASS, schema 2, 2 samples.
- Calibration evaluation — PASS, 2 samples, 0 expensive inference runs.
- Two report generations — identical SHA-256 hashes.
- Repeated landscape/vertical seed generation reused existing artifacts; report
  hashes remained `208fdd5824050584…` and `9d12277618dfb7af…`.
- `calibration/manifest.v2.json` hash unchanged across evaluation:
  `040725c49ad79590e96be3155b70d29dd6f5256e3424135c8176580e1ec5768c`.
- `active-play-v1` policy file hash unchanged across evaluation:
  `62a34b23d3bf8533a2ad968a68e9071c54a60a4daaa289e081643cb35a9411c0`.
- Reviewer labels overwritten — none.
- Production threshold changes — none.

One first fresh-image pytest run failed because the Dockerfile did not copy the
tracked calibration manifests. `COPY calibration ./calibration` fixed the packaging
defect; the rebuilt image passed all 139 tests.

Warnings:

- one existing Starlette `TestClient` deprecation warning;
- pip emitted its standard root-user warning during Docker build;
- current sample count and human Active Play review duration are insufficient for any
  accuracy claim.

## Changed files

Core:

- `app/schemas/active_play.py`
- `app/services/active_play/__init__.py`
- `app/services/active_play/policy.py`
- `app/services/active_play/features.py`
- `app/services/active_play/engine.py`
- `app/services/active_play/persistence.py`
- `app/services/jobs/workflow.py`
- `app/api/v1/analyses.py`

Calibration and reports:

- `app/schemas/evidence_calibration.py`
- `app/services/evidence_calibration/dataset.py`
- `app/services/evidence_calibration/evaluator.py`
- `app/services/evidence_calibration/reporting.py`
- `calibration/manifest.v2.json`
- `calibration/sample-template.v2.json`
- `calibration-results.json`
- `CALIBRATION_REPORT.md`
- `CALIBRATION_DISAGREEMENTS.md`

Tests/build/docs:

- `tests/test_active_play.py`
- `tests/test_api_workflow.py`
- `tests/test_evidence_calibration.py`
- `Dockerfile`
- `ACTIVE_PLAY_DESIGN.md`
- `ACTIVE_PLAY_CALIBRATION_GUIDE.md`
- `README.md`
- `CURRENT_STATE_AUDIT.md`
- `PHASE_1_6A_REPORT.md`

`PHASE_1_6_PRODUCT_READINESS_AUDIT.md` was supplied as source material and was not
edited.

## Known limitations and activation conditions

No ball evidence exists. Warm-up and retrieval can resemble play; slow live play can
resemble idle. Candidate association, court calibration, occlusion, vertical framing,
and recording quality remain upstream risks. The policy is deterministic but not
validated, and the current two-video dataset has no human Active Play intervals.

Before player-facing activation, Court4 needs a balanced, consented, independently
reviewed development/validation/holdout dataset; reviewed false-active/false-idle
budgets; acceptable boundary error, abstention, and coverage; stable current-schema
tracking artifacts; frozen policy review; privacy/product approval; and full
player-facing regression review.

Recommended next step: perform Phase 1.6A calibration only—collect and adjudicate
partial Active Play interval labels across current-schema recordings. Do not begin
rally segmentation or Phase 1.6B.
