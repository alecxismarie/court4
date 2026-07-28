# Play History Contribution Policy

Policy version: `play-history-v1`

The centralized implementation is
`app/services/history/policy.py`. Frontend code displays backend decisions and does not
reimplement eligibility.

## Decision order

1. Failed analyses are `EXCLUDED`.
2. An `UNSUITABLE` analysis-readiness assessment or any blocking evidence failure is
   `EXCLUDED`.
3. Pending, processing, or incomplete analyses are `PROVISIONAL`.
4. Completed legacy analyses without current analytics or evidence fields are
   `NOT_EVALUATED`.
5. Current completed analyses are `EXCLUDED` when observation coverage, usable tracked
   duration, continuity, fragment count, observed duration, movement duration, or
   explicit measurement confidence fails the current minimum.
6. Otherwise the analysis is `INCLUDED`.

The policy reuses the existing `recording-quality-v1` engineering thresholds. It does
not change recording-quality assessment, Match IQ gates, analytics calculations, or
confidence calculations. Low interpretation or recommendation confidence alone does
not exclude otherwise trustworthy movement measurements.

## Contribution-safe totals

- Include each analysis ID at most once and include only `INCLUDED` decisions.
- Sum `analytics.observed_duration_seconds` for reliable observation and
  `zone_occupancy.tracked_time_seconds` for qualified movement time.
- Never substitute upload duration, missing values, zeros for unavailable values, or
  Active Play shadow output.
- Derive the most-observed zone from included zone seconds only. Report summed zone
  seconds as its denominator and the number of contributing analyses.
- Show verified Match IQ summaries only for included analyses with generated
  `NORMAL` or `CAUTIOUS` reports.

Comparability and progress rules are intentionally separate from contribution. See:

- `PLAY_HISTORY_COMPARABILITY_POLICY.md`
- `PLAY_HISTORY_AGGREGATION_POLICY.md`

Reason codes and contribution decisions are retained in the typed API for auditability.
They are rendered on Analysis History, not on the player-facing Play History page.
