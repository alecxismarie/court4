"""Player tracking backends and exceptions."""

from app.services.tracking.exceptions import (
    CalibrationReportNotFoundError,
    CalibrationReportReadError,
    DetectorUnavailableError,
    IneligibleTrackSelectionError,
    PlayerSelectionError,
    TrackingConfigurationError,
    TrackingError,
    TrackingOutputExistsError,
    TrackingVideoNotFoundError,
    TrackingVideoReadError,
    UnknownTrackSelectionError,
)
from app.services.tracking.json_tracking_backend import JsonTrackingBackend
from app.services.tracking.ultralytics_bytetrack_backend import UltralyticsByteTrackBackend

__all__ = [
    "CalibrationReportNotFoundError",
    "CalibrationReportReadError",
    "DetectorUnavailableError",
    "IneligibleTrackSelectionError",
    "JsonTrackingBackend",
    "PlayerSelectionError",
    "TrackingConfigurationError",
    "TrackingError",
    "TrackingOutputExistsError",
    "TrackingVideoNotFoundError",
    "TrackingVideoReadError",
    "UltralyticsByteTrackBackend",
    "UnknownTrackSelectionError",
]
