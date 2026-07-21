import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from app.schemas.player_tracking import TrackedPersonDetection
from app.services.detection.interfaces import ImageArray, PersonDetectionBackend
from app.services.tracking.exceptions import DetectorUnavailableError


class JsonTrackingBackend(PersonDetectionBackend):
    """Controlled tracking backend for offline validation and deterministic tests.

    The JSONL file must contain one object per detection:
    `{"frame_index": 0, "track_id": 1, "bounding_box": {...}, "confidence": 0.9}`.
    Track IDs are supplied by the fixture; this backend does not perform association.
    """

    def __init__(self, detections_path: Path, *, model_name: str = "controlled-json") -> None:
        self._detections_by_frame = _load_detections(detections_path)
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def track_frame(
        self,
        frame: ImageArray,
        *,
        frame_index: int,
        timestamp_seconds: float,
    ) -> Sequence[TrackedPersonDetection]:
        del frame, timestamp_seconds
        return self._detections_by_frame.get(frame_index, ())

    def close(self) -> None:
        return None


def _load_detections(detections_path: Path) -> dict[int, tuple[TrackedPersonDetection, ...]]:
    if not detections_path.exists():
        raise DetectorUnavailableError(
            f"Controlled detections file does not exist: {detections_path}"
        )
    if not detections_path.is_file():
        raise DetectorUnavailableError(
            f"Controlled detections path is not a file: {detections_path}"
        )

    detections_by_frame: dict[int, list[TrackedPersonDetection]] = {}
    lines = detections_path.read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            frame_index = int(payload["frame_index"])
            detection = TrackedPersonDetection.model_validate(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise DetectorUnavailableError(
                f"Invalid controlled detection on line {line_number}: {detections_path}"
            ) from exc
        if frame_index < 0:
            raise DetectorUnavailableError(
                f"Controlled detection frame_index must be non-negative on line {line_number}."
            )
        detections_by_frame.setdefault(frame_index, []).append(detection)

    return {
        frame_index: tuple(detections) for frame_index, detections in detections_by_frame.items()
    }


def build_controlled_detection_line(
    *,
    frame_index: int,
    track_id: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    confidence: float,
) -> str:
    payload = {
        "frame_index": frame_index,
        "track_id": track_id,
        "bounding_box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "confidence": confidence,
    }
    return json.dumps(payload, separators=(",", ":"))


def empty_frame(width: int = 1, height: int = 1) -> ImageArray:
    return np.zeros((height, width, 3), dtype=np.uint8)
