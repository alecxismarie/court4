# Court4 Calibration Disagreements

Dataset: `court4-real-video-expansion` version `2.0.0`
Manifest SHA256: `a10bc6660136365b660a9bffd96d8fa7bc37377dceb3e14d871a02d9fe9f2f2c`

This report identifies disagreements and incomplete annotations. It does not resolve labels or change policy.

Total findings: 2

## 1. `landscape-indoor-doubles-01` — INCOMPLETE_ANNOTATION

- Court4 output: PARTIAL
- Human expectation: Complete independent review
- Reason: Unreviewed fields: review_status, camera_distance, lighting_condition, recording_stability, human_review.player_candidates.stable_real_players, human_review.player_candidates.candidate_mappings, human_review.player_candidates.selected_player_identity_correct, human_review.tracking.intervals, human_review.insight.generated_insights
- Affected threshold or rule: not identified
- Artifact evidence: inspection_metadata:READY, analysis_job:READY, tracking:READY, player_candidates:LEGACY_COMPATIBLE, analytics:READY, timeline:READY, match_iq:LEGACY_COMPATIBLE, court_calibration:READY

## 2. `vertical-indoor-drill-01` — INCOMPLETE_ANNOTATION

- Court4 output: PARTIAL
- Human expectation: Complete independent review
- Reason: Unreviewed fields: review_status, match_format, camera_distance, lighting_condition, recording_stability, human_review.player_candidates.stable_real_players, human_review.player_candidates.candidate_mappings, human_review.player_candidates.selected_player_identity_correct, human_review.tracking.intervals, human_review.insight.generated_insights
- Affected threshold or rule: not identified
- Artifact evidence: inspection_metadata:READY, analysis_job:READY, tracking:READY, player_candidates:LEGACY_COMPATIBLE, analytics:MISSING, timeline:MISSING, match_iq:MISSING, court_calibration:READY
