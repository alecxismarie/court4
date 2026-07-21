import json
from collections.abc import Callable
from pathlib import Path

import cv2
import pytest

from app.sports.pickleball import (
    CalibrationGeometryError,
    CalibrationImageNotFoundError,
    CalibrationImageReadError,
    CalibrationOutputExistsError,
    CalibrationPointValidationError,
    CourtCalibrationResult,
    calibrate_court,
    court_point_to_image,
    court_points_to_image,
    image_point_to_court,
    image_points_to_court,
)
from app.sports.pickleball.geometry import Point2D, ordered_court_corner_points
from scripts.calibrate_court import main as calibration_cli_main

VALID_IMAGE_POINTS: tuple[Point2D, Point2D, Point2D, Point2D] = (
    (80.0, 760.0),
    (720.0, 760.0),
    (600.0, 120.0),
    (200.0, 120.0),
)


def test_valid_calibration_matrix_generation(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    result = _calibrate(tmp_path, image_path)

    assert result.report.calibration_id == "calibration-test"
    assert len(result.report.image_to_court_matrix) == 3
    assert len(result.report.image_to_court_matrix[0]) == 3
    assert result.report.reprojection_error == pytest.approx(0.0, abs=1e-5)
    assert result.report.round_trip_error < 1e-8


def test_inverse_matrix_generation(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)

    projected = court_points_to_image(ordered_court_corner_points(), result.report)

    _assert_points_close(projected, VALID_IMAGE_POINTS, tolerance=1e-4)


def test_image_point_to_court_transformation(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)

    assert image_point_to_court(VALID_IMAGE_POINTS[0], result.report) == pytest.approx(
        (0.0, 0.0),
        abs=1e-5,
    )


def test_image_points_to_court_transformation(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)

    mapped = image_points_to_court(VALID_IMAGE_POINTS, result.report)

    _assert_points_close(mapped, ordered_court_corner_points(), tolerance=1e-5)


def test_court_point_to_image_transformation(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)

    assert court_point_to_image((0.0, 0.0), result.report) == pytest.approx(
        VALID_IMAGE_POINTS[0],
        abs=1e-4,
    )


def test_round_trip_transformation_accuracy(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)
    court_point = (10.0, 22.0)

    image_point = court_point_to_image(court_point, result.report)
    round_tripped = image_point_to_court(image_point, result.report)

    assert round_tripped == pytest.approx(court_point, abs=1e-8)


def test_out_of_bounds_input_points(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    with pytest.raises(CalibrationPointValidationError, match="outside image bounds"):
        _calibrate(
            tmp_path,
            image_path,
            image_points=((80.0, 760.0), (900.0, 760.0), (600.0, 120.0), (200.0, 120.0)),
        )


def test_duplicate_points_are_rejected(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    with pytest.raises(CalibrationPointValidationError, match="unique"):
        _calibrate(
            tmp_path,
            image_path,
            image_points=((80.0, 760.0), (80.0, 760.0), (600.0, 120.0), (200.0, 120.0)),
        )


def test_collinear_points_are_rejected(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    with pytest.raises(CalibrationGeometryError, match="area|collinear"):
        _calibrate(
            tmp_path,
            image_path,
            image_points=((100.0, 100.0), (200.0, 100.0), (300.0, 100.0), (400.0, 100.0)),
        )


def test_self_intersecting_or_incorrectly_ordered_points_are_rejected(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    with pytest.raises(CalibrationGeometryError, match="convex|self-intersecting"):
        _calibrate(
            tmp_path,
            image_path,
            image_points=((80.0, 760.0), (720.0, 760.0), (200.0, 120.0), (600.0, 120.0)),
        )


def test_missing_image_handling(tmp_path: Path) -> None:
    with pytest.raises(CalibrationImageNotFoundError, match="does not exist"):
        _calibrate(tmp_path, tmp_path / "missing.jpg")


def test_unreadable_image_handling(tmp_path: Path) -> None:
    image_path = tmp_path / "broken.jpg"
    image_path.write_text("not an image", encoding="utf-8")

    with pytest.raises(CalibrationImageReadError, match="OpenCV could not read"):
        _calibrate(tmp_path, image_path)


def test_json_report_and_images_are_created(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    result = _calibrate(tmp_path, image_path)

    assert result.calibration_path.exists()
    assert result.verification_image_path.exists()
    assert result.top_down_image_path is not None
    assert result.top_down_image_path.exists()

    metadata = json.loads(result.calibration_path.read_text(encoding="utf-8"))
    assert metadata["calibration_id"] == "calibration-test"
    assert metadata["source_image"] == "frame.jpg"
    assert metadata["coordinate_system"]["origin"] == "near-left"
    assert metadata["court_dimensions"] == {
        "width": 20.0,
        "length": 44.0,
        "non_volley_zone_depth": 7.0,
    }
    assert metadata["top_down_image"] == "top_down.jpg"


def test_deterministic_output_naming(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    result = _calibrate(tmp_path, image_path, analysis_id="analysis-123")

    assert result.calibration_dir == (
        tmp_path / "output" / "analysis-123" / "calibrations" / "calibration-test"
    )
    assert result.calibration_path == result.calibration_dir / "calibration.json"
    assert result.verification_image_path == result.calibration_dir / "verification.jpg"


def test_existing_output_directory_is_rejected(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    _calibrate(tmp_path, image_path)

    with pytest.raises(CalibrationOutputExistsError, match="already exists"):
        _calibrate(tmp_path, image_path)


def test_cli_success_behavior(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")

    exit_code = calibration_cli_main(
        [
            "--input",
            str(image_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--analysis-id",
            "cli-analysis",
            "--calibration-id",
            "cli-calibration",
            "--near-left",
            "80,760",
            "--near-right",
            "720,760",
            "--far-right",
            "600,120",
            "--far-left",
            "200,120",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"calibration_id": "cli-calibration"' in captured.out
    assert (tmp_path / "output" / "cli-analysis" / "calibrations" / "cli-calibration").exists()


def test_cli_failure_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = calibration_cli_main(
        [
            "--input",
            str(tmp_path / "missing.jpg"),
            "--output-dir",
            str(tmp_path / "output"),
            "--calibration-id",
            "missing-image",
            "--near-left",
            "80,760",
            "--near-right",
            "720,760",
            "--far-right",
            "600,120",
            "--far-left",
            "200,120",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error:" in captured.err


def test_verification_image_is_readable(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "frame.jpg")
    result = _calibrate(tmp_path, image_path)

    verification = cv2.imread(str(result.verification_image_path), cv2.IMREAD_COLOR)

    assert verification is not None
    assert verification.shape[:2] == (900, 800)


def _calibrate(
    tmp_path: Path,
    image_path: Path,
    *,
    image_points: tuple[Point2D, Point2D, Point2D, Point2D] = VALID_IMAGE_POINTS,
    analysis_id: str | None = None,
) -> CourtCalibrationResult:
    return calibrate_court(
        image_path=image_path,
        output_dir=tmp_path / "output",
        image_points=image_points,
        calibration_id="calibration-test",
        analysis_id=analysis_id,
        numeric_tolerance=0.000001,
        min_polygon_area_pixels=1000.0,
        transition_area_depth_feet=8.0,
        top_down_width_pixels=500,
    )


def _assert_points_close(
    actual: tuple[Point2D, ...],
    expected: tuple[Point2D, ...],
    *,
    tolerance: float,
) -> None:
    assert len(actual) == len(expected)
    for actual_point, expected_point in zip(actual, expected, strict=True):
        assert actual_point == pytest.approx(expected_point, abs=tolerance)
