from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.analytics import AnalyticsReport, TimelinePosition, TimelineReport
from app.schemas.match_iq import (
    MatchIQFocusRecommendation,
    MatchIQInsight,
    MatchIQMetricEvidence,
    MatchIQReport,
)

MATCH_IQ_ENGINE_VERSION = "match-iq-rules-v1"

MIN_RELIABLE_OBSERVATIONS = 3
MIN_RELIABLE_TRACKED_SECONDS = 1.0

HIGH_ZONE_PERCENTAGE = 55.0
LOW_TRANSITION_PERCENTAGE = 20.0
BALANCED_ZONE_MIN_PERCENTAGE = 20.0
BALANCED_ZONE_MAX_PERCENTAGE = 45.0
SHORT_TOTAL_DISTANCE_FEET = 10.0
MEANINGFUL_HALF_DISTANCE_DELTA_FEET = 5.0
HALF_DISTANCE_RATIO = 1.25

METRICS_USED = [
    "distance.total_distance_feet",
    "distance.average_movement_feet_per_second",
    "timeline_observation_count",
    "zone_occupancy.tracked_time_seconds",
    "zone_occupancy.kitchen.percentage",
    "zone_occupancy.transition_zone.percentage",
    "zone_occupancy.baseline_area.percentage",
    "timeline.positions",
]

DEFAULT_LIMITATIONS = [
    "Match IQ uses movement metrics only.",
    (
        "Court4 does not evaluate shots, serves, rallies, ball movement, opponents, "
        "scoring, or intent."
    ),
    "Court4 does not compare against previous matches because player history is not available yet.",
]


@dataclass(frozen=True)
class MatchIQRule:
    rule_id: str
    priority: int
    thresholds: dict[str, float]
    evaluate: Callable[[AnalyticsReport, TimelineReport | None], MatchIQInsight | None]


def generate_match_iq(
    *,
    analytics: AnalyticsReport,
    timeline: TimelineReport | None,
    created_at: datetime | None = None,
) -> MatchIQReport:
    report_created_at = created_at or datetime.now(tz=UTC)
    insufficient_reason = _insufficient_data_reason(analytics)
    if insufficient_reason:
        return MatchIQReport(
            analysis_id=analytics.analysis_id,
            status="insufficient_data",
            engine_version=MATCH_IQ_ENGINE_VERSION,
            summary="Court4 does not have enough movement data to generate a reliable Match IQ.",
            insights=[],
            focus=None,
            limitations=[insufficient_reason, *DEFAULT_LIMITATIONS],
            metrics_used=METRICS_USED,
            created_at=report_created_at,
        )

    insights = [
        insight
        for rule in sorted(_rules(), key=lambda item: item.priority)
        if (insight := rule.evaluate(analytics, timeline)) is not None
    ][:4]

    summary = _summary_for(analytics=analytics, insights=insights)
    return MatchIQReport(
        analysis_id=analytics.analysis_id,
        status="generated",
        engine_version=MATCH_IQ_ENGINE_VERSION,
        summary=summary,
        insights=insights,
        focus=_focus_for(insights),
        limitations=DEFAULT_LIMITATIONS,
        metrics_used=METRICS_USED,
        created_at=report_created_at,
    )


