from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.recording_quality import RecordingQualityAssessment


class CandidateQuality(StrEnum):
    strong = "STRONG"
    usable = "USABLE"
    uncertain = "UNCERTAIN"
    rejected = "REJECTED"


class CandidateReviewStatus(StrEnum):
    pending = "PENDING"
    selected = "SELECTED"
    rejected = "REJECTED"
    merged = "MERGED"


class CourtSide(StrEnum):
    near = "NEAR"
    far = "FAR"
    mixed = "MIXED"
    unknown = "UNKNOWN"


class RecordingSuitabilityStatus(StrEnum):
    suitable = "SUITABLE"
    limited = "LIMITED"
    unsuitable = "UNSUITABLE"


class AverageBoundingBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    width_pixels: float = Field(ge=0)
    height_pixels: float = Field(ge=0)
    area_ratio: float = Field(ge=0, le=1)


class AutomaticMergeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_track_id: int = Field(ge=0)
    to_track_id: int = Field(ge=0)
    temporal_gap_seconds: float = Field(ge=0)
    endpoint_distance_feet: float = Field(ge=0)
    required_speed_feet_per_second: float = Field(ge=0)
    bounding_box_area_ratio: float = Field(ge=1)
    appearance_similarity: float | None = Field(default=None, ge=0, le=1)
    court_side_consistent: bool
    reasons: list[str]


class CandidatePreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_seconds: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    full_frame_artifact: str | None = None
    crop_artifact: str | None = None


class PlayerCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    source_raw_track_ids: list[int]
    first_observed_timestamp: float = Field(ge=0)
    last_observed_timestamp: float = Field(ge=0)
    total_observed_duration: float = Field(ge=0)
    total_observed_frames: int = Field(ge=0)
    court_distance_feet: float = Field(default=0, ge=0)
    court_movement_rate_feet_per_second: float = Field(default=0, ge=0)
    in_court_observation_ratio: float = Field(ge=0, le=1)
    selection_eligible: bool = True
    selection_exclusion_reasons: list[str] = Field(default_factory=list)
    representative_frame: int | None = Field(default=None, ge=0)
    representative_crop_artifact: str | None = None
    representative_full_frame_artifact: str | None = None
    preview_frames: list[CandidatePreview] = Field(default_factory=list)
    average_bounding_box: AverageBoundingBox
    court_side_estimate: CourtSide
    quality: CandidateQuality
    quality_reasons: list[str]
    warnings: list[str]
    automatic_merge_evidence: list[AutomaticMergeEvidence]
    review_status: CandidateReviewStatus = CandidateReviewStatus.pending
    rejection_reason: str | None = None
    manual_merge_id: str | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "PlayerCandidate":
        if not self.source_raw_track_ids:
            raise ValueError("A player candidate must contain at least one raw track.")
        if len(set(self.source_raw_track_ids)) != len(self.source_raw_track_ids):
            raise ValueError("A raw track may occur only once in a player candidate.")
        if self.last_observed_timestamp < self.first_observed_timestamp:
            raise ValueError("Candidate timestamps are out of order.")
        if not self.selection_eligible and not self.selection_exclusion_reasons:
            raise ValueError("An ineligible candidate must include an exclusion reason.")
        return self


class ManualMergeDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    merge_id: str
    source_candidate_ids: list[str]
    source_raw_track_ids: list[int]
    merged_candidate_id: str
    active: bool
    created_at: datetime
    undone_at: datetime | None = None


class RecordingSuitability(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RecordingSuitabilityStatus
    reasons: list[str]
    guidance: list[str]
    orientation: str
    detected_people: int = Field(ge=0)
    usable_candidate_count: int = Field(ge=0)


class CandidateBuildPerformance(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_build_seconds: float = Field(ge=0)
    preview_generation_seconds: float = Field(ge=0)


class PlayerCandidateCollection(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=2, ge=1)
    analysis_id: str
    candidates: list[PlayerCandidate]
    excluded_candidates: list[PlayerCandidate]
    selected_candidate_id: str | None = None
    manual_merge_decisions: list[ManualMergeDecision] = Field(default_factory=list)
    recording_suitability: RecordingSuitability
    analysis_readiness: RecordingQualityAssessment | None = None
    performance: CandidateBuildPerformance
    generated_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_unique_membership(self) -> "PlayerCandidateCollection":
        active_tracks: set[int] = set()
        active_ids: set[str] = set()
        for candidate in [*self.candidates, *self.excluded_candidates]:
            if candidate.candidate_id in active_ids:
                raise ValueError("Candidate IDs must be unique.")
            active_ids.add(candidate.candidate_id)
            for track_id in candidate.source_raw_track_ids:
                if track_id in active_tracks:
                    raise ValueError("A raw track may belong to only one active candidate.")
                active_tracks.add(track_id)
        if self.selected_candidate_id is not None and self.selected_candidate_id not in active_ids:
            raise ValueError("Selected candidate does not exist.")
        return self


class CandidateSelectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)


class CandidateRejectRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = "not_a_player"


class CandidateMergeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_ids: list[str]

    @model_validator(mode="after")
    def validate_ids(self) -> "CandidateMergeRequest":
        if len(self.candidate_ids) != 2 or len(set(self.candidate_ids)) != 2:
            raise ValueError("Exactly two distinct candidates are required.")
        return self


class CandidateUnmergeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
