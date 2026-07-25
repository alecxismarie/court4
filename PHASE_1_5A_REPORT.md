# Court4 Phase 1.5A — Calibration Dataset Expansion

## Implementation verdict

Phase 1.5A is complete.

Court4's calibration workflow is ready to onboard and independently review a balanced
20–30 recording dataset. The implementation remains deterministic, artifact-reusing,
CLI-only, and backward compatible with the Phase 1.5 manifest.

No recordings were collected, no missing human labels were invented, no expensive
inference ran, and no production threshold changed.

## Schema changes

`app/schemas/evidence_calibration.py` now accepts manifest schema 1 and 2.

Schema v2 adds:

- typed indoor/outdoor, singles/doubles, camera position, camera distance, lighting,
  stability, orientation, visibility, resolution, and FPS metadata;
- separate external-video, local-uncommitted-video, and persisted-artifact references;
- development, validation, and holdout splits;
- stable real-player IDs;
- candidate-to-player mappings with court-player, spectator, duplicate, uncertain, and
  false-detection roles;
- multiple candidate fragments for one real player;
- optional time intervals for identity, continuity, occlusion, outside-frame state,
  tracking gaps, observed-time agreement, and gap-label agreement;
- per-insight measurement, interpretation, confidence, limitation, action, wording, and
  expected-gate review;
- sample and stage artifact-readiness classifications;
- dataset-balance results; and
- structured calibration disagreements.

Unknown and unreviewed remain distinct and do not enter metric denominators.

## CLI additions

The calibration CLI now supports:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v2.json
python -m scripts.calibrate_evidence validate-sample `
  calibration/manifest.v2.json <sample-id>
python -m scripts.calibrate_evidence template <sample-id> --output <path>
python -m scripts.calibrate_evidence summarize calibration/manifest.v2.json
python -m scripts.calibrate_evidence review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence artifact-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence unresolved-mappings calibration/manifest.v2.json
python -m scripts.calibrate_evidence insight-review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence evaluate calibration/manifest.v2.json
```

Template output is not overwritten unless `--force` is explicit. Evaluation writes JSON,
the main Markdown report, and the focused disagreement report but cannot overwrite the
manifest.

## Sample onboarding workflow

1. Generate an editable sample template.
2. Add safe external or repository-relative ignored local video references.
3. Record typed metadata known to the reviewer.
4. Add separate analysis IDs for available artifact stages.
5. Assign development, validation, or holdout before threshold analysis.
6. Add stable players and candidate mappings.
7. Add representative continuity intervals when justified.
8. Review generated insights individually.
9. Validate the sample and complete manifest.
10. Review balance, incomplete fields, mappings, artifact readiness, and disagreements.
11. Regenerate reports.

`calibration/sample-template.v2.json` demonstrates the format without copying media or
containing machine-specific paths.

## Dataset-balance checks

The centralized policy in `app/services/evidence_calibration/dataset.py` recommends:

- 20–30 total recordings; and
- at least two samples per expected balance value before that value is no longer marked
  underrepresented.

The report covers indoor/outdoor, singles/doubles, ideal/poor, landscape/vertical,
baseline/diagonal, near/distant, 720p/1080p, stable/unstable, obstruction, tracking
strength, four quality statuses, and dataset splits.

Balance never blocks evaluation.

The current two samples are missing:

- outdoor;
- singles;
- ideal-quality, `EXCELLENT`, and `GOOD`;
- diagonal camera placement;
- reviewed near and distant placement;
- 1080p;
- reviewed stable and unstable recording;
- none, minor, and severe obstruction; and
- holdout coverage.

Landscape and vertical, poor recording conditions, baseline camera position, 720p,
moderate obstruction, strong and fragmented tracking, `LIMITED`, `UNSUITABLE`,
development, and validation have some representation, but most remain underrepresented.

## Artifact compatibility

Every stage reports actual version, expected version, and compatibility:

- `READY`
- `LEGACY_COMPATIBLE`
- `PARTIAL`
- `INCOMPATIBLE`
- `MISSING`

