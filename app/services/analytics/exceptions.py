class AnalyticsError(Exception):
    """Base exception for expected analytics failures."""


class MissingTrackingForAnalyticsError(AnalyticsError):
    """Raised when tracking inputs are missing or invalid."""


class MissingSelectedPlayerError(AnalyticsError):
    """Raised when no selected player exists in the tracking report."""


class MissingCalibrationForAnalyticsError(AnalyticsError):
    """Raised when the matching calibration report is missing or invalid."""


class NoPlayerTrajectoryError(AnalyticsError):
    """Raised when the selected player has no valid court trajectory."""


class AnalyticsOutputExistsError(AnalyticsError):
    """Raised when the analytics output directory already exists."""
