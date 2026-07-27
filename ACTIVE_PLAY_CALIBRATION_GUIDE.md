# Court4 Shadow Active Play Calibration Guide

## Scope

This workflow reviews `active-play-v1` estimates. It does not label rallies, points,
serves, shots, ball movement, scores, or tactics. Never infer a human label from the
Court4 output, and never overwrite an existing reviewer label.

## Review workflow

1. Generate or reuse `active_play/active_play.json`, `features.jsonl`, and
   `windows.jsonl` without rerunning detector inference.
2. Watch only a bounded interval and add it to
   `human_review.active_play.intervals` in a schema-v2 calibration sample.
3. Record `start_time_seconds`, `end_time_seconds`, expected
   `LIKELY_ACTIVE`/`LIKELY_IDLE` or `UNCERTAIN`, boundary tolerance, reviewer
   confidence, Court4 state, and notes.
4. If Court4 boundaries are reviewable, record both Court4 boundary timestamps.
5. Mark false-active, false-idle, or unknown-but-reviewable explicitly. Use
   `uncertain_human_label` when the human judgment is not reliable.
6. Validate and evaluate the manifest. Inspect raw durations and disagreements before
   considering a threshold experiment.

Example:

```json
{
  "start_time_seconds": 15.0,
  "end_time_seconds": 42.0,
  "expected_state": "LIKELY_ACTIVE",
  "boundary_tolerance_seconds": 0.5,
  "court4_state": "UNKNOWN",
  "court4_start_time_seconds": 15.0,
  "court4_end_time_seconds": 42.0,
  "reviewer_confidence": "MODERATE",
  "false_active": false,
  "false_idle": false,
  "unknown_but_reviewable": true,
  "uncertain_human_label": false,
  "notes": "Partial interval review; no rally claim."
}
```

Adjacent intervals may touch but must not overlap. Supply Court4 start and end
together. Leave intervals empty when no human review exists.

## Metrics

The evaluator reports reviewed duration, likely-active and likely-idle agreement,
false-active duration, false-idle duration, unknown duration, boundary error,
abstention rate, and coverage rate. Every duration metric includes raw seconds and
interval counts. Uncertain and unreviewed human labels are excluded from agreement
denominators. These outputs are provisional calibration evidence, not broad accuracy.

## Threshold safety

Place exploratory changes in `active_play_threshold_simulations`. Only development
samples are eligible. Validation and holdout samples are listed as excluded.
Simulation reads persisted features, never runs inference, never edits reviewer
labels, and never mutates `ACTIVE_PLAY_POLICY`.

```bash
python -m scripts.calibrate_evidence validate calibration/manifest.v2.json
python -m scripts.calibrate_evidence evaluate calibration/manifest.v2.json
```

## Activation gate

Player-facing activation requires an independently reviewed, balanced dataset;
acceptable false-active and false-idle duration; acceptable boundary error; measured
abstention and coverage; frozen policy/version review; regression verification; and
explicit product/privacy approval. Until then, use only the internal debug artifact.

## Readiness view

`/internal/calibration` summarizes shadow interval counts, reviewed duration,
likely-active/likely-idle/unknown seconds, false-active and false-idle duration,
boundary review, abstention, coverage, artifact schema currency, and review blockers.
It does not compute new intervals or accept labels.

With the seeded samples, Active Play has two generated `UNKNOWN` intervals covering
75.6 seconds, zero reviewed intervals, zero reviewed seconds, zero current-schema
sample artifacts, and two stale-artifact samples. False-active, false-idle, boundary,
abstention, and coverage rates remain `NOT_REVIEWED`; they are not zero.

The verdict cannot advance from evidence collection until bounded human review covers
both likely-active and likely-idle examples, boundary labels, a holdout split,
current-schema artifacts, balanced conditions, and resolved critical findings.
