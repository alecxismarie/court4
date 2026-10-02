"""Label-based offline evaluation. Detector confidence is deliberately not an input."""

from typing import Any

import cv2
import numpy as np

from scripts.court_vision_annotations import (
    CORNERS,
    KEYPOINTS,
    LINES,
    REQUIRED_LINES,
    FrameAnnotation,
)

# Experimental evaluation policy, not production detector/calibration thresholds.
POLICY: dict[str, Any] = {
    "version": "court-vision-evaluation-v1",
    "max_projection_diagonal_fraction": 0.005,
    "max_court_error_feet": 0.5,
    "min_required_line_coverage": 0.30,
    "min_line_support_fraction": 0.70,
    "line_sample_spacing_px": 2.0,
}


def project(points: Any, matrix: Any) -> Any:
    array = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    homogeneous = np.column_stack((array, np.ones(len(array)))) @ matrix.T
    if not np.isfinite(homogeneous).all() or np.any(np.abs(homogeneous[:, 2]) < 1e-10):
        raise ValueError("Projection is nonfinite or crosses the homography horizon.")
    return homogeneous[:, :2] / homogeneous[:, 2:]


def summary(errors: list[float], diagonal: float) -> dict[str, Any] | None:
    if not errors:
        return None
    return {
        "count": len(errors),
        "mean_px": float(np.mean(errors)),
        "median_px": float(np.median(errors)),
        "p95_px": float(np.percentile(errors, 95)),
        "max_px": float(max(errors)),
        "p95_diagonal_fraction": float(np.percentile(errors, 95) / diagonal),
    }


def line_metrics(line: Any, endpoints: Any, diagonal: float) -> dict[str, Any] | None:
    """Arc-length weighted distance to the finite proposed segment on labeled visible runs.

    Projecting visible runs onto that segment supplies union coverage, not evidence for
    hidden paint. No nearest unrelated image edge or detector contour is used as truth.
    """
    if not line.visible_runs:
        return None
    start, end = endpoints
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length < 1e-8:
        raise ValueError("Collapsed projected court line.")
    samples: list[Any] = []
    weights: list[float] = []
    intervals: list[tuple[float, float]] = []
    for run in line.visible_runs:
        for a, b in zip(run.points, run.points[1:], strict=False):
            a, b = np.asarray(a), np.asarray(b)
            segment_length = float(np.linalg.norm(b - a))
            count = max(1, int(np.ceil(segment_length / POLICY["line_sample_spacing_px"])))
            samples.extend(a + ((i + 0.5) / count) * (b - a) for i in range(count))
            weights.extend([segment_length / count] * count)
            t = sorted(float(np.dot(p - start, direction) / length**2) for p in (a, b))
            intervals.append((max(0.0, t[0]), min(1.0, t[1])))
    observed = np.asarray(samples)
    t = np.clip((observed - start) @ direction / length**2, 0, 1)
    distances = np.linalg.norm(observed - (start + t[:, None] * direction), axis=1)
    tolerance = diagonal * POLICY["max_projection_diagonal_fraction"]
    coverage, previous_end = 0.0, 0.0
    for left, right in sorted(intervals):
        if right > max(left, previous_end):
            coverage += right - max(left, previous_end)
        previous_end = max(previous_end, right)
    weight_array = np.asarray(weights)
    order = np.argsort(distances, kind="stable")
    cumulative = np.cumsum(weight_array[order]) / weight_array.sum()
    p95_index = min(int(np.searchsorted(cumulative, 0.95)), len(order) - 1)
    p95 = float(distances[order[p95_index]])
    return {
        "mean_px": float(np.average(distances, weights=weights)),
        "p95_px": p95,
        "max_px": float(distances.max()),
        "p95_diagonal_fraction": p95 / diagonal,
        "support_fraction": float(np.average(distances <= tolerance, weights=weights)),
        "visible_length_px": float(weight_array.sum()),
        "projected_coverage": coverage,
        "annotation_uncertainty_px": line.uncertainty_px,
    }


