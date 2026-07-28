# Play History Aggregation Policy

Policy version: `play-history-aggregation-v1`

Implementation: `app/services/history/aggregation.py`

## Movement pace

Group movement pace is:

> sum of measured distance in metres ÷ sum of qualified tracked seconds

It is time-normalized and never compares raw cumulative distance across recordings.
Reports without a positive qualified tracked-time denominator are excluded from this
metric. The graph exposes the method, unit, contributing report IDs/counts, qualified
observation duration, period, and provisional status.

## Court positioning

Kitchen, transition, and baseline shares are:

> sum of qualified seconds in the zone ÷ sum of qualified tracked seconds

This duration-weighted calculation prevents a short recording from receiving the same
weight as a materially longer recording. Source percentages are not averaged equally.

## Counts and missing values

No raw event count is currently compared. A future count metric must be normalized by
qualified observation time unless recordings have an explicitly compatible
denominator.

Missing values are excluded. They are never replaced with zero. If either comparison
group lacks a usable value, the typed metric is `null` and the graph displays
`Unavailable` as a gap.

## Outliers and dominance

No outlier is silently removed.

- All eligible values remain in the aggregate.
- A movement-pace observation more than 3× above or below the group median marks the
  result provisional and is disclosed.
- If one report supplies more than 60% of a group’s qualified duration, the weighted
  result remains visible but is marked provisional and disclosed.

These are deterministic private-alpha engineering governance checks, not scientific
outlier or performance thresholds.

## Interpretation boundary

Neutral direction labels are `increased`, `decreased`, and `remained similar`.
Court-position summaries require at least a five-percentage-point difference before
describing a provisional change. Smaller differences show “No clear change yet.”

The graph uses neutral colors and no positive/negative arrows. Every comparison states:

> These changes describe Court4’s observations across comparable recordings. They do
> not automatically mean better or worse performance.

Movement and court-position changes do not establish skill, tactics, intent,
efficiency, match outcome, or genuine performance improvement.
