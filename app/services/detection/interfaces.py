from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.schemas.player_tracking import TrackedPersonDetection

ImageArray = NDArray[np.uint8]


class PersonDetectionBackend(Protocol):
    @property
    def model_name(self) -> str: ...

    def track_frame(
        self,
        frame: ImageArray,
        *,
        frame_index: int,
        timestamp_seconds: float,
    ) -> Sequence[TrackedPersonDetection]: ...

    def close(self) -> None: ...
