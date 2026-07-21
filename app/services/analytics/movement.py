import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.analytics import (
    AnalyticsArtifacts,
    AnalyticsReport,
    DistanceMetrics,
    MovementSummaryReport,
    TimelinePosition,
    TimelineReport,
)
from app.schemas.calibration import CourtCalibrationReport
from app.schemas.player_tracking import PlayerObservation, PlayerTrackingReport
from app.services.analytics.exceptions import (
    AnalyticsError,
    AnalyticsOutputExistsError,
    MissingCalibrationForAnalyticsError,
    MissingSelectedPlayerError,
    MissingTrackingForAnalyticsError,
    NoPlayerTrajectoryError,
)
from app.services.analytics.heatmap import write_heatmap_image
from app.services.analytics.summary import build_movement_summary
from app.services.analytics.trajectory import write_trajectory_image
from app.services.analytics.zones import calculate_zone_occupancy
from app.services.tracking.exceptions import TrackingError
from app.services.video.player_analysis import load_calibration_report
from app.services.video.player_selection import load_tracking_report

logger = logging.getLogger(__name__)

FEET_TO_METERS = 0.3048


@dataclass(frozen=True)
class AnalyticsResult:
    report: AnalyticsReport
    movement_summary: MovementSummaryReport
    timeline: TimelineReport
    analytics_dir: Path
    analytics_path: Path
    movement_summary_path: Path
    timeline_path: Path
    trajectory_path: Path
    heatmap_path: Path


def generate_match_analytics(
    *,
    analysis_id: str,
    output_dir: Path,
    transition_area_depth_feet: float,
    image_width_pixels: int,
) -> AnalyticsResult:
    if not analysis_id.strip():
        raise MissingTrackingForAnalyticsError("Analysis ID cannot be empty.")
    if transition_area_depth_feet <= 0:
        raise AnalyticsError("Transition area depth must be greater than zero feet.")
    if image_width_pixels <= 0:
        raise AnalyticsError("Analytics image width must be positive.")

    analysis_dir = output_dir.expanduser() / analysis_id
    tracking_path = analysis_dir / "tracking" / "tracking.json"
    tracking_report = _load_tracking_report_for_analytics(tracking_path)
    selected_track_id = tracking_report.selected_player_track_id
    if selected_track_id is None:
        raise MissingSelectedPlayerError(
            "Tracking report does not have a selected player track ID. "
            "Run scripts.select_player first."
        )

    calibration_path = (
        analysis_dir / "calibrations" / tracking_report.calibration_id / "calibration.json"
    )
    calibration = _load_calibration_report_for_analytics(calibration_path)
    if calibration.calibration_id != tracking_report.calibration_id:
        raise MissingCalibrationForAnalyticsError(
            "Calibration ID does not match tracking report "
            f"({calibration.calibration_id} != {tracking_report.calibration_id})."
        )

    observations_path = tracking_path.parent / tracking_report.artifacts.observations_jsonl
    selected_observations = _load_selected_observations(
        observations_path=observations_path,
        selected_track_id=selected_track_id,
    )
    timeline_positions = _timeline_positions(selected_observations)
    if not timeline_positions:
        raise NoPlayerTrajectoryError(
            f"Selected track ID {selected_track_id} has no valid in-court observations."
        )

    analytics_dir = analysis_dir / "analytics"
    if analytics_dir.exists():
        raise AnalyticsOutputExistsError(
            f"Analytics output directory already exists: {analytics_dir}"
        )
    analytics_dir.mkdir(parents=True, exist_ok=False)

    created_at = datetime.now(tz=UTC)
    distance = calculate_distance_metrics(timeline_positions)
    zone_occupancy = calculate_zone_occupancy(
        selected_observations,
        transition_area_depth_feet=transition_area_depth_feet,
    )
    average_court_position = _average_court_position(timeline_positions)

    timeline = TimelineReport(
        analysis_id=tracking_report.analysis_id,
        selected_player_track_id=selected_track_id,
        observation_count=len(timeline_positions),
        positions=list(timeline_positions),
        created_at=created_at,
    )
    movement_summary = build_movement_summary(
        tracking_report=tracking_report,
        selected_player_track_id=selected_track_id,
        observations=selected_observations,
        total_distance_feet=distance.total_distance_feet,
        total_distance_meters=distance.total_distance_meters,
        average_movement_feet_per_second=distance.average_movement_feet_per_second,
        average_movement_meters_per_second=distance.average_movement_meters_per_second,
        average_court_position=average_court_position,
        zone_occupancy=zone_occupancy,
        created_at=created_at,
    )

    analytics_path = analytics_dir / "analytics.json"
    movement_summary_path = analytics_dir / "movement_summary.json"
    timeline_path = analytics_dir / "timeline.json"
    trajectory_path = analytics_dir / "trajectory.png"
    heatmap_path = analytics_dir / "heatmap.png"

    write_trajectory_image(
        positions=timeline_positions,
        output_path=trajectory_path,
        image_width_pixels=image_width_pixels,
    )
    write_heatmap_image(
        positions=timeline_positions,
        output_path=heatmap_path,
        image_width_pixels=image_width_pixels,
    )

    report = AnalyticsReport(
        analysis_id=tracking_report.analysis_id,
        source_tracking_report=str(tracking_path.relative_to(analysis_dir)),
        source_observations=str(observations_path.relative_to(analysis_dir)),
        calibration_id=tracking_report.calibration_id,
        selected_player_track_id=selected_track_id,
        distance=distance,
        timeline_observation_count=len(timeline_positions),
        average_court_position=average_court_position,
        zone_occupancy=zone_occupancy,
        artifacts=AnalyticsArtifacts(
            analytics_json=analytics_path.name,
            movement_summary_json=movement_summary_path.name,
            timeline_json=timeline_path.name,
            trajectory_png=trajectory_path.name,
            heatmap_png=heatmap_path.name,
        ),
        created_at=created_at,
    )

    _write_json(report, analytics_path)
    _write_json(movement_summary, movement_summary_path)
    _write_json(timeline, timeline_path)

    logger.info(
        "movement_analytics_completed",
        extra={
            "analysis_id": tracking_report.analysis_id,
            "selected_player_track_id": selected_track_id,
            "analytics_path": str(analytics_path),
            "timeline_observation_count": len(timeline_positions),
            "total_distance_feet": distance.total_distance_feet,
        },
    )
    return AnalyticsResult(
        report=report,
        movement_summary=movement_summary,
        timeline=timeline,
        analytics_dir=analytics_dir,
        analytics_path=analytics_path,
        movement_summary_path=movement_summary_path,
        timeline_path=timeline_path,
        trajectory_path=trajectory_path,
        heatmap_path=heatmap_path,
    )


