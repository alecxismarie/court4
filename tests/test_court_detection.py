from pathlib import Path

import cv2
import numpy as np

from app.schemas.jobs import CourtDetectionOutcome
from app.services.court_detection.automatic import detect_pickleball_court


def test_automatic_detection_rejects_frame_border_as_court(tmp_path: Path) -> None:
    frame_path = tmp_path / "frame.jpg"
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    cv2.rectangle(image, (0, 0), (639, 359), (255, 255, 255), thickness=8)
    assert cv2.imwrite(str(frame_path), image)

    result = detect_pickleball_court(
        frame_paths=[frame_path],
        output_dir=tmp_path / "output",
        analysis_id="frame-border",
        calibration_id="automatic",
        min_confidence=0.72,
        low_confidence_threshold=0.25,
        numeric_tolerance=0.000001,
        min_polygon_area_pixels=1000,
        transition_area_depth_feet=8,
        top_down_width_pixels=1000,
    )

    assert result.outcome == CourtDetectionOutcome.failed
    assert result.image_points is None
    assert result.calibration is None
