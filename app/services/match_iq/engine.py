from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas.analytics import AnalyticsReport, TimelineReport
from app.schemas.match_iq import (
    InsightQualityGate,
    MatchIQConfidence,
    MatchIQConfidenceRating,
    MatchIQFocusRecommendation,
    MatchIQInsight,
    MatchIQMetricEvidence,
    MatchIQReport,
)
from app.schemas.recording_quality import RecordingQualityAssessment, RecordingQualityLevel

MATCH_IQ_ENGINE_VERSION = "match-iq-rules-v2"

MIN_OBSERVATIONS = 3
MIN_TRACKED_SECONDS = 1.0
CAUTIOUS_TRACKED_SECONDS = 15.0
HIGH_ZONE_PERCENTAGE = 55.0
LOW_TRANSITION_PERCENTAGE = 20.0
BALANCED_ZONE_MIN_PERCENTAGE = 20.0
BALANCED_ZONE_MAX_PERCENTAGE = 45.0
SHORT_TOTAL_DISTANCE_FEET = 10.0

METRICS_USED = [
    "distance.total_distance_feet",
    "distance.average_movement_feet_per_second",
    "timeline_observation_count",
    "observed_duration_seconds",
    "unobserved_gap_seconds",
    "source_fragment_count",
    "zone_occupancy.tracked_time_seconds",
    "zone_occupancy.kitchen.percentage",
    "zone_occupancy.transition_zone.percentage",
    "zone_occupancy.baseline_area.percentage",
]

DEFAULT_LIMITATIONS = [
    "Results describe only the continuity-safe movement sample Court4 observed.",
    (
        "Court4 does not evaluate shots, serves, rallies, ball movement, opponents, "
        "scoring, outcomes, tactics, or intent."
    ),
    "Zone labels describe court geometry, not whether positioning was good or bad.",
]


@dataclass(frozen=True)
class MatchIQRule:
    rule_id: str
    priority: int
    evaluate: Callable[
        [AnalyticsReport, MatchIQConfidence, InsightQualityGate],
        MatchIQInsight | None,
    ]


def generate_match_iq(
    *,
    analytics: AnalyticsReport,
    timeline: TimelineReport | None,
    recording_quality: RecordingQualityAssessment | None = None,
    created_at: datetime | None = None,
) -> MatchIQReport:
    del timeline  # Phase 1.4 deliberately disables unsafe timeline-half rules.
    report_created_at = created_at or datetime.now(tz=UTC)
    gate = _quality_gate(analytics, recording_quality)
    confidence = _confidence_for(analytics, recording_quality, gate)
    insufficient_reason = _insufficient_data_reason(analytics, recording_quality)
    if gate == "INSUFFICIENT_EVIDENCE":
        return MatchIQReport(
            analysis_id=analytics.analysis_id,
            status="insufficient_data",
            engine_version=MATCH_IQ_ENGINE_VERSION,
            summary="Insufficient evidence for a verified movement insight.",
            insights=[],
            focus=None,
            limitations=[
                insufficient_reason or "Recording or tracking evidence is unsuitable.",
                *DEFAULT_LIMITATIONS,
            ],
            metrics_used=METRICS_USED,
            quality_gate=gate,
            confidence=confidence,
            recording_quality=recording_quality,
            created_at=report_created_at,
        )

    insights = [
        insight
        for rule in sorted(_rules(), key=lambda item: item.priority)
        if (insight := rule.evaluate(analytics, confidence, gate)) is not None
    ][:4]
    return MatchIQReport(
        analysis_id=analytics.analysis_id,
        status="generated",
        engine_version=MATCH_IQ_ENGINE_VERSION,
        summary=_summary_for(analytics=analytics, insights=insights, gate=gate),
        insights=insights,
        focus=_focus_for(insights, gate),
        limitations=_report_limitations(analytics, recording_quality),
        metrics_used=METRICS_USED,
        quality_gate=gate,
        confidence=confidence,
        recording_quality=recording_quality,
        created_at=report_created_at,
    )


