# Experimental ball detection and trajectory evidence (Phase 1.9A1)

Phase 1.9A1 extends the 1.9A0 foundation with a real, conservative detector and a
separate temporal tracker. The result is developer-review evidence, not a production
accuracy claim and not a player-facing analytic. `BALL_TRACKING_ENABLED` remains
`false` by default. Nothing schedules this stage in the primary analysis workflow.

## Detector and model provenance

The concrete detector is `opencv_color_motion_ball_detector` version `1.0.0`. It has
no learned weights, so `model_identifier` and `model_sha256` are honestly `null`.
It generates yellow/lime color candidates, then requires bounded size, circularity,
color fill, frame-to-frame motion, and an acceptance confidence. Every raw candidate
is recorded with its measurements and rejection reasons. A generated candidate is
not called an observation unless all gates pass.

This small CPU-only detector was selected because it is deterministic, auditable,
needs no new dependency or runtime model provisioning, and can prove the end-to-end
evidence architecture safely. It is not a generic ball classifier. It will miss
white/orange balls, very small or heavily blurred balls, stationary balls, balls
whose color is shifted by lighting, and balls obscured for long intervals. Bright
clothing, signs, or court markings can still create rejected candidates or false
positives. Real-video accuracy remains unmeasured until consent-cleared evaluation
footage is available.

The tracker is `bounded_nearest_trajectory_tracker` version `1.0.0`. Detection and
association are separate steps. The tracker uses bounded image-space association,
records impossible-motion rejections, starts explicit segments after long gaps, and
linearly interpolates only short gaps of at most four frames. Interpolated points
are labeled `interpolated`, carry both observed endpoint frame indices, and use
reduced confidence. Gaps and reacquisitions remain explicit events.

## Independent execution

`analysis_stage_executions` records each attempt of an optional stage. Attempts are
owner- and analysis-scoped, linked to their parent analysis run, and have independent
queued/processing/terminal states. Starting, failing, or rerunning an optional stage
does not transition the player-facing `analyses` row. Only one active attempt of a
stage type may exist for an analysis; terminal attempts are immutable and a rerun
receives the next attempt number.

Ball shadow execution is an internal service boundary, not a public API. It is
fail-closed behind `BALL_TRACKING_ENABLED=false`. No Match IQ, Analysis History,
Play History, Player Workspace, or overall completion code reads stage execution or
ball artifacts.

## Evidence and provenance

Stage configuration is a normalized, deterministic, secret-free deep merge of
defaults and request overrides. Its SHA-256 fingerprint and full effective
configuration are stored with strict stage provenance. Detector and tracker
identities record the concrete executed components. Learned-model fields remain
`null` because this implementation uses no learned weights; they are never inferred
from installed packages.

Stage output keys are attempt-qualified. Ball output begins at
`ball/attempt-NNNN/`, preventing reruns from colliding. Completed prior metadata is
retained with producing run/stage/checksum/schema links. Completing a newer attempt
promotes its outputs and marks earlier attempt outputs historical without deleting
rows or copying large files. Frame observations remain JSONL artifacts, never one
database row per frame.

Version 1 contracts cover per-frame detections, reconstructed track, evidence report,
trajectory image, overlay video, and review sidecar. Per-frame detection distinguishes
`observed`, `missing`, and `frame_failed`; candidate disposition distinguishes
`accepted` and `rejected`; track samples distinguish `observed` and `interpolated`.
Reports explicitly say `available`, `no_ball_detected`, `insufficient_observations`,
`analysis_failed`, or `truncated` and provide reasons. The contracts intentionally
exclude contact, hitter, shot, rally, outcome, bounce, height, scoring, and coaching
claims.

The overlay draws accepted observations, confidence, a bounded trail, inferred gaps,
and reacquisition markers. The trajectory PNG is explicitly image-space. Both are
developer-review artifacts. They are not exposed by a new public endpoint or UI.

## Calibration claim boundary

Calibration generation means only that a mathematically usable homography exists.
It does not mean the selected lines are the court. Human review is a separate,
checksum-bound immutable record; old calibrations remain unverified unless reviewed.

A verified homography permits only an **approximate court-plane projection**. A
single-camera homography cannot establish exact airborne 3D position, ball height,
exact bounce location, or a physical 3D trajectory. Ball image-space evidence may be
available while court projection is unavailable.

## Frames and review

`OpenCVFrameSource` streams frame index, timestamp, image, and immutable source
metadata with bounded memory. It creates no raw-frame cache and introduces no player
tracking/ball tracking coupling. Future integrated scheduling can fan this common
contract into independent consumers; the Phase 1.9A feasibility spike may perform a
second decode only as a small offline experiment.

The review-sidecar contract names observed, interpolated, reacquired, and
low-confidence visual states. It does not provide trajectory editing or contact
labels.

## Isolation and regression safeguards

- The global and Railway-facing default remains `BALL_TRACKING_ENABLED=false`.
- The service fails closed before creating a stage record when the flag is disabled.
- A ball attempt is optional and shadow-only. Its terminal state never transitions
  the parent analysis or changes overall completion.
- Artifacts live only under `ball/attempt-NNNN/`; reruns preserve prior attempts.
- No workflow, Match IQ, Player History, Play History, trusted movement metric,
  coaching, or player-facing API imports or consumes these contracts.
- Frame processing streams video twice (detection and overlay), caches no raw frames,
  caps work at 18,000 frames by default, bounds candidates to 24 per frame, and bounds
  the overlay trail to 24 samples.
- Attempt outputs are built in a partial directory and promoted atomically. Failed
  partial output is removed, while the stage receives only a safe failure category.

## Calibration boundary and future sports

Image-space tracking is sport-neutral low-level physics evidence. Court-plane fields
are optional and are attached only when the existing calibration is human-verified
and checksum-bound to the exact calibration artifact. Even then the claim is only an
`approximate_court_plane_projection`; it cannot establish airborne height, exact 3D
trajectory, exact bounce, or contact.

The detector/tracker contracts avoid pickleball rally semantics so a future Padel
adapter can reuse raw image-space candidates, observations, gaps, and provenance.
Padel court geometry, walls, sport rules, and event semantics are not implemented in
this phase.

## Local developer review

The offline command does not require enabling the application feature flag. It
requires an explicit experimental acknowledgement and an external purpose-specific
model-evaluation consent reference:

```powershell
python -m scripts.run_experimental_ball_tracking `
  --input <consent-cleared-clip> `
  --output-dir <new-output-directory> `
  --consent-reference <external-reference> `
  --acknowledge-experimental
```

The reference is routing evidence, not a substitute for reviewing the authoritative
consent record. Existing private-alpha uploads are ineligible by default and must not
be used merely because their bytes exist locally.

## Offline feasibility harness

`python -m scripts.validate_ball_feasibility --manifest <path>` validates, but does
not create, a dataset of 2–3 manually prepared 10–20 second clips. Each clip must be
checksum-pinned, fixed-camera metadata must be explicit, labels must be manual and
frame ordered, and purpose-specific model-evaluation consent evidence is required.
No private-alpha upload is automatically eligible, and evaluation consent does not
authorize training.

Future consent-cleared evaluation may compare this deterministic baseline with
zero-shot full-frame or court-ROI/tiled learned detectors. Thresholds and detector
choice must not be promoted from synthetic tests. Any such evaluation must first ask
whether representative footage contains recoverable ball pixels and must not produce
player-facing claims.
