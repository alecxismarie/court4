from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ACTIVE_PLAY_SCHEMA_VERSION = 1
ACTIVE_PLAY_POLICY_VERSION = "active-play-v1"


class StrictActivePlayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActivePlayState(StrEnum):
    likely_active = "LIKELY_ACTIVE"
    likely_idle = "LIKELY_IDLE"
    unknown = "UNKNOWN"


class ActivePlayConfidence(StrEnum):
    high = "HIGH"
    moderate = "MODERATE"
    low = "LOW"
    not_available = "NOT_AVAILABLE"


class VisibilityQuality(StrEnum):
    high = "HIGH"
    moderate = "MODERATE"
    low = "LOW"
    not_available = "NOT_AVAILABLE"


class TrackingGapSeverity(StrEnum):
    none = "NONE"
    minor = "MINOR"
    severe = "SEVERE"


class CandidateContinuityQuality(StrEnum):
    strong = "STRONG"
    limited = "LIMITED"
    poor = "POOR"
    not_available = "NOT_AVAILABLE"


class ActivePlayReasonCode(StrEnum):
    sufficient_tracked_coverage = "SUFFICIENT_TRACKED_COVERAGE"
    sustained_multi_player_movement = "SUSTAINED_MULTI_PLAYER_MOVEMENT"
    simultaneous_movement = "SIMULTANEOUS_MOVEMENT"
    meaningful_direction_changes = "MEANINGFUL_DIRECTION_CHANGES"
    stationary_player_with_active_peers = "STATIONARY_PLAYER_WITH_ACTIVE_PEERS"
    sustained_low_movement = "SUSTAINED_LOW_MOVEMENT"
    stable_low_activity = "STABLE_LOW_ACTIVITY"
    casual_low_intensity_movement = "CASUAL_LOW_INTENSITY_MOVEMENT"
    kitchen_low_movement_safeguard = "KITCHEN_LOW_MOVEMENT_SAFEGUARD"
    insufficient_tracked_coverage = "INSUFFICIENT_TRACKED_COVERAGE"
    insufficient_reliable_players = "INSUFFICIENT_RELIABLE_PLAYERS"
    one_player_only = "ONE_PLAYER_ONLY"
    tracking_gap = "TRACKING_GAP"
    severe_tracking_gaps = "SEVERE_TRACKING_GAPS"
    fragmented_candidates = "FRAGMENTED_CANDIDATES"
    unsuitable_recording = "UNSUITABLE_RECORDING"
    stale_source_artifact = "STALE_SOURCE_ARTIFACT"
    short_context = "SHORT_CONTEXT"
    conflicting_evidence = "CONFLICTING_EVIDENCE"
    no_observations = "NO_OBSERVATIONS"


class ActivePlayCoverage(StrictActivePlayModel):
    observed_seconds: float = Field(ge=0)
    window_seconds: float = Field(gt=0)
    observed_ratio: float = Field(ge=0, le=1)
    visible_player_count: int = Field(ge=0)
    reliable_player_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_coverage(self) -> "ActivePlayCoverage":
        if self.observed_seconds > self.window_seconds + 1e-6:
            raise ValueError("Observed time cannot exceed window time.")
        expected_ratio = self.observed_seconds / self.window_seconds
        if abs(expected_ratio - self.observed_ratio) > 1e-5:
            raise ValueError("Observed ratio must match observed and window seconds.")
        if self.reliable_player_count > self.visible_player_count:
            raise ValueError("Reliable player count cannot exceed visible player count.")
        return self


class ActivePlaySignals(StrictActivePlayModel):
    smoothed_speed_feet_per_second: float = Field(ge=0)
    speed_change_feet_per_second_squared: float = Field(ge=0)
    movement_intensity: float = Field(ge=0, le=1)
    direction_changes_per_second: float = Field(ge=0)
    mean_stationary_seconds_per_player: float = Field(ge=0)
    low_movement_kitchen_player_count: int = Field(ge=0)
    moving_player_count: int = Field(ge=0)
    simultaneous_movement: bool
    simultaneous_movement_seconds: float = Field(ge=0)
    visibility_quality: VisibilityQuality
    tracking_gap_severity: TrackingGapSeverity
    candidate_continuity: CandidateContinuityQuality


class ActivePlayLineage(StrictActivePlayModel):
    candidate_ids: list[str] = Field(default_factory=list)
    source_raw_track_ids: list[int] = Field(default_factory=list)


