# Current Court4 Task

## Status
IDLE

## Current task
None.

## Last completed task
Verified court calibration safety gate and concurrency protection.

## Last completed outcome
- Generated and verified calibration states are separate.
- Verification is bound to calibration ID and checksum.
- Recalibration invalidates stale measurements.
- Unverified calibration cannot feed downstream measurements.
- Manual calibration uses repository-managed workspace/S3.
- Stale concurrent saves are blocked by row-version checks.

## Next planned work
Set up multi-agent handoff workflow, then choose the next Pickleball stabilization task.

## Do not change without explicit instruction
- detector confidence formula or thresholds
- YOLO settings
- ByteTrack settings
- analytics formulas
- Match IQ formulas
- Padel gates
- ball tracking flag
- Railway variables
- storage limits
