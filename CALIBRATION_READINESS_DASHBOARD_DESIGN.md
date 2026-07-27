# Court4 Calibration Readiness Dashboard Design

## Purpose and boundary

The dashboard is a read-only internal view for Court4's product owner and engineering
team. It explains calibration coverage, review completion, artifact compatibility,
shadow Active Play evidence, policy integrity, and the blockers to Phase 1.6B.

It is not a calibration engine, annotation tool, approval workflow, or source of
player-facing analytics. It never runs inference, edits a manifest or label, changes a
threshold, accepts a proposal, enables Active Play, or modifies analytics or Match IQ.

## Sources and summary contract

One typed backend response is the browser's only source:

- `calibration/manifest.v2.json` for samples, splits, metadata, and reviews;
- `calibration-results.json` for evaluated metrics, artifact status, disagreements,
  simulations, policy hashes, and shadow Active Play results;
- `calibration-readiness-integrity.json` for repeat-report hash verification;
- `calibration/readiness-governance.json` for explicit human governance approvals;
- the current immutable recording-quality, Active Play, and readiness policies.

The response contains source status, dataset overview/balance, artifact readiness,
separate review progress, calibration outcomes, Active Play shadow metrics,
disagreements, policy safety, a readiness decision, and deterministic next actions.
The frontend renders these values and performs no metric or verdict calculation.

## Readiness and failure behavior

The centralized `calibration-readiness-v1` policy emits `NOT_READY`,
`COLLECTING_EVIDENCE`, `READY_FOR_POLICY_REVIEW`, or `READY_FOR_PHASE_1_6B`, with
reasons, blockers, warnings, satisfied criteria, and policy version. Targets are
engineering governance gates, not scientific validation thresholds.

Manifest/report/policy hash mismatches are `STALE`. Missing or invalid sources remain a
typed 200 response with `MISSING` or `INVALID` state and a `NOT_READY` verdict, allowing
the internal page to explain recovery. Unreviewed denominators render as not reviewed,
never as successful zero-error performance. Responses never include recording paths or
machine-specific absolute paths.

## Access

`GET /api/v1/internal/calibration-readiness` and `/internal/calibration` are explicitly
internal development surfaces. The page is absent from public navigation and contains
no write controls.
