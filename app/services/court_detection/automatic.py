import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.calibration import CourtCalibrationReport
from app.schemas.jobs import CourtDetectionOutcome
from app.sports.pickleball import CourtCalibrationError, calibrate_court
from app.sports.pickleball.geometry import Point2D

logger = logging.getLogger(__name__)

ImageArray = NDArray[np.uint8]
MAX_AUTOMATIC_COURT_AREA_RATIO = 0.75


@dataclass(frozen=True)
class AutomaticCourtDetectionResult:
    outcome: CourtDetectionOutcome
    confidence: float
    selected_frame_path: Path | None
    image_points: tuple[Point2D, Point2D, Point2D, Point2D] | None
    calibration: CourtCalibrationReport | None
    artifacts: tuple[Path, ...]


@dataclass(frozen=True)
class _CourtCandidate:
    frame_path: Path
    image_points: tuple[Point2D, Point2D, Point2D, Point2D]
    confidence: float


def detect_pickleball_court(
    *,
    frame_paths: Sequence[Path],
    output_dir: Path,
    analysis_id: str,
    calibration_id: str,
    min_confidence: float,
    low_confidence_threshold: float,
    numeric_tolerance: float,
    min_polygon_area_pixels: float,
    transition_area_depth_feet: float,
    top_down_width_pixels: int,
) -> AutomaticCourtDetectionResult:
    """Detect a court quadrilateral from sampled frames and calibrate when confident.

    The detector is intentionally deterministic and local: it searches sampled images for
    high-contrast court-line masks, scores four-corner outer-boundary candidates, and reuses
    the existing manual calibration path once a confident candidate is found.
    """
    if min_confidence <= 0 or min_confidence > 1:
        raise ValueError("Minimum court detection confidence must be in (0, 1].")
    if low_confidence_threshold < 0 or low_confidence_threshold > min_confidence:
        raise ValueError("Low-confidence threshold must be between 0 and the minimum confidence.")

    candidates = [
        candidate
        for frame_path in frame_paths
        if (candidate := _detect_frame_candidate(frame_path, min_polygon_area_pixels)) is not None
    ]
    if not candidates:
        return AutomaticCourtDetectionResult(
            outcome=CourtDetectionOutcome.failed,
            confidence=0.0,
            selected_frame_path=None,
            image_points=None,
            calibration=None,
            artifacts=(),
        )

    best = max(candidates, key=lambda candidate: candidate.confidence)
    if best.confidence < low_confidence_threshold:
        return AutomaticCourtDetectionResult(
            outcome=CourtDetectionOutcome.failed,
            confidence=best.confidence,
            selected_frame_path=best.frame_path,
            image_points=best.image_points,
            calibration=None,
            artifacts=(),
        )
    if best.confidence < min_confidence:
        return AutomaticCourtDetectionResult(
            outcome=CourtDetectionOutcome.low_confidence,
            confidence=best.confidence,
            selected_frame_path=best.frame_path,
            image_points=best.image_points,
            calibration=None,
            artifacts=(),
        )

    try:
        calibration = calibrate_court(
            image_path=best.frame_path,
            output_dir=output_dir,
            image_points=best.image_points,
            calibration_id=calibration_id,
            analysis_id=analysis_id,
            numeric_tolerance=numeric_tolerance,
            min_polygon_area_pixels=min_polygon_area_pixels,
            transition_area_depth_feet=transition_area_depth_feet,
            top_down_width_pixels=top_down_width_pixels,
        )
    except CourtCalibrationError:
        logger.info(
            "automatic_court_detection_calibration_failed",
            extra={"analysis_id": analysis_id, "selected_frame": str(best.frame_path)},
            exc_info=True,
        )
        return AutomaticCourtDetectionResult(
            outcome=CourtDetectionOutcome.failed,
            confidence=best.confidence,
            selected_frame_path=best.frame_path,
            image_points=best.image_points,
            calibration=None,
            artifacts=(),
        )

    artifacts = tuple(
        path
        for path in (
            calibration.calibration_path,
            calibration.verification_image_path,
            calibration.top_down_image_path,
        )
        if path is not None
    )
    return AutomaticCourtDetectionResult(
        outcome=CourtDetectionOutcome.detected,
        confidence=best.confidence,
        selected_frame_path=best.frame_path,
        image_points=best.image_points,
        calibration=calibration.report,
        artifacts=artifacts,
    )


