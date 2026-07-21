import pytest

from app.sports.pickleball.geometry import (
    COURT_CORNERS,
    REGULATION_COURT,
    ordered_court_corner_points,
)
from app.sports.pickleball.landmarks import build_court_landmarks


def test_regulation_court_dimensions() -> None:
    assert REGULATION_COURT.width_feet == 20.0
    assert REGULATION_COURT.length_feet == 44.0
    assert REGULATION_COURT.net_y_feet == 22.0
    assert REGULATION_COURT.non_volley_zone_depth_feet == 7.0
    assert REGULATION_COURT.near_kitchen_y_feet == 15.0
    assert REGULATION_COURT.far_kitchen_y_feet == 29.0


def test_standardized_corner_coordinates() -> None:
    assert COURT_CORNERS == {
        "near_left": (0.0, 0.0),
        "near_right": (20.0, 0.0),
        "far_right": (20.0, 44.0),
        "far_left": (0.0, 44.0),
    }
    assert ordered_court_corner_points() == (
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 44.0),
        (0.0, 44.0),
    )


def test_landmark_coordinates() -> None:
    landmarks = build_court_landmarks(transition_area_depth_feet=8.0)
    lines = {line.name: line for line in landmarks.lines}

    assert lines["near_baseline"].start == (0.0, 0.0)
    assert lines["near_baseline"].end == (20.0, 0.0)
    assert lines["far_baseline"].start == (0.0, 44.0)
    assert lines["far_baseline"].end == (20.0, 44.0)
    assert lines["net_line"].start == (0.0, 22.0)
    assert lines["net_line"].end == (20.0, 22.0)
    assert lines["near_kitchen_line"].start == (0.0, 15.0)
    assert lines["far_kitchen_line"].start == (0.0, 29.0)
    assert lines["near_center_service_line"].start == (10.0, 0.0)
    assert lines["near_center_service_line"].end == (10.0, 15.0)
    assert lines["far_center_service_line"].start == (10.0, 29.0)
    assert lines["far_center_service_line"].end == (10.0, 44.0)


def test_zone_coordinates_and_transition_definition() -> None:
    landmarks = build_court_landmarks(transition_area_depth_feet=8.0)
    zones = {zone.name: zone for zone in landmarks.zones}

    assert zones["near_non_volley_zone"].points == (
        (0.0, 15.0),
        (20.0, 15.0),
        (20.0, 22.0),
        (0.0, 22.0),
    )
    assert zones["far_non_volley_zone"].points == (
        (0.0, 22.0),
        (20.0, 22.0),
        (20.0, 29.0),
        (0.0, 29.0),
    )
    assert zones["near_transition_area"].points == (
        (0.0, 7.0),
        (20.0, 7.0),
        (20.0, 15.0),
        (0.0, 15.0),
    )
    assert zones["far_transition_area"].points == (
        (0.0, 29.0),
        (20.0, 29.0),
        (20.0, 37.0),
        (0.0, 37.0),
    )
    assert zones["near_baseline_area"].points[-1] == (0.0, 7.0)
    assert zones["far_baseline_area"].points[0] == (0.0, 37.0)


def test_transition_depth_must_fit_inside_service_area() -> None:
    with pytest.raises(ValueError, match="Transition area depth"):
        build_court_landmarks(transition_area_depth_feet=16.0)
