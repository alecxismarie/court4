# Court4 Calibration Readiness Policy

Policy version: `calibration-readiness-v1`

All targets below are provisional engineering governance gates. They organize evidence
review; they are not scientific accuracy thresholds and do not validate Active Play.

## Verdicts

- `NOT_READY`: required sources are missing, invalid, or stale; inference occurred; a
  policy or reviewer-label integrity check failed; or deterministic output is not
  verified.
- `COLLECTING_EVIDENCE`: sources and integrity checks are current, but dataset,
  artifact, review, balance, boundary, disagreement, or error-budget evidence is
  incomplete.
- `READY_FOR_POLICY_REVIEW`: evidence targets are satisfied, but recording/Active Play
  policies or false-active/false-idle budgets lack explicit governance approval.
- `READY_FOR_PHASE_1_6B`: evidence targets, integrity checks, holdout protection,
  budgets, and policy approvals are all satisfied.

## Initial governance targets

- at least 20 total samples, reusing the existing dataset-balance target;
- development, validation, and holdout samples all present;
- at least 5 fully reviewed samples, reusing the calibration minimum;
- at least 5 samples backed by current candidate schema artifacts;
- at least 300 reviewed Active Play seconds across at least 10 intervals;
- both likely-active and likely-idle human-reviewed evidence present;
- at least 10 reviewed Active Play boundaries;
- every required balance value represented, with two samples per value preferred;
- no unresolved critical artifact, identity, continuity, or Active Play disagreement;
- zero expensive inference runs during calibration evaluation;
- current manifest and policy hashes match the evaluated report;
- repeat report hashes match;
- threshold simulations preserve validation/holdout exclusion;
- explicit approval of both policies and both error budgets.

Changing these targets requires a new readiness-policy version and review. The
dashboard cannot change or approve them.
