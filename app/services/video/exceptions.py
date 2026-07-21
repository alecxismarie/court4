class VideoInspectionError(Exception):
    """Base exception for expected video inspection failures."""


class VideoValidationError(VideoInspectionError):
    """Raised when a video path or option fails validation."""


class VideoFileNotFoundError(VideoValidationError):
    """Raised when the requested video file does not exist."""


class UnsupportedVideoExtensionError(VideoValidationError):
    """Raised when a video extension is not allowed."""


class VideoFileTooLargeError(VideoValidationError):
    """Raised when a video exceeds the configured size limit."""


class VideoOpenError(VideoInspectionError):
    """Raised when OpenCV cannot open a video."""


class VideoMetadataError(VideoInspectionError):
    """Raised when usable video metadata cannot be read."""


class FrameSamplingError(VideoInspectionError):
    """Raised when sampled frames cannot be saved."""


class OutputDirectoryExistsError(VideoInspectionError):
    """Raised when the analysis output directory already exists."""