def calculate_distance_metrics(positions: Sequence[TimelinePosition]) -> DistanceMetrics:
    total_distance_feet = 0.0
    for current, next_position in zip(positions, positions[1:], strict=False):
        total_distance_feet += math.hypot(next_position.x - current.x, next_position.y - current.y)

    tracked_duration_seconds = (
        positions[-1].timestamp_seconds - positions[0].timestamp_seconds
        if len(positions) >= 2
        else 0.0
    )
    average_feet_per_second = (
        total_distance_feet / tracked_duration_seconds if tracked_duration_seconds > 0 else 0.0
    )
    return DistanceMetrics(
        total_distance_feet=total_distance_feet,
        total_distance_meters=total_distance_feet * FEET_TO_METERS,
        average_movement_feet_per_second=average_feet_per_second,
        average_movement_meters_per_second=average_feet_per_second * FEET_TO_METERS,
    )


def _load_tracking_report_for_analytics(tracking_path: Path) -> PlayerTrackingReport:
    try:
        return load_tracking_report(tracking_path)
    except TrackingError as exc:
        raise MissingTrackingForAnalyticsError(str(exc)) from exc


def _load_calibration_report_for_analytics(calibration_path: Path) -> CourtCalibrationReport:
    try:
        return load_calibration_report(calibration_path)
    except TrackingError as exc:
        raise MissingCalibrationForAnalyticsError(str(exc)) from exc


def _load_selected_observations(
    *,
    observations_path: Path,
    selected_track_id: int,
) -> list[PlayerObservation]:
    if not observations_path.exists():
        raise MissingTrackingForAnalyticsError(
            f"Observations JSONL does not exist: {observations_path}"
        )
    if not observations_path.is_file():
        raise MissingTrackingForAnalyticsError(
            f"Observations JSONL path is not a file: {observations_path}"
        )

    observations: list[PlayerObservation] = []
    for line_number, line in enumerate(
        observations_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            observation = PlayerObservation.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise MissingTrackingForAnalyticsError(
                f"Invalid observation JSONL line {line_number}: {observations_path}"
            ) from exc
        if observation.track_id == selected_track_id:
            _validate_court_position(observation)
            observations.append(observation)

    observations.sort(key=lambda item: (item.timestamp_seconds, item.frame_index))
    if not observations:
        raise NoPlayerTrajectoryError(
            f"Selected track ID {selected_track_id} has no observations in observations.jsonl."
        )
    return observations


def _timeline_positions(observations: Sequence[PlayerObservation]) -> tuple[TimelinePosition, ...]:
    return tuple(
        TimelinePosition(
            timestamp_seconds=observation.timestamp_seconds,
            x=observation.court_position[0],
            y=observation.court_position[1],
        )
        for observation in observations
        if observation.inside_court
    )


def _validate_court_position(observation: PlayerObservation) -> None:
    x, y = observation.court_position
    if not math.isfinite(x) or not math.isfinite(y):
        raise MissingTrackingForAnalyticsError(
            f"Observation has invalid court coordinates at frame {observation.frame_index}."
        )


def _average_court_position(
    positions: Sequence[TimelinePosition],
) -> tuple[float, float] | None:
    if not positions:
        return None
    x = sum(position.x for position in positions) / len(positions)
    y = sum(position.y for position in positions) / len(positions)
    return (x, y)


def _write_json(model: BaseModel, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