def _rules() -> tuple[MatchIQRule, ...]:
    return (
        MatchIQRule(
            rule_id="positioning-high-baseline-v1",
            priority=10,
            thresholds={"baseline_area_percentage_min": HIGH_ZONE_PERCENTAGE},
            evaluate=_high_baseline_occupancy,
        ),
        MatchIQRule(
            rule_id="positioning-high-kitchen-v1",
            priority=20,
            thresholds={"kitchen_percentage_min": HIGH_ZONE_PERCENTAGE},
            evaluate=_high_kitchen_occupancy,
        ),
        MatchIQRule(
            rule_id="positioning-high-transition-v1",
            priority=30,
            thresholds={"transition_zone_percentage_min": HIGH_ZONE_PERCENTAGE},
            evaluate=_high_transition_occupancy,
        ),
        MatchIQRule(
            rule_id="positioning-low-transition-v1",
            priority=40,
            thresholds={"transition_zone_percentage_max": LOW_TRANSITION_PERCENTAGE},
            evaluate=_low_transition_occupancy,
        ),
        MatchIQRule(
            rule_id="positioning-balanced-zones-v1",
            priority=50,
            thresholds={
                "zone_percentage_min": BALANCED_ZONE_MIN_PERCENTAGE,
                "zone_percentage_max": BALANCED_ZONE_MAX_PERCENTAGE,
            },
            evaluate=_balanced_positioning,
        ),
        MatchIQRule(
            rule_id="positioning-primary-zone-v1",
            priority=55,
            thresholds={"high_zone_percentage_max": HIGH_ZONE_PERCENTAGE},
            evaluate=_primary_zone_distribution,
        ),
        MatchIQRule(
            rule_id="movement-short-total-distance-v1",
            priority=60,
            thresholds={"total_distance_feet_max": SHORT_TOTAL_DISTANCE_FEET},
            evaluate=_short_total_distance,
        ),
        MatchIQRule(
            rule_id="movement-measured-distance-v1",
            priority=70,
            thresholds={
                "timeline_observation_count_min": MIN_RELIABLE_OBSERVATIONS,
                "tracked_time_seconds_min": MIN_RELIABLE_TRACKED_SECONDS,
            },
            evaluate=_measured_distance,
        ),
        MatchIQRule(
            rule_id="timeline-first-half-higher-distance-v1",
            priority=80,
            thresholds={
                "distance_ratio_min": HALF_DISTANCE_RATIO,
                "distance_delta_feet_min": MEANINGFUL_HALF_DISTANCE_DELTA_FEET,
            },
            evaluate=_first_half_higher_distance,
        ),
        MatchIQRule(
            rule_id="timeline-second-half-higher-distance-v1",
            priority=90,
            thresholds={
                "distance_ratio_min": HALF_DISTANCE_RATIO,
                "distance_delta_feet_min": MEANINGFUL_HALF_DISTANCE_DELTA_FEET,
            },
            evaluate=_second_half_higher_distance,
        ),
    )


