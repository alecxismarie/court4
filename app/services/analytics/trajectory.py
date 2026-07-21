from collections.abc import Sequence
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.schemas.analytics import TimelinePosition
from app.services.analytics.exceptions import AnalyticsError
from app.sports.pickleball.geometry import REGULATION_COURT, Point2D

ImageArray = NDArray[np.uint8]


def write_trajectory_image(
    *,
    positions: Sequence[TimelinePosition],
    output_path: Path,
    image_width_pixels: int,
) -> None:
    image = base_court_canvas(image_width_pixels=image_width_pixels)
    if positions:
        pixel_points = [_court_to_pixel((position.x, position.y), image) for position in positions]
        for first, second in zip(pixel_points, pixel_points[1:], strict=False):
            cv2.line(image, first, second, (40, 90, 220), thickness=3)
        cv2.circle(image, pixel_points[0], 9, (0, 170, 0), thickness=-1)
        cv2.circle(image, pixel_points[-1], 9, (0, 0, 220), thickness=-1)
        _draw_label(image, "start", (pixel_points[0][0] + 10, pixel_points[0][1] - 8))
        _draw_label(image, "end", (pixel_points[-1][0] + 10, pixel_points[-1][1] - 8))

    if not cv2.imwrite(str(output_path), image):
        raise AnalyticsError(f"OpenCV could not write trajectory image: {output_path}")


def base_court_canvas(*, image_width_pixels: int) -> ImageArray:
    court = REGULATION_COURT
    margin = max(24, int(round(image_width_pixels * 0.04)))
    court_width_pixels = image_width_pixels - margin * 2
    court_height_pixels = int(round(court_width_pixels * court.length_feet / court.width_feet))
    image_height_pixels = court_height_pixels + margin * 2
    image = np.full((image_height_pixels, image_width_pixels, 3), 250, dtype=np.uint8)

    line_color = (35, 35, 35)
    court_color = (235, 245, 235)
    top_left = (margin, margin)
    bottom_right = (margin + court_width_pixels, margin + court_height_pixels)
    cv2.rectangle(image, top_left, bottom_right, court_color, thickness=-1)
    cv2.rectangle(image, top_left, bottom_right, line_color, thickness=2)

    for y in (
        court.near_kitchen_y_feet,
        court.net_y_feet,
        court.far_kitchen_y_feet,
    ):
        start = _court_to_pixel((0.0, y), cast(ImageArray, image))
        end = _court_to_pixel((court.width_feet, y), cast(ImageArray, image))
        cv2.line(image, start, end, line_color, thickness=2)

    near_center_start = _court_to_pixel((court.center_x_feet, 0.0), cast(ImageArray, image))
    near_center_end = _court_to_pixel(
        (court.center_x_feet, court.near_kitchen_y_feet),
        cast(ImageArray, image),
    )
    far_center_start = _court_to_pixel(
        (court.center_x_feet, court.far_kitchen_y_feet),
        cast(ImageArray, image),
    )
    far_center_end = _court_to_pixel(
        (court.center_x_feet, court.length_feet),
        cast(ImageArray, image),
    )
    cv2.line(image, near_center_start, near_center_end, line_color, thickness=2)
    cv2.line(image, far_center_start, far_center_end, line_color, thickness=2)
    return cast(ImageArray, image)


def court_to_pixel(point: Point2D, image: ImageArray) -> tuple[int, int]:
    return _court_to_pixel(point, image)


def _court_to_pixel(point: Point2D, image: ImageArray) -> tuple[int, int]:
    court = REGULATION_COURT
    height, width = image.shape[:2]
    margin = max(24, int(round(width * 0.04)))
    court_width_pixels = width - margin * 2
    court_height_pixels = height - margin * 2
    x = margin + (point[0] / court.width_feet) * court_width_pixels
    y = margin + ((court.length_feet - point[1]) / court.length_feet) * court_height_pixels
    return (int(round(x)), int(round(y)))


def _draw_label(image: ImageArray, label: str, origin: tuple[int, int]) -> None:
    cv2.putText(
        image,
        label,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        thickness=3,
        lineType=cv2.LINE_AA,
    )
    cv2.putText(
        image,
        label,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        thickness=1,
        lineType=cv2.LINE_AA,
    )
