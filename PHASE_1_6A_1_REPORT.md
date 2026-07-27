# Court4 Phase 1.6A.1 Report

Date: 2026-07-27

## Implementation verdict

Implemented. Court4 now has an internal, read-only calibration-readiness dashboard and
typed backend summary. It remains an engineering evidence tool: it does not run
inference, edit human labels, mutate thresholds, enable Active Play, change Match IQ,
or appear in the normal player workflow.

Design:

- `CALIBRATION_READINESS_DASHBOARD_DESIGN.md`
- `CALIBRATION_READINESS_POLICY.md`

## Architecture and access boundary

`CalibrationReadinessService` reads the schema-v2 manifest, generated calibration
results, Markdown report hashes, governance record, and immutable policy definitions.
It creates a single strict Pydantic response for
`GET /api/v1/internal/calibration-readiness`. The Next.js route
`/internal/calibration` validates that response with Zod and renders it without
recomputing metrics or verdicts.

Only `GET` exists. Missing, invalid, and stale inputs remain typed states with a
`NOT_READY` verdict. Responses exclude video paths and machine-specific source paths.
The route has no link in desktop or mobile primary navigation and no write controls.

## Readiness model

The versioned `calibration-readiness-v1` policy emits:

- `NOT_READY` for unavailable/stale sources or failed integrity/no-inference checks;
- `COLLECTING_EVIDENCE` while evidence targets remain incomplete;
- `READY_FOR_POLICY_REVIEW` after evidence gates but before explicit governance;
- `READY_FOR_PHASE_1_6B` only after all evidence, policy, and error-budget gates.

The targets are provisional engineering governance gates, not scientific validation
thresholds. Every verdict includes blockers, warnings, satisfied criteria, and
deterministic recommended actions.

## Current seeded result

The existing artifacts were evaluated twice without inference:

- 2 samples: 1 development, 1 validation, 0 holdout;
- 0 fully reviewed, 2 partially reviewed;
- artifact readiness: 1 legacy-compatible, 1 partial, 0 ready;
- Active Play: 2 generated `UNKNOWN` intervals, 75.6 seconds unknown, 0 reviewed
  intervals, 0 reviewed seconds;
- 0 current-schema Active Play samples and 2 stale-artifact samples;
- false-active, false-idle, boundary, abstention, and coverage metrics:
  `NOT_REVIEWED`;
- deterministic repeat report status: `MATCH`;
- expensive inference runs: 0;
- verdict: `COLLECTING_EVIDENCE`.

No human interval labels were invented. Current blockers include dataset size, no
holdout, incomplete identity/continuity/insight review, no Active Play human review,
legacy artifacts, missing balance cases, and unresolved critical findings.

## Policy and regression safety

Calibration results now persist recording and Active Play policy versions and hashes,
plus per-sample Active Play interval/schema metadata. A separate integrity artifact
binds the manifest, policies, JSON result, and both Markdown reports. Repeat generation
must match before the integrity gate passes.

Threshold simulations remain in-memory, development-only, and non-mutating.
Validation and holdout IDs are excluded. The current report verifies zero inference,
unchanged policy hashes, unchanged manifest/reviewer-label hash, and deterministic
output. Existing analytics and Match IQ implementations were not modified.

## UI behavior

The dashboard displays source status, dataset overview and balance, artifact readiness,
review progress, provisional outcomes, Active Play shadow evidence, disagreements,
policy safety, decision basis, and next actions. Zero denominators render as “Not
reviewed”; provisional results do not render as validated percentages. It explicitly
states that no rally, point, serve, shot, or tactical-event detection exists.

## Validation

All required validation completed:

- Docker: `docker build -t court4:phase16a1 .` passed.
- Backend: 144 pytest tests passed; Ruff check passed; Ruff format check passed for
  103 files; mypy passed for 85 source files.
- API smoke: `/health`, `/docs`, and
  `/api/v1/internal/calibration-readiness` returned HTTP 200 from the final image.
- Calibration: schema-v1 and schema-v2 manifests passed; both schema-v2 sample records
  passed; two no-inference report generations produced `NOT_VERIFIED` then `MATCH`;
  0 expensive inference runs were recorded.
- Frontend: ESLint and TypeScript passed; 77 Vitest tests passed; the production
  Next.js build passed and emitted `/internal/calibration`; 8 Playwright scenarios
  passed, including deterministic refresh and absence from public navigation.

Warnings:

- pytest emitted one upstream Starlette `TestClient`/httpx deprecation warning.
- Vitest emitted the upstream Vite CJS Node API deprecation warning.
- Playwright reported the existing workflow spec as slow and logged the existing
  `NO_COLOR`/`FORCE_COLOR` warning.
- The unconstrained detector dependency resolved a CUDA-enabled Torch stack during
  the clean build, producing a 3.18 GB image. This is a dependency/image-size concern,
  not a Phase 1.6A.1 functional failure.

## Known limitations and activation conditions

The current two-video dataset cannot support broad accuracy, robustness, or
generalization claims. It lacks outdoor, singles, ideal-quality, camera-distance,
stability, obstruction, 1080p, fully reviewed identity, continuity, and holdout
coverage. Warm-up and ball retrieval may resemble active play, and stationary live
play may remain uncertain.

Before player-facing activation, Court4 requires independent, balanced development,
validation, and holdout evidence; current-schema artifacts; sufficient reviewed
active/idle duration and boundaries; accepted false-active/false-idle budgets;
measured abstention and coverage; resolved critical findings; frozen versioned
policies; regression verification; and explicit product/privacy approval.

## Recommended next step

Use the dashboard to prioritize the first independently reviewed holdout sample and
bounded Active Play interval labels. Do not begin Phase 1.6B until the evidence gates
reach policy review.
