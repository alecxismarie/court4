# Court4 Calibration Guide

Phase 1.5A adds schema v2 for larger-dataset collection. Schema v1 remains readable,
and `calibration/manifest.v1.json` is preserved unchanged.

## Scope

The calibration workflow evaluates Court4's existing recording-quality and evidence
policies against structured review labels. It is an internal engineering tool, not a
player-facing feature or a scientific benchmark.

It does not:

- rerun detector inference by default;
- modify production thresholds;
- overwrite reviewer labels;
- add coaching rules; or
- establish broad accuracy from the two seed samples.

## Files

- Manifest: `calibration/manifest.v1.json`
- Expanded manifest: `calibration/manifest.v2.json`
- Sample template: `calibration/sample-template.v2.json`
- Manifest and review schema: `app/schemas/evidence_calibration.py`
- Evaluator: `app/services/evidence_calibration/evaluator.py`
- Report renderer: `app/services/evidence_calibration/reporting.py`
- CLI: `scripts/calibrate_evidence.py`
- Machine-readable output: `calibration-results.json`
- Human-readable output: `CALIBRATION_REPORT.md`

## Validate and evaluate

Validate the manifest without evaluating artifacts:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v1.json
```

Validate the expanded manifest or one sample:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v2.json
python -m scripts.calibrate_evidence validate-sample `
  calibration/manifest.v2.json landscape-indoor-doubles-01
```

Evaluate existing artifacts and regenerate both reports:

```powershell
python -m scripts.calibrate_evidence evaluate calibration/manifest.v1.json
```

Phase 1.5A evaluation uses v2 and also writes `CALIBRATION_DISAGREEMENTS.md`:

```powershell
python -m scripts.calibrate_evidence evaluate calibration/manifest.v2.json
```

Custom output paths:

```powershell
python -m scripts.calibrate_evidence evaluate calibration/manifest.v1.json `
  --json-output calibration-results.json `
  --markdown-output CALIBRATION_REPORT.md
```

The CLI prints the number of expensive inference runs. A normal evaluation must report
zero.

`--allow-expensive-recomputation` is an explicit permission flag. The current repository
does not configure an automatic inference hook, so the flag alone does not start
inference. Missing artifacts remain visible for manual resolution.

## Dataset-management commands

Generate an overwrite-safe sample template:

```powershell
python -m scripts.calibrate_evidence template outdoor-diagonal-01 `
  --output calibration/reviews/outdoor-diagonal-01.json
```

Inspect collection and review readiness:

```powershell
python -m scripts.calibrate_evidence summarize calibration/manifest.v2.json
python -m scripts.calibrate_evidence review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence artifact-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence unresolved-mappings calibration/manifest.v2.json
python -m scripts.calibrate_evidence insight-review-status calibration/manifest.v2.json
```

The template command refuses to overwrite an existing file unless `--force` is supplied.
Balance warnings do not block evaluation. The centralized balance policy recommends
20–30 samples and warns below two samples per expected category value.

## Add a sample

Add one object to `samples` with a unique lowercase `sample_id`. Only `sample_id` and at
least one artifact analysis ID are structurally required. Add environmental metadata and
labels only when they are known.

Use repository-relative paths:

```json
{
  "sample_id": "landscape-outdoor-01",
  "video_reference": "data/output/example/uploads/source.mp4",
  "recording_environment": "Outdoor, late afternoon",
  "orientation": "LANDSCAPE",
  "resolution": {"width": 1920, "height": 1080},
  "fps": 30,
  "camera_position": "Behind the baseline",
  "court_visibility": "FULL",
  "expected_players_on_court": 4,
  "expected_recording_quality": "GOOD",
  "expected_insight_eligibility": "CAUTIOUS",
  "review_status": "PARTIALLY_REVIEWED",
  "artifacts": {
    "artifact_root": "data/output",
    "inspection_analysis_id": "example",
    "court_analysis_id": "example",
    "tracking_analysis_id": "example",
    "candidates_analysis_id": "example",
    "analytics_analysis_id": "example",
    "match_iq_analysis_id": "example"
  }
}
```

Do not add or copy video files into Git. References may point to ignored local artifacts.

## Reuse split artifacts

A sample may use different analysis IDs for each pipeline stage. This supports preserved
real-model runs without copying artifacts:

- `inspection_analysis_id` for `metadata.json` and `job.json`;
- `court_analysis_id` for `calibrations/*/calibration.json`;
- `tracking_analysis_id` for `tracking/tracking.json`;
- `candidates_analysis_id` for `tracking/player_candidates.json`;
- `analytics_analysis_id` for `analytics/analytics.json` and `timeline.json`; and
- `match_iq_analysis_id` for `analytics/match_iq.json`.