def _high_baseline_occupancy(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    percentage = analytics.zone_occupancy.baseline_area.percentage
    if percentage < HIGH_ZONE_PERCENTAGE:
        return None
    return _zone_insight(
        insight_id="baseline-occupancy",
        rule_id="positioning-high-baseline-v1",
        priority=10,
        title="Baseline area was the largest positioning signal",
        zone_label="baseline area",
        metric="zone_occupancy.baseline_area.percentage",
        percentage=percentage,
        threshold=f">= {HIGH_ZONE_PERCENTAGE:.1f}%",
    )


def _high_kitchen_occupancy(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    percentage = analytics.zone_occupancy.kitchen.percentage
    if percentage < HIGH_ZONE_PERCENTAGE:
        return None
    return _zone_insight(
        insight_id="kitchen-occupancy",
        rule_id="positioning-high-kitchen-v1",
        priority=20,
        title="Kitchen time was the largest positioning signal",
        zone_label="kitchen",
        metric="zone_occupancy.kitchen.percentage",
        percentage=percentage,
        threshold=f">= {HIGH_ZONE_PERCENTAGE:.1f}%",
    )


def _high_transition_occupancy(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    percentage = analytics.zone_occupancy.transition_zone.percentage
    if percentage < HIGH_ZONE_PERCENTAGE:
        return None
    return _zone_insight(
        insight_id="transition-occupancy",
        rule_id="positioning-high-transition-v1",
        priority=30,
        title="Transition-zone time was the largest positioning signal",
        zone_label="transition zone",
        metric="zone_occupancy.transition_zone.percentage",
        percentage=percentage,
        threshold=f">= {HIGH_ZONE_PERCENTAGE:.1f}%",
    )


def _low_transition_occupancy(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    percentage = analytics.zone_occupancy.transition_zone.percentage
    if percentage > LOW_TRANSITION_PERCENTAGE:
        return None
    return MatchIQInsight(
        id="low-transition-occupancy",
        rule_id="positioning-low-transition-v1",
        priority=40,
        title="Transition-zone time was limited",
        statement=(f"Court4 measured {percentage:.1f}% of tracked time in the transition zone."),
        evidence=[
            _evidence(
                metric="zone_occupancy.transition_zone.percentage",
                label="Transition-zone occupancy",
                value=percentage,
                formatted_value=f"{percentage:.1f}%",
                threshold=f"<= {LOW_TRANSITION_PERCENTAGE:.1f}%",
            )
        ],
    )


def _balanced_positioning(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    percentages = {
        "Kitchen": analytics.zone_occupancy.kitchen.percentage,
        "Transition": analytics.zone_occupancy.transition_zone.percentage,
        "Baseline": analytics.zone_occupancy.baseline_area.percentage,
    }
    if (
        min(percentages.values()) < BALANCED_ZONE_MIN_PERCENTAGE
        or max(percentages.values()) > BALANCED_ZONE_MAX_PERCENTAGE
    ):
        return None
    formatted = ", ".join(f"{label} {value:.1f}%" for label, value in percentages.items())
    occupancy_range = f"{min(percentages.values()):.1f}% to {max(percentages.values()):.1f}%"
    return MatchIQInsight(
        id="balanced-positioning",
        rule_id="positioning-balanced-zones-v1",
        priority=50,
        title="Tracked time was balanced across court zones",
        statement=f"Court4 measured a balanced zone distribution: {formatted}.",
        evidence=[
            _evidence(
                metric="zone_occupancy.zone_percentages",
                label="Zone occupancy range",
                value=occupancy_range,
                formatted_value=occupancy_range,
                threshold=(
                    f"each zone between {BALANCED_ZONE_MIN_PERCENTAGE:.1f}% "
                    f"and {BALANCED_ZONE_MAX_PERCENTAGE:.1f}%"
                ),
            )
        ],
    )


def _primary_zone_distribution(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    zones = {
        "kitchen": (
            "Kitchen",
            analytics.zone_occupancy.kitchen.percentage,
            "zone_occupancy.kitchen.percentage",
        ),
        "transition zone": (
            "Transition zone",
            analytics.zone_occupancy.transition_zone.percentage,
            "zone_occupancy.transition_zone.percentage",
        ),
        "baseline area": (
            "Baseline area",
            analytics.zone_occupancy.baseline_area.percentage,
            "zone_occupancy.baseline_area.percentage",
        ),
    }
    zone_name, (zone_label, percentage, metric) = max(
        zones.items(),
        key=lambda item: item[1][1],
    )
    if percentage >= HIGH_ZONE_PERCENTAGE:
        return None
    if (
        min(zone[1] for zone in zones.values()) >= BALANCED_ZONE_MIN_PERCENTAGE
        and percentage <= BALANCED_ZONE_MAX_PERCENTAGE
    ):
        return None
    return MatchIQInsight(
        id="primary-zone-distribution",
        rule_id="positioning-primary-zone-v1",
        priority=55,
        title=f"{zone_label} was the largest measured zone",
        statement=(
            f"Court4 measured {percentage:.1f}% of tracked time in the {zone_name}, "
            "without any zone reaching the high-occupancy threshold."
        ),
        evidence=[
            _evidence(
                metric=metric,
                label=f"{zone_label} occupancy",
                value=percentage,
                formatted_value=f"{percentage:.1f}%",
                threshold=f"largest zone and < {HIGH_ZONE_PERCENTAGE:.1f}%",
            )
        ],
    )


def _short_total_distance(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    distance = analytics.distance.total_distance_feet
    if distance > SHORT_TOTAL_DISTANCE_FEET:
        return None
    return MatchIQInsight(
        id="short-total-distance",
        rule_id="movement-short-total-distance-v1",
        priority=60,
        title="Tracked movement distance was short",
        statement=f"Court4 measured {distance:.1f} ft of movement in the tracked sample.",
        evidence=[
            _evidence(
                metric="distance.total_distance_feet",
                label="Total distance",
                value=distance,
                formatted_value=f"{distance:.1f} ft",
                threshold=f"<= {SHORT_TOTAL_DISTANCE_FEET:.1f} ft",
            )
        ],
    )


def _measured_distance(
    analytics: AnalyticsReport,
    _timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    distance = analytics.distance.total_distance_feet
    speed = analytics.distance.average_movement_feet_per_second
    tracked_seconds = analytics.zone_occupancy.tracked_time_seconds
    return MatchIQInsight(
        id="measured-movement",
        rule_id="movement-measured-distance-v1",
        priority=70,
        title="Movement sample was measured",
        statement=(
            f"Court4 measured {distance:.1f} ft over {tracked_seconds:.1f} seconds, "
            f"averaging {speed:.2f} ft/s."
        ),
        evidence=[
            _evidence(
                metric="distance.total_distance_feet",
                label="Total distance",
                value=distance,
                formatted_value=f"{distance:.1f} ft",
                threshold="reported from analytics distance metric",
            ),
            _evidence(
                metric="distance.average_movement_feet_per_second",
                label="Average movement",
                value=speed,
                formatted_value=f"{speed:.2f} ft/s",
                threshold="reported from analytics distance metric",
            ),
            _evidence(
                metric="zone_occupancy.tracked_time_seconds",
                label="Tracked time",
                value=tracked_seconds,
                formatted_value=f"{tracked_seconds:.1f} sec",
                threshold=f">= {MIN_RELIABLE_TRACKED_SECONDS:.1f} sec",
            ),
        ],
    )


def _first_half_higher_distance(
    _analytics: AnalyticsReport,
    timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    half_metrics = _half_distance_metrics(timeline)
    if not half_metrics:
        return None
    first_half, second_half = half_metrics
    if first_half < second_half * HALF_DISTANCE_RATIO:
        return None
    if first_half - second_half < MEANINGFUL_HALF_DISTANCE_DELTA_FEET:
        return None
    return _half_distance_insight(
        insight_id="first-half-distance",
        rule_id="timeline-first-half-higher-distance-v1",
        priority=80,
        title="First half had more tracked movement",
        first_half=first_half,
        second_half=second_half,
    )


def _second_half_higher_distance(
    _analytics: AnalyticsReport,
    timeline: TimelineReport | None,
) -> MatchIQInsight | None:
    half_metrics = _half_distance_metrics(timeline)
    if not half_metrics:
        return None
    first_half, second_half = half_metrics
    if second_half < first_half * HALF_DISTANCE_RATIO:
        return None
    if second_half - first_half < MEANINGFUL_HALF_DISTANCE_DELTA_FEET:
        return None
    return _half_distance_insight(
        insight_id="second-half-distance",
        rule_id="timeline-second-half-higher-distance-v1",
        priority=90,
        title="Second half had more tracked movement",
        first_half=first_half,
        second_half=second_half,
    )


def _zone_insight(
    *,
    insight_id: str,
    rule_id: str,
    priority: int,
    title: str,
    zone_label: str,
    metric: str,
    percentage: float,
    threshold: str,
) -> MatchIQInsight:
    return MatchIQInsight(
        id=insight_id,
        rule_id=rule_id,
        priority=priority,
        title=title,
        statement=f"Court4 measured {percentage:.1f}% of tracked time in the {zone_label}.",
        evidence=[
            _evidence(
                metric=metric,
                label=f"{zone_label.title()} occupancy",
                value=percentage,
                formatted_value=f"{percentage:.1f}%",
                threshold=threshold,
            )
        ],
    )


def _half_distance_insight(
    *,
    insight_id: str,
    rule_id: str,
    priority: int,
    title: str,
    first_half: float,
    second_half: float,
) -> MatchIQInsight:
    larger_half = "first half" if first_half > second_half else "second half"
    larger_value = max(first_half, second_half)
    smaller_value = min(first_half, second_half)
    return MatchIQInsight(
        id=insight_id,
        rule_id=rule_id,
        priority=priority,
        title=title,
        statement=(
            f"The {larger_half} covered {larger_value:.1f} ft, compared with "
            f"{smaller_value:.1f} ft in the other half."
        ),
        evidence=[
            _evidence(
                metric="timeline.positions.first_half_distance_feet",
                label="First-half distance",
                value=first_half,
                formatted_value=f"{first_half:.1f} ft",
                threshold=(
                    f"larger half >= {HALF_DISTANCE_RATIO:.2f}x other half and "
                    f"delta >= {MEANINGFUL_HALF_DISTANCE_DELTA_FEET:.1f} ft"
                ),
            ),
            _evidence(
                metric="timeline.positions.second_half_distance_feet",
                label="Second-half distance",
                value=second_half,
                formatted_value=f"{second_half:.1f} ft",
                threshold=(
                    f"larger half >= {HALF_DISTANCE_RATIO:.2f}x other half and "
                    f"delta >= {MEANINGFUL_HALF_DISTANCE_DELTA_FEET:.1f} ft"
                ),
            ),
        ],
    )


def _half_distance_metrics(timeline: TimelineReport | None) -> tuple[float, float] | None:
    if timeline is None or len(timeline.positions) < MIN_RELIABLE_OBSERVATIONS:
        return None
    first_timestamp = timeline.positions[0].timestamp_seconds
    last_timestamp = timeline.positions[-1].timestamp_seconds
    if last_timestamp <= first_timestamp:
        return None
    midpoint = first_timestamp + ((last_timestamp - first_timestamp) / 2)
    first_half_positions = [
        position for position in timeline.positions if position.timestamp_seconds <= midpoint
    ]
    second_half_positions = [
        position for position in timeline.positions if position.timestamp_seconds >= midpoint
    ]
    if len(first_half_positions) < 2 or len(second_half_positions) < 2:
        return None
    return (_distance(first_half_positions), _distance(second_half_positions))


def _distance(positions: Sequence[TimelinePosition]) -> float:
    total_distance = 0.0
    for current, next_position in zip(positions, positions[1:], strict=False):
        total_distance += (
            (next_position.x - current.x) ** 2 + (next_position.y - current.y) ** 2
        ) ** 0.5
    return total_distance


def _summary_for(*, analytics: AnalyticsReport, insights: Sequence[MatchIQInsight]) -> str:
    if insights:
        primary = insights[0]
        return (
            f"Match IQ found {len(insights)} movement observation"
            f"{'' if len(insights) == 1 else 's'}. Top signal: {primary.statement}"
        )
    return (
        "Court4 measured movement data but no rule crossed a Match IQ threshold. "
        f"Tracked sample: {analytics.timeline_observation_count} observations over "
        f"{analytics.zone_occupancy.tracked_time_seconds:.1f} seconds."
    )


def _focus_for(insights: Sequence[MatchIQInsight]) -> MatchIQFocusRecommendation | None:
    if not insights:
        return None
    primary = insights[0]
    if primary.id in {
        "baseline-occupancy",
        "kitchen-occupancy",
        "transition-occupancy",
        "low-transition-occupancy",
        "balanced-positioning",
        "primary-zone-distribution",
    }:
        return MatchIQFocusRecommendation(
            title="Focus area: positioning mix",
            statement=(
                "Use the zone-occupancy insight as the main movement focus for this match. "
                "Court4 is only reporting where tracked time was spent."
            ),
            supporting_insight_ids=[primary.id],
        )
    if primary.id == "short-total-distance":
        return MatchIQFocusRecommendation(
            title="Focus area: movement sample length",
            statement=(
                "Use a longer tracked segment before treating Match IQ as a practice guide. "
                "This focus is based only on the short total-distance metric."
            ),
            supporting_insight_ids=[primary.id],
        )
    return MatchIQFocusRecommendation(
        title="Focus area: measured movement",
        statement=(
            "Review the measured movement metrics and artifacts for the selected player. "
            "Court4 is not assigning intent or evaluating shot quality."
        ),
        supporting_insight_ids=[primary.id],
    )


def _insufficient_data_reason(analytics: AnalyticsReport) -> str | None:
    if analytics.timeline_observation_count < MIN_RELIABLE_OBSERVATIONS:
        return (
            "Insufficient data: fewer than "
            f"{MIN_RELIABLE_OBSERVATIONS} timeline observations were available."
        )
    if analytics.zone_occupancy.tracked_time_seconds < MIN_RELIABLE_TRACKED_SECONDS:
        return (
            "Insufficient data: tracked movement time was below "
            f"{MIN_RELIABLE_TRACKED_SECONDS:.1f} seconds."
        )
    return None


def _evidence(
    *,
    metric: str,
    label: str,
    value: float | int | str,
    formatted_value: str,
    threshold: str,
) -> MatchIQMetricEvidence:
    return MatchIQMetricEvidence(
        metric=metric,
        label=label,
        value=value,
        formatted_value=formatted_value,
        threshold=threshold,
    )
