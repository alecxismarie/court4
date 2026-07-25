# Court4 Calibration Annotation Guide

## General rules

Review the video and artifacts independently of the desired metric outcome.

- Use `NOT_REVIEWED` when the field has not been checked.
- Use `UNKNOWN` when it was checked but cannot be established reliably.
- Leave optional counts absent rather than guessing.
- Add notes for ambiguity, occlusion, or assumptions.
- Use stable pseudonymous IDs such as `player-near-left`, not personal names.
- Never change Court4 artifacts to make them agree with a review.

Partial review is valid and expected while the dataset grows.

## Recording review

Record:

- indoor or outdoor;
- singles or doubles;
- camera position and distance;
- landscape or vertical;
- source resolution and frame rate;
- lighting;
- obstruction;
- recording stability;
- court visibility; and
- independently judged quality.

Court4 does not automatically verify environment, match format, camera distance,
lighting, stability, or obstruction. These are human labels even when metadata such as
resolution and FPS is machine-readable.

## Player identity review

### Stable players

Create one `stable_real_players` entry for each expected court player whose identity can
be followed. A stable ID represents a person within one sample only unless a separate,
consented cross-video protocol is established.

### Candidate mappings

Review every candidate included in the annotation scope:

- `COURT_PLAYER`: a primary candidate representing a court player;
- `DUPLICATE`: another fragment representing a player already mapped;
- `SPECTATOR`: a real person who is not an active court player;
- `FALSE_DETECTION`: not a person or not a meaningful person track;
- `UNCERTAIN`: the reviewer cannot determine the role; or
- `NOT_REVIEWED`: not yet examined.

One player may map to several candidate fragments. Each candidate ID may appear once in
the mapping list. Court-player and duplicate mappings must reference a declared stable
player ID.

`mapping_correct` records whether the candidate-to-player association is correct after
review. Unknown and unreviewed mappings are excluded from mapping-accuracy metrics.

Record the selected candidate and expected selected player only when selection occurred
and identity is visually confirmed.

## Tracking continuity intervals

Interval review is optional. Select representative spans that cover clean tracking,
occlusion, gaps, fragmentation, and identity ambiguity.

For each interval record:

- start and end seconds;
- expected stable player;
- Court4 candidate ID, when present;
- identity correct or incorrect;
- continuity acceptable or broken;
- occlusion;
- player outside frame;
- tracking gap;
- observed-time agreement;
- gap-label agreement; and
- whether the interval remains uncertain.

End time must be after start time. Intervals for the same expected player may touch but
must not overlap. Different players may have overlapping time intervals.

Do not label an identity switch when the player is genuinely outside the frame. Use the
outside-frame and uncertainty labels so later analysis can distinguish detector error
from unavailable evidence.

## Insight review

Create one `generated_insights` entry per reviewed insight using the persisted insight
identifier. Review:

- measurement correctness;
- whether interpretation is justified by the measurement;
- confidence appropriateness;
- limitation accuracy;
- conservative action;
- wording understandability; and
- expected gate.

Measurement correctness and interpretation justification are separate. A numeric
measurement can be correct while a conclusion is unsupported. Likewise, clear wording
does not make an unsupported conclusion valid.

Use `NOT_REVIEWED` for dimensions outside the review scope. Per-insight metrics exclude
those fields.

## Review completion

Use the CLI to find remaining work:

```powershell
python -m scripts.calibrate_evidence review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence unresolved-mappings calibration/manifest.v2.json
python -m scripts.calibrate_evidence insight-review-status calibration/manifest.v2.json
python -m scripts.calibrate_evidence artifact-status calibration/manifest.v2.json
```

Only change `review_status` to `REVIEWED` when the declared review scope is complete and
notes explain intentionally unreviewed areas. Generated reports never update the
manifest.

## Interpreting metrics

Every metric uses only reviewed labels. A zero denominator means no reviewed evidence,
not zero errors. Raw duplicate and missed counts per sample intentionally do not show a
percentage because a percentage would be misleading.

All results remain provisional when review coverage is below the configured minimum.
Dataset balance is a collection warning and does not validate scientific
representativeness.
