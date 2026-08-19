# Ball evidence foundation (Phase 1.9A0)

This phase prepares evidence architecture. It does not implement ball detection or
expose ball-derived analytics.

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
configuration are stored with strict stage provenance. Unknown detector, model, and
tracker facts remain `null`; they are never inferred from installed packages.

Stage output keys are attempt-qualified. Ball output begins at
`ball/attempt-NNNN/`, preventing reruns from colliding. Completed prior metadata is
retained with producing run/stage/checksum/schema links. Completing a newer attempt
promotes its outputs and marks earlier attempt outputs historical without deleting
rows or copying large files. Frame observations remain JSONL artifacts, never one
database row per frame.

Prepared version 1 contracts cover detections, reconstructed track, evidence report,
trajectory image, overlay video, and review sidecar. Observed and interpolated ball
samples are different states. The contracts intentionally exclude contact, hitter,
shot, rally, outcome, bounce, height, scoring, and coaching claims.

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

The review-sidecar contract reserves visual states for observed, interpolated,
reacquired, and low-confidence evidence. It does not provide trajectory editing or
contact labels.

## Offline feasibility harness

`python -m scripts.validate_ball_feasibility --manifest <path>` validates, but does
not create, a dataset of 2–3 manually prepared 10–20 second clips. Each clip must be
checksum-pinned, fixed-camera metadata must be explicit, labels must be manual and
frame ordered, and purpose-specific model-evaluation consent evidence is required.
No private-alpha upload is automatically eligible, and evaluation consent does not
authorize training.

After this foundation passes, a separate spike may compare zero-shot full-frame
YOLO, court-ROI/tiled YOLO, and deterministic temporal reconstruction. Its only first
question is whether representative footage contains enough recoverable ball pixels;
it must not produce player-facing claims.
