from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.stage_execution import StageProvenance


class BallObservationState(StrEnum):
    observed = "observed"
    interpolated = "interpolated"


class BallFrameDetectionState(StrEnum):
    observed = "observed"
    missing = "missing"
    frame_failed = "frame_failed"


class BallCandidateDisposition(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


class BallEvidenceStatus(StrEnum):
    available = "available"
    no_ball_detected = "no_ball_detected"
    insufficient_observations = "insufficient_observations"
    excessive_track_fragmentation = "excessive_track_fragmentation"
    analysis_failed = "analysis_failed"
    truncated = "truncated"


class BallTrackEventType(StrEnum):
    segment_started = "segment_started"
    gap_started = "gap_started"
    reacquired = "reacquired"
    segment_ended = "segment_ended"


class BallTrackSegmentStatus(StrEnum):
    candidate_trajectory = "candidate_trajectory"
    fragment = "fragment"


class CourtProjectionMethod(StrEnum):
    approximate_court_plane_projection = "approximate_court_plane_projection"


class CalibrationEvidenceState(StrEnum):
    absent = "absent"
    generated_unverified = "generated_unverified"
    verified = "verified"


class BallArtifactKind(StrEnum):
    detections = "ball_detections"
    track = "ball_track"
    tracking_report = "ball_tracking_report"
    trajectory = "ball_trajectory"
    overlay = "ball_overlay"
    review_sidecar = "ball_review_sidecar"


class BallArtifactContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: BallArtifactKind
    filename: str
    content_type: str
    schema_version: int | None = Field(default=None, ge=1)


BALL_ARTIFACT_CONTRACTS = (
    BallArtifactContract(
        kind=BallArtifactKind.detections,
        filename="detections.v1.jsonl",
        content_type="application/x-ndjson",
        schema_version=1,
    ),
    BallArtifactContract(
        kind=BallArtifactKind.track,
        filename="track.v1.jsonl",
        content_type="application/x-ndjson",
        schema_version=1,
    ),
    BallArtifactContract(
        kind=BallArtifactKind.tracking_report,
        filename="tracking-report.v1.json",
        content_type="application/json",
        schema_version=1,
    ),
    BallArtifactContract(
        kind=BallArtifactKind.trajectory,
        filename="trajectory.v1.png",
        content_type="image/png",
        schema_version=1,
    ),
    BallArtifactContract(
        kind=BallArtifactKind.overlay,
        filename="overlay.v1.mp4",
        content_type="video/mp4",
        schema_version=1,
    ),
    BallArtifactContract(
        kind=BallArtifactKind.review_sidecar,
        filename="review-sidecar.v1.json",
        content_type="application/json",
        schema_version=1,
    ),
)


class BallBoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    x1: float
    y1: float
    x2: float
    y2: float

    @model_validator(mode="after")
    def validate_order(self) -> BallBoundingBox:
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Ball bounding box must have positive width and height.")
        return self


class BallDetectionCandidate(BaseModel):
    """Auditable detector candidate; a candidate is not necessarily an observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    candidate_id: str
    image_x: float
    image_y: float
    bounding_box: BallBoundingBox
    confidence: float = Field(ge=0, le=1)
    radius_pixels: float = Field(gt=0)
    circularity: float = Field(ge=0, le=1)
    color_fill_ratio: float = Field(ge=0, le=1)
    motion_fill_ratio: float = Field(ge=0, le=1)
    disposition: BallCandidateDisposition
    rejection_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_disposition(self) -> BallDetectionCandidate:
        if self.disposition == BallCandidateDisposition.accepted and self.rejection_reasons:
            raise ValueError("Accepted candidates cannot contain rejection reasons.")
        if self.disposition == BallCandidateDisposition.rejected and not self.rejection_reasons:
            raise ValueError("Rejected candidates must contain at least one reason.")
        return self


class BallFrameDetection(BaseModel):
    """Per-frame detector output, including explicit missing and failed states."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    state: BallFrameDetectionState
    candidates: tuple[BallDetectionCandidate, ...] = ()
    accepted_candidate_id: str | None = None
    error_category: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> BallFrameDetection:
        accepted = [
            candidate
            for candidate in self.candidates
            if candidate.disposition == BallCandidateDisposition.accepted
        ]
        if self.state == BallFrameDetectionState.observed:
            if len(accepted) != 1 or self.accepted_candidate_id != accepted[0].candidate_id:
                raise ValueError(
                    "Observed frames require exactly one identified accepted candidate."
                )
        elif accepted or self.accepted_candidate_id is not None:
            raise ValueError("Missing and failed frames cannot contain an accepted candidate.")
        if self.state == BallFrameDetectionState.frame_failed and not self.error_category:
            raise ValueError("Failed frames require a safe error category.")
        if self.state != BallFrameDetectionState.frame_failed and self.error_category is not None:
            raise ValueError("Only failed frames may contain an error category.")
        return self


class BallObservation(BaseModel):
    """Version 1 evidence sample. It intentionally contains no match-event semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    image_x: float
    image_y: float
    bounding_box: BallBoundingBox | None = None
    confidence: float = Field(ge=0, le=1)
    observation_state: BallObservationState
    track_segment_id: str
    gap_length_frames: int = Field(ge=0)
    court_x: float | None = None
    court_y: float | None = None
    court_projection_method: CourtProjectionMethod | None = None
    detector_name: str | None = None
    detector_version: str | None = None
    model_identifier: str | None = None
    model_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_video_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    configuration_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    association_distance_pixels: float | None = Field(default=None, ge=0)
    inferred_from_frame_indices: tuple[int, int] | None = None

    @model_validator(mode="after")
    def distinguish_observed_and_interpolated(self) -> BallObservation:
        if self.observation_state == BallObservationState.observed and self.gap_length_frames != 0:
            raise ValueError("Observed samples must have a zero frame gap.")
        if (
            self.observation_state == BallObservationState.interpolated
            and self.gap_length_frames < 1
        ):
            raise ValueError("Interpolated samples must identify a non-zero frame gap.")
        if self.observation_state == BallObservationState.observed:
            if self.inferred_from_frame_indices is not None:
                raise ValueError("Observed samples cannot identify interpolation endpoints.")
        elif self.inferred_from_frame_indices is None:
            raise ValueError("Interpolated samples must identify their observed endpoints.")
        court_values = (self.court_x, self.court_y, self.court_projection_method)
        if any(value is not None for value in court_values) and not all(
            value is not None for value in court_values
        ):
            raise ValueError("Court projection coordinates and method must be present together.")
        return self


class BallTrackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    event_type: BallTrackEventType
    frame_index: int = Field(ge=0)
    track_segment_id: str
    gap_length_frames: int = Field(default=0, ge=0)
    detail: str | None = None


class BallTrackSegmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    track_segment_id: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    observation_count: int = Field(ge=1)
    observed_count: int = Field(ge=1)
    interpolated_count: int = Field(ge=0)
    mean_confidence: float = Field(ge=0, le=1)
    status: BallTrackSegmentStatus
    quality_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_segment(self) -> BallTrackSegmentEvidence:
        if self.end_frame < self.start_frame:
            raise ValueError("Track segment end must not precede its start.")
        if self.observation_count != self.observed_count + self.interpolated_count:
            raise ValueError("Track segment counts must reconcile.")
        if self.status == BallTrackSegmentStatus.fragment and not self.quality_reasons:
            raise ValueError("Track fragments must explain their limited status.")
        return self


class ConfidencePercentiles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    p10: float | None = Field(default=None, ge=0, le=1)
    p50: float | None = Field(default=None, ge=0, le=1)
    p90: float | None = Field(default=None, ge=0, le=1)


class ProcessingTimings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decode_seconds: float = Field(ge=0)
    detection_seconds: float = Field(ge=0)
    reconstruction_seconds: float = Field(ge=0)
    total_seconds: float = Field(ge=0)


class BallTrackingReport(BaseModel):
    """Versioned evidence-quality report with no production threshold or coaching claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    evidence_status: BallEvidenceStatus = BallEvidenceStatus.available
    quality_reasons: tuple[str, ...] = ()
    eligible_frames: int = Field(ge=0)
    processed_frames: int = Field(default=0, ge=0)
    frame_failure_count: int = Field(default=0, ge=0)
    processing_truncated: bool = False
    raw_detection_coverage: float = Field(ge=0, le=1)
    reconstructed_track_coverage: float = Field(ge=0, le=1)
    observed_frame_count: int = Field(ge=0)
    interpolated_frame_count: int = Field(ge=0)
    observed_interpolated_ratio: float | None = Field(default=None, ge=0)
    confidence_percentiles: ConfidencePercentiles
    longest_gap_frames: int = Field(ge=0)
    average_gap_frames: float = Field(ge=0)
    reacquisition_count: int = Field(ge=0)
    track_segment_count: int = Field(ge=0)
    fragmentation_rate: float = Field(ge=0)
    rejected_detection_count: int = Field(ge=0)
    impossible_motion_count: int = Field(ge=0)
    track_events: tuple[BallTrackEvent, ...] = ()
    track_segments: tuple[BallTrackSegmentEvidence, ...] = ()
    court_mapped_coverage: float = Field(ge=0, le=1)
    calibration_state: CalibrationEvidenceState
    processing_timings: ProcessingTimings
    provenance: StageProvenance

    @model_validator(mode="after")
    def validate_evidence_status(self) -> BallTrackingReport:
        if self.evidence_status != BallEvidenceStatus.available and not self.quality_reasons:
            raise ValueError("Unavailable or limited evidence must explain why.")
        if self.processing_truncated and self.evidence_status != BallEvidenceStatus.truncated:
            raise ValueError("Truncated processing must use the truncated evidence status.")
        return self


class BallReviewSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    analysis_id: str
    stage_attempt: int = Field(ge=1)
    overlay_storage_key: str | None = None
    trajectory_storage_key: str | None = None
    report_storage_key: str
    visual_states: tuple[str, ...] = (
        "observed",
        "interpolated",
        "reacquired_segment",
        "low_confidence_interval",
    )
    reviewer_state: str = "unreviewed"
    notes: str | None = None
