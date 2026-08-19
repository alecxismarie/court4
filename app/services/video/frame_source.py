from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, cast

import cv2
import numpy as np
from numpy.typing import NDArray

type ImageFrame = NDArray[np.uint8]


class FrameSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoSourceMetadata:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int


@dataclass(frozen=True)
class VideoFrame:
    frame_index: int
    timestamp_seconds: float
    image: ImageFrame
    source: VideoSourceMetadata


class FrameSource(Protocol):
    @property
    def metadata(self) -> VideoSourceMetadata: ...

    def __iter__(self) -> Iterator[VideoFrame]: ...


class OpenCVFrameSource:
    """Streaming, bounded-memory frame source shared by independent CV stages."""

    def __init__(self, video_path: Path) -> None:
        resolved = video_path.expanduser().resolve()
        if not resolved.is_file():
            raise FrameSourceError(f"Video source is unavailable: {resolved}")
        capture = cv2.VideoCapture(str(resolved))
        if not capture.isOpened():
            capture.release()
            raise FrameSourceError(f"OpenCV could not open video source: {resolved}")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if width <= 0 or height <= 0 or fps <= 0:
            capture.release()
            raise FrameSourceError("OpenCV could not determine valid video source metadata.")
        self._capture = capture
        self._metadata = VideoSourceMetadata(
            path=resolved,
            width=width,
            height=height,
            fps=fps,
            frame_count=max(0, frame_count),
        )
        self._closed = False

    @property
    def metadata(self) -> VideoSourceMetadata:
        return self._metadata

    def __iter__(self) -> Iterator[VideoFrame]:
        frame_index = 0
        while not self._closed:
            success, frame = self._capture.read()
            if not success:
                break
            yield VideoFrame(
                frame_index=frame_index,
                timestamp_seconds=frame_index / self._metadata.fps,
                image=cast(ImageFrame, frame),
                source=self._metadata,
            )
            frame_index += 1

    def close(self) -> None:
        if not self._closed:
            self._capture.release()
            self._closed = True

    def __enter__(self) -> OpenCVFrameSource:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        self.close()
