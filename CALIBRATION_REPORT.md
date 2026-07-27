# Court4 Calibration Report

Dataset: `court4-real-video-expansion` version `2.0.0`
Manifest SHA256: `040725c49ad79590e96be3155b70d29dd6f5256e3424135c8176580e1ec5768c`
Reference time: `2026-07-25T00:00:00+00:00`

## Dataset summary

- Samples: 2
- Reviewed or partially reviewed: 2
- Not reviewed: 0
- Expensive inference rerun: disabled; 0 inference runs performed
- Validation status: provisional; this dataset is not representative.

## Sample results

| Sample | Evaluation | Readiness | Human quality | Court4 quality | Expected gate | Court4 gate | Exact | Artifacts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| landscape-indoor-doubles-01 | PARTIAL | LEGACY_COMPATIBLE | UNSUITABLE | UNSUITABLE | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | yes | inspection_metadata:AVAILABLE, analysis_job:AVAILABLE, tracking:AVAILABLE, player_candidates:STALE, analytics:AVAILABLE, timeline:AVAILABLE, match_iq:STALE, active_play:AVAILABLE, court_calibration:AVAILABLE |
| vertical-indoor-drill-01 | PARTIAL | PARTIAL | LIMITED | LIMITED | MEASUREMENT_ONLY | MEASUREMENT_ONLY | yes | inspection_metadata:AVAILABLE, analysis_job:AVAILABLE, tracking:AVAILABLE, player_candidates:STALE, analytics:NOT_REFERENCED, timeline:NOT_REFERENCED, match_iq:NOT_REFERENCED, active_play:AVAILABLE, court_calibration:AVAILABLE |

## Recording-quality classification

- Exact agreement: 2/2 (100.0%) — provisional
- Acceptable agreement (exact or one adjacent level): 2/2 (100.0%) — provisional
- Quality overestimation count: 0
- Quality underestimation count: 0

Per expected status:

- `UNSUITABLE`: 1
- `LIMITED`: 1
- `GOOD`: 0
- `EXCELLENT`: 0

Confusion matrix (rows expected, columns Court4):

| Expected | UNSUITABLE | LIMITED | GOOD | EXCELLENT |
| --- | ---: | ---: | ---: | ---: |
| UNSUITABLE | 1 | 0 | 0 | 0 |
| LIMITED | 0 | 1 | 0 | 0 |
| GOOD | 0 | 0 | 0 | 0 |
| EXCELLENT | 0 | 0 | 0 | 0 |

## Evidence-gate outcomes

- Valid insights correctly allowed: 0/0 (not available) — provisional
- Weak insights correctly reduced to measurement-only: 1/1 (100.0%) — provisional
- Unsuitable insights correctly suppressed: 1/1 (100.0%) — provisional
- Valid insights incorrectly suppressed: 0
- Weak insights incorrectly allowed: 0
- Unsuitable insights incorrectly allowed: 0

## Candidate reliability

- Expected player recall: 6/6 (100.0%) — provisional
- Duplicate candidates: not reviewed
- Missed players: 0
- Spectator promotions: not reviewed
- Selected-player identity accuracy: 0/0 (not available) — provisional
- Candidate precision: 0/0 (not available) — provisional
- Candidate-to-player mapping accuracy: 0/0 (not available) — provisional
- Duplicate candidates per labeled sample: 0/0 (not available) — provisional
- Missed players per labeled sample: 0/2 (not available) — provisional
- Counts are included only where a reviewer supplied the corresponding label.

## Tracking-continuity review

- Reviewed intervals: 0
- Correctly maintained identity intervals: 0/0 (not available) — provisional
- Identity-switch intervals: 0
- Fragmented intervals: 0
- Valid observed-time agreement: 0/0 (not available) — provisional
- Gap-label agreement: 0/0 (not available) — provisional

## Shadow Active Play interval review

- Reviewed duration: 0.000s across 0 intervals
- Likely-active agreement: 0.000/0.000s (not available; 0 intervals) — provisional
- Likely-idle agreement: 0.000/0.000s (not available; 0 intervals) — provisional
- False-active: 0.000s across 0 intervals
- False-idle: 0.000s across 0 intervals
- Unknown: 0.000s across 0 intervals
- Abstention rate: 0.000/0.000s (not available; 0 intervals) — provisional
- Coverage rate: 0.000/0.000s (not available; 0 intervals) — provisional
- Boundary error: 0 boundaries; mean=not available; max=not available
- These are raw interval/duration measures, not broad accuracy.

