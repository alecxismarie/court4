"""Automatic court detection services."""

from app.services.court_detection.automatic import (
    AutomaticCourtDetectionResult,
    detect_pickleball_court,
)

__all__ = ["AutomaticCourtDetectionResult", "detect_pickleball_court"]