class ActivePlayEstimate(StrictActivePlayModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    state: ActivePlayState
    confidence: ActivePlayConfidence
    coverage: ActivePlayCoverage
    signals: ActivePlaySignals
    reason_codes: list[ActivePlayReasonCode]
    limitations: list[str]
    lineage: ActivePlayLineage
    policy_version: str = ACTIVE_PLAY_POLICY_VERSION

    @model_validator(mode="after")
    def validate_interval(self) -> "ActivePlayEstimate":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Active Play interval end must be after start.")
        if abs((self.end_seconds - self.start_seconds) - self.coverage.window_seconds) > 1e-5:
            raise ValueError("Coverage window duration must match interval duration.")
        if not self.reason_codes:
            raise ValueError("Every Active Play estimate requires at least one reason.")
        if not self.limitations:
            raise ValueError("Every Active Play estimate requires at least one limitation.")
        return self


class MotionFeatureWindow(StrictActivePlayModel):
    """Time-window motion evidence before policy classification."""

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    coverage: ActivePlayCoverage
    signals: ActivePlaySignals
    evidence_reason_codes: list[ActivePlayReasonCode]
    lineage: ActivePlayLineage
    policy_version: str = ACTIVE_PLAY_POLICY_VERSION

    @model_validator(mode="after")
    def validate_window(self) -> "MotionFeatureWindow":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Motion feature window end must be after start.")
        if abs((self.end_seconds - self.start_seconds) - self.coverage.window_seconds) > 1e-5:
            raise ValueError("Coverage window duration must match feature window duration.")
        return self


class ActivePlayWindow(ActivePlayEstimate):
    """Classified time window retained for traceability."""


class ActivePlayInterval(ActivePlayEstimate):
    source_window_count: int = Field(ge=1)


class ActivePlaySourceArtifacts(StrictActivePlayModel):
    tracking_report: str
    observations: str
    player_candidates: str
    tracking_schema_version: str = "UNVERSIONED"
    observations_schema_version: str = "UNVERSIONED"
    tracking_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observations_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidates_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_schema_version: int = Field(ge=1)


class ActivePlayArtifacts(StrictActivePlayModel):
    report_json: str
    features_jsonl: str
    windows_jsonl: str


class ActivePlaySummary(StrictActivePlayModel):
    source_duration_seconds: float = Field(ge=0)
    likely_active_seconds: float = Field(ge=0)
    likely_idle_seconds: float = Field(ge=0)
    unknown_seconds: float = Field(ge=0)
    classifiable_seconds: float = Field(ge=0)
    classifiable_ratio: float = Field(ge=0, le=1)
    interval_count: int = Field(ge=0)
    window_count: int = Field(ge=0)
    confidence_distribution: dict[ActivePlayConfidence, int]
    reason_distribution: dict[ActivePlayReasonCode, int]


class ActivePlayReport(StrictActivePlayModel):
    schema_version: Literal[1] = 1
    analysis_id: str
    policy_version: str = ACTIVE_PLAY_POLICY_VERSION
    shadow_mode: Literal[True] = True
    validated: Literal[False] = False
    source_artifacts: ActivePlaySourceArtifacts
    summary: ActivePlaySummary
    windows: list[ActivePlayWindow]
    intervals: list[ActivePlayInterval]
    artifacts: ActivePlayArtifacts
    limitations: list[str]
    created_at: datetime

    @model_validator(mode="after")
    def validate_report(self) -> "ActivePlayReport":
        if len(self.windows) != self.summary.window_count:
            raise ValueError("Active Play window count does not match the summary.")
        if len(self.intervals) != self.summary.interval_count:
            raise ValueError("Active Play interval count does not match the summary.")
        estimates = [*self.windows, *self.intervals]
        if any(item.policy_version != self.policy_version for item in estimates):
            raise ValueError("Every Active Play estimate must use the report policy.")
        for estimates_of_kind in (self.windows, self.intervals):
            ordered = sorted(
                estimates_of_kind,
                key=lambda item: (item.start_seconds, item.end_seconds),
            )
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if current.start_seconds < previous.end_seconds - 1e-6:
                    raise ValueError("Active Play estimates must not overlap.")
        total_state_seconds = (
            self.summary.likely_active_seconds
            + self.summary.likely_idle_seconds
            + self.summary.unknown_seconds
        )
        if abs(total_state_seconds - self.summary.source_duration_seconds) > 1e-5:
            raise ValueError("Active Play state durations must cover the source duration.")
        return self
