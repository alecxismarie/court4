from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analytics import AnalyticsReport
from app.schemas.calibration import CourtCalibrationReport
from app.schemas.match_iq import MatchIQReport
from app.schemas.player_candidates import PlayerCandidateCollection
from app.schemas.player_tracking import PlayerTrackingReport, TrackSummary
from app.schemas.recording_quality import RecordingQualityAssessment
from app.schemas.video import VideoMetadataReport


class AnalysisStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class AnalysisStage(StrEnum):
    uploaded = "uploaded"
    inspected = "inspected"
    calibrated = "calibrated"
    tracked = "tracked"
    player_selected = "player_selected"
    analyzed = "analyzed"


class CourtDetectionOutcome(StrEnum):
    detected = "detected"
    low_confidence = "low_confidence"
    failed = "failed"


class ApiErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    error: ApiErrorDetail


class AnalysisArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    url: str
    content_type: str
    size_bytes: int = Field(ge=0)


class CalibrationPointRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float
    y: float


class DetectedCourtCorners(BaseModel):
    model_config = ConfigDict(frozen=True)

    near_left: CalibrationPointRequest
    near_right: CalibrationPointRequest
    far_right: CalibrationPointRequest
    far_left: CalibrationPointRequest


class AnalysisJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    status: AnalysisStatus
    current_stage: AnalysisStage
    source_video: str | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    inspection_completed: bool = False
    calibration_completed: bool = False
    tracking_completed: bool = False
    player_selected: bool = False
    analytics_completed: bool = False
    manual_calibration_required: bool = False
    court_detection_status: CourtDetectionOutcome | None = None
    court_detection_confidence: float | None = Field(default=None, ge=0, le=1)
    court_detection_selected_frame: str | None = None
    court_detection_detected_corners: DetectedCourtCorners | None = None
    upload_preflight: RecordingQualityAssessment | None = None
    analysis_readiness: RecordingQualityAssessment | None = None
    available_artifacts: list[AnalysisArtifact] = Field(default_factory=list)


class AnalysisJobResponse(AnalysisJob):
    model_config = ConfigDict(frozen=True)


class SampledFrameArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame_number: int = Field(ge=1)
    path: str
    url: str
    content_type: str
    size_bytes: int = Field(ge=0)


class SampledFramesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    frames: list[SampledFrameArtifact]


class CalibrationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    calibration_id: str | None = Field(default=None, description="Optional calibration ID.")
    source_frame: str = Field(
        description="Artifact-relative sampled frame path, such as frames/frame_000001.jpg."
    )
    near_left: CalibrationPointRequest
    near_right: CalibrationPointRequest
    far_right: CalibrationPointRequest
    far_left: CalibrationPointRequest

    @field_validator("source_frame")
    @classmethod
    def validate_source_frame(cls, value: str) -> str:
        return _validate_relative_artifact_path(value)


class CalibrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    calibration: CourtCalibrationReport
    artifacts: list[AnalysisArtifact]
    job: AnalysisJobResponse


class CourtDetectionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    status: CourtDetectionOutcome
    confidence: float = Field(ge=0, le=1)
    selected_frame: str | None
    detected_corners: DetectedCourtCorners | None
    manual_calibration_required: bool
    calibration: CourtCalibrationReport | None
    artifacts: list[AnalysisArtifact]
    job: AnalysisJobResponse


class TrackingBackend(StrEnum):
    controlled_json = "controlled-json"
    ultralytics = "ultralytics"


class TrackingRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    calibration_id: str
    backend: TrackingBackend
    detections_jsonl: str | None = Field(
        default=None,
        description="Artifact-relative JSONL path for the controlled backend.",
    )
    model_path: str | None = Field(
        default=None,
        description="Optional model path restricted to the configured model directory.",
    )
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    frame_interval: int | None = Field(default=None, ge=1)

    @field_validator("detections_jsonl", "model_path")
    @classmethod
    def validate_optional_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_relative_artifact_path(value)


class TrackingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    tracking: PlayerTrackingReport
    artifacts: list[AnalysisArtifact]
    job: AnalysisJobResponse
    player_candidates: PlayerCandidateCollection | None = None


class PlayerSelectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)


class PlayersResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    track_summaries: list[TrackSummary]
    player_selection_artifact: AnalysisArtifact | None
    selected_player_track_id: int | None


class PlayerSelectionResponse(PlayersResponse):
    model_config = ConfigDict(frozen=True)

    job: AnalysisJobResponse


class AnalyticsGenerationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    analytics: AnalyticsReport
    match_iq: MatchIQReport | None = None
    artifacts: list[AnalysisArtifact]
    job: AnalysisJobResponse


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    analytics: AnalyticsReport
    match_iq: MatchIQReport | None = None


class UploadVideoResponse(AnalysisJobResponse):
    model_config = ConfigDict(frozen=True)


class DuplicateUploadActions(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_existing: bool = True
    reanalyze: bool = True


class DuplicateUploadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["duplicate"] = "duplicate"
    duplicate_type: Literal["exact"] = "exact"
    existing_analysis_id: str
    uploaded_at: datetime
    actions: DuplicateUploadActions = Field(default_factory=DuplicateUploadActions)


UploadAnalysisResponse = UploadVideoResponse | DuplicateUploadResponse


class InspectionMetadataResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    metadata: VideoMetadataReport


def _validate_relative_artifact_path(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("Path cannot be empty.")
    path = PurePosixPath(cleaned)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Path must be relative to the analysis directory.")
    return path.as_posix()
