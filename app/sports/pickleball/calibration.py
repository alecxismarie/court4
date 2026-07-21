import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.calibration import (
    CalibrationCoordinateSystem,
    CalibrationCourtDimensions,
    CourtCalibrationReport,
    OrderedCalibrationPoints,
)
from app.sports.pickleball.exceptions import (
    CalibrationGeometryError,
    CalibrationImageNotFoundError,
    CalibrationImageReadError,
    CalibrationOutputExistsError,
    CalibrationPointValidationError,
)
from app.sports.pickleball.geometry import (
    COORDINATE_SYSTEM,
    ORDERED_CORNER_NAMES,
    REGULATION_COURT,
    Point2D,
    ordered_court_corner_points,
)
from app.sports.pickleball.landmarks import CourtLine, build_court_landmarks

logger = logging.getLogger(__name__)

Matrix3x3 = NDArray[np.float64]
ImageArray = NDArray[np.uint8]


@dataclass(frozen=True)
class CourtCalibrationResult:
    report: CourtCalibrationReport
    calibration_dir: Path
    calibration_path: Path
    verification_image_path: Path
    top_down_image_path: Path | None


def calibrate_court(
    *,
    image_path: Path,
    output_dir: Path,
    image_points: Sequence[Point2D],
    calibration_id: str | None = None,
    analysis_id: str | None = None,
    numeric_tolerance: float,
    min_polygon_area_pixels: float,
    transition_area_depth_feet: float,
    top_down_width_pixels: int,
) -> CourtCalibrationResult:
    """Create a manual pickleball court calibration from four ordered image points.

    The required point order is near-left, near-right, far-right, far-left. The returned
    homography maps image pixel coordinates into court feet using the Court4 coordinate
    convention: origin at near-left, x across court width, y along court length.
    """
    _validate_positive_options(
        numeric_tolerance=numeric_tolerance,
        min_polygon_area_pixels=min_polygon_area_pixels,
        top_down_width_pixels=top_down_width_pixels,
    )
    resolved_image_path = image_path.expanduser()
    image = _read_image(resolved_image_path)
    image_height, image_width = image.shape[:2]

    validated_image_points = _validate_image_points(
        image_points=image_points,
        image_width=image_width,
        image_height=image_height,
        numeric_tolerance=numeric_tolerance,
        min_polygon_area_pixels=min_polygon_area_pixels,
    )
    resolved_calibration_id = _validate_output_id(calibration_id or uuid4().hex, "calibration ID")
    resolved_analysis_id = (
        _validate_output_id(analysis_id, "analysis ID") if analysis_id is not None else None
    )
    calibration_dir = _calibration_output_dir(
        output_dir=output_dir,
        calibration_id=resolved_calibration_id,
        analysis_id=resolved_analysis_id,
    )

    image_to_court_matrix = _compute_perspective_transform(
        source_points=validated_image_points,
        destination_points=ordered_court_corner_points(),
    )
    court_to_image_matrix = _compute_perspective_transform(
        source_points=ordered_court_corner_points(),
        destination_points=validated_image_points,
    )

    reprojection_error = _mean_point_error(
        actual=image_points_to_court(validated_image_points, image_to_court_matrix),
        expected=ordered_court_corner_points(),
    )
    round_trip_error = _round_trip_error(
        image_to_court_matrix=image_to_court_matrix,
        court_to_image_matrix=court_to_image_matrix,
    )
    _validate_calibration_quality(
        reprojection_error=reprojection_error,
        round_trip_error=round_trip_error,
        numeric_tolerance=numeric_tolerance,
    )

    calibration_dir.mkdir(parents=True, exist_ok=False)
    verification_image_path = calibration_dir / "verification.jpg"
    top_down_image_path = calibration_dir / "top_down.jpg"
    calibration_path = calibration_dir / "calibration.json"

    _write_verification_image(
        image=image,
        image_points=validated_image_points,
        court_to_image_matrix=court_to_image_matrix,
        output_path=verification_image_path,
        transition_area_depth_feet=transition_area_depth_feet,
    )
    _write_top_down_image(
        image=image,
        image_points=validated_image_points,
        output_path=top_down_image_path,
        width_pixels=top_down_width_pixels,
    )

    report = _build_report(
        calibration_id=resolved_calibration_id,
        source_image=resolved_image_path.name,
        image_width=image_width,
        image_height=image_height,
        image_points=validated_image_points,
        image_to_court_matrix=image_to_court_matrix,
        court_to_image_matrix=court_to_image_matrix,
        reprojection_error=reprojection_error,
        round_trip_error=round_trip_error,
        top_down_image=top_down_image_path.name,
    )
    _write_calibration_report(report, calibration_path)

    logger.info(
        "court_calibration_completed",
        extra={
            "calibration_id": resolved_calibration_id,
            "analysis_id": resolved_analysis_id,
            "source_image": str(resolved_image_path),
            "calibration_path": str(calibration_path),
            "reprojection_error": reprojection_error,
            "round_trip_error": round_trip_error,
        },
    )
    return CourtCalibrationResult(
        report=report,
        calibration_dir=calibration_dir,
        calibration_path=calibration_path,
        verification_image_path=verification_image_path,
        top_down_image_path=top_down_image_path,
    )


