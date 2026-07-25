# Court4 Phase 1.5 — Real-Video Evidence Calibration

## Implementation verdict

Phase 1.5 is complete.

Court4 now has a deterministic, repository-native calibration framework for comparing
the existing recording-quality assessment, evidence gate, candidate output, confidence,
measurement-only behavior, and Match IQ suppression decisions with structured human
review labels.

The framework reuses persisted artifacts and performed zero expensive inference runs
during this phase. It does not mutate production thresholds, overwrite reviewer labels,
add coaching rules, or claim scientific validation.

## Architecture delivered

The framework is intentionally internal and CLI-based:

1. `calibration/manifest.v1.json` stores versioned sample metadata, split artifact
   references, expected outcomes, partial human-review labels, and threshold simulations.
2. `app/schemas/evidence_calibration.py` validates the manifest and generated results
   with strict, immutable Pydantic models that reject unknown fields.
3. `app/services/evidence_calibration/manifest.py` loads the manifest, verifies unique
   sample IDs, and records a content digest.
4. `app/services/evidence_calibration/evaluator.py` reads existing inspection, court,
   tracking, candidate, analytics, timeline, and Match IQ artifacts. Missing or stale
   stages are reported per sample and do not stop the remaining dataset.
5. The evaluator recomputes only inexpensive current policy decisions in memory using
   the manifest reference time.
6. `app/services/evidence_calibration/reporting.py` writes stable JSON and Markdown
   reports without absolute local paths and refuses to write over the reviewer manifest.
7. `scripts/calibrate_evidence.py` provides manifest validation and evaluation commands.

No frontend review page was added. Calibration requires local artifact access, partial
review labels, and batch diagnostics; exposing that state in the player-facing product
would add complexity without improving the current two-sample workflow.

## Schema and workflow

Primary paths:

- Manifest: `calibration/manifest.v1.json`
- Manifest and review schema: `app/schemas/evidence_calibration.py`
- Evaluator: `app/services/evidence_calibration/evaluator.py`
- Reporter: `app/services/evidence_calibration/reporting.py`
- CLI: `scripts/calibrate_evidence.py`
- Machine-readable report: `calibration-results.json`
- Human-readable report: `CALIBRATION_REPORT.md`
- Operator guide: `CALIBRATION_GUIDE.md`
- Design and audit: `PHASE_1_5_CALIBRATION_DESIGN.md`

Supported review sections cover:

- recording visibility, stability, player size, obstruction, and quality verdict;
- expected and represented players, duplicates, misses, spectator promotion, and
  selected identity;
- continuity, fragmentation, gaps, and observed gameplay coverage; and
- quality correctness, confidence, measurement-only and suppression decisions,
  interpretation, limitations, wording, conservative action, and recording guidance.

All labels are optional. `UNKNOWN` and `NOT_REVIEWED` remain distinct and are excluded
from denominators instead of being converted to negative or zero values.

## CLI usage

