# Play History Comparability Policy

Policy version: `play-history-comparability-v1`

Implementation:

- `app/services/history/comparability.py`
- `app/services/history/grouping.py`
- `app/services/history/progress_policy.py`

## Separate decisions

Play History exposes four independent decisions:

1. **Contribution** (`play-history-v1`): may this report contribute any Play History
   data?
2. **Comparability** (`play-history-comparability-v1`): may this report participate in
   this comparison?
3. **Trend** (`play-history-trend-v1`): do the comparable reports and deterministic
   groups support displaying a change?
4. **Interpretation** (`play-history-interpretation-v1`): may Court4 describe what the
   measured change means?

Each decision contains a status, player-facing reasons, limitations, source versions,
and its policy version. Statuses are `ELIGIBLE`, `PROVISIONAL`, `INELIGIBLE`, and
`NOT_EVALUATED`.

Contribution thresholds remain unchanged. A contribution-eligible report can still be
provisional or ineligible for comparison.

## Comparability inputs

The policy checks only persisted evidence:

- contribution status;
- recording-quality status;
- reliable observation and qualified tracked duration;
- tracking and measurement confidence when present;
- analytics schema, zone-definition, normalized court-geometry, units, and
  contribution-policy versions;
- missing or unreadable measurements.

Weak or unavailable tracking/measurement confidence blocks comparison when explicitly
present. A limited recording remains provisional. Missing measurements are not
inferred.

Match format and camera placement are not currently persisted. Their compatibility is
therefore explicitly unknown and all current comparisons remain provisional. Court4
does not infer singles, doubles, camera placement, tactical context, or opponent
conditions.

## Deterministic grouping

Grouping policy version: `play-history-grouping-v1`

- Sort ascending by normalized UTC analysis timestamp, then analysis ID.
- Deduplicate by analysis ID.
- Three comparable reports establish an initial baseline only.
- A displayed comparison requires at least four reports and at least two reports in
  each group.
- Use at most the eight most recent comparable reports.
- For an even window, split it into equal non-overlapping earlier and recent groups.
- For an odd window, omit the single middle report and use equal groups on either side.
- Groups never overlap.
- Reports outside the bounded window and an omitted middle report are disclosed in the
  trend limitations.
- A missing or unreadable timestamp makes the persisted job legacy/not evaluated; it
  is not silently inserted into a comparison.

Examples:

- 0 reports: no qualified history.
- 1–2 reports: building baseline.
- 3 reports: initial baseline, no trend graph.
- 4 reports: 2 earlier / 2 recent.
- 5 reports: 2 earlier / middle omitted / 2 recent.
- 8+ reports: most recent 8, split 4 / 4.

## Version compatibility

Numeric comparisons require identical analytics-schema, zone-definition,
court-geometry, units, and contribution-policy versions. Match IQ engine versions are
exposed separately. Mixed required versions produce an ineligible trend rather than a
coerced comparison.

All thresholds and minimum counts in this policy are private-alpha engineering
governance values. They are not scientifically validated performance standards.

Play History comparisons are read-only projections rather than persisted analysis
artifacts. They are regenerated deterministically under the policy versions returned
by the API. Previously generated individual analysis artifacts are never reinterpreted
or mutated in place.
