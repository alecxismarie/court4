from __future__ import annotations

from collections import deque
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.ball_tracking import BallObservation, BallObservationState, BallTrackEvent
from app.services.video.frame_source import OpenCVFrameSource

Image = NDArray[np.uint8]


class BallVisualizationError(RuntimeError):
    pass


def write_trajectory_image(
    *,
    output_path: Path,
    width: int,
    height: int,
    observations: tuple[BallObservation, ...],
    evidence_label: str,
) -> None:
    canvas = np.full((height, width, 3), 18, dtype=np.uint8)
    cv2.putText(
        canvas,
        "Experimental image-space ball trajectory",
        (24, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (235, 235, 235),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        evidence_label,
        (24, 68),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (160, 190, 190),
        1,
        cv2.LINE_AA,
    )
    by_segment: dict[str, list[BallObservation]] = {}
    for observation in observations:
        by_segment.setdefault(observation.track_segment_id, []).append(observation)
    for segment in by_segment.values():
        for previous, current in zip(segment, segment[1:], strict=False):
            color = (
                (0, 190, 255)
                if BallObservationState.interpolated
                in {previous.observation_state, current.observation_state}
                else (80, 235, 135)
            )
            cv2.line(
                canvas,
                _point(previous),
                _point(current),
                color,
                1 if color == (0, 190, 255) else 2,
                cv2.LINE_AA,
            )
        for observation in segment:
            cv2.circle(
                canvas,
                _point(observation),
                3,
                (
                    (0, 190, 255)
                    if observation.observation_state == BallObservationState.interpolated
                    else (80, 235, 135)
                ),
                -1,
                cv2.LINE_AA,
            )
    if not observations:
        cv2.putText(
            canvas,
            "No accepted ball observations",
            (24, max(105, height // 2)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (80, 160, 255),
            2,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(output_path), canvas):
        raise BallVisualizationError("OpenCV could not write the trajectory image.")


def write_overlay_video(
    *,
    video_path: Path,
    output_path: Path,
    observations: tuple[BallObservation, ...],
    events: tuple[BallTrackEvent, ...],
    max_frames: int,
) -> None:
    by_frame = {observation.frame_index: observation for observation in observations}
    event_frames = {
        event.frame_index: event for event in events if event.event_type == "reacquired"
    }
    with OpenCVFrameSource(video_path) as source:
        metadata = source.metadata
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),  # type: ignore[attr-defined]
            metadata.fps,
            (metadata.width, metadata.height),
        )
        if not writer.isOpened():
            writer.release()
            raise BallVisualizationError("OpenCV MP4 overlay writer is unavailable.")
        trail: deque[BallObservation] = deque(maxlen=24)
        try:
            for frame in source:
                if frame.frame_index >= max_frames:
                    break
                image = frame.image.copy()
                observation = by_frame.get(frame.frame_index)
                if observation is not None:
                    trail.append(observation)
                _draw_trail(image, trail)
                if observation is not None:
                    _draw_observation(image, observation)
                event = event_frames.get(frame.frame_index)
                if event is not None:
                    cv2.putText(
                        image,
                        f"REACQUIRED after {event.gap_length_frames} frames",
                        (18, 34),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 190, 255),
                        2,
                        cv2.LINE_AA,
                    )
                cv2.putText(
                    image,
                    "EXPERIMENTAL BALL EVIDENCE",
                    (18, metadata.height - 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 190, 255),
                    1,
                    cv2.LINE_AA,
                )
                writer.write(image)
        finally:
            writer.release()
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise BallVisualizationError("Overlay video was not created.")


def _draw_trail(image: Image, trail: deque[BallObservation]) -> None:
    points = list(trail)
    for previous, current in zip(points, points[1:], strict=False):
        inferred = BallObservationState.interpolated in {
            previous.observation_state,
            current.observation_state,
        }
        cv2.line(
            image,
            _point(previous),
            _point(current),
            (0, 190, 255) if inferred else (80, 235, 135),
            1 if inferred else 2,
            cv2.LINE_AA,
        )


def _draw_observation(image: Image, observation: BallObservation) -> None:
    inferred = observation.observation_state == BallObservationState.interpolated
    color = (0, 190, 255) if inferred else (80, 235, 135)
    cv2.circle(image, _point(observation), 6, color, 2, cv2.LINE_AA)
    label = (
        f"inferred gap={observation.gap_length_frames}"
        if inferred
        else f"observed {observation.confidence:.2f}"
    )
    x, y = _point(observation)
    cv2.putText(
        image,
        label,
        (max(4, x + 8), max(18, y - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        1,
        cv2.LINE_AA,
    )


def _point(observation: BallObservation) -> tuple[int, int]:
    return (int(round(observation.image_x)), int(round(observation.image_y)))