## Insight-integrity findings

- Recording Quality Verdict Correct: 2/2 (100.0%) — provisional
- Confidence Levels Justified: 1/1 (100.0%) — provisional
- Measurement Only Decision Correct: 1/1 (100.0%) — provisional
- Suppression Decision Correct: 2/2 (100.0%) — provisional
- Interpretation Justified: 0/0 (not available) — provisional
- Limitations Accurate: 2/2 (100.0%) — provisional
- Wording Understandable: 0/0 (not available) — provisional
- Action Appropriately Conservative: 2/2 (100.0%) — provisional
- Recording Guidance Accurate: 1/1 (100.0%) — provisional
- Generated Measurement Correctness: 0/0 (not available) — provisional
- Generated Interpretation Justification: 0/0 (not available) — provisional
- Generated Confidence Appropriateness: 0/0 (not available) — provisional
- Generated Limitation Accuracy: 0/0 (not available) — provisional
- Generated Conservative Action Agreement: 0/0 (not available) — provisional
- Generated Wording Understandability: 0/0 (not available) — provisional

## Dataset balance

- Collection size: 2/20-30
- Minimum target per category value: 2

| Category | Counts | Missing | Underrepresented |
| --- | --- | --- | --- |
| environment | INDOOR=2, OUTDOOR=0 | OUTDOOR | none |
| match_format | SINGLES=0, DOUBLES=1 | SINGLES | DOUBLES |
| recording_condition | IDEAL=0, POOR=2 | IDEAL | none |
| orientation | LANDSCAPE=1, VERTICAL=1 | none | LANDSCAPE, VERTICAL |
| camera_position | BASELINE=2, DIAGONAL=0 | DIAGONAL | none |
| camera_distance | NEAR=0, DISTANT=0 | NEAR, DISTANT | none |
| resolution | 720P=1, 1080P=0 | 1080P | 720P |
| recording_stability | STABLE=0, UNSTABLE=0 | STABLE, UNSTABLE | none |
| obstruction | NONE=0, MINOR=0, MODERATE=1, SEVERE=0 | NONE, MINOR, SEVERE | MODERATE |
| tracking | STRONG=1, FRAGMENTED=1 | none | STRONG, FRAGMENTED |
| quality | EXCELLENT=0, GOOD=0, LIMITED=1, UNSUITABLE=1 | EXCELLENT, GOOD | LIMITED, UNSUITABLE |
| dataset_split | DEVELOPMENT=1, VALIDATION=1, HOLDOUT=0 | HOLDOUT | DEVELOPMENT, VALIDATION |

Provisional balance warnings:

- Dataset has 2 samples; recommended collection size is 20-30.
- environment: missing OUTDOOR
- match_format: missing SINGLES
- match_format: underrepresented DOUBLES (<2 samples)
- recording_condition: missing IDEAL
- orientation: underrepresented LANDSCAPE, VERTICAL (<2 samples)
- camera_position: missing DIAGONAL
- camera_distance: missing NEAR, DISTANT
- resolution: missing 1080P
- resolution: underrepresented 720P (<2 samples)
- recording_stability: missing STABLE, UNSTABLE
- obstruction: missing NONE, MINOR, SEVERE
- obstruction: underrepresented MODERATE (<2 samples)
- tracking: underrepresented STRONG, FRAGMENTED (<2 samples)
- quality: missing EXCELLENT, GOOD
- quality: underrepresented LIMITED, UNSUITABLE (<2 samples)
- dataset_split: missing HOLDOUT
- dataset_split: underrepresented DEVELOPMENT, VALIDATION (<2 samples)
- No holdout samples are present; final generalization is unmeasured.

## Artifact compatibility