def image_point_to_court(
    point: Point2D,
    calibration: CourtCalibrationReport | Matrix3x3,
) -> Point2D:
    return _transform_point(point, _matrix_from_calibration(calibration, "image_to_court_matrix"))


def image_points_to_court(
    points: Sequence[Point2D],
    calibration: CourtCalibrationReport | Matrix3x3,
) -> tuple[Point2D, ...]:
    matrix = _matrix_from_calibration(calibration, "image_to_court_matrix")
    return tuple(_transform_point(point, matrix) for point in points)


def court_point_to_image(
    point: Point2D,
    calibration: CourtCalibrationReport | Matrix3x3,
) -> Point2D:
    return _transform_point(point, _matrix_from_calibration(calibration, "court_to_image_matrix"))


def court_points_to_image(
    points: Sequence[Point2D],
    calibration: CourtCalibrationReport | Matrix3x3,
) -> tuple[Point2D, ...]:
    matrix = _matrix_from_calibration(calibration, "court_to_image_matrix")
    return tuple(_transform_point(point, matrix) for point in points)


def _read_image(image_path: Path) -> ImageArray:
    if not image_path.exists():
        raise CalibrationImageNotFoundError(f"Calibration image does not exist: {image_path}")
    if not image_path.is_file():
        raise CalibrationImageReadError(f"Calibration image input is not a file: {image_path}")

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise CalibrationImageReadError(f"OpenCV could not read calibration image: {image_path}")
    return cast(ImageArray, image)


def _validate_positive_options(
    *,
    numeric_tolerance: float,
    min_polygon_area_pixels: float,
    top_down_width_pixels: int,
) -> None:
    if numeric_tolerance <= 0:
        raise CalibrationPointValidationError("Numeric validation tolerance must be positive.")
    if min_polygon_area_pixels <= 0:
        raise CalibrationGeometryError("Minimum polygon area must be positive.")
    if top_down_width_pixels <= 0:
        raise CalibrationPointValidationError("Top-down output width must be positive.")


