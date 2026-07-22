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
    assert report.summary.startswith("Match IQ found")
    assert [insight.rule_id for insight in report.insights] == [
        "positioning-high-transition-v1",
        "movement-short-total-distance-v1",
        "movement-measured-distance-v1",
    ]
    assert report.insights[0].statement == (
        "Court4 measured 100.0% of tracked time in the transition zone."
    )
    assert report.insights[0].evidence[0].metric == "zone_occupancy.transition_zone.percentage"
    assert report.insights[0].evidence[0].formatted_value == "100.0%"
    assert report.insights[0].evidence[0].threshold == ">= 55.0%"
    assert report.focus is not None
    assert report.focus.supporting_insight_ids == ["transition-occupancy"]
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
    assert report.summary == (
        "Court4 does not have enough movement data to generate a reliable Match IQ."
    )
    assert report.insights == []
    assert report.focus is None
    assert (
        report.limitations[0]
        == "Insufficient data: fewer than 3 timeline observations were available."
    )


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
