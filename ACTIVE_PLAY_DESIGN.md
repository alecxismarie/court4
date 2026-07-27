# Court4 Shadow Active Play Design

## Boundary

Phase 1.6A produces an internal, deterministic estimate of recording intervals. It does
not detect rallies, points, serves, shots, scores, tactics, or ball movement, and it
does not change player-facing analytics.

Allowed states are:

- `LIKELY_ACTIVE`
- `LIKELY_IDLE`
- `UNKNOWN`

Every window and merged interval carries a categorical confidence, evidence coverage,
motion signals, deterministic reason codes, limitations, candidate/raw-fragment
lineage, and `active-play-v1`.

Confidence is `MODERATE`, `LOW`, or `NOT_AVAILABLE`; shadow v1 deliberately never
emits `HIGH`. Evidence reasons are typed and grouped as positive support
(`SUSTAINED_MULTI_PLAYER_MOVEMENT`, `SIMULTANEOUS_MOVEMENT`,
`MEANINGFUL_DIRECTION_CHANGES`, `SUSTAINED_LOW_MOVEMENT`,
`STABLE_LOW_ACTIVITY`, `SUFFICIENT_TRACKED_COVERAGE`) or abstention support
(`INSUFFICIENT_TRACKED_COVERAGE`, `INSUFFICIENT_RELIABLE_PLAYERS`,
`ONE_PLAYER_ONLY`, `TRACKING_GAP`, `SEVERE_TRACKING_GAPS`,
`FRAGMENTED_CANDIDATES`, `UNSUITABLE_RECORDING`, `STALE_SOURCE_ARTIFACT`,
`SHORT_CONTEXT`, `KITCHEN_LOW_MOVEMENT_SAFEGUARD`, `CONFLICTING_EVIDENCE`). The
schema is the exhaustive source.

## Evidence contract

Feature windows are time-based and non-overlapping. Position smoothing and derivatives
stay within one raw track and one continuity-safe observation segment. Long gaps,
track changes, occlusion-like coverage loss, short context, unsuitable recording
evidence, or too few reliable player streams force `UNKNOWN`.

Coverage is elapsed window time with the minimum number of reliable candidate streams
observed, not total candidate duration and not the existing in-court observation ratio.
Low-movement `USABLE` candidates remain eligible as Active Play evidence even if the
player-selection policy excludes them.

Provisional motion evidence includes smoothed speed, speed-change proxy, normalized
movement intensity, direction-change frequency, stationary duration, visible/reliable
player counts, simultaneous movement, gap severity, and candidate continuity quality.
All values and thresholds are centralized in the immutable versioned policy module.

`LIKELY_ACTIVE` requires sufficient coverage plus sustained, simultaneous movement
across at least two reliable candidate streams. `LIKELY_IDLE` requires sufficient
coverage of multiple reliable streams and sustained low activity. A stationary player
never makes a window idle when active peers are observed. One moving player with
missing peers, gaps, or conflicting evidence remains `UNKNOWN`.

## Interval construction

The engine classifies windows first. Adjacent windows merge only when state matches,
the time boundary is continuous, and neither side hides an unknown gap. Merged
confidence is the weaker confidence. Coverage and signals are duration-weighted or
combined conservatively; reasons, limitations, candidate IDs, and raw fragments are
deduplicated in deterministic order. Short and rapidly changing intervals are
preserved rather than cosmetically smoothed.

## Persistence and shadow access

The stage writes:

- `active_play/windows.jsonl`
- `active_play/features.jsonl`
- `active_play/active_play.json`

The report records schema/policy versions and SHA-256 lineage for tracking,
observations, and candidate artifacts. Generation is idempotent for an existing valid
artifact. Only debug routes under
`/api/v1/analyses/{analysis_id}/debug/active-play` expose it. Normal jobs, analytics,
Match IQ, cards, dashboards, and frontend contracts remain unchanged.

## Calibration compatibility

Calibration samples may add partially reviewed Active Play intervals with human state,
Court4 state, boundary tolerance, reviewer confidence, false-active/false-idle flags,
unknown-but-reviewable state, and notes. Metrics use reviewed seconds and interval
counts, keep uncertain/unreviewed labels out of agreement denominators, and report
abstention and reviewed coverage explicitly. Validation and holdout samples never tune
policy; no evaluator mutates policy or reviewer labels.

The policy and all resulting metrics are provisional until a balanced, independently
reviewed development/validation/holdout dataset meets the activation gates in
`PHASE_1_6_PRODUCT_READINESS_AUDIT.md`.
