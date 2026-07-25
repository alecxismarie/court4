# Court4 Phase 1.5A — Calibration Dataset Expansion Design

## Purpose and boundary

Phase 1.5A prepares the existing calibration framework for a deliberately collected,
independently reviewed set of approximately 20–30 recordings. It improves the data
contract, onboarding, annotation diagnostics, balance reporting, artifact compatibility,
metrics, and disagreement review.

It does not collect the recordings, infer missing human labels, tune production
thresholds, add coaching intelligence, or expose calibration in the player workflow.

## Phase 1.5 workflow audit

The Phase 1.5 workflow is a safe foundation:

1. `calibration/manifest.v1.json` identifies videos and split persisted artifacts.
2. Strict Pydantic models reject malformed manifests and unknown fields.
3. The CLI reuses artifacts and runs only inexpensive policy functions in memory.
4. Evaluation continues after missing, invalid, or stale sample artifacts.
5. JSON and Markdown reports are deterministic and cannot overwrite the manifest.
6. All ratios show raw counts and are provisional below five reviewed samples.

The original manifest remains readable and unchanged.

## Missing labels and annotation bottlenecks

The two seed samples contain aggregate recording, candidate, tracking, and insight
judgments, but they do not contain:

- stable real-player identities;
- candidate-fragment-to-player mappings;
- reviewed duplicate or spectator candidate counts;
- selected-player identity labels;
- interval-level identity, continuity, gap, occlusion, or observed-time labels;
- per-insight measurement, interpretation, confidence, limitation, action, or wording
  review;
- independently reviewed camera distance, lighting, or stability; or
- a holdout sample.

The largest bottleneck is identity annotation. Candidate fragments need to be compared
with the video by a human, and one real player may legitimately map to several
candidates. Interval annotation is intentionally optional so reviewers can label useful
segments without annotating every frame.

## Artifact compatibility risks

The current inspection, court-calibration, tracking, and analytics JSON files do not
carry explicit schema versions. A successfully parsed artifact is reported as
`UNVERSIONED` rather than being assigned an invented version.

Both seed candidate collections use schema 1 while the current candidate schema is 3.
The landscape Match IQ artifact uses engine v1 while the current engine is v2. These
remain readable and are classified `LEGACY_COMPATIBLE`.

The vertical sample has no selected-player analytics, timeline, or Match IQ reference
and is classified `PARTIAL`. Invalid artifacts are `INCOMPATIBLE`; entirely unavailable
chains are `MISSING`. Evaluation continues for other stages and samples.

## Required dataset balance

The centralized balance policy is defined by `DatasetBalancePolicy` in
`app/services/evidence_calibration/dataset.py`:

- recommended collection size: 20–30 samples;
- minimum representation warning boundary: two samples per category value; and
- reporting only—imbalance never blocks evaluation.

Coverage is summarized across:

- indoor/outdoor;
- singles/doubles;
- ideal/poor recording conditions;
- landscape/vertical;
- baseline/diagonal camera positions;
- near/distant placement;
- 720p/1080p;
- stable/unstable recording;
- obstruction levels;
- strong/fragmented tracking;
- all four recording-quality outcomes; and
- development/validation/holdout splits.

Unknown and unreviewed metadata does not count as represented coverage.

## Schema v2 design

Schema v2 is additive and preserves the v1 field names. New samples can record:

- typed recording environment, format, camera placement, distance, lighting, stability,
  obstruction, visibility, orientation, resolution, and FPS;
- separate external, local-uncommitted, and persisted-artifact references;
- stable player IDs and multiple candidate fragments per real player;
- candidate roles: court player, spectator, duplicate, uncertain, or false detection;
- optional interval reviews with validated time ranges and no overlap for the same
  expected player;
- per-insight review fields; and
- `DEVELOPMENT`, `VALIDATION`, or `HOLDOUT` assignment.

`UNKNOWN` means a reviewer cannot establish the value. `NOT_REVIEWED` means no review
was completed. Neither is treated as a negative label.

## Threshold safety

Threshold simulations use only `DEVELOPMENT` samples. Validation and holdout samples are
listed as excluded and cannot produce simulated gains or losses. Every proposal remains
exploratory, reports regressions, and uses an immutable copy of the production threshold
set.

With only two samples, the split is not meaningful for generalization: landscape is
development, vertical is validation, and there is no holdout. The report states this
explicitly.

## CLI workflow

The CLI now supports:

- whole-manifest and single-sample validation;
- safe template generation with explicit overwrite permission;
- dataset-balance summary;
- incomplete-review listing;
- missing, stale, and incompatible artifact listing;
- unresolved candidate mapping listing;
- per-insight review status; and
- deterministic evaluation and report regeneration.

Templates remain JSON files for deliberate human editing. Interactive terminal editing
was rejected because it would obscure diffs, complicate partial-label preservation, and
provide no reliable video annotation surface.

## Internal review UI decision

A development-only frontend is not justified yet. The repository has two samples, and
review requires side-by-side access to private local video, candidate identifiers, and
artifact files. A frontend that only edits manifest fields would add another
serialization path without solving video annotation.

The CLI and review templates are safer, diffable, and testable. A UI should be
reconsidered only when repeated reviewer errors show that the file workflow is the
limiting factor.

## Implementation changes

- Add schema v2 while accepting schema v1.
- Add interval, identity mapping, per-insight, split, compatibility, balance, and
  disagreement models.
- Add deterministic dataset-management CLI commands.
- Add explicit artifact readiness at stage and sample level.
- Extend candidate, continuity, and insight metrics using reviewed denominators only.
- Generate `CALIBRATION_DISAGREEMENTS.md`.
- Preserve `manifest.v1.json` and seed `manifest.v2.json` without inventing new labels.
- Document private-recording collection and annotation procedures.

Actual collection, consent, independent review, and adjudication remain human work.