def _detect_frame_candidate(
    frame_path: Path,
    min_polygon_area_pixels: float,
) -> _CourtCandidate | None:
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        logger.info("court_detection_frame_read_failed", extra={"frame_path": str(frame_path)})
        return None

    mask = _court_line_mask(cast(ImageArray, image))
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    height, width = image.shape[:2]
    image_area = float(width * height)
    best: _CourtCandidate | None = None
    for contour in contours:
        candidate = _candidate_from_contour(
            contour=cast(NDArray[np.int32], contour),
            frame_path=frame_path,
            image_area=image_area,
            min_polygon_area_pixels=min_polygon_area_pixels,
        )
        if candidate is None:
            continue
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    return best


def _court_line_mask(image: ImageArray) -> ImageArray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    colored_mask = cv2.inRange(
        hsv,
        np.array([0, 35, 35], dtype=np.uint8),
        np.array([179, 255, 255], dtype=np.uint8),
    )

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    height, width = image.shape[:2]
    colored_ratio = cv2.countNonZero(colored_mask) / float(width * height)
    mask = colored_mask if 0.00005 <= colored_ratio <= 0.20 else edges

    kernel = np.ones((5, 5), dtype=np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    dilated = cv2.dilate(closed, kernel, iterations=1)
    return cast(ImageArray, dilated)


def _candidate_from_contour(
    *,
    contour: NDArray[np.int32],
    frame_path: Path,
    image_area: float,
    min_polygon_area_pixels: float,
) -> _CourtCandidate | None:
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    if hull_area < min_polygon_area_pixels:
        return None

    perimeter = cv2.arcLength(hull, closed=True)
    if perimeter <= 0:
        return None

    for epsilon_factor in (0.015, 0.025, 0.04, 0.06, 0.09):
        approx = cv2.approxPolyDP(hull, epsilon_factor * perimeter, closed=True)
        if len(approx) != 4:
            continue

        points = tuple((float(point[0][0]), float(point[0][1])) for point in approx)
        ordered = _order_corners(points)
        area = abs(float(cv2.contourArea(np.array(ordered, dtype=np.float32))))
        if area < min_polygon_area_pixels:
            return None
        if image_area and area / image_area > MAX_AUTOMATIC_COURT_AREA_RATIO:
            continue

        confidence = _score_candidate(
            image_area=image_area,
            polygon_area=area,
            hull_area=hull_area,
            ordered_points=ordered,
        )
        return _CourtCandidate(
            frame_path=frame_path,
            image_points=ordered,
            confidence=confidence,
        )
    return None


def _order_corners(
    points: Sequence[Point2D],
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    sorted_by_y = sorted(points, key=lambda point: point[1])
    far = sorted(sorted_by_y[:2], key=lambda point: point[0])
    near = sorted(sorted_by_y[2:], key=lambda point: point[0])
    return (near[0], near[1], far[1], far[0])


def _score_candidate(
    *,
    image_area: float,
    polygon_area: float,
    hull_area: float,
    ordered_points: tuple[Point2D, Point2D, Point2D, Point2D],
) -> float:
    area_ratio = polygon_area / image_area if image_area else 0.0
    area_score = _clamp((area_ratio - 0.03) / 0.22)
    solidity_score = _clamp(polygon_area / hull_area) if hull_area else 0.0
    side_balance_score = _side_balance_score(ordered_points)
    return _clamp(0.20 + 0.55 * area_score + 0.15 * solidity_score + 0.10 * side_balance_score)


def _side_balance_score(points: tuple[Point2D, Point2D, Point2D, Point2D]) -> float:
    near_left, near_right, far_right, far_left = points
    near_width = _distance(near_left, near_right)
    far_width = _distance(far_left, far_right)
    left_side = _distance(near_left, far_left)
    right_side = _distance(near_right, far_right)
    ratios = [
        _min_over_max(near_width, far_width),
        _min_over_max(left_side, right_side),
    ]
    return sum(ratios) / len(ratios)


def _min_over_max(first: float, second: float) -> float:
    maximum = max(first, second)
    if maximum <= 0:
        return 0.0
    return min(first, second) / maximum


def _distance(first: Point2D, second: Point2D) -> float:
    return float(np.hypot(first[0] - second[0], first[1] - second[1]))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