Inspection, court calibration, tracking, and analytics artifacts currently do not
persist schema versions. They are parsed and reported as `UNVERSIONED`; no version is
invented. Invalid court calibrations and other malformed artifacts are incompatible.

Current sample readiness:

- landscape: `LEGACY_COMPATIBLE`
  - candidate schema 1 versus current schema 3;
  - Match IQ engine v1 versus current v2.
- vertical: `PARTIAL`
  - candidate schema 1 versus current schema 3;
  - analytics, timeline, and Match IQ are not referenced.

## Metrics added

Player identity:

- expected-player recall;
- candidate precision;
- selected-player identity accuracy;
- candidate-to-player mapping accuracy;
- duplicate candidates;
- missed players;
- spectator promotions; and
- raw duplicate and missed counts per labeled sample.

Tracking continuity:

- reviewed interval count;
- correctly maintained identity intervals;
- identity-switch intervals;
- fragmented intervals;
- valid observed-time agreement; and
- gap-label agreement.

Per-insight review:

- measurement correctness;
- interpretation justification;
- confidence appropriateness;
- limitation accuracy;
- conservative-action agreement; and
- wording-understandability agreement.

Only explicitly reviewed labels enter denominators. Raw per-sample error totals do not
show a misleading percentage.

The seed samples have no detailed candidate mappings, interval labels, selected
identity, or per-insight reviews, so those expanded metrics correctly report zero
denominators.

## Disagreement reporting

`CALIBRATION_DISAGREEMENTS.md` reports Court4 output, human expectation, artifact
evidence, reason, affected rule, and category without changing either output or label.

Supported categories include recording assessment, court detection, candidate
association, tracking continuity, measurement, insight gating, wording, and incomplete
annotation.

The current report contains two findings, both `INCOMPLETE_ANNOTATION`. No reviewed
Court4-versus-human output disagreement was found in the two seed cases.

## Legacy migration behavior

`calibration/manifest.v1.json` remains unchanged and validates directly under the
expanded code. No destructive migration is required.

`calibration/manifest.v2.json` preserves every existing expected outcome and aggregate
review label. New identity, mapping, interval, and per-insight fields are empty or
unreviewed rather than inferred.

The landscape sample is tagged `DEVELOPMENT`; the vertical sample is tagged
`VALIDATION`. No holdout is invented.

## Threshold safety

Simulations now use only development samples. Validation and holdout samples are listed
as excluded and cannot produce proposal gains or losses.

Current exploratory results:

- lowering `blocking_short_edge_pixels` from 480 to 360 regresses the development
  landscape sample;
- raising `minimum_tracked_seconds` from 5 to 15 changes no eligible development sample;
  the vertical validation sample is excluded.

Verified production values after evaluation:

- `blocking_short_edge_pixels=480`
- `minimum_tracked_seconds=5.0`

## Validation

### Final Docker image

```powershell
docker build -t court4:phase15a .
```

Result: passed.

- Image ID:
  `sha256:a3892cb3baa68a6d2408d599d26070fd453ffed9f4b940be69a4406202d852b4`
- Reported size: 3,181,509,188 bytes

### Backend

