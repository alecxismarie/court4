from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.ball_tracking import (
    BallBoundingBox,
    BallCandidateDisposition,
    BallDetectionCandidate,
    BallFrameDetection,
    BallFrameDetectionState,
)
from app.services.video.frame_source import VideoFrame

Mask = NDArray[np.uint8]


@dataclass(frozen=True)
class OpenCVBallDetectorConfig:
    hue_min: int = 24
    hue_max: int = 96
    saturation_min: int = 80
    value_min: int = 95
    motion_threshold: int = 18
    min_radius_pixels: float = 2.0
    max_radius_fraction: float = 0.055
    min_circularity: float = 0.42
    min_color_fill_ratio: float = 0.38
    min_motion_fill_ratio: float = 0.08
    max_aspect_ratio: float = 1.9
    acceptance_confidence: float = 0.48
    max_candidates_per_frame: int = 24

    def __post_init__(self) -> None:
        if not 0 <= self.hue_min <= self.hue_max <= 179:
            raise ValueError("Detector hue bounds must be ordered within OpenCV HSV range.")
        if not 0 <= self.saturation_min <= 255 or not 0 <= self.value_min <= 255:
            raise ValueError("Detector saturation and value thresholds must be bytes.")
        if not 0 <= self.motion_threshold <= 255:
            raise ValueError("Detector motion threshold must be a byte.")
        if self.min_radius_pixels <= 0 or not 0 < self.max_radius_fraction < 0.5:
            raise ValueError("Detector size bounds are invalid.")
        for value in (
            self.min_circularity,
            self.min_color_fill_ratio,
            self.min_motion_fill_ratio,
            self.acceptance_confidence,
        ):
            if not 0 <= value <= 1:
                raise ValueError("Detector evidence thresholds must be between zero and one.")
        if self.max_aspect_ratio < 1 or self.max_candidates_per_frame < 1:
            raise ValueError("Detector shape and candidate bounds are invalid.")

    def as_dict(self) -> dict[str, float | int]:
        return {
            "hue_min": self.hue_min,
            "hue_max": self.hue_max,
            "saturation_min": self.saturation_min,
            "value_min": self.value_min,
            "motion_threshold": self.motion_threshold,
            "min_radius_pixels": self.min_radius_pixels,
            "max_radius_fraction": self.max_radius_fraction,
            "min_circularity": self.min_circularity,
            "min_color_fill_ratio": self.min_color_fill_ratio,
            "min_motion_fill_ratio": self.min_motion_fill_ratio,
            "max_aspect_ratio": self.max_aspect_ratio,
            "acceptance_confidence": self.acceptance_confidence,
            "max_candidates_per_frame": self.max_candidates_per_frame,
        }


class BallDetector(Protocol):
    name: str
    version: str
    model_identifier: str | None
    model_sha256: str | None

    def detect(self, frame: VideoFrame) -> BallFrameDetection: ...


@dataclass(frozen=True)
class _CandidateMeasurement:
    candidate_id: str
    image_x: float
    image_y: float
    bounding_box: BallBoundingBox
    confidence: float
    radius_pixels: float
    circularity: float
    color_fill_ratio: float
    motion_fill_ratio: float
    rejection_reasons: tuple[str, ...]


