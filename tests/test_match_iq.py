from datetime import UTC, datetime

from app.schemas.analytics import (
    AnalyticsArtifacts,
    AnalyticsReport,
    DistanceMetrics,
    TimelinePosition,
    TimelineReport,
    ZoneOccupancyMetric,
    ZoneOccupancyReport,
)
from app.schemas.recording_quality import (
    PreflightStage,
    RecordingQualityAssessment,
    RecordingQualityLevel,
)
from app.services.match_iq import MATCH_IQ_ENGINE_VERSION, generate_match_iq

CREATED_AT = datetime(2026, 7, 22, tzinfo=UTC)


def test_match_iq_generates_factual_evidence_backed_insights() -> None:
    analytics = _analytics_report(
        total_distance_feet=1.25,
        average_movement_feet_per_second=0.89,
        observation_count=15,
        tracked_time_seconds=1.4,
        kitchen_percentage=0.0,
        transition_percentage=100.0,
        baseline_percentage=0.0,
    )
    timeline = _timeline_report(
        [
            (0.0, 13.0, 31.0),
            (0.5, 12.5, 30.8),
            (1.0, 12.2, 30.6),
            (1.4, 11.9, 30.4),
        ]
    )

    report = generate_match_iq(
        analytics=analytics,
        timeline=timeline,
        created_at=CREATED_AT,
    )

    assert report.status == "generated"
    assert report.engine_version == MATCH_IQ_ENGINE_VERSION
    assert report.quality_gate == "MEASUREMENT_ONLY"
    assert report.summary.startswith("Court4 measured movement")
    assert [insight.rule_id for insight in report.insights] == [
        "positioning-high-transition-v2",
        "movement-short-total-distance-v2",
        "movement-measured-distance-v2",
    ]
    assert report.insights[0].statement == (
        "In the observed sample, 100.0% of continuity-safe tracked time "
        "was assigned to the transition zone."
    )
    assert report.insights[0].evidence[0].metric == "zone_occupancy.transition_zone.percentage"
    assert report.insights[0].evidence[0].formatted_value == "100.0%"
    assert report.insights[0].evidence[0].threshold == ">= 55.0%"
    assert report.insights[0].interpretation is None
    assert report.insights[0].action is None
    assert report.focus is None
    assert report.confidence is not None
    assert report.confidence.recording.level == "NOT_AVAILABLE"
    assert report.confidence.measurement.level == "MODERATE"
    assert "distance.total_distance_feet" in report.metrics_used


def test_match_iq_returns_insufficient_data_without_insights() -> None:
    analytics = _analytics_report(
        total_distance_feet=0.0,
        average_movement_feet_per_second=0.0,
        observation_count=2,
        tracked_time_seconds=0.5,
        kitchen_percentage=0.0,
        transition_percentage=100.0,
        baseline_percentage=0.0,
    )

    report = generate_match_iq(analytics=analytics, timeline=None, created_at=CREATED_AT)

    assert report.status == "insufficient_data"
    assert report.summary == "Insufficient evidence for a verified movement insight."
    assert report.quality_gate == "INSUFFICIENT_EVIDENCE"
    assert report.insights == []
    assert report.focus is None
    assert (
        report.limitations[0]
        == "Insufficient evidence: fewer than 3 valid court observations were available."
    )


def test_unsuitable_recording_suppresses_insights_and_separates_confidence() -> None:
    analytics = _analytics_report(
        total_distance_feet=45.0,
        average_movement_feet_per_second=1.5,
        observation_count=120,
        tracked_time_seconds=30,
        kitchen_percentage=60,
        transition_percentage=20,
        baseline_percentage=20,
    )
    quality = RecordingQualityAssessment(
        stage=PreflightStage.analysis,
        status=RecordingQualityLevel.unsuitable,
        reason_codes=["tracking_gaps_excessive"],
        assessed_at=CREATED_AT,
    )

    report = generate_match_iq(
        analytics=analytics,
        timeline=None,
        recording_quality=quality,
        created_at=CREATED_AT,
    )

    assert report.status == "insufficient_data"
    assert report.quality_gate == "INSUFFICIENT_EVIDENCE"
    assert report.insights == []
    assert report.confidence is not None
    assert report.confidence.recording.level == "LOW"
    assert report.confidence.interpretation.level == "NOT_AVAILABLE"
    assert report.confidence.recommendation.level == "NOT_AVAILABLE"


def test_fragmented_track_is_measurement_only_and_half_rules_are_disabled() -> None:
    analytics = _analytics_report(
        total_distance_feet=45.0,
        average_movement_feet_per_second=1.5,
        observation_count=120,
        tracked_time_seconds=30,
        kitchen_percentage=60,
        transition_percentage=20,
        baseline_percentage=20,
    ).model_copy(
        update={
            "source_fragment_count": 2,
            "unobserved_gap_seconds": 12.0,
            "observed_duration_seconds": 30.0,
        }
    )

    report = generate_match_iq(analytics=analytics, timeline=None, created_at=CREATED_AT)

    assert report.quality_gate == "MEASUREMENT_ONLY"
    assert all(insight.interpretation is None for insight in report.insights)
    assert all(insight.action is None for insight in report.insights)
    assert not any("timeline-" in insight.rule_id for insight in report.insights)


def _analytics_report(
    *,
    total_distance_feet: float,
    average_movement_feet_per_second: float,
    observation_count: int,
    tracked_time_seconds: float,
    kitchen_percentage: float,
    transition_percentage: float,
    baseline_percentage: float,
) -> AnalyticsReport:
    return AnalyticsReport(
        analysis_id="analysis-123",
        source_tracking_report="tracking/tracking.json",
        source_observations="tracking/observations.jsonl",
        calibration_id="auto-court-detection",
        selected_player_track_id=2,
        observed_duration_seconds=tracked_time_seconds,
        distance=DistanceMetrics(
            total_distance_feet=total_distance_feet,
            total_distance_meters=total_distance_feet * 0.3048,
            average_movement_feet_per_second=average_movement_feet_per_second,
            average_movement_meters_per_second=average_movement_feet_per_second * 0.3048,
        ),
        timeline_observation_count=observation_count,
        average_court_position=(12.4, 30.7),
        zone_occupancy=ZoneOccupancyReport(
            kitchen=ZoneOccupancyMetric(seconds=0.0, percentage=kitchen_percentage),
            transition_zone=ZoneOccupancyMetric(
                seconds=tracked_time_seconds * (transition_percentage / 100),
                percentage=transition_percentage,
            ),
            baseline_area=ZoneOccupancyMetric(seconds=0.0, percentage=baseline_percentage),
            tracked_time_seconds=tracked_time_seconds,
        ),
        artifacts=AnalyticsArtifacts(
            analytics_json="analytics.json",
            movement_summary_json="movement_summary.json",
            timeline_json="timeline.json",
            trajectory_png="trajectory.png",
            heatmap_png="heatmap.png",
        ),
        created_at=CREATED_AT,
    )


def _timeline_report(points: list[tuple[float, float, float]]) -> TimelineReport:
    return TimelineReport(
        analysis_id="analysis-123",
        selected_player_track_id=2,
        observation_count=len(points),
        positions=[
            TimelinePosition(timestamp_seconds=timestamp, x=x, y=y) for timestamp, x, y in points
        ],
        created_at=CREATED_AT,
    )
