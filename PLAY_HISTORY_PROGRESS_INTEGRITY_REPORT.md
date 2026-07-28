# Play History Progress Integrity Report

## Verdict

Implemented. Play History now describes qualified observed change through separate,
versioned contribution, comparability, trend, interpretation, grouping, and
aggregation policies. It does not automatically equate movement change with better
performance.

## Architecture

- Contribution remains governed by `play-history-v1`; its thresholds are unchanged.
- Comparability evaluates report-specific evidence and exposes unknown match/camera
  context as limitations.
- Trend eligibility enforces quantity, source-version compatibility, and deterministic
  non-overlapping groups.
- Interpretation eligibility permits neutral descriptive language only and remains
  provisional without a validated outcome metric.
- Active versions are exposed in the typed Play History API.

## Grouping and aggregation

- Three comparable reports establish only an initial baseline.
- Four reports are the minimum for a displayed 2-versus-2 comparison.
- Chronological UTC ordering uses analysis ID as a deterministic tie-breaker.
- The most recent eight reports form the maximum window; an odd middle report is
  omitted and disclosed.
- Movement pace is normalized by qualified tracked duration.
- Court-zone shares are weighted by qualified tracked duration.
- Missing values are omitted, never converted to zero.
- Outliers are retained; deterministic 3× pace and 60% duration-dominance checks mark
  affected output provisional.

## Player experience

- The main question is now “How has my observed play changed?”
- No-report, building-baseline, three-report baseline, comparison-ready, and
  incompatible-report states are distinct.
- Graphs show metric, unit, periods, supporting counts, reliable duration, aggregation
  method, missing-value gaps, and provisional status.
- Neutral colors and neutral increased/decreased/similar labels avoid positive or
  negative performance implication.
- Play-style summaries cite the direct earlier/recent measurement, supporting count,
  duration, provisional state, and limitations.
- A read-only drill-down lists considered reports, comparison status, qualified
  duration, and report links without internal reason codes.
- Dashboard progress includes qualified-analysis count, comparison period, reliable
  observation duration, provisional status, and a Play History link.

## Regression protection

No source analysis artifact is regenerated or mutated. This pass does not change:

- distance or zone calculations;
- recording-quality thresholds;
- Match IQ rules or confidence calculations;
- calibration, tracking, or reviewer labels;
- contribution thresholds;
- Active Play shadow behavior;
- Analysis History completeness or existing deep links.

## Validation

Final validation completed on 2026-07-28.

Backend commands ran in the mounted Python 3.12 Court4 container:

- `ruff format app tests scripts`: pass; 113 files unchanged.
- `ruff check .`: pass; 0 errors.
- `ruff format --check .`: pass; 148 files formatted.
- `mypy app scripts tests`: pass; 0 issues in 113 source files.
- `pytest -q`: pass; 164 tests.

Backend warning: one existing Starlette/httpx TestClient deprecation warning.

Frontend commands:

- `npm.cmd run lint`: pass; 0 warnings or errors.
- `npm.cmd run typecheck`: pass.
- `npm.cmd test`: pass; 21 files and 98 tests.
- `npm.cmd run build`: pass; 12 static pages generated and `/play-history` included.
- `npm.cmd run e2e`: pass; 21 browser scenarios, including all 10 integrity cases.

Frontend warnings: the existing Vite CJS API deprecation notice, Playwright’s
`NO_COLOR`/`FORCE_COLOR` notice, and slow-test-file suggestions. The first expanded
Playwright run had two assertion-only failures; both assertions were corrected and the
final run passed 21/21.

Live and safety checks:

- `/health`: `200`, status `ok`.
- `/docs`: `200`.
- `/`: `200`.
- `/play-history`: `200`.
- Live API exposes all six policy versions and the honest
  `NO_QUALIFIED_REPORTS` state for the current local data.
- No Active Play reference exists in the history projection or player progress UI.
- No unsupported improvement/tactical wording was found in player progress source.
- No diff exists in source analytics, recording-quality, Match IQ,
  evidence-calibration, or reviewer-label implementation.
- `git diff --check`: pass.

Final failures: 0.

## Remaining limitations

Match format, camera placement, opponent context, rally/shot outcomes, and validated
match-performance outcomes are not persisted. Comparisons therefore remain provisional
and descriptive. Genuine performance evaluation requires validated outcome metrics and
context collection in a future explicitly scoped phase.