class OpenCVColorMotionBallDetector:
    """Conservative experimental detector for moving yellow/lime pickleballs.

    It is deliberately not a generic ball classifier. Color blobs remain raw candidates until
    geometry, size, motion, and confidence gates all pass. This keeps candidate generation from
    being represented as a detection.
    """

    name: str = "opencv_color_motion_ball_detector"
    version: str = "1.0.0"
    model_identifier: str | None = None
    model_sha256: str | None = None

    def __init__(self, config: OpenCVBallDetectorConfig | None = None) -> None:
        self.config = config or OpenCVBallDetectorConfig()
        self._previous_gray: NDArray[np.uint8] | None = None

    def detect(self, frame: VideoFrame) -> BallFrameDetection:
        image = frame.image
        gray = cast(NDArray[np.uint8], cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        color_mask = cast(
            Mask,
            cv2.inRange(
                hsv,
                np.array(
                    [
                        self.config.hue_min,
                        self.config.saturation_min,
                        self.config.value_min,
                    ],
                    dtype=np.uint8,
                ),
                np.array([self.config.hue_max, 255, 255], dtype=np.uint8),
            ),
        )
        color_mask = cast(
            Mask,
            cv2.morphologyEx(
                color_mask,
                cv2.MORPH_OPEN,
                np.ones((3, 3), dtype=np.uint8),
            ),
        )
        motion_mask = self._motion_mask(gray)
        self._previous_gray = gray

        contours, _ = cv2.findContours(color_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[
            : self.config.max_candidates_per_frame
        ]
        measurements = [
            self._measure_candidate(
                contour=cast(NDArray[np.int32], contour),
                color_mask=color_mask,
                motion_mask=motion_mask,
                frame=frame,
                candidate_index=index,
            )
            for index, contour in enumerate(contours)
        ]
        accepted_indices = [
            index for index, candidate in enumerate(measurements) if not candidate.rejection_reasons
        ]
        winner_index = (
            max(accepted_indices, key=lambda index: measurements[index].confidence)
            if accepted_indices
            else None
        )
        candidates = tuple(
            self._candidate_model(
                measurement,
                accepted=index == winner_index,
                lower_ranked=index in accepted_indices and index != winner_index,
            )
            for index, measurement in enumerate(measurements)
        )
        if winner_index is None:
            return BallFrameDetection(
                frame_index=frame.frame_index,
                timestamp_seconds=frame.timestamp_seconds,
                state=BallFrameDetectionState.missing,
                candidates=candidates,
            )
        return BallFrameDetection(
            frame_index=frame.frame_index,
            timestamp_seconds=frame.timestamp_seconds,
            state=BallFrameDetectionState.observed,
            candidates=candidates,
            accepted_candidate_id=measurements[winner_index].candidate_id,
        )

    def _motion_mask(self, gray: NDArray[np.uint8]) -> Mask | None:
        if self._previous_gray is None:
            return None
        difference = cv2.absdiff(gray, self._previous_gray)
        _, mask = cv2.threshold(
            difference,
            self.config.motion_threshold,
            255,
            cv2.THRESH_BINARY,
        )
        return cast(Mask, cv2.dilate(mask, np.ones((5, 5), dtype=np.uint8), iterations=1))

    def _measure_candidate(
        self,
        *,
        contour: NDArray[np.int32],
        color_mask: Mask,
        motion_mask: Mask | None,
        frame: VideoFrame,
        candidate_index: int,
    ) -> _CandidateMeasurement:
        area = float(cv2.contourArea(contour))
        x, y, width, height = cv2.boundingRect(contour)
        (center_x, center_y), radius = cv2.minEnclosingCircle(contour)
        perimeter = float(cv2.arcLength(contour, closed=True))
        circularity = min(1.0, 4.0 * math.pi * area / (perimeter * perimeter)) if perimeter else 0.0
        box_area = max(1, width * height)
        color_fill = float(cv2.countNonZero(color_mask[y : y + height, x : x + width])) / box_area
        motion_fill = (
            float(cv2.countNonZero(motion_mask[y : y + height, x : x + width])) / box_area
            if motion_mask is not None
            else 0.0
        )
        aspect_ratio = max(width, height) / max(1, min(width, height))
        max_radius = min(frame.source.width, frame.source.height) * self.config.max_radius_fraction
        rejection_reasons: list[str] = []
        if radius < self.config.min_radius_pixels:
            rejection_reasons.append("below_minimum_size")
        if radius > max_radius:
            rejection_reasons.append("above_maximum_size")
        if circularity < self.config.min_circularity:
            rejection_reasons.append("insufficient_circularity")
        if color_fill < self.config.min_color_fill_ratio:
            rejection_reasons.append("insufficient_color_fill")
        if aspect_ratio > self.config.max_aspect_ratio:
            rejection_reasons.append("excessive_aspect_ratio")
        if motion_mask is None:
            rejection_reasons.append("motion_warmup")
        elif motion_fill < self.config.min_motion_fill_ratio:
            rejection_reasons.append("insufficient_motion")
        size_score = min(1.0, radius / max(self.config.min_radius_pixels * 2.5, 1.0))
        confidence = min(
            1.0,
            0.30 * circularity + 0.25 * color_fill + 0.30 * motion_fill + 0.15 * size_score,
        )
        if confidence < self.config.acceptance_confidence:
            rejection_reasons.append("below_acceptance_confidence")
        return _CandidateMeasurement(
            candidate_id=f"f{frame.frame_index:08d}-c{candidate_index:03d}",
            image_x=float(center_x),
            image_y=float(center_y),
            bounding_box=BallBoundingBox(
                x1=float(x),
                y1=float(y),
                x2=float(x + width),
                y2=float(y + height),
            ),
            confidence=confidence,
            radius_pixels=float(radius),
            circularity=circularity,
            color_fill_ratio=color_fill,
            motion_fill_ratio=motion_fill,
            rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        )

    @staticmethod
    def _candidate_model(
        measurement: _CandidateMeasurement,
        *,
        accepted: bool,
        lower_ranked: bool,
    ) -> BallDetectionCandidate:
        reasons = measurement.rejection_reasons
        if lower_ranked:
            reasons = ("lower_ranked_candidate",)
        return BallDetectionCandidate(
            candidate_id=measurement.candidate_id,
            image_x=measurement.image_x,
            image_y=measurement.image_y,
            bounding_box=measurement.bounding_box,
            confidence=measurement.confidence,
            radius_pixels=measurement.radius_pixels,
            circularity=measurement.circularity,
            color_fill_ratio=measurement.color_fill_ratio,
            motion_fill_ratio=measurement.motion_fill_ratio,
            disposition=(
                BallCandidateDisposition.accepted if accepted else BallCandidateDisposition.rejected
            ),
            rejection_reasons=() if accepted else reasons,
        )