Executed in the final image with the current workspace mounted:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy app scripts tests
python -m pytest -q
```

Results:

- Ruff: passed
- Format: 106 files already formatted
- mypy: no issues in 89 source files
- pytest: 126 tests passed
- collection verification: 126 tests collected
- Phase 1.5 plus Phase 1.5A calibration tests: 31 passed

Runtime:

- `GET /health`: HTTP 200, `{"status":"ok"}`
- `GET /docs`: HTTP 200, Swagger UI present

The temporary runtime container was stopped.

### Calibration workflow

Validated:

- Phase 1.5 manifest: schema 1, 2 samples
- Phase 1.5A manifest: schema 2, 2 samples
- single-sample validation
- sample-template generation
- dataset summary
- incomplete-review report
- artifact status
- unresolved mappings
- pending insight review
- full v2 evaluation

The reports were regenerated twice with identical hashes:

- `calibration-results.json`:
  `336D7A4649B731C63F2FAA70649FD0843B3C7C0751C1C961328553BE454417F3`
- `CALIBRATION_REPORT.md`:
  `417B2BC6A227AF1B5CBC74E9722C4E5828FA0DDE404237DC4194945075DF7327`
- `CALIBRATION_DISAGREEMENTS.md`:
  `1A4EAEA92F7A9623B42A94FD6A0DEEDF257E0F548BD0A8889A8B0BCF303B61F7`

The v2 manifest hash was unchanged before and after both evaluations:

`A10BC6660136365B660A9BFFD96D8FA7BC37377DCEB3E14D871A02D9FE9F2F2C`

No Windows absolute paths were found in the v2 manifest, template, or generated reports.
Both evaluations reported zero expensive inference runs.

### Frontend

No frontend code or player-facing workflow changed in Phase 1.5A, so the conditional
frontend validation suite was not rerun. The internal review UI was intentionally
skipped.

## Corrected development findings and warnings

Corrected before final validation:

- Initial static checks found import ordering, formatting, and type issues in new files.
- One interval-validation test used a value rejected by the field constraint before
  reaching the intended range validator; the fixture was corrected.
- Candidate precision was defined conservatively so duplicate fragments are not counted
  as unique correct candidates.
- Court-calibration compatibility was strengthened from existence-only checking to
  schema parsing.
- Dataset limitations and next actions were made data-dependent rather than hardcoded to
  two samples.

Non-blocking warnings:

- Starlette reports its current `httpx` TestClient integration as deprecated in favor of
  `httpx2`.
- Docker warns about running pip as root inside the image.
- Broad detector dependency ranges produce a large image and caused the dependency layer
  to rebuild when README changed.

No final validation command failed.

## Files added or changed

Added:

- `PHASE_1_5A_DATASET_DESIGN.md`
- `DATASET_COLLECTION_GUIDE.md`
- `ANNOTATION_GUIDE.md`
- `CALIBRATION_DISAGREEMENTS.md`
- `PHASE_1_5A_REPORT.md`
- `calibration/manifest.v2.json`
- `calibration/sample-template.v2.json`
- `app/services/evidence_calibration/dataset.py`
- `tests/test_evidence_calibration_dataset.py`

Changed:

- `app/schemas/evidence_calibration.py`
- `app/services/evidence_calibration/evaluator.py`
- `app/services/evidence_calibration/reporting.py`
- `scripts/calibrate_evidence.py`
- `CALIBRATION_GUIDE.md`
- `CALIBRATION_REPORT.md`
- `calibration-results.json`
- `README.md`
- `CURRENT_STATE_AUDIT.md`

The original v1 manifest and existing human labels were preserved.

## Remaining manual work

- Obtain consent and collect the actual recordings.
- Independently label metadata, stable players, candidate mappings, selected identity,
  intervals, and insights.
- Resolve duplicate and spectator counts for the seed videos.
- Add a true holdout set.
- Preserve independent reviewer decisions and adjudicate disagreements.
- Add frame-level or interval-level gold labels where measurement accuracy is required.
- Upgrade or regenerate legacy artifacts only through an explicitly approved workflow.

The framework cannot perform these human review tasks automatically.

## Recommended recording collection plan

For approximately 25 recordings:

- 15 development;
- 5 validation;
- 5 holdout;
- roughly balanced indoor and outdoor;
- both singles and doubles;
- at least five reviewed examples of each quality level where feasible;
- landscape and intentional vertical boundary cases;
- baseline and diagonal positions;
- near, medium, and distant placement;
- 720p and 1080p;
- stable and unstable footage;
- all obstruction levels;
- spectators, irrelevant detections, and occlusion cases; and
- a gold subset with two independent reviewers and interval-level identity labels.

Assign the split before threshold proposal work. Do not move difficult validation or
holdout cases into development.

## Readiness verdict

Court4 is ready for controlled collection and independent annotation of a 20–30 video
calibration dataset.

It is not yet calibrated on that dataset, not scientifically validated, and not ready
for threshold changes based on the two seed videos. Actual dataset collection and review
remain human work.
