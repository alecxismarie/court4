from dataclasses import dataclass

from app.sports.pickleball.geometry import REGULATION_COURT, Point2D


@dataclass(frozen=True)
class CourtLine:
    name: str
    start: Point2D
    end: Point2D


@dataclass(frozen=True)
class CourtPolygon:
    name: str
    points: tuple[Point2D, Point2D, Point2D, Point2D]


@dataclass(frozen=True)
class PickleballCourtLandmarks:
    lines: tuple[CourtLine, ...]
    zones: tuple[CourtPolygon, ...]


def build_court_landmarks(transition_area_depth_feet: float) -> PickleballCourtLandmarks:
    if transition_area_depth_feet <= 0:
        raise ValueError("Transition area depth must be greater than zero feet.")

    court = REGULATION_COURT
    near_transition_start_y = court.near_kitchen_y_feet - transition_area_depth_feet
    far_transition_end_y = court.far_kitchen_y_feet + transition_area_depth_feet

    if near_transition_start_y <= 0 or far_transition_end_y >= court.length_feet:
        raise ValueError(
            "Transition area depth must fit between the baseline and non-volley zone line."
        )

    lines = (
        CourtLine("near_baseline", (0.0, 0.0), (court.width_feet, 0.0)),
        CourtLine(
            "far_baseline",
            (0.0, court.length_feet),
            (court.width_feet, court.length_feet),
        ),
        CourtLine("net_line", (0.0, court.net_y_feet), (court.width_feet, court.net_y_feet)),
        CourtLine(
            "near_kitchen_line",
            (0.0, court.near_kitchen_y_feet),
            (court.width_feet, court.near_kitchen_y_feet),
        ),
        CourtLine(
            "far_kitchen_line",
            (0.0, court.far_kitchen_y_feet),
            (court.width_feet, court.far_kitchen_y_feet),
        ),
        CourtLine(
            "near_center_service_line",
            (court.center_x_feet, 0.0),
            (court.center_x_feet, court.near_kitchen_y_feet),
        ),
        CourtLine(
            "far_center_service_line",
            (court.center_x_feet, court.far_kitchen_y_feet),
            (court.center_x_feet, court.length_feet),
        ),
    )

    zones = (
        _zone("near_non_volley_zone", court.near_kitchen_y_feet, court.net_y_feet),
        _zone("far_non_volley_zone", court.net_y_feet, court.far_kitchen_y_feet),
        _zone("near_transition_area", near_transition_start_y, court.near_kitchen_y_feet),
        _zone("far_transition_area", court.far_kitchen_y_feet, far_transition_end_y),
        _zone("near_baseline_area", 0.0, near_transition_start_y),
        _zone("far_baseline_area", far_transition_end_y, court.length_feet),
    )

    return PickleballCourtLandmarks(lines=lines, zones=zones)


def _zone(name: str, near_y: float, far_y: float) -> CourtPolygon:
    court = REGULATION_COURT
    return CourtPolygon(
        name=name,
        points=(
            (0.0, near_y),
            (court.width_feet, near_y),
            (court.width_feet, far_y),
            (0.0, far_y),
        ),
    )
