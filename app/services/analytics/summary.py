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
    selected_player_candidate_id: str | None = None,
    source_raw_track_ids: Sequence[int] | None = None,
    observed_duration_seconds: float | None = None,
    unobserved_gap_seconds: float = 0.0,
    continuity_warnings: Sequence[str] = (),
) -> MovementSummaryReport:
    valid_court_observation_count = sum(
        1 for observation in observations if observation.inside_court
    )
    span_duration_seconds = (
        observations[-1].timestamp_seconds - observations[0].timestamp_seconds
        if len(observations) >= 2
        else 0.0
    )
    tracked_duration_seconds = (
        max(0.0, observed_duration_seconds)
        if observed_duration_seconds is not None
        else max(0.0, span_duration_seconds)
    )
    raw_track_ids = list(source_raw_track_ids or [selected_player_track_id])
    return MovementSummaryReport(
        analysis_id=tracking_report.analysis_id,
        selected_player_track_id=selected_player_track_id,
        selected_player_candidate_id=selected_player_candidate_id,
        source_fragment_count=len(raw_track_ids),
        source_raw_track_ids=raw_track_ids,
        observed_duration_seconds=tracked_duration_seconds,
        unobserved_gap_seconds=max(0.0, unobserved_gap_seconds),
        continuity_warnings=list(continuity_warnings),
        match_duration_seconds=tracking_report.performance.source_duration_seconds,
        tracked_duration_seconds=tracked_duration_seconds,
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
