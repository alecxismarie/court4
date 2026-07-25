# Court4 Phase 1.5 — Real-Video Evidence Calibration Design

## Purpose and boundary

Phase 1.5 evaluates the Phase 1.4 recording-quality, evidence-gating, confidence,
measurement-only, and suppression policies. It does not add a new intelligence
subsystem, mutate production thresholds, rerun detector inference by default, or add
player-facing annotation controls.

The framework is deterministic and repository-native:

1. a versioned JSON manifest describes samples, reusable artifact locations, expected
   outcomes, and structured review labels;
2. strict Pydantic schemas validate the manifest and review data;
3. a CLI reads existing artifacts and recomputes only inexpensive policy decisions in
   memory;
4. an evaluator compares Court4 output with available labels and aggregates raw counts;
5. JSON and Markdown reports are written without machine-specific absolute paths.

## Phase 1.4 audit

### What is currently measurable

| Layer | Persisted or derivable evidence | Evaluation use |
| --- | --- | --- |
| Upload inspection | Extension, width, height, orientation, FPS, duration | Re-run upload preflight deterministically and compare the quality status. |
| Court recognition | Calibration artifact, recognition status, heuristic confidence | Confirm artifact availability; do not treat heuristic confidence as a calibrated probability. |
| Person tracking | Raw track count, track summaries, observation artifacts, model name | Report availability and detector coverage without claiming player identity accuracy. |
| Player candidates | Candidate count, quality, eligibility, raw fragments, in-court ratio, duration, gaps, review state | Derive analysis readiness and compare candidate counts where human labels exist. |
| Analytics | Continuity-safe duration, fragments, gaps, distance, zones, timeline count | Re-run Match IQ policy decisions in memory when analytics exist. |
| Match IQ | Gate, five confidence dimensions, interpretation/action suppression, limitations | Compare eligibility and human integrity labels; flag legacy engine output as stale. |

### Configurable policies

`RecordingQualityThresholds` centralizes:

- blocking, minimum, and excellent short-edge resolution;
- blocking, minimum, and excellent FPS;
- minimum and excellent recording duration;
- minimum and excellent tracked duration;
- minimum and excellent visibility ratio;
- warning and blocking gap ratio; and
- maximum candidate fragments.

Match IQ separately defines minimum observations, minimum tracked seconds, cautious
tracked seconds, and descriptive rule thresholds. Phase 1.5 reports these values but
does not change them.

Threshold simulation creates an immutable copy of `RecordingQualityThresholds`, reruns
the same assessment functions in memory, and reports affected samples, improvements,
regressions, and uncertainty. It never assigns to the production constant.

### Outputs that can be evaluated automatically

- exact and adjacent-level recording-quality agreement;
- overestimation and underestimation;
- recording-quality confusion matrix;
- expected versus actual evidence gate;
- false acceptance and false suppression;
- aggregate candidate recall inputs, duplicate/miss/spectator counts, and selection
  accuracy when those labels are present;
- boolean insight-integrity review outcomes;
- missing artifact and stale schema/engine warnings; and
- threshold-simulation deltas.

### Outcomes that require human review

- whether the full court is actually visible;
- camera stability, obstruction, and player image size;
- whether a detection represents an active court player;
- duplicate identities, missed players, spectator promotion, and selected identity;
- continuity and fragmentation acceptability;
- whether confidence rationales are justified;
- whether an interpretation is warranted;
- whether limitations are complete and understandable; and
- whether a review action is appropriately conservative.

The evaluator never fabricates these labels from detector output.

## Calibration data contract

The manifest uses a strict, versioned JSON schema. Unknown fields are rejected. Sample
IDs must be unique and stable. Artifact paths must be repository-relative, and analysis
IDs are validated before resolving paths beneath the configured artifact root.

Each sample may contain:

- recording environment and camera metadata;
- expected recording quality and insight eligibility;
- references to separate inspection, court, tracking, candidate, analytics, and Match IQ
  analysis directories;
- artifact-reuse notes and expected schema versions;
- partial structured recording, candidate, tracking, and insight reviews;
- overall review status, reviewer confidence, and notes; and
- explicit threshold simulations at manifest level.

`UNKNOWN` means the reviewer cannot establish a verdict. `NOT_REVIEWED` means no review
has occurred. Missing optional fields remain missing and are excluded from metrics.

## Artifact reuse and freshness

The two available real videos have split legacy artifacts:

- source analysis directories contain inspection/court data;
- Phase 1.3A repro directories contain preserved YOLO/ByteTrack tracking and Phase 1.3B
  candidate data;
- only the landscape source has legacy analytics and Match IQ.

The evaluator therefore permits per-stage analysis IDs. It reads artifacts but never
writes into analysis directories. Current upload/readiness assessments and Match IQ are
computed in memory with a manifest reference time. Existing candidate schema versions
and Match IQ engine versions are compared with current constants and reported as stale
when they differ.

Missing artifacts do not abort the dataset. The sample receives warnings and any
remaining comparable fields are still evaluated.

## Metrics and sample-size policy

Every metric reports numerator, denominator, percentage, and a `provisional` flag. A
metric is provisional below five reviewed samples. Percentages remain descriptive raw
ratios and are never presented as scientific accuracy.

Acceptable recording-quality agreement means an exact match or one adjacent level on:

`UNSUITABLE < LIMITED < GOOD < EXCELLENT`.

`UNKNOWN` and `NOT_REVIEWED` labels are excluded from agreement denominators.

Evidence-gate categories are evaluated as:

- valid: `NORMAL` or `CAUTIOUS`;
- weak: `MEASUREMENT_ONLY`;
- unsuitable: `INSUFFICIENT_EVIDENCE`.

Candidate and insight-integrity metrics are calculated only for explicitly labeled
fields.

## Internal interface decision

No frontend calibration page is justified in Phase 1.5. The current product frontend is
player-facing, while calibration requires local artifact access, schema diagnostics,
partial labels, and reproducible batch output. A CLI plus human-readable manifest keeps
the tool clearly internal and avoids exposing technical evaluation state to players.

This decision can be revisited only after the dataset and review workflow are large
enough to make a dedicated annotation surface materially safer than direct manifest
review.

## Current dataset limitations

- Only two unique real videos are available.
- Both are indoor recordings from a behind-baseline position.
- The landscape clip is low resolution; the vertical clip is short and vertically
  framed.
- Labels come from existing documented manual review, not an independent blinded review.
- Candidate identity, duplicate count, missed intervals, position error, distance error,
  and zone-occupancy error do not have frame-level ground truth.
- Neither sample has a complete Phase 1.4 artifact chain; legacy artifacts must be
  interpreted with freshness warnings.
- The vertical sample has no selected-player analytics artifact.

The resulting report is a framework smoke evaluation and policy-consistency check. It is
not scientific validation and cannot support broad accuracy claims.