def evaluate(frame: FrameAnnotation, corners: Any | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "outcome": "abstain",
        "reasons": [],
        "corner_projection": None,
        "landmark_projection": None,
        "interior_projection": None,
        "court_error_p95_feet": None,
        "keypoint_errors_px": {},
        "lines": {},
    }
    if corners is None:
        result["reasons"] = ["no_proposal"]
        return result
    if frame.review_status != "reviewed":
        result["reasons"] = ["labels_not_reviewed"]
        return result
    if frame.suitability == "no_target_court":
        result.update(outcome="incorrect", reasons=["proposal_on_no_target_court"])
        return result
    if frame.orientation == "unresolved":
        result["reasons"] = ["unresolved_orientation"]
        return result
    diagonal = float(np.hypot(frame.width, frame.height))
    try:
        array = np.asarray(corners, dtype=np.float32)
        if array.shape != (4, 2) or not np.isfinite(array).all():
            raise ValueError("Invalid corner array.")
        if np.any(array < 0) or np.any(array >= (frame.width, frame.height)):
            raise ValueError("Proposal corners outside the frame.")
        if not cv2.isContourConvex(array) or abs(cv2.contourArea(array)) < 1:
            raise ValueError("Degenerate or crossing corners.")
        matrix = cv2.getPerspectiveTransform(
            np.array(list(KEYPOINTS.values())[:4], np.float32), array
        )
        if abs(np.linalg.det(matrix)) < 1e-12:
            raise ValueError("Singular homography.")
        # A horizon inside the court invalidates the whole plane, even if some points project.
        denominators = np.column_stack((list(KEYPOINTS.values())[:4], np.ones(4))) @ matrix[2]
        if np.min(denominators) * np.max(denominators) <= 0:
            raise ValueError("Homography horizon intersects court.")
        predicted = project(list(KEYPOINTS.values()), matrix)
        inverse = np.linalg.inv(matrix)
        errors, feet_errors, uncertainties = {}, [], []
        for name, pixel in zip(KEYPOINTS, predicted, strict=True):
            label = frame.keypoints[name]
            if label.visibility != "visible":
                continue
            assert label.xy is not None and label.uncertainty_px is not None
            errors[name] = float(np.linalg.norm(pixel - label.xy))
            feet_errors.append(
                float(np.linalg.norm(project([label.xy], inverse)[0] - KEYPOINTS[name]))
            )
            uncertainties.append(label.uncertainty_px)
        result["keypoint_errors_px"] = errors
        result["corner_projection"] = summary(
            [v for k, v in errors.items() if k in CORNERS], diagonal
        )
        result["interior_projection"] = summary(
            [v for k, v in errors.items() if k not in CORNERS], diagonal
        )
        result["landmark_projection"] = summary(list(errors.values()), diagonal)
        if feet_errors:
            result["court_error_p95_feet"] = float(np.percentile(feet_errors, 95))
        result["lines"] = {
            name: line_metrics(frame.lines[name], project(points, matrix), diagonal)
            for name, points in LINES.items()
        }
    except (ValueError, np.linalg.LinAlgError, cv2.error):
        result.update(outcome="incorrect", reasons=["invalid_proposal_geometry"])
        return result

    tolerance = diagonal * POLICY["max_projection_diagonal_fraction"]
    # Contradictions take precedence over incomplete coverage. Uncertain labels cannot
    # manufacture either acceptance or a contradiction within their uncertainty band.
    contradictions = [
        f"keypoint_misaligned:{name}"
        for name, error in errors.items()
        if error > tolerance + (frame.keypoints[name].uncertainty_px or 0)
    ]
    contradictions.extend(
        f"line_misaligned:{name}"
        for name, metric in result["lines"].items()
        if metric and metric["p95_px"] > tolerance + frame.lines[name].uncertainty_px
    )
    if contradictions:
        result.update(outcome="incorrect", reasons=contradictions)
        return result
    missing = []
    if frame.suitability != "full_geometry_supported":
        missing.append("partial_or_ambiguous_target")
    # Conservative foundation: all outer corners plus two visible interior labels.
    if not all(name in errors for name in CORNERS) or len(errors) < 6:
        missing.append("insufficient_visible_keypoints")
    for name in REQUIRED_LINES:
        metric = result["lines"][name]
        if not metric or (
            metric["projected_coverage"] < POLICY["min_required_line_coverage"]
            or metric["support_fraction"] < POLICY["min_line_support_fraction"]
        ):
            missing.append(f"insufficient_line_support:{name}")
    if any(u > tolerance for u in uncertainties) or any(
        frame.lines[name].uncertainty_px > tolerance for name in REQUIRED_LINES
    ):
        missing.append("annotation_uncertainty_too_large")
    if errors and max(errors.values()) > tolerance:
        missing.append("projection_error_within_annotation_uncertainty")
    if any(metric and metric["p95_px"] > tolerance for metric in result["lines"].values()):
        missing.append("line_error_within_annotation_uncertainty")
    if feet_errors and result["court_error_p95_feet"] > POLICY["max_court_error_feet"]:
        missing.append("court_coordinate_error_exceeds_policy")
    result.update(outcome="abstain" if missing else "accept", reasons=missing)
    return result
