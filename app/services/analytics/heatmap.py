from collections.abc import Sequence
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.analytics import TimelinePosition
from app.services.analytics.exceptions import AnalyticsError
from app.services.analytics.trajectory import ImageArray, base_court_canvas, court_to_pixel

HeatArray = NDArray[np.float32]


def write_heatmap_image(
    *,
    positions: Sequence[TimelinePosition],
    output_path: Path,
    image_width_pixels: int,
) -> None:
    court = base_court_canvas(image_width_pixels=image_width_pixels)
    heat: HeatArray = np.zeros(court.shape[:2], dtype=np.float32)
    for position in positions:
        cv2.circle(
            heat,
            court_to_pixel((position.x, position.y), court),
            radius=max(6, image_width_pixels // 40),
            color=1.0,
            thickness=-1,
        )

    if np.max(heat) > 0:
        blurred = cast(
            HeatArray,
            cv2.GaussianBlur(heat, (0, 0), sigmaX=max(5, image_width_pixels / 80)),
        )
        max_heat = float(np.max(blurred))
        heat_uint8 = np.clip((blurred / max_heat) * 255.0, 0, 255).astype(np.uint8)
        colored = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_JET)
        mask = heat_uint8 > 0
        court[mask] = cv2.addWeighted(court, 0.45, colored, 0.55, 0)[mask]

    if not cv2.imwrite(str(output_path), cast(ImageArray, court)):
        raise AnalyticsError(f"OpenCV could not write heatmap image: {output_path}")