Validate the manifest:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v1.json
```

Evaluate reusable artifacts and regenerate both reports:

```powershell
python -m scripts.calibrate_evidence evaluate calibration/manifest.v1.json
```

The CLI supports custom report paths and an explicit
`--allow-expensive-recomputation` permission flag. The repository has no configured
automatic inference hook, so the flag alone does not run inference. Default evaluation
is read-only with respect to source artifacts and human labels.

## Metrics implemented

Recording quality:

- exact agreement;
- acceptable agreement, defined as exact or one adjacent quality level;
- overestimation and underestimation counts;
- confusion matrix; and
- per-expected-status counts.

Evidence gates:

- valid insights correctly allowed;
- weak evidence correctly reduced to measurement-only;
- unsuitable evidence correctly suppressed;
- valid evidence incorrectly suppressed;
- weak evidence incorrectly allowed; and
- unsuitable evidence incorrectly allowed.

Candidate reliability, where labeled:

- expected-player recall;
- duplicate candidates;
- missed players;
- spectator promotion; and
- selected-player identity accuracy.

Insight integrity, where labeled:

- recording verdict correctness;
- confidence justification;
- measurement-only correctness;
- suppression correctness;
- interpretation justification;
- limitation accuracy;
- wording understandability;
- conservative action; and
- recording-guidance accuracy.

Every ratio includes raw counts. Ratios with no denominator show no percentage.
Metrics supported by fewer than five reviewed samples are explicitly provisional.

## Existing real-video samples

Two existing videos were added without copying or committing large media:

### Landscape indoor doubles

- Expected and current quality: `UNSUITABLE`
- Expected and current evidence gate: `INSUFFICIENT_EVIDENCE`
- Candidates: 80 total, 4 selectable after current in-memory eligibility normalization
- Available labels: 4 expected players and 4 represented; fragmentation reviewed as
  unacceptable
- Artifact state: inspection, court, tracking, analytics, and timeline available;
  candidate schema 1 is stale against schema 3; persisted Match IQ engine v1 is stale
  against v2

### Vertical indoor drill

- Expected and current quality: `LIMITED`
- Expected and current evidence gate: `MEASUREMENT_ONLY`
- Candidates: 2 total, 1 selectable
- Available labels: 2 expected players and 2 represented; vertical orientation,
  measurement-only handling, recommendation suppression, and recording guidance are
  partially reviewed
- Artifact state: inspection, court, tracking, and candidates available; candidate
  schema 1 is stale against schema 3; selected-player analytics, timeline, and persisted
  Match IQ are not referenced

Both samples remain `PARTIALLY_REVIEWED`.

## Calibration findings

The current report records:

- Recording-quality exact agreement: 2/2 (100.0%), provisional
- Recording-quality acceptable agreement: 2/2 (100.0%), provisional
- Overestimation: 0
- Underestimation: 0
- Weak evidence correctly made measurement-only: 1/1 (100.0%), provisional
- Unsuitable evidence correctly suppressed: 1/1 (100.0%), provisional
- Valid-evidence cases: 0/0, not available
- False acceptance: 0 observed
- False suppression: 0 observed
- Expected-player recall: 6/6 (100.0%), provisional
- Missed players: 0 across two explicitly labeled samples
- Duplicate candidates: not reviewed
- Spectator promotions: not reviewed
- Selected-player identity: 0/0, not available
- Expensive inference: 0 runs

These results demonstrate policy consistency on the two seed videos. They do not
establish accuracy on representative recordings.

## Threshold analysis

Two in-memory sensitivity checks were included:

| Policy | Current | Simulated | Affected | Improvements | Regressions |
| --- | ---: | ---: | --- | --- | --- |
| `blocking_short_edge_pixels` | 480 | 360 | landscape sample | none | landscape sample |
| `minimum_tracked_seconds` | 5 | 15 | vertical sample | none | vertical sample |

Lowering the blocking resolution threshold would move the landscape assessment away
from its reviewed label. Raising minimum tracked time would move the vertical assessment
away from its reviewed label. Neither simulation supports a production change.

`QUALITY_THRESHOLDS` remains unchanged. A dedicated test verifies that simulations do
not mutate the production constant.

## Validation

### Backend and container

Build:

```powershell
docker build -t court4:phase15 .
```

Result: passed. Image ID:
`sha256:346e4c068f4ece50ce0a661cdcdff59a3225e686c62aead6848b5bd7ed1b3736`.
Reported image size: 3,181,491,148 bytes.

Final backend gate, executed in that image with the current workspace mounted:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy app scripts tests
python -m pytest -q
```

Results:

- Ruff check: passed
- Ruff format check: 99 files already formatted
- mypy: no issues in 87 source files
- pytest: 110 tests passed
- collection verification: 110 tests collected

Live image checks:

- `GET /health`: HTTP 200, `{"status":"ok"}`
- `GET /docs`: HTTP 200, Swagger UI present
- `GET /openapi.json`: Court4 version 0.5.0

Temporary validation containers were stopped after the checks.

### Calibration workflow

Commands:

```powershell
python -m scripts.calibrate_evidence validate calibration/manifest.v1.json
python -m scripts.calibrate_evidence evaluate calibration/manifest.v1.json `
  --json-output calibration-results.json `
  --markdown-output CALIBRATION_REPORT.md
```

Results:

- Manifest valid: schema 1, 2 samples
- Evaluation complete: 2 samples
- Expensive inference runs: 0
- Evaluation repeated twice with identical file hashes
- `calibration-results.json` SHA256:
  `FAEE4C2E99E7EEED73546EEBCD119474E3898B35B6ACE3E83ED7B1B2F425A2C9`
- `CALIBRATION_REPORT.md` SHA256:
  `00D752954B3F5CE7C548C70FC37977FE2E25877E58A1A52DC4113F19750AB336`
- Windows absolute-path scan: no matches in the manifest or generated reports

### Frontend regression

The player-facing frontend changed earlier in the working tree, so the full frontend
gate was rerun:

- ESLint: passed with no warnings or errors
- TypeScript: passed
- Vitest: 17 files, 75 tests passed
- Next.js production build: passed
- Playwright: 7 scenarios passed in 24.3 seconds

The Playwright coverage includes normal, limited, unsuitable, manual calibration,
missing-model recovery, fragmented-candidate review, and persisted manual-review paths.

## Corrected pre-final failures and warnings

Corrected during validation:

1. The first final backend run found one unsorted import in the new calibration test.
   The import was reordered.
2. The next run found an incorrect test import path for `QUALITY_THRESHOLDS`.
   It was changed to the package's public export.
3. An operator verification attempt invoked `python scripts/calibrate_evidence.py`
   directly and failed with `ModuleNotFoundError: app`. The documented and supported
   module command, `python -m scripts.calibrate_evidence`, passed and was used for the
   reproducibility proof. Generated reports were unchanged during the failed attempt.

Non-blocking warnings:

- Starlette reports that its current `httpx` TestClient integration is deprecated in
  favor of `httpx2`.
- Vitest reports that Vite's CommonJS Node API is deprecated.
- Playwright reports that `NO_COLOR` is ignored when `FORCE_COLOR` is set.
- The Docker dependency install warns about running pip as root, which is normal in this
  image build.
- The detector dependency layer makes the image large and resolves current compatible
  versions within broad dependency ranges.

No final validation command failed.

## Files added or changed for Phase 1.5

Added:

- `PHASE_1_5_CALIBRATION_DESIGN.md`
- `CALIBRATION_GUIDE.md`
- `CALIBRATION_REPORT.md`
- `PHASE_1_5_REPORT.md`
- `calibration-results.json`
- `calibration/manifest.v1.json`
- `app/schemas/evidence_calibration.py`
- `app/services/evidence_calibration/__init__.py`
- `app/services/evidence_calibration/manifest.py`
- `app/services/evidence_calibration/evaluator.py`
- `app/services/evidence_calibration/reporting.py`
- `scripts/calibrate_evidence.py`
- `tests/test_evidence_calibration.py`

Changed:

- `app/services/recording_quality/assessment.py` — accepts an optional immutable
  threshold set for simulation; production callers retain the same defaults
- `README.md` — adds calibration commands and boundaries
- `CURRENT_STATE_AUDIT.md` — records the Phase 1.5 framework and current evidence limits

Pre-existing Phase 1.3, Phase 1.4, and player-facing UI changes in the dirty worktree
were preserved.

## Remaining limitations

- Two videos are not representative and cannot support broad validation claims.
- Neither sample is fully or independently reviewed.
- There are no reviewed `GOOD` or `EXCELLENT` samples and no valid normal/cautious gate
  examples.
- Candidate duplicate, spectator promotion, and selected-player identity metrics lack
  denominators.
- There is no frame-level identity, continuity, position, distance, or zone ground truth.
- Both candidate artifacts are legacy schema 1; the landscape Match IQ artifact is
  legacy engine v1.
- The vertical sample has no selected-player analytics chain.
- Heuristic and model confidence values are not calibrated probabilities.
- Threshold simulations cover only observed seed boundaries and are not optimization.

## Recommended dataset collection plan

1. Complete independent reviews of both seed samples, preferably by two reviewers with
   adjudication for disagreements.
2. Add at least three fully reviewed samples to meet the framework's minimum denominator
   before interpreting any percentage beyond a smoke signal.
3. Build a balanced next set of 20–30 recordings containing `EXCELLENT`, `GOOD`,
   `LIMITED`, and `UNSUITABLE` examples and all four evidence-gate outcomes.
4. Stratify recordings by landscape/vertical orientation, resolution, FPS, duration,
   indoor/outdoor lighting, camera distance, stability, court visibility, obstruction,
   and spectator presence.
5. Add frame-level player identity, active-court-player, continuity, fragmentation, and
   gap labels for a smaller gold subset.
6. Add selected-player identity labels and preserve reviewer disagreement rather than
   forcing consensus into the source labels.
7. Only after the expanded report is reviewed, propose one threshold change at a time
   with affected samples, improvements, regressions, and an explicit production code
   review.

## Readiness verdict

Court4 is ready to expand and repeatedly evaluate a real-video calibration dataset.
Phase 1.5 acceptance criteria are met, and existing application behavior remains intact.

Court4 is not yet broadly validated, and the current evidence does not justify changing
production thresholds or beginning a later intelligence phase.
