"""Automatic court detection services."""

from app.services.court_detection.automatic import (
    AutomaticCourtDetectionResult,
    RecognitionFramesUnavailableError,
    detect_pickleball_court,
)

__all__ = [
    "AutomaticCourtDetectionResult",
    "RecognitionFramesUnavailableError",
    "detect_pickleball_court",
]
