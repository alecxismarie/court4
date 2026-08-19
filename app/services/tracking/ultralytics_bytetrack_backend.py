from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.player_tracking import BoundingBox, TrackedPersonDetection
from app.services.detection.interfaces import ImageArray, PersonDetectionBackend
from app.services.tracking.exceptions import DetectorRuntimeUnavailableError
from app.services.tracking.model_provisioning import verify_detector_model


class UltralyticsByteTrackBackend(PersonDetectionBackend):
    """Ultralytics YOLO person detector with integrated ByteTrack association.

    This adapter imports Ultralytics lazily and requires a local model weight file. It
    does not download weights. Install the optional `detector` extra and place the
    configured model file on disk before using it.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        expected_model_sha256: str,
        confidence_threshold: float,
        image_size: int,
    ) -> None:
        verify_detector_model(model_path, expected_model_sha256)

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorRuntimeUnavailableError(
                "Ultralytics is not installed. Install the optional detector extra with "
                "`python -m pip install -e .[detector]`."
            ) from exc

        self._model_path = model_path
        self._confidence_threshold = confidence_threshold
        self._image_size = image_size
        self._model: Any | None = YOLO(str(model_path))

    @property
    def model_name(self) -> str:
        return f"ultralytics-bytetrack:{self._model_path.name}"

    def track_frame(
        self,
        frame: ImageArray,
        *,
        frame_index: int,
        timestamp_seconds: float,
    ) -> tuple[TrackedPersonDetection, ...]:
        del frame_index, timestamp_seconds
        if self._model is None:
            return ()
        results = self._model.track(
            frame,
            persist=True,
            classes=[0],
            conf=self._confidence_threshold,
            imgsz=self._image_size,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        if not results:
            return ()

        boxes = getattr(results[0], "boxes", None)
        if boxes is None or boxes.id is None:
            return ()

        xyxy = _to_numpy(boxes.xyxy)
        confidences = _to_numpy(boxes.conf)
        track_ids = _to_numpy(boxes.id)

        detections: list[TrackedPersonDetection] = []
        for box, confidence, track_id in zip(xyxy, confidences, track_ids, strict=True):
            detections.append(
                TrackedPersonDetection(
                    track_id=int(track_id),
                    bounding_box=BoundingBox(
                        x1=float(box[0]),
                        y1=float(box[1]),
                        x2=float(box[2]),
                        y2=float(box[3]),
                    ),
                    confidence=float(confidence),
                )
            )
        return tuple(detections)

    def close(self) -> None:
        self._model = None


def _to_numpy(value: Any) -> np.ndarray[Any, Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)
