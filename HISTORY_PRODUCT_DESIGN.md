# Court4 History Product Design

## Product contract

**Analysis History** answers “What did Court4 analyze?” It retains every persisted
analysis: ready, limited, unsuitable, processing, failed, incomplete, and legacy.
Evidence quality never removes a recording from this history.

**Play History** answers “How has my observed play changed over time?” It is a
read-only projection that uses only analyses included by versioned contribution,
comparability, trend, interpretation, grouping, and aggregation policies.

> Every recording remains available in Analysis History. Only evidence-qualified
> analyses may contribute to Play History.

## Behavior

- Contribution eligibility requires completed analytics, non-blocking recording
  quality, sufficient observation coverage and usable tracked time, acceptable track
  continuity, and available movement measurements.
- Contribution decisions are separate from comparability, trend, and interpretation
  decisions. Every decision exposes status, reasons, limitations, source versions, and
  its policy version.
- Processing or incomplete analyses are provisional. Missing current evidence fields
  or unreadable legacy metadata are not evaluated. Court4 does not infer missing facts.
- Play History aggregates included analyses only, uses qualified observation rather
  than upload duration, preserves units and denominators, and does not compare mixed
  required source versions.
- Fewer than three comparable analyses is a building-baseline state. Exactly three
  establish an initial baseline without a trend graph.
- Four or more comparable analyses may form deterministic, non-overlapping earlier and
  recent groups with at least two reports each.
- Movement pace is normalized by qualified tracked duration. Court-zone shares are
  duration weighted. Missing values are excluded rather than treated as zero.
- Movement pace and court position describe change, not match success. Court4 does not
  label those changes as verified improvement without a validated outcome metric.
- Contribution states, quality gates, evidence reasons, and processing details stay
  on Analysis History. Play History shows player-facing evaluation, graphs, play-style
  changes, verified report insights, and a concise supporting-report drill-down.
- Legacy analyses remain reopenable when their original deep link is valid and never
  enter totals by assumption.

Private-alpha scope is one local filesystem workspace. There is no account identity,
user isolation, cross-device sync, or database-backed ownership yet.
