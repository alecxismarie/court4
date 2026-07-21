class TrackingError(Exception):
    """Base exception for expected player-tracking failures."""


class TrackingVideoNotFoundError(TrackingError):
    """Raised when the source video is missing."""


class TrackingVideoReadError(TrackingError):
    """Raised when OpenCV cannot read the source video."""


class CalibrationReportNotFoundError(TrackingError):
    """Raised when the calibration report is missing."""


class CalibrationReportReadError(TrackingError):
    """Raised when the calibration report cannot be parsed."""


class DetectorUnavailableError(TrackingError):
    """Raised when the configured detector or model is unavailable."""


class TrackingConfigurationError(TrackingError):
    """Raised when tracking settings are invalid."""


class TrackingOutputExistsError(TrackingError):
    """Raised when the tracking output directory already exists."""


class PlayerSelectionError(TrackingError):
    """Base exception for manual player selection failures."""


class UnknownTrackSelectionError(PlayerSelectionError):
    """Raised when the requested track ID does not exist."""


class IneligibleTrackSelectionError(PlayerSelectionError):
    """Raised when the requested track is not eligible for selection."""
