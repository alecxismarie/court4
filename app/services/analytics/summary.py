from collections.abc import Sequence
from datetime import datetime

from app.schemas.analytics import MovementSummaryReport, ZoneOccupancyReport
from app.schemas.player_tracking import PlayerObservation, PlayerTrackingReport


def build_movement_summary(
    *,
    tracking_report: PlayerTrackingReport,
    selected_player_track_id: int,
    observations: Sequence[PlayerObservation],
    total_distance_feet: float,
    total_distance_meters: float,
    average_movement_feet_per_second: float,
    average_movement_meters_per_second: float,
    average_court_position: tuple[float, float] | None,
    zone_occupancy: ZoneOccupancyReport,
    created_at: datetime,
) -> MovementSummaryReport:
    valid_court_observation_count = sum(
        1 for observation in observations if observation.inside_court
    )
    tracked_duration_seconds = (
        observations[-1].timestamp_seconds - observations[0].timestamp_seconds
        if len(observations) >= 2
        else 0.0
    )
    return MovementSummaryReport(
        analysis_id=tracking_report.analysis_id,
        selected_player_track_id=selected_player_track_id,
        match_duration_seconds=tracking_report.performance.source_duration_seconds,
        tracked_duration_seconds=max(0.0, tracked_duration_seconds),
        total_processed_observations=len(observations),
        valid_court_observation_count=valid_court_observation_count,
        total_distance_feet=total_distance_feet,
        total_distance_meters=total_distance_meters,
        average_court_position=average_court_position,
        average_movement_feet_per_second=average_movement_feet_per_second,
        average_movement_meters_per_second=average_movement_meters_per_second,
        zone_occupancy=zone_occupancy,
        created_at=created_at,
    )
