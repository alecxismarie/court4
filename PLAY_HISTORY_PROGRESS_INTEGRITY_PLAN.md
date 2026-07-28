# Play History Progress Integrity Plan

## Current logic

Play History currently includes reports that pass `play-history-v1`, sorts them by
analysis date, splits three or more reports into earlier and recent groups, averages
movement pace and zone percentages per report, and describes measured changes without
claiming verified improvement.

## Integrity findings

- One contribution decision is being reused as a proxy for comparability.
- Three reports can currently produce a comparison with a one-report earlier group.
- Zone percentages are averaged equally instead of using qualified tracked duration.
- Graphs do not expose complete report-count, period, duration, aggregation, or
  provisional context.
- Match format and camera placement are not persisted, so full compatibility cannot be
  claimed.
- Source schema, zone, geometry, units, grouping, aggregation, trend, and
  interpretation policy versions are not exposed together.
- Dashboard progress copy lacks period and qualified-observation denominators.

## Required corrections

- Keep contribution, comparability, trend, and interpretation decisions separate and
  versioned.
- Treat three reports as an initial baseline only; require two non-overlapping reports
  per group before displaying a provisional comparison.
- Use deterministic chronological grouping with a bounded window and explicit odd-count
  handling.
- Normalize group movement pace by qualified tracked duration and duration-weight zone
  occupancy. Exclude missing values rather than substituting zero.
- Retain outliers, expose their effect, and mark deterministic dominance/outlier checks
  as provisional governance safeguards.
- Expose group dates, supporting report counts and IDs, qualified duration,
  aggregation methods, policy versions, limitations, and provisional status in the
  typed API.
- Use neutral change language and state that observed changes do not automatically mean
  better or worse performance.
- Keep report-level evidence mechanics in Analysis History while adding a read-only
  contributing-report drill-down to Play History.

## Boundaries

This pass will not change source analytics, contribution thresholds, recording-quality
assessment, Match IQ, calibration, tracking, reviewer labels, Active Play, or existing
analysis artifacts. All initial comparison thresholds are engineering governance
values, not scientifically validated performance standards.