| Sample | Stage | Actual version | Expected version | Compatibility |
| --- | --- | --- | --- | --- |
| landscape-indoor-doubles-01 | inspection_metadata | UNVERSIONED | UNVERSIONED | READY |
| landscape-indoor-doubles-01 | analysis_job | UNVERSIONED | UNVERSIONED | READY |
| landscape-indoor-doubles-01 | tracking | UNVERSIONED | UNVERSIONED | READY |
| landscape-indoor-doubles-01 | player_candidates | 1 | 3 | LEGACY_COMPATIBLE |
| landscape-indoor-doubles-01 | analytics | UNVERSIONED | UNVERSIONED | READY |
| landscape-indoor-doubles-01 | timeline | UNVERSIONED | UNVERSIONED | READY |
| landscape-indoor-doubles-01 | match_iq | match-iq-rules-v1 | match-iq-rules-v2 | LEGACY_COMPATIBLE |
| landscape-indoor-doubles-01 | active_play | active-play-v1 | active-play-v1 | READY |
| landscape-indoor-doubles-01 | court_calibration | UNVERSIONED | UNVERSIONED | READY |
| vertical-indoor-drill-01 | inspection_metadata | UNVERSIONED | UNVERSIONED | READY |
| vertical-indoor-drill-01 | analysis_job | UNVERSIONED | UNVERSIONED | READY |
| vertical-indoor-drill-01 | tracking | UNVERSIONED | UNVERSIONED | READY |
| vertical-indoor-drill-01 | player_candidates | 1 | 3 | LEGACY_COMPATIBLE |
| vertical-indoor-drill-01 | analytics | unavailable | unavailable | MISSING |
| vertical-indoor-drill-01 | timeline | unavailable | unavailable | MISSING |
| vertical-indoor-drill-01 | match_iq | unavailable | unavailable | MISSING |
| vertical-indoor-drill-01 | active_play | active-play-v1 | active-play-v1 | READY |
| vertical-indoor-drill-01 | court_calibration | UNVERSIONED | UNVERSIONED | READY |

## Common failure reasons

- `tracked_duration_limited`: 2
- `candidate_quality_usable`: 1
- `tracking_gaps_present`: 1
- `upload_preflight_blocked`: 1
- `upload_preflight_limited`: 1

## Policy error reasons

- False Acceptance: none observed
- False Suppression: none observed
- Quality Overestimation: none observed
- Quality Underestimation: none observed

## Threshold-analysis findings

### `blocking_short_edge_pixels`

- Current value: 480
- Proposed value: 360
- Affected samples: landscape-indoor-doubles-01
- Improvements: none
- Regressions: landscape-indoor-doubles-01
- Excluded validation/holdout samples: vertical-indoor-drill-01
- Unchanged samples: 0
- Exploratory: yes
- Remaining uncertainty: Exploratory development-split simulation only. Validation and holdout samples are excluded. The dataset is too small for a production recommendation, and production policy is not mutated.

### `minimum_tracked_seconds`

- Current value: 5
- Proposed value: 15
- Affected samples: none
- Improvements: none
- Regressions: none
- Excluded validation/holdout samples: vertical-indoor-drill-01
- Unchanged samples: 1
- Exploratory: yes
- Remaining uncertainty: Exploratory development-split simulation only. Validation and holdout samples are excluded. The dataset is too small for a production recommendation, and production policy is not mutated.


## Active Play threshold-analysis findings

- No Active Play threshold simulations were requested.
## Samples requiring manual review

- `landscape-indoor-doubles-01`
- `vertical-indoor-drill-01`

## Dataset limitations

- The dataset contains 2 samples; balance and review coverage must be assessed before interpreting aggregate metrics.
- Sample count is below the manifest minimum of 5.
- Unreviewed and unknown labels are excluded; incomplete coverage remains provisional.
- This report is a deterministic framework evaluation, not scientific validation.
- Some reusable artifacts are legacy-compatible rather than current.
- At least one sample has a partial artifact chain.
- No holdout sample exists; generalization remains unmeasured.
- No interval-level tracking ground truth is currently reviewed.

## Recommended next actions

1. Complete independent review for samples listed as requiring manual review.
2. Collect toward the documented 20-30 sample target and address balance gaps.
3. Collect landscape and vertical recordings across lighting, camera distance, obstruction, and spectator conditions.
4. Add frame-level player identity and continuity labels before claiming candidate precision or tracking accuracy.
5. Keep all threshold changes manual; rerun this report and inspect regressions before any production edit.

## Verdict

The calibration framework is operational, but current coverage and review completeness remain insufficient for broad validation. Production thresholds remain unchanged.