def _validate_image_points(
    *,
    image_points: Sequence[Point2D],
    image_width: int,
    image_height: int,
    numeric_tolerance: float,
    min_polygon_area_pixels: float,
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    if len(image_points) != 4:
        raise CalibrationPointValidationError(
            "Exactly four image points are required in near-left, near-right, "
            "far-right, far-left order."
        )

    points = tuple(
        _validate_point(
            point=point,
            point_name=ORDERED_CORNER_NAMES[index],
            image_width=image_width,
            image_height=image_height,
        )
        for index, point in enumerate(image_points)
    )

    _validate_no_duplicates(points, numeric_tolerance)
    _validate_polygon_geometry(points, numeric_tolerance, min_polygon_area_pixels)
    return cast(tuple[Point2D, Point2D, Point2D, Point2D], points)


def _validate_point(
    *,
    point: Point2D,
    point_name: str,
    image_width: int,
    image_height: int,
) -> Point2D:
    if len(point) != 2:
        raise CalibrationPointValidationError(f"{point_name} must contain exactly two values.")

    x = float(point[0])
    y = float(point[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise CalibrationPointValidationError(f"{point_name} must contain finite numeric values.")
    if x < 0 or x >= image_width or y < 0 or y >= image_height:
        raise CalibrationPointValidationError(
            f"{point_name} coordinate ({x}, {y}) is outside image bounds "
            f"0 <= x < {image_width}, 0 <= y < {image_height}."
        )
    return (x, y)


def _validate_no_duplicates(points: Sequence[Point2D], numeric_tolerance: float) -> None:
    for first_index, first_point in enumerate(points):
        for second_index in range(first_index + 1, len(points)):
            if _distance(first_point, points[second_index]) <= numeric_tolerance:
                raise CalibrationPointValidationError("Calibration points must be unique.")


def _validate_polygon_geometry(
    points: Sequence[Point2D],
    numeric_tolerance: float,
    min_polygon_area_pixels: float,
) -> None:
    area = _polygon_area(points)
    if area < min_polygon_area_pixels:
        raise CalibrationGeometryError(
            f"Calibration polygon area is too small ({area:.3f} pixels)."
        )

    cross_products = []
    for index in range(4):
        previous_point = points[index]
        current_point = points[(index + 1) % 4]
        next_point = points[(index + 2) % 4]
        cross_products.append(_cross(previous_point, current_point, next_point))

    if any(abs(value) <= numeric_tolerance for value in cross_products):
        raise CalibrationGeometryError("Calibration polygon contains collinear points.")

    positive = [value > 0 for value in cross_products]
    if not all(value == positive[0] for value in positive):
        raise CalibrationGeometryError(
            "Calibration points must form a convex polygon in near-left, near-right, "
            "far-right, far-left order."
        )

    if _segments_intersect(points[0], points[1], points[2], points[3]) or _segments_intersect(
        points[1],
        points[2],
        points[3],
        points[0],
    ):
        raise CalibrationGeometryError("Calibration points form a self-intersecting court polygon.")


def _polygon_area(points: Sequence[Point2D]) -> float:
    total = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total += point[0] * next_point[1] - next_point[0] * point[1]
    return abs(total) / 2.0


def _cross(first: Point2D, second: Point2D, third: Point2D) -> float:
    return (second[0] - first[0]) * (third[1] - second[1]) - (second[1] - first[1]) * (
        third[0] - second[0]
    )


def _segments_intersect(a: Point2D, b: Point2D, c: Point2D, d: Point2D) -> bool:
    def orientation(first: Point2D, second: Point2D, third: Point2D) -> float:
        return (second[1] - first[1]) * (third[0] - second[0]) - (second[0] - first[0]) * (
            third[1] - second[1]
        )

    first = orientation(a, b, c)
    second = orientation(a, b, d)
    third = orientation(c, d, a)
    fourth = orientation(c, d, b)
    return first * second < 0 and third * fourth < 0


def _distance(first: Point2D, second: Point2D) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _compute_perspective_transform(
    *,
    source_points: Sequence[Point2D],
    destination_points: Sequence[Point2D],
) -> Matrix3x3:
    source = np.array(source_points, dtype=np.float32)
    destination = np.array(destination_points, dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(source, destination)
    return _validate_matrix(np.asarray(matrix, dtype=np.float64))


def _validate_matrix(matrix: NDArray[Any]) -> Matrix3x3:
    normalized = np.asarray(matrix, dtype=np.float64)
    if normalized.shape != (3, 3):
        raise CalibrationGeometryError("Perspective transform matrix must be 3x3.")
    if not np.all(np.isfinite(normalized)):
        raise CalibrationGeometryError("Perspective transform matrix contains invalid values.")
    determinant = float(np.linalg.det(normalized))
    if abs(determinant) <= 1e-12:
        raise CalibrationGeometryError("Perspective transform matrix is singular.")
    return cast(Matrix3x3, normalized)


def _matrix_from_calibration(
    calibration: CourtCalibrationReport | Matrix3x3,
    matrix_attr: str,
) -> Matrix3x3:
    if isinstance(calibration, CourtCalibrationReport):
        matrix = getattr(calibration, matrix_attr)
    else:
        matrix = calibration
    return _validate_matrix(np.asarray(matrix, dtype=np.float64))


def _transform_point(point: Point2D, matrix: Matrix3x3) -> Point2D:
    x = float(point[0])
    y = float(point[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise CalibrationPointValidationError("Transform point must contain finite values.")

    transformed = matrix @ np.array([x, y, 1.0], dtype=np.float64)
    denominator = float(transformed[2])
    if abs(denominator) <= 1e-12:
        raise CalibrationGeometryError("Perspective transform denominator is too close to zero.")

    transformed_x = float(transformed[0] / denominator)
    transformed_y = float(transformed[1] / denominator)
    if not math.isfinite(transformed_x) or not math.isfinite(transformed_y):
        raise CalibrationGeometryError("Perspective transform produced invalid coordinates.")
    return (transformed_x, transformed_y)


def _mean_point_error(actual: Sequence[Point2D], expected: Sequence[Point2D]) -> float:
    errors = [
        _distance(actual_point, expected_point)
        for actual_point, expected_point in zip(actual, expected, strict=True)
    ]
    return sum(errors) / len(errors)


def _round_trip_error(
    *,
    image_to_court_matrix: Matrix3x3,
    court_to_image_matrix: Matrix3x3,
) -> float:
    representative_points = (
        (0.0, 0.0),
        (REGULATION_COURT.width_feet, 0.0),
        (REGULATION_COURT.width_feet, REGULATION_COURT.length_feet),
        (0.0, REGULATION_COURT.length_feet),
        (REGULATION_COURT.center_x_feet, REGULATION_COURT.net_y_feet),
        (REGULATION_COURT.center_x_feet, REGULATION_COURT.near_kitchen_y_feet),
        (REGULATION_COURT.center_x_feet, REGULATION_COURT.far_kitchen_y_feet),
    )

    errors = []
    for court_point in representative_points:
        image_point = _transform_point(court_point, court_to_image_matrix)
        round_tripped = _transform_point(image_point, image_to_court_matrix)
        errors.append(_distance(court_point, round_tripped))
    return max(errors)


def _validate_calibration_quality(
    *,
    reprojection_error: float,
    round_trip_error: float,
    numeric_tolerance: float,
) -> None:
    if reprojection_error > numeric_tolerance:
        raise CalibrationGeometryError(
            "Calibration corner reprojection error exceeds numeric tolerance "
            f"({reprojection_error:.12f} > {numeric_tolerance:.12f})."
        )
    if round_trip_error > numeric_tolerance:
        raise CalibrationGeometryError(
            "Calibration round-trip error exceeds numeric tolerance "
            f"({round_trip_error:.12f} > {numeric_tolerance:.12f})."
        )


def _calibration_output_dir(
    *,
    output_dir: Path,
    calibration_id: str,
    analysis_id: str | None,
) -> Path:
    base_dir = output_dir.expanduser()
    if analysis_id is None:
        calibration_dir = base_dir / "calibrations" / calibration_id
    else:
        calibration_dir = base_dir / analysis_id / "calibrations" / calibration_id

    if calibration_dir.exists():
        raise CalibrationOutputExistsError(
            f"Calibration output directory already exists: {calibration_dir}"
        )
    return calibration_dir


def _validate_output_id(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CalibrationPointValidationError(f"{label} cannot be empty.")
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
        raise CalibrationPointValidationError(f"{label} must not contain path separators.")
    return cleaned


def _build_report(
    *,
    calibration_id: str,
    source_image: str,
    image_width: int,
    image_height: int,
    image_points: Sequence[Point2D],
    image_to_court_matrix: Matrix3x3,
    court_to_image_matrix: Matrix3x3,
    reprojection_error: float,
    round_trip_error: float,
    top_down_image: str | None,
) -> CourtCalibrationReport:
    court = REGULATION_COURT
    return CourtCalibrationReport(
        calibration_id=calibration_id,
        source_image=source_image,
        image_width=image_width,
        image_height=image_height,
        coordinate_system=CalibrationCoordinateSystem(**COORDINATE_SYSTEM),
        court_dimensions=CalibrationCourtDimensions(
            width=court.width_feet,
            length=court.length_feet,
            non_volley_zone_depth=court.non_volley_zone_depth_feet,
        ),
        image_points=_ordered_points_model(image_points),
        court_points=_ordered_points_model(ordered_court_corner_points()),
        image_to_court_matrix=_matrix_to_json(image_to_court_matrix),
        court_to_image_matrix=_matrix_to_json(court_to_image_matrix),
        reprojection_error=reprojection_error,
        round_trip_error=round_trip_error,
        top_down_image=top_down_image,
        created_at=datetime.now(tz=UTC),
    )


def _ordered_points_model(points: Sequence[Point2D]) -> OrderedCalibrationPoints:
    return OrderedCalibrationPoints(
        near_left=points[0],
        near_right=points[1],
        far_right=points[2],
        far_left=points[3],
    )


def _matrix_to_json(matrix: Matrix3x3) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix.tolist()]


def _write_calibration_report(report: CourtCalibrationReport, calibration_path: Path) -> None:
    calibration_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _write_verification_image(
    *,
    image: ImageArray,
    image_points: Sequence[Point2D],
    court_to_image_matrix: Matrix3x3,
    output_path: Path,
    transition_area_depth_feet: float,
) -> None:
    verification = image.copy()
    landmarks = build_court_landmarks(transition_area_depth_feet)

    outer_points = court_points_to_image(ordered_court_corner_points(), court_to_image_matrix)
    _draw_polyline(verification, outer_points, color=(0, 255, 255), thickness=3, closed=True)

    line_colors = {
        "net_line": (0, 0, 255),
        "near_kitchen_line": (255, 0, 255),
        "far_kitchen_line": (255, 0, 255),
        "near_center_service_line": (255, 255, 0),
        "far_center_service_line": (255, 255, 0),
        "near_baseline": (0, 255, 255),
        "far_baseline": (0, 255, 255),
    }
    for line in landmarks.lines:
        _draw_projected_line(
            image=verification,
            line=line,
            matrix=court_to_image_matrix,
            color=line_colors.get(line.name, (255, 255, 255)),
        )

    for name, point in zip(ORDERED_CORNER_NAMES, image_points, strict=True):
        pixel = _to_int_point(point)
        cv2.circle(verification, pixel, 6, (0, 255, 0), thickness=-1)
        _draw_label(verification, name.replace("_", "-"), pixel)

    if not cv2.imwrite(str(output_path), verification):
        raise CalibrationImageReadError(f"OpenCV could not write verification image: {output_path}")


def _draw_projected_line(
    *,
    image: ImageArray,
    line: CourtLine,
    matrix: Matrix3x3,
    color: tuple[int, int, int],
) -> None:
    start, end = court_points_to_image((line.start, line.end), matrix)
    cv2.line(image, _to_int_point(start), _to_int_point(end), color, thickness=2)


def _draw_polyline(
    image: ImageArray,
    points: Sequence[Point2D],
    *,
    color: tuple[int, int, int],
    thickness: int,
    closed: bool,
) -> None:
    int_points = np.array([_to_int_point(point) for point in points], dtype=np.int32)
    cv2.polylines(image, [int_points], isClosed=closed, color=color, thickness=thickness)


def _draw_label(image: ImageArray, label: str, pixel: tuple[int, int]) -> None:
    x, y = pixel
    label_origin = (x + 8, max(15, y - 8))
    cv2.putText(
        image,
        label,
        label_origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 0, 0),
        thickness=3,
        lineType=cv2.LINE_AA,
    )
    cv2.putText(
        image,
        label,
        label_origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        thickness=1,
        lineType=cv2.LINE_AA,
    )


def _write_top_down_image(
    *,
    image: ImageArray,
    image_points: Sequence[Point2D],
    output_path: Path,
    width_pixels: int,
) -> None:
    court = REGULATION_COURT
    height_pixels = int(round(width_pixels * court.length_feet / court.width_feet))
    top_down_points = (
        (0.0, 0.0),
        (float(width_pixels - 1), 0.0),
        (float(width_pixels - 1), float(height_pixels - 1)),
        (0.0, float(height_pixels - 1)),
    )
    image_to_top_down = _compute_perspective_transform(
        source_points=image_points,
        destination_points=top_down_points,
    )
    warped = cv2.warpPerspective(image, image_to_top_down, (width_pixels, height_pixels))
    if not cv2.imwrite(str(output_path), warped):
        raise CalibrationImageReadError(f"OpenCV could not write top-down image: {output_path}")


def _to_int_point(point: Point2D) -> tuple[int, int]:
    return (int(round(point[0])), int(round(point[1])))
