from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.player_candidates import RecordingSuitability
from app.schemas.recording_quality import RecordingQualityAssessment


class VideoMetadataReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    filename: str
    file_size_bytes: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    frame_count: int = Field(gt=0)
    duration_seconds: float = Field(gt=0)
    codec: str | None
    sample_interval_seconds: float = Field(gt=0)
    sampled_frames: int = Field(ge=0)
    rotation_degrees: int = 0
    recording_suitability: RecordingSuitability | None = None
    upload_preflight: RecordingQualityAssessment | None = None
    created_at: datetime
