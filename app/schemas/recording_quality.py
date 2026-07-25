from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RecordingQualityLevel(StrEnum):
    excellent = "EXCELLENT"
    good = "GOOD"
    limited = "LIMITED"
    unsuitable = "UNSUITABLE"


class QualityCheckStatus(StrEnum):
    passed = "PASSED"
    warning = "WARNING"
    failed = "FAILED"


class PreflightStage(StrEnum):
    upload = "UPLOAD_PREFLIGHT"
    analysis = "ANALYSIS_READINESS"


class QualityCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    label: str
    status: QualityCheckStatus
    message: str
    measured_value: str | None = None


class UploadQualitySignals(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: str
    orientation: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    duration_seconds: float = Field(gt=0)


class AnalysisQualitySignals(BaseModel):
    model_config = ConfigDict(frozen=True)

    court_detection_status: str | None = None
    court_detection_confidence: float | None = Field(default=None, ge=0, le=1)
    calibration_completed: bool
    detected_people: int = Field(ge=0)
    selectable_candidate_count: int = Field(ge=0)
    candidate_quality: str | None = None
    player_visibility_ratio: float | None = Field(default=None, ge=0, le=1)
    tracked_duration_seconds: float = Field(ge=0)
    unobserved_gap_seconds: float = Field(ge=0)
    tracking_gap_ratio: float = Field(ge=0, le=1)
    fragment_count: int = Field(ge=0)


class RecordingQualityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: PreflightStage
    status: RecordingQualityLevel
    passed_checks: list[QualityCheck] = Field(default_factory=list)
    warnings: list[QualityCheck] = Field(default_factory=list)
    blocking_failures: list[QualityCheck] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    guidance: list[str] = Field(default_factory=list)
    upload_signals: UploadQualitySignals | None = None
    analysis_signals: AnalysisQualitySignals | None = None
    assessed_at: datetime
