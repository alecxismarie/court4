# Court4 Recording Standard

## User recording guide

- Place the camera behind or diagonally behind the baseline.
- Keep the full court visible.
- Use landscape orientation when possible.
- Keep the camera stable.
- Record at least 720p; 1080p is recommended.
- Capture enough continuous gameplay to provide a useful sample.
- Usable tracked time matters more than total video duration.

Court4 assesses only signals it can measure. It does not claim to recognize gameplay,
rallies, paddles, or whether every visible person is a player.

## Quality levels

| Level | Meaning |
| --- | --- |
| `EXCELLENT` | All minimum checks pass and the stronger recommended recording/tracking checks pass. |
| `GOOD` | The evidence passes all minimum checks with no material warning. |
| `LIMITED` | Processing may continue, but warnings limit interpretation or reduce output to measurements. |
| `UNSUITABLE` | At least one blocking failure prevents honest movement insight. |

## Two-stage preflight

### Upload preflight

Runs after video inspection and persists in `metadata.json` and `job.json`.

| Signal | Minimum | Recommended |
| --- | ---: | ---: |
| Format | A configured supported video extension and readable metadata | — |
| Orientation | Vertical is allowed with a warning | Landscape |
| Resolution | 720 pixels on the short edge | 1080 pixels on the short edge |
| FPS | 24 FPS | 30 FPS |
| Total duration | 10 seconds | 60 seconds |

A short edge below 480 pixels, FPS below 15, or duration below 10 seconds is initially
blocking. Values between the blocking and minimum thresholds are `LIMITED`.

### Analysis readiness

Runs after court calibration, person tracking, and candidate building. It is persisted in
`tracking/player_candidates.json` and `job.json`.

| Signal | Minimum | Recommended |
| --- | ---: | ---: |
| Court visibility/calibration | Valid completed calibration | Automatic detection confidence at least 0.72, or reviewed manual calibration |
| Player candidates | At least one selectable `USABLE` candidate | A selected or available `STRONG` candidate |
| Player visibility | 65% in calibrated court | 85% in calibrated court |
| Tracked duration | 5 continuity-safe seconds | 30 seconds |
| Tracking gaps | No blocking gap; gap ratio at most 50% | Gap ratio at most 10% |
| Fragment count | At most 3 selectable fragments | 1 fragment |

Tracked duration is computed from observed fragments. Gap duration is the difference
between the candidate timestamp span and observed fragment duration. No movement is
interpolated through a gap.

## Assessment response

Each stage returns:

- `status`;
- typed `signals`;
- `passed_checks`;
- `warnings`;
- `blocking_failures`;
- `reason_codes`; and
- `guidance`.

Reason codes are for diagnostics and tests. The normal UI presents the human-readable
check messages and guidance instead of internal codes.

## Validation status

These are initial engineering thresholds chosen to abstain on clearly weak evidence.
They have not been validated against a labeled recording-quality dataset, player
identity ground truth, tracking precision/recall, or movement measurement error. Changes
to them must be centralized, documented, and accompanied by fixtures plus real-video
review.
