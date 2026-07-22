import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PointTuple = tuple[float, float]


class BoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float

    @field_validator("x1", "y1", "x2", "y2")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Bounding box coordinates must be finite.")
        return value

    @model_validator(mode="after")
    def validate_ordering(self) -> "BoundingBox":
        if self.x2 <= self.x1:
            raise ValueError("Bounding box x2 must be greater than x1.")
        if self.y2 <= self.y1:
            raise ValueError("Bounding box y2 must be greater than y1.")
        return self

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    def bottom_center(self) -> PointTuple:
        return ((self.x1 + self.x2) / 2.0, self.y2)

    def is_inside_image(self, image_width: int, image_height: int) -> bool:
        return self.x1 >= 0 and self.y1 >= 0 and self.x2 < image_width and self.y2 < image_height


class TrackedPersonDetection(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    bounding_box: BoundingBox
    confidence: float = Field(ge=0, le=1)


class PlayerObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    track_id: int = Field(ge=0)
    bounding_box: BoundingBox
    confidence: float = Field(ge=0, le=1)
    image_ground_point: PointTuple
    court_position: PointTuple
    inside_court: bool
    inside_extended_court: bool
    excluded_from_player_tracks: bool
    interpolated: bool = False


class TrackSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: int = Field(ge=0)
    preview_image: str | None = None
    first_frame: int = Field(ge=0)
    last_frame: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    first_timestamp_seconds: float = Field(ge=0)
    last_timestamp_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    average_confidence: float = Field(ge=0, le=1)
    court_distance_feet: float = Field(default=0, ge=0)
    court_movement_rate_feet_per_second: float = Field(default=0, ge=0)
    court_observation_count: int = Field(ge=0)
    extended_court_observation_count: int = Field(ge=0)
    inside_extended_court_ratio: float = Field(ge=0, le=1)
    eligible_for_selection: bool
    rejection_reasons: list[str]


class TrackingArtifacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    tracking_json: str
    observations_jsonl: str
    player_selection_image: str
    annotated_video: str


class TrackingPerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_duration_seconds: float = Field(ge=0)
    source_frame_count: int = Field(ge=0)
    processed_frame_count: int = Field(ge=0)
    skipped_frame_count: int = Field(ge=0)
    processing_time_seconds: float = Field(ge=0)
    average_processing_fps: float = Field(ge=0)
    detector_time_seconds: float = Field(ge=0)


class PlayerTrackingReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    source_video: str
    calibration_id: str
    model_name: str
    processed_frame_count: int = Field(ge=0)
    source_frame_count: int = Field(ge=0)
    frame_interval: int = Field(ge=1)
    track_count: int = Field(ge=0)
    eligible_player_track_ids: list[int]
    selected_player_track_id: int | None = None
    selected_player_saved_at: datetime | None = None
    court_inclusion_margin_feet: float = Field(ge=0)
    track_summaries: list[TrackSummary]
    artifacts: TrackingArtifacts
    performance: TrackingPerformanceSummary
    created_at: datetime
