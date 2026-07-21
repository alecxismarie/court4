from collections.abc import Callable
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import pytest


@pytest.fixture
def synthetic_video_factory() -> Callable[..., Path]:
    def create_video(
        path: Path,
        *,
        frame_count: int = 30,
        fps: float = 10.0,
        width: int = 64,
        height: int = 48,
    ) -> Path:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the synthetic test video.")

        try:
            for index in range(frame_count):
                frame = np.zeros((height, width, 3), dtype=np.uint8)
                frame[:, :, 0] = (index * 7) % 255
                frame[:, :, 1] = (index * 13) % 255
                frame[:, :, 2] = (index * 19) % 255
                writer.write(frame)
        finally:
            writer.release()

        return path

    return create_video


@pytest.fixture
def synthetic_court_video_factory() -> Callable[..., Path]:
    def create_video(
        path: Path,
        *,
        frame_count: int = 30,
        fps: float = 10.0,
        width: int = 800,
        height: int = 900,
        court_scale: float = 1.0,
    ) -> Path:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the synthetic court test video.")

        try:
            for index in range(frame_count):
                frame = _synthetic_court_frame(
                    width=width,
                    height=height,
                    court_scale=court_scale,
                    brightness=245 - (index % 3) * 8,
                )
                writer.write(frame)
        finally:
            writer.release()

        return path

    return create_video


@pytest.fixture
def synthetic_court_image_factory() -> Callable[..., Path]:
    def create_image(
        path: Path,
        *,
        width: int = 800,
        height: int = 900,
    ) -> Path:
        image = np.full((height, width, 3), 245, dtype=np.uint8)
        court_polygon = np.array(
            [(80, 760), (720, 760), (600, 120), (200, 120)],
            dtype=np.int32,
        )
        cv2.polylines(image, [court_polygon], isClosed=True, color=(0, 140, 0), thickness=3)
        cv2.line(image, (140, 440), (660, 440), (0, 0, 255), thickness=2)
        cv2.line(image, (110, 540), (690, 540), (255, 0, 255), thickness=2)
        cv2.line(image, (170, 340), (630, 340), (255, 0, 255), thickness=2)
        if not cv2.imwrite(str(path), image):
            raise RuntimeError("OpenCV could not create the synthetic test court image.")
        return path

    return create_image


def _synthetic_court_frame(
    *,
    width: int,
    height: int,
    court_scale: float,
    brightness: int,
) -> np.ndarray:
    image = np.full((height, width, 3), brightness, dtype=np.uint8)
    base_corners = np.array(
        [
            (0.10 * width, 0.84 * height),
            (0.90 * width, 0.84 * height),
            (0.75 * width, 0.13 * height),
            (0.25 * width, 0.13 * height),
        ],
        dtype=np.float32,
    )
    center = np.array((width / 2.0, height / 2.0), dtype=np.float32)
    corners = center + (base_corners - center) * court_scale
    court_polygon = corners.astype(np.int32)

    cv2.polylines(image, [court_polygon], isClosed=True, color=(0, 140, 0), thickness=3)
    for first, second, color in (
        (
            _interpolate(corners[0], corners[3], 0.50),
            _interpolate(corners[1], corners[2], 0.50),
            (0, 0, 255),
        ),
        (
            _interpolate(corners[0], corners[3], 0.66),
            _interpolate(corners[1], corners[2], 0.66),
            (255, 0, 255),
        ),
        (
            _interpolate(corners[0], corners[3], 0.34),
            _interpolate(corners[1], corners[2], 0.34),
            (255, 0, 255),
        ),
    ):
        cv2.line(image, _point_to_int(first), _point_to_int(second), color, thickness=2)
    return image


def _interpolate(first: np.ndarray, second: np.ndarray, ratio: float) -> np.ndarray:
    return cast(np.ndarray, first + (second - first) * ratio)


def _point_to_int(point: np.ndarray) -> tuple[int, int]:
    return (int(round(float(point[0]))), int(round(float(point[1]))))
