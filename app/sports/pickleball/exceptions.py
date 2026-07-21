class CourtCalibrationError(Exception):
    """Base exception for expected court calibration failures."""


class CalibrationImageNotFoundError(CourtCalibrationError):
    """Raised when the source image does not exist."""


class CalibrationImageReadError(CourtCalibrationError):
    """Raised when OpenCV cannot read the source image."""


class CalibrationPointValidationError(CourtCalibrationError):
    """Raised when supplied calibration points are invalid."""


class CalibrationGeometryError(CourtCalibrationError):
    """Raised when supplied points cannot form a usable court polygon."""


class CalibrationOutputExistsError(CourtCalibrationError):
    """Raised when the requested calibration output directory already exists."""
