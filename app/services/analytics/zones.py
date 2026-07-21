from collections.abc import Sequence

from app.schemas.analytics import ZoneOccupancyMetric, ZoneOccupancyReport
from app.schemas.player_tracking import PlayerObservation
from app.sports.pickleball.geometry import REGULATION_COURT, Point2D

ZoneName = str

KITCHEN = "kitchen"
TRANSITION_ZONE = "transition_zone"
BASELINE_AREA = "baseline_area"


def classify_court_zone(
    point: Point2D,
    *,
    transition_area_depth_feet: float,
) -> ZoneName | None:
    x, y = point
    court = REGULATION_COURT
    if x < 0.0 or x > court.width_feet or y < 0.0 or y > court.length_feet:
        return None

    if court.near_kitchen_y_feet <= y <= court.far_kitchen_y_feet:
        return KITCHEN

    near_transition_start_y = court.near_kitchen_y_feet - transition_area_depth_feet
    far_transition_end_y = court.far_kitchen_y_feet + transition_area_depth_feet
    if near_transition_start_y <= y < court.near_kitchen_y_feet:
        return TRANSITION_ZONE
    if court.far_kitchen_y_feet < y <= far_transition_end_y:
        return TRANSITION_ZONE

    return BASELINE_AREA


def calculate_zone_occupancy(
    observations: Sequence[PlayerObservation],
    *,
    transition_area_depth_feet: float,
) -> ZoneOccupancyReport:
    zone_seconds = {KITCHEN: 0.0, TRANSITION_ZONE: 0.0, BASELINE_AREA: 0.0}
    inside_observations = [
        observation
        for observation in observations
        if observation.inside_court
        and classify_court_zone(
            observation.court_position,
            transition_area_depth_feet=transition_area_depth_feet,
        )
        is not None
    ]
    inside_observations.sort(key=lambda item: (item.timestamp_seconds, item.frame_index))

    for current, next_observation in zip(
        inside_observations,
        inside_observations[1:],
        strict=False,
    ):
        duration = max(0.0, next_observation.timestamp_seconds - current.timestamp_seconds)
        zone = classify_court_zone(
            current.court_position,
            transition_area_depth_feet=transition_area_depth_feet,
        )
        if zone is not None:
            zone_seconds[zone] += duration

    tracked_time_seconds = sum(zone_seconds.values())
    return ZoneOccupancyReport(
        kitchen=_zone_metric(zone_seconds[KITCHEN], tracked_time_seconds),
        transition_zone=_zone_metric(zone_seconds[TRANSITION_ZONE], tracked_time_seconds),
        baseline_area=_zone_metric(zone_seconds[BASELINE_AREA], tracked_time_seconds),
        tracked_time_seconds=tracked_time_seconds,
    )


def _zone_metric(seconds: float, tracked_time_seconds: float) -> ZoneOccupancyMetric:
    percentage = (seconds / tracked_time_seconds * 100.0) if tracked_time_seconds > 0 else 0.0
    return ZoneOccupancyMetric(seconds=seconds, percentage=percentage)