The evaluator reads these files and computes current assessments in memory. It never
writes into the referenced analysis directories.

Missing stages are allowed. They appear as `MISSING` or `NOT_REFERENCED`, and the runner
continues with other samples. Readable old candidate schemas and Match IQ engines appear
as `STALE`.

Phase 1.5A also classifies each stage and sample as `READY`, `LEGACY_COMPATIBLE`,
`PARTIAL`, `INCOMPATIBLE`, or `MISSING`. Inspection, court, tracking, and analytics
artifacts currently lack persisted schema versions and are reported as `UNVERSIONED`;
the evaluator does not invent version numbers.

## Label a sample

Use `UNKNOWN` when a reviewer cannot establish a verdict and `NOT_REVIEWED` when no
review occurred. Leave optional boolean/count fields absent instead of guessing.

### Recording review

- full court visible;
- camera stable;
- players large enough;
- obstruction severity; and
- recording-quality verdict.

### Candidate review

- expected court-player count;
- expected players represented in Court4 candidates;
- duplicate candidates;
- missed players;
- spectators incorrectly promoted; and
- selected-player identity correctness.

### Tracking review

- continuity acceptable;
- fragmentation severity;
- excessive gaps; and
- observed gameplay coverage acceptable.

### Insight review

- quality verdict correct;
- confidence justified;
- measurement-only decision correct;
- suppression decision correct;
- interpretation justified;
- limitations accurate;
- wording understandable;
- action appropriately conservative; and
- recording guidance accurate.

Each section accepts notes and reviewer confidence. `PARTIALLY_REVIEWED` is appropriate
when only some fields can be established.

The report generator cannot write to the manifest path. This prevents accidental label
overwrite.

## Interpret the metrics

Recording-quality exact agreement requires the same status. Acceptable agreement also
includes one adjacent level:

`UNSUITABLE < LIMITED < GOOD < EXCELLENT`.

Evidence gates are grouped as:

- valid: `NORMAL` or `CAUTIOUS`;
- weak: `MEASUREMENT_ONLY`; and
- unsuitable: `INSUFFICIENT_EVIDENCE`.

Candidate and insight metrics include only explicitly labeled fields. Unlabeled error
counts are reported as `not reviewed`, not zero.

Every ratio includes raw counts, a percentage when a denominator exists, and a
provisional marker when fewer than five reviewed samples support it. A provisional
percentage is descriptive only.

## Threshold simulations

Add a manifest-level entry:

```json
{
  "threshold": "blocking_short_edge_pixels",
  "proposed_value": 360,
  "rationale": "Sensitivity check only."
}
```

The evaluator creates an immutable alternative threshold set and reruns inexpensive
assessments in memory. The report shows:

- current and proposed value;
- affected samples;
- exact-agreement improvements;
- exact-agreement regressions; and
- remaining uncertainty.

Simulations never mutate `QUALITY_THRESHOLDS` and never edit production code.

Schema-v2 simulations use only `DEVELOPMENT` samples. `VALIDATION` and `HOLDOUT` samples
are listed as excluded and cannot contribute simulated gains or losses. Every proposal
is exploratory.

## Dataset collection priorities

Collect and independently review at least:

1. three additional samples before reading aggregate percentages as more than framework
   smoke results;
2. landscape and vertical recordings at multiple resolutions;
3. indoor and outdoor lighting;
4. near and far camera positions;
5. stable and moving cameras;
6. full and partial court visibility;
7. recordings with spectators, occlusion, and irrelevant detections; and
8. frame-level player identity/continuity labels for candidate precision, recall, and
   fragmentation evaluation.

Position, distance, and zone measurements require separate ground-truth court-coordinate
labels before measurement error can be validated.

See `DATASET_COLLECTION_GUIDE.md` for consent, privacy, split, and file-handling rules.
See `ANNOTATION_GUIDE.md` for identity, interval, and per-insight review.
See `PHASE_1_5A_REPORT.md` for exact implementation and validation evidence.

## Internal readiness dashboard

After validating and evaluating the schema-v2 manifest twice, open
`/internal/calibration`. Its only source is the read-only
`GET /api/v1/internal/calibration-readiness` response.

The page separates dataset coverage, artifact compatibility, review completion,
provisional outcomes, Active Play shadow evidence, integrity, and readiness blockers.
Missing, invalid, or hash-mismatched inputs are `MISSING`, `INVALID`, or `STALE` and
force `NOT_READY`. A denominator of zero is `NOT_REVIEWED`, not a successful rate.

The page has no annotation, inference, threshold, approval, or activation controls.
Governance targets in `CALIBRATION_READINESS_POLICY.md` are engineering gates, not
scientific claims.