def _rules() -> tuple[MatchIQRule, ...]:
    return (
        MatchIQRule("positioning-high-baseline-v2", 10, _high_baseline_occupancy),
        MatchIQRule("positioning-high-kitchen-v2", 20, _high_kitchen_occupancy),
        MatchIQRule("positioning-high-transition-v2", 30, _high_transition_occupancy),
        MatchIQRule("positioning-low-transition-v2", 40, _low_transition_occupancy),
        MatchIQRule("positioning-zone-distribution-v2", 50, _zone_distribution),
        MatchIQRule("movement-short-total-distance-v2", 60, _short_total_distance),
        MatchIQRule("movement-measured-distance-v2", 70, _measured_distance),
    )


def _high_baseline_occupancy(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    return _high_zone_insight(
        analytics=analytics,
        confidence=confidence,
        gate=gate,
        percentage=analytics.zone_occupancy.baseline_area.percentage,
        zone="baseline area",
        metric="zone_occupancy.baseline_area.percentage",
        insight_id="baseline-occupancy",
        rule_id="positioning-high-baseline-v2",
        priority=10,
    )


def _high_kitchen_occupancy(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    return _high_zone_insight(
        analytics=analytics,
        confidence=confidence,
        gate=gate,
        percentage=analytics.zone_occupancy.kitchen.percentage,
        zone="kitchen",
        metric="zone_occupancy.kitchen.percentage",
        insight_id="kitchen-occupancy",
        rule_id="positioning-high-kitchen-v2",
        priority=20,
    )


def _high_transition_occupancy(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    return _high_zone_insight(
        analytics=analytics,
        confidence=confidence,
        gate=gate,
        percentage=analytics.zone_occupancy.transition_zone.percentage,
        zone="transition zone",
        metric="zone_occupancy.transition_zone.percentage",
        insight_id="transition-occupancy",
        rule_id="positioning-high-transition-v2",
        priority=30,
    )


def _high_zone_insight(
    *,
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
    percentage: float,
    zone: str,
    metric: str,
    insight_id: str,
    rule_id: str,
    priority: int,
) -> MatchIQInsight | None:
    if percentage < HIGH_ZONE_PERCENTAGE:
        return None
    observation = (
        f"In the observed sample, {percentage:.1f}% of continuity-safe tracked time "
        f"was assigned to the {zone}."
    )
    return _insight(
        insight_id=insight_id,
        rule_id=rule_id,
        priority=priority,
        title=f"Observed time in the {zone}",
        observation=observation,
        evidence=[
            _evidence(
                metric=metric,
                label=f"{zone.title()} occupancy",
                value=percentage,
                formatted_value=f"{percentage:.1f}%",
                threshold=f">= {HIGH_ZONE_PERCENTAGE:.1f}%",
            ),
            _tracked_time_evidence(analytics),
        ],
        confidence=confidence,
        gate=gate,
        interpretation=(
            f"The {zone} was the largest measured location category in this observed sample."
        ),
        action="Review the heatmap and trajectory around this measured zone.",
    )


def _low_transition_occupancy(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    percentage = analytics.zone_occupancy.transition_zone.percentage
    if percentage > LOW_TRANSITION_PERCENTAGE:
        return None
    observation = (
        f"In the observed sample, {percentage:.1f}% of continuity-safe tracked time "
        "was assigned to the transition zone."
    )
    return _insight(
        insight_id="low-transition-occupancy",
        rule_id="positioning-low-transition-v2",
        priority=40,
        title="Observed transition-zone time",
        observation=observation,
        evidence=[
            _evidence(
                metric="zone_occupancy.transition_zone.percentage",
                label="Transition-zone occupancy",
                value=percentage,
                formatted_value=f"{percentage:.1f}%",
                threshold=f"<= {LOW_TRANSITION_PERCENTAGE:.1f}%",
            ),
            _tracked_time_evidence(analytics),
        ],
        confidence=confidence,
        gate=gate,
        interpretation=(
            "The transition zone was a smaller measured location category in this sample."
        ),
        action="Review the heatmap to see where the observed sample was concentrated.",
    )


def _zone_distribution(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    zones = {
        "kitchen": analytics.zone_occupancy.kitchen.percentage,
        "transition zone": analytics.zone_occupancy.transition_zone.percentage,
        "baseline area": analytics.zone_occupancy.baseline_area.percentage,
    }
    if (
        max(zones.values()) >= HIGH_ZONE_PERCENTAGE
        or min(zones.values()) <= LOW_TRANSITION_PERCENTAGE
    ):
        return None
    formatted = ", ".join(f"{label} {value:.1f}%" for label, value in zones.items())
    observation = f"In the observed sample, tracked time was distributed as {formatted}."
    return _insight(
        insight_id="zone-distribution",
        rule_id="positioning-zone-distribution-v2",
        priority=50,
        title="Observed zone distribution",
        observation=observation,
        evidence=[
            _evidence(
                metric="zone_occupancy.zone_percentages",
                label="Zone occupancy",
                value=formatted,
                formatted_value=formatted,
                threshold=(
                    f"all zones between {BALANCED_ZONE_MIN_PERCENTAGE:.1f}% and "
                    f"{BALANCED_ZONE_MAX_PERCENTAGE:.1f}%"
                ),
            ),
            _tracked_time_evidence(analytics),
        ],
        confidence=confidence,
        gate=gate,
        interpretation="No single measured zone dominated this observed sample.",
        action="Compare the heatmap with the source video before drawing a broader conclusion.",
    )


def _short_total_distance(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight | None:
    distance = analytics.distance.total_distance_feet
    if distance > SHORT_TOTAL_DISTANCE_FEET:
        return None
    observation = (
        f"Court4 measured {distance:.1f} ft of continuity-safe movement in "
        f"{analytics.observed_duration_seconds:.1f} seconds of observed tracking."
    )
    return _insight(
        insight_id="short-total-distance",
        rule_id="movement-short-total-distance-v2",
        priority=60,
        title="Observed movement distance",
        observation=observation,
        evidence=[
            _evidence(
                metric="distance.total_distance_feet",
                label="Observed distance",
                value=distance,
                formatted_value=f"{distance:.1f} ft",
                threshold=f"<= {SHORT_TOTAL_DISTANCE_FEET:.1f} ft",
            ),
            _observed_duration_evidence(analytics),
        ],
        confidence=confidence,
        gate=gate,
        interpretation=(
            "The measured distance is small, but Court4 cannot tell whether that reflects "
            "play, camera coverage, or missed tracking."
        ),
        action="Review the trajectory and confirm the selected player stays visible.",
    )


def _measured_distance(
    analytics: AnalyticsReport,
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
) -> MatchIQInsight:
    distance = analytics.distance.total_distance_feet
    speed = analytics.distance.average_movement_feet_per_second
    observation = (
        f"Court4 measured {distance:.1f} ft across "
        f"{analytics.observed_duration_seconds:.1f} seconds of continuity-safe tracking, "
        f"averaging {speed:.2f} ft/s."
    )
    return _insight(
        insight_id="measured-movement",
        rule_id="movement-measured-distance-v2",
        priority=70,
        title="Continuity-safe movement measurement",
        observation=observation,
        evidence=[
            _evidence(
                metric="distance.total_distance_feet",
                label="Observed distance",
                value=distance,
                formatted_value=f"{distance:.1f} ft",
                threshold="reported from continuity-safe analytics",
            ),
            _evidence(
                metric="distance.average_movement_feet_per_second",
                label="Average observed movement",
                value=speed,
                formatted_value=f"{speed:.2f} ft/s",
                threshold="distance divided by observed duration",
            ),
            _observed_duration_evidence(analytics),
        ],
        confidence=confidence,
        gate=gate,
        interpretation="This describes the measured sample only; it is not a performance rating.",
        action="Review the trajectory beside the video to verify the measured path.",
    )


def _insight(
    *,
    insight_id: str,
    rule_id: str,
    priority: int,
    title: str,
    observation: str,
    evidence: list[MatchIQMetricEvidence],
    confidence: MatchIQConfidence,
    gate: InsightQualityGate,
    interpretation: str,
    action: str,
) -> MatchIQInsight:
    allow_interpretation = gate in {"NORMAL", "CAUTIOUS"}
    allow_action = allow_interpretation and confidence.recommendation.level in {
        "HIGH",
        "MODERATE",
    }
    limitations = [
        "This observation covers tracked time only and may not represent the full recording.",
        "Court4 does not know the rally, shot, outcome, opponent, or player intent.",
    ]
    if gate == "MEASUREMENT_ONLY":
        limitations.insert(
            0,
            "Recording or tracking limitations suppress interpretation and advice.",
        )
    return MatchIQInsight(
        id=insight_id,
        rule_id=rule_id,
        priority=priority,
        title=title,
        statement=observation,
        observation=observation,
        evidence=evidence,
        confidence=confidence,
        interpretation=interpretation if allow_interpretation else None,
        limitations=limitations,
        action=action if allow_action else None,
        quality_gate=gate,
    )


def _quality_gate(
    analytics: AnalyticsReport,
    recording_quality: RecordingQualityAssessment | None,
) -> InsightQualityGate:
    if (
        analytics.timeline_observation_count < MIN_OBSERVATIONS
        or analytics.zone_occupancy.tracked_time_seconds < MIN_TRACKED_SECONDS
        or (
            recording_quality is not None
            and recording_quality.status == RecordingQualityLevel.unsuitable
        )
    ):
        return "INSUFFICIENT_EVIDENCE"
    if recording_quality is not None and recording_quality.status == RecordingQualityLevel.limited:
        return "MEASUREMENT_ONLY"
    if (
        analytics.source_fragment_count > 1
        or analytics.unobserved_gap_seconds > 0
        or analytics.observed_duration_seconds < CAUTIOUS_TRACKED_SECONDS
    ):
        return "MEASUREMENT_ONLY"
    if recording_quality is None or recording_quality.status == RecordingQualityLevel.good:
        return "CAUTIOUS"
    return "NORMAL"


def _confidence_for(
    analytics: AnalyticsReport,
    recording_quality: RecordingQualityAssessment | None,
    gate: InsightQualityGate,
) -> MatchIQConfidence:
    if recording_quality is None:
        recording = MatchIQConfidenceRating(
            level="NOT_AVAILABLE",
            rationale="This legacy analysis has no persisted recording-quality assessment.",
        )
    elif recording_quality.status == RecordingQualityLevel.excellent:
        recording = MatchIQConfidenceRating(
            level="HIGH", rationale="Recording checks met the recommended engineering thresholds."
        )
    elif recording_quality.status == RecordingQualityLevel.good:
        recording = MatchIQConfidenceRating(
            level="MODERATE", rationale="Recording checks met the minimum engineering thresholds."
        )
    else:
        recording = MatchIQConfidenceRating(
            level="LOW",
            rationale="Recording or readiness checks contain warnings or blocking failures.",
        )

    if analytics.source_fragment_count == 1 and analytics.unobserved_gap_seconds == 0:
        tracking = MatchIQConfidenceRating(
            level="MODERATE", rationale="The selected movement sample is one continuous fragment."
        )
    else:
        tracking = MatchIQConfidenceRating(
            level="LOW",
            rationale=(
                f"The sample contains {analytics.source_fragment_count} fragment(s) and "
                f"{analytics.unobserved_gap_seconds:.1f} seconds of unobserved gaps."
            ),
        )

    enough_measurement = (
        analytics.timeline_observation_count >= MIN_OBSERVATIONS
        and analytics.zone_occupancy.tracked_time_seconds >= MIN_TRACKED_SECONDS
    )
    measurement = MatchIQConfidenceRating(
        level=("MODERATE" if enough_measurement else "LOW"),
        rationale=(
            f"{analytics.timeline_observation_count} court observations and "
            f"{analytics.observed_duration_seconds:.1f} observed seconds support the measurement."
        ),
    )
    interpretation = MatchIQConfidenceRating(
        level=("MODERATE" if gate in {"NORMAL", "CAUTIOUS"} else "NOT_AVAILABLE"),
        rationale=(
            "Only a sample-level location description is allowed."
            if gate in {"NORMAL", "CAUTIOUS"}
            else "Evidence quality suppresses interpretation."
        ),
    )
    recommendation = MatchIQConfidenceRating(
        level=("MODERATE" if gate in {"NORMAL", "CAUTIOUS"} else "NOT_AVAILABLE"),
        rationale=(
            "Court4 can suggest artifact review but not tactical coaching."
            if gate in {"NORMAL", "CAUTIOUS"}
            else "Evidence quality suppresses review advice."
        ),
    )
    return MatchIQConfidence(
        recording=recording,
        tracking=tracking,
        measurement=measurement,
        interpretation=interpretation,
        recommendation=recommendation,
    )


def _summary_for(
    *,
    analytics: AnalyticsReport,
    insights: Sequence[MatchIQInsight],
    gate: InsightQualityGate,
) -> str:
    if gate == "MEASUREMENT_ONLY":
        return (
            "Court4 measured movement, but recording or tracking limitations mean "
            "interpretation and advice are suppressed."
        )
    if insights:
        return (
            f"Court4 verified {len(insights)} movement observation"
            f"{'' if len(insights) == 1 else 's'} in the tracked sample."
        )
    return "Court4 measured movement, but no descriptive rule crossed its configured threshold."


def _focus_for(
    insights: Sequence[MatchIQInsight],
    gate: InsightQualityGate,
) -> MatchIQFocusRecommendation | None:
    if gate not in {"NORMAL", "CAUTIOUS"} or not insights:
        return None
    first = insights[0]
    if first.action is None:
        return None
    return MatchIQFocusRecommendation(
        title="What to review next",
        statement=first.action,
        supporting_insight_ids=[first.id],
    )


def _report_limitations(
    analytics: AnalyticsReport,
    recording_quality: RecordingQualityAssessment | None,
) -> list[str]:
    limitations = list(DEFAULT_LIMITATIONS)
    if recording_quality is None:
        limitations.insert(0, "Recording quality was not persisted for this legacy analysis.")
    if analytics.source_fragment_count > 1:
        limitations.insert(
            0,
            f"The selected sample combines {analytics.source_fragment_count} tracking fragments.",
        )
    if analytics.unobserved_gap_seconds > 0:
        limitations.insert(
            0,
            f"{analytics.unobserved_gap_seconds:.1f} seconds were unobserved and not interpolated.",
        )
    return limitations


def _insufficient_data_reason(
    analytics: AnalyticsReport,
    recording_quality: RecordingQualityAssessment | None,
) -> str | None:
    if (
        recording_quality is not None
        and recording_quality.status == RecordingQualityLevel.unsuitable
    ):
        return "Analysis readiness is unsuitable; normal Match IQ is suppressed."
    if analytics.timeline_observation_count < MIN_OBSERVATIONS:
        return (
            f"Insufficient evidence: fewer than {MIN_OBSERVATIONS} valid court observations "
            "were available."
        )
    if analytics.zone_occupancy.tracked_time_seconds < MIN_TRACKED_SECONDS:
        return (
            f"Insufficient evidence: less than {MIN_TRACKED_SECONDS:.1f} second of "
            "continuity-safe tracked time was available."
        )
    return None


def _tracked_time_evidence(analytics: AnalyticsReport) -> MatchIQMetricEvidence:
    seconds = analytics.zone_occupancy.tracked_time_seconds
    return _evidence(
        metric="zone_occupancy.tracked_time_seconds",
        label="Zone tracked time",
        value=seconds,
        formatted_value=f"{seconds:.1f} seconds",
        threshold="continuity-safe in-court intervals only",
    )


def _observed_duration_evidence(analytics: AnalyticsReport) -> MatchIQMetricEvidence:
    seconds = analytics.observed_duration_seconds
    return _evidence(
        metric="observed_duration_seconds",
        label="Observed duration",
        value=seconds,
        formatted_value=f"{seconds:.1f} seconds",
        threshold="same-fragment gaps of no more than 1 second",
    )


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
