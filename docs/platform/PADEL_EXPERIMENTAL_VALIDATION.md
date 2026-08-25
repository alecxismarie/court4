# Padel experimental validation

Court4 treats Padel as a durable sport identity but does not run Pickleball calibration,
movement analytics, Match IQ, or Play History interpretation for Padel analyses.

## Current compatibility audit

- Sport-neutral: upload storage, authentication and ownership, video decoding, timestamps,
  generic person detections/tracks, player identity continuity contracts, low-level ball
  observations/trajectories, stage execution, artifacts, and build provenance.
- Pickleball-specific: 20 x 44 ft calibration, kitchen and transition zones, automatic court
  detection, active-play rules, movement images, Match IQ, and Play History comparison.
- Requires Padel validation/adapters: court calibration, court-side candidate heuristics,
  wall/glass/reflection handling, player eligibility thresholds, and ball detector tuning.

The current experimental ball detector is specifically a yellow/lime color-and-motion detector.
It is not represented as a universal racket-sport detector. The trajectory evidence contract is
reusable; rebound, bounce, contact, and shot interpretation are not implemented.

## Consent-cleared workflow

Run video inspection and produce the structured report:

```powershell
python -m scripts.validate_padel_video `
  --input 'C:\path\to\consent-cleared-padel.mp4' `
  --output-dir '.\data\output\padel-validation' `
  --analysis-id 'padel-validation-001' `
  --consent-reference 'owner-validation-YYYY-MM-DD' `
  --acknowledge-experimental
```

After reviewing sampled frames for court visibility, glass reflections, and camera angle, run the
optional low-level ball evidence experiment separately:

```powershell
python -m scripts.run_experimental_ball_tracking `
  --sport padel `
  --input 'C:\path\to\consent-cleared-padel.mp4' `
  --output-dir '.\data\output\padel-ball-validation' `
  --analysis-id 'padel-validation-001' `
  --consent-reference 'owner-validation-YYYY-MM-DD' `
  --acknowledge-experimental
```

Do not report detection accuracy without ground-truth annotations. Record observation coverage,
trajectory fragmentation, false positives, reflection interference, occlusions, runtime, and
resource use as evidence—not as mature Padel analytics.
