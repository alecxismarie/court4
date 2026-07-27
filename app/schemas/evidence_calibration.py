from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.active_play import ActivePlayState

CALIBRATION_MANIFEST_SCHEMA_VERSION = 2
MINIMUM_RECOMMENDED_SAMPLE_SIZE = 5


class StrictCalibrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CalibrationQualityLabel(StrEnum):
    excellent = "EXCELLENT"
    good = "GOOD"
    limited = "LIMITED"
    unsuitable = "UNSUITABLE"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class ExpectedInsightEligibility(StrEnum):
    normal = "NORMAL"
    cautious = "CAUTIOUS"
    measurement_only = "MEASUREMENT_ONLY"
    insufficient_evidence = "INSUFFICIENT_EVIDENCE"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class ReviewStatus(StrEnum):
    not_reviewed = "NOT_REVIEWED"
    partially_reviewed = "PARTIALLY_REVIEWED"
    reviewed = "REVIEWED"


class ReviewerConfidence(StrEnum):
    low = "LOW"
    moderate = "MODERATE"
    high = "HIGH"


class RecordingOrientation(StrEnum):
    landscape = "LANDSCAPE"
    vertical = "VERTICAL"
    square = "SQUARE"
    unknown = "UNKNOWN"


class CourtVisibility(StrEnum):
    full = "FULL"
    partial = "PARTIAL"
    not_visible = "NOT_VISIBLE"
    unknown = "UNKNOWN"


class SeverityLabel(StrEnum):
    none = "NONE"
    minor = "MINOR"
    moderate = "MODERATE"
    severe = "SEVERE"
    unknown = "UNKNOWN"


class ReviewValue(StrEnum):
    yes = "YES"
    no = "NO"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class DatasetSplit(StrEnum):
    development = "DEVELOPMENT"
    validation = "VALIDATION"
    holdout = "HOLDOUT"


class RecordingEnvironment(StrEnum):
    indoor = "INDOOR"
    outdoor = "OUTDOOR"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class MatchFormat(StrEnum):
    singles = "SINGLES"
    doubles = "DOUBLES"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class CameraPositionLabel(StrEnum):
    baseline = "BASELINE"
    diagonal = "DIAGONAL"
    sideline = "SIDELINE"
    elevated = "ELEVATED"
    other = "OTHER"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class CameraDistanceLabel(StrEnum):
    near = "NEAR"
    medium = "MEDIUM"
    distant = "DISTANT"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class LightingCondition(StrEnum):
    bright = "BRIGHT"
    adequate = "ADEQUATE"
    dim = "DIM"
    uneven = "UNEVEN"
    backlit = "BACKLIT"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class RecordingStability(StrEnum):
    stable = "STABLE"
    mostly_stable = "MOSTLY_STABLE"
    unstable = "UNSTABLE"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class CandidateRole(StrEnum):
    court_player = "COURT_PLAYER"
    spectator = "SPECTATOR"
    duplicate = "DUPLICATE"
    uncertain = "UNCERTAIN"
    false_detection = "FALSE_DETECTION"
    not_reviewed = "NOT_REVIEWED"


class ContinuityLabel(StrEnum):
    acceptable = "ACCEPTABLE"
    broken = "BROKEN"
    unknown = "UNKNOWN"
    not_reviewed = "NOT_REVIEWED"


class ArtifactReadiness(StrEnum):
    ready = "READY"
    legacy_compatible = "LEGACY_COMPATIBLE"
    partial = "PARTIAL"
    incompatible = "INCOMPATIBLE"
    missing = "MISSING"


class DisagreementCategory(StrEnum):
    recording_assessment = "RECORDING_ASSESSMENT"
    court_detection = "COURT_DETECTION"
    candidate_association = "CANDIDATE_ASSOCIATION"
    tracking_continuity = "TRACKING_CONTINUITY"
    measurement = "MEASUREMENT"
    insight_gating = "INSIGHT_GATING"
    wording = "WORDING"
    active_play = "ACTIVE_PLAY"
    incomplete_annotation = "INCOMPLETE_ANNOTATION"


class SampleResolution(StrictCalibrationModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ArtifactReuseReferences(StrictCalibrationModel):
    artifact_root: str = "data/output"
    inspection_analysis_id: str | None = None
    court_analysis_id: str | None = None
    tracking_analysis_id: str | None = None
    candidates_analysis_id: str | None = None
    analytics_analysis_id: str | None = None
    match_iq_analysis_id: str | None = None
    active_play_analysis_id: str | None = None
    inference_run_id: str | None = None
    reuse_notes: str | None = None

    @field_validator("artifact_root")
    @classmethod
    def validate_artifact_root(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator(
        "inspection_analysis_id",
        "court_analysis_id",
        "tracking_analysis_id",
        "candidates_analysis_id",
        "analytics_analysis_id",
        "match_iq_analysis_id",
        "active_play_analysis_id",
    )
    @classmethod
    def validate_analysis_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 64:
            raise ValueError("Analysis IDs must contain between 1 and 64 characters.")
        if not cleaned[0].isalnum() or any(
            not (character.isalnum() or character in {"_", "-"}) for character in cleaned
        ):
            raise ValueError(
                "Analysis IDs may contain only letters, numbers, underscores, and hyphens."
            )
        return cleaned

    @model_validator(mode="after")
    def require_reference(self) -> "ArtifactReuseReferences":
        analysis_ids = (
            self.inspection_analysis_id,
            self.court_analysis_id,
            self.tracking_analysis_id,
            self.candidates_analysis_id,
            self.analytics_analysis_id,
            self.match_iq_analysis_id,
            self.active_play_analysis_id,
        )
        if not any(analysis_ids):
            raise ValueError("At least one reusable analysis ID is required.")
        return self


class RecordingReview(StrictCalibrationModel):
    full_court_visible: bool | None = None
    camera_stable: bool | None = None
    players_large_enough: bool | None = None
    obstruction_severity: SeverityLabel | None = None
    recording_quality_verdict: CalibrationQualityLabel = CalibrationQualityLabel.not_reviewed
    notes: str | None = None
    reviewer_confidence: ReviewerConfidence | None = None


class StableRealPlayer(StrictCalibrationModel):
    player_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    display_label: str | None = None
    notes: str | None = None


class CandidatePlayerMapping(StrictCalibrationModel):
    candidate_id: str
    player_id: str | None = None
    role: CandidateRole = CandidateRole.not_reviewed
    mapping_correct: ReviewValue = ReviewValue.not_reviewed
    notes: str | None = None

    @model_validator(mode="after")
    def require_player_for_player_role(self) -> "CandidatePlayerMapping":
        if (
            self.role in {CandidateRole.court_player, CandidateRole.duplicate}
            and not self.player_id
        ):
            raise ValueError("Court-player and duplicate mappings require a player_id.")
        return self


class PlayerCandidateReview(StrictCalibrationModel):
    expected_court_player_count: int | None = Field(default=None, ge=0)
    expected_players_represented: int | None = Field(default=None, ge=0)
    duplicate_candidates: int | None = Field(default=None, ge=0)
    missed_players: int | None = Field(default=None, ge=0)
    spectators_incorrectly_promoted: int | None = Field(default=None, ge=0)
    selected_player_identity_correct: bool | None = None
    stable_real_players: list[StableRealPlayer] = Field(default_factory=list)
    candidate_mappings: list[CandidatePlayerMapping] = Field(default_factory=list)
    selected_player_id: str | None = None
    selected_candidate_id: str | None = None
    notes: str | None = None
    reviewer_confidence: ReviewerConfidence | None = None

    @model_validator(mode="after")
    def validate_player_counts(self) -> "PlayerCandidateReview":
        if (
            self.expected_court_player_count is not None
            and self.expected_players_represented is not None
            and self.expected_players_represented > self.expected_court_player_count
        ):
            raise ValueError("Expected represented players cannot exceed expected court players.")
        player_ids = [player.player_id for player in self.stable_real_players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("Stable real-player IDs must be unique within a sample.")
        candidate_ids = [mapping.candidate_id for mapping in self.candidate_mappings]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("Candidate IDs may appear only once in candidate mappings.")
        known_players = set(player_ids)
        for mapping in self.candidate_mappings:
            if mapping.player_id is not None and mapping.player_id not in known_players:
                raise ValueError(
                    f"Candidate mapping references unknown player_id: {mapping.player_id}."
                )
        if self.selected_player_id is not None and self.selected_player_id not in known_players:
            raise ValueError("Selected player ID must reference a stable real player.")
        return self


class TrackingReviewInterval(StrictCalibrationModel):
    start_time_seconds: float = Field(ge=0)
    end_time_seconds: float = Field(gt=0)
    expected_player_id: str
    candidate_id: str | None = None
    identity_correct: ReviewValue = ReviewValue.not_reviewed
    continuity: ContinuityLabel = ContinuityLabel.not_reviewed
    occlusion: ReviewValue = ReviewValue.not_reviewed
    player_outside_frame: ReviewValue = ReviewValue.not_reviewed
    tracking_gap: ReviewValue = ReviewValue.not_reviewed
    observed_time_agreement: ReviewValue = ReviewValue.not_reviewed
    gap_label_agreement: ReviewValue = ReviewValue.not_reviewed
    uncertain_interval: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "TrackingReviewInterval":
        if self.end_time_seconds <= self.start_time_seconds:
            raise ValueError("Tracking interval end time must be after start time.")
        return self


class TrackingReview(StrictCalibrationModel):
    continuity_acceptable: bool | None = None
    fragmentation_severity: SeverityLabel | None = None
    excessive_gaps: bool | None = None
    observed_gameplay_coverage_acceptable: bool | None = None
    intervals: list[TrackingReviewInterval] = Field(default_factory=list)
    notes: str | None = None
    reviewer_confidence: ReviewerConfidence | None = None

    @model_validator(mode="after")
    def reject_overlapping_player_intervals(self) -> "TrackingReview":
        by_player: dict[str, list[TrackingReviewInterval]] = {}
        for interval in self.intervals:
            by_player.setdefault(interval.expected_player_id, []).append(interval)
        for player_id, intervals in by_player.items():
            ordered = sorted(intervals, key=lambda item: item.start_time_seconds)
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if current.start_time_seconds < previous.end_time_seconds:
                    raise ValueError(f"Tracking intervals overlap for expected player {player_id}.")
        return self


class ExpectedActivePlayState(StrEnum):
    likely_active = "LIKELY_ACTIVE"
    likely_idle = "LIKELY_IDLE"
    uncertain = "UNCERTAIN"
    not_reviewed = "NOT_REVIEWED"


class ActivePlayReviewInterval(StrictCalibrationModel):
    start_time_seconds: float = Field(ge=0)
    end_time_seconds: float = Field(gt=0)
    expected_state: ExpectedActivePlayState = ExpectedActivePlayState.not_reviewed
    boundary_tolerance_seconds: float = Field(default=0.5, ge=0)
    court4_state: ActivePlayState | None = None
    court4_start_time_seconds: float | None = Field(default=None, ge=0)
    court4_end_time_seconds: float | None = Field(default=None, gt=0)
    reviewer_confidence: ReviewerConfidence | None = None
    false_active: bool | None = None
    false_idle: bool | None = None
    unknown_but_reviewable: bool | None = None
    uncertain_human_label: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "ActivePlayReviewInterval":
        if self.end_time_seconds <= self.start_time_seconds:
            raise ValueError("Active Play review interval end time must be after start time.")
        if (self.court4_start_time_seconds is None) != (self.court4_end_time_seconds is None):
            raise ValueError("Court4 interval boundaries must be supplied together.")
        if (
            self.court4_start_time_seconds is not None
            and self.court4_end_time_seconds is not None
            and self.court4_end_time_seconds <= self.court4_start_time_seconds
        ):
            raise ValueError("Court4 interval end time must be after start time.")
        return self


class ActivePlayReview(StrictCalibrationModel):
    intervals: list[ActivePlayReviewInterval] = Field(default_factory=list)
    notes: str | None = None
    reviewer_confidence: ReviewerConfidence | None = None

    @model_validator(mode="after")
    def reject_overlapping_intervals(self) -> "ActivePlayReview":
        ordered = sorted(self.intervals, key=lambda item: item.start_time_seconds)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_time_seconds < previous.end_time_seconds:
                raise ValueError("Active Play review intervals must not overlap.")
        return self


class GeneratedInsightReview(StrictCalibrationModel):
    insight_id: str
    measurement_correct: ReviewValue = ReviewValue.not_reviewed
    interpretation_justified: ReviewValue = ReviewValue.not_reviewed
    confidence_appropriate: ReviewValue = ReviewValue.not_reviewed
    limitation_accurate: ReviewValue = ReviewValue.not_reviewed
    action_conservative: ReviewValue = ReviewValue.not_reviewed
    wording_understandable: ReviewValue = ReviewValue.not_reviewed
    expected_gate_result: ExpectedInsightEligibility = ExpectedInsightEligibility.not_reviewed
    notes: str | None = None


class InsightReview(StrictCalibrationModel):
    recording_quality_verdict_correct: bool | None = None
    confidence_levels_justified: bool | None = None
    measurement_only_decision_correct: bool | None = None
    suppression_decision_correct: bool | None = None
    interpretation_justified: bool | None = None
    limitations_accurate: bool | None = None
    wording_understandable: bool | None = None
    action_appropriately_conservative: bool | None = None
    recording_guidance_accurate: bool | None = None
    generated_insights: list[GeneratedInsightReview] = Field(default_factory=list)
    notes: str | None = None
    reviewer_confidence: ReviewerConfidence | None = None

    @model_validator(mode="after")
    def validate_unique_insights(self) -> "InsightReview":
        insight_ids = [insight.insight_id for insight in self.generated_insights]
        if len(insight_ids) != len(set(insight_ids)):
            raise ValueError("Generated insight IDs must be unique within a sample.")
        return self


class HumanReview(StrictCalibrationModel):
    recording: RecordingReview | None = None
    player_candidates: PlayerCandidateReview | None = None
    tracking: TrackingReview | None = None
    active_play: ActivePlayReview | None = None
    insight: InsightReview | None = None


class CalibrationSample(StrictCalibrationModel):
    sample_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    dataset_split: DatasetSplit = DatasetSplit.development
    video_reference: str | None = None
    external_video_reference: str | None = None
    local_video_reference: str | None = None
    recording_environment: str | None = None
    environment_type: RecordingEnvironment = RecordingEnvironment.not_reviewed
    match_format: MatchFormat = MatchFormat.not_reviewed
    orientation: RecordingOrientation | None = None
    resolution: SampleResolution | None = None
    fps: float | None = Field(default=None, gt=0)
    camera_position: str | None = None
    camera_position_label: CameraPositionLabel = CameraPositionLabel.not_reviewed
    camera_distance: CameraDistanceLabel = CameraDistanceLabel.not_reviewed
    lighting_condition: LightingCondition = LightingCondition.not_reviewed
    recording_stability: RecordingStability = RecordingStability.not_reviewed
    court_visibility: CourtVisibility | None = None
    expected_players_on_court: int | None = Field(default=None, ge=0)
    known_spectators_or_irrelevant_detections: list[str] = Field(default_factory=list)
    expected_recording_quality: CalibrationQualityLabel = CalibrationQualityLabel.not_reviewed
    expected_insight_eligibility: ExpectedInsightEligibility = (
        ExpectedInsightEligibility.not_reviewed
    )
    reviewer_notes: str | None = None
    review_status: ReviewStatus = ReviewStatus.not_reviewed
    reviewer_confidence: ReviewerConfidence | None = None
    artifacts: ArtifactReuseReferences
    human_review: HumanReview | None = None

    @field_validator("video_reference")
    @classmethod
    def validate_video_reference(cls, value: str | None) -> str | None:
        return _validate_relative_path(value) if value is not None else None

    @field_validator("local_video_reference")
    @classmethod
    def validate_local_video_reference(cls, value: str | None) -> str | None:
        return _validate_relative_path(value) if value is not None else None


class ThresholdSimulation(StrictCalibrationModel):
    threshold: str
    proposed_value: float = Field(ge=0)
    rationale: str
    exploratory: bool = True


class CalibrationManifest(StrictCalibrationModel):
    schema_version: Literal[1, 2] = 1
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    dataset_version: str
    description: str | None = None
    reference_time: datetime
    minimum_recommended_sample_size: int = Field(
        default=MINIMUM_RECOMMENDED_SAMPLE_SIZE,
        ge=1,
    )
    threshold_simulations: list[ThresholdSimulation] = Field(default_factory=list)
    active_play_threshold_simulations: list[ThresholdSimulation] = Field(default_factory=list)
    samples: list[CalibrationSample]

    @model_validator(mode="after")
    def validate_unique_samples(self) -> "CalibrationManifest":
        sample_ids = [sample.sample_id for sample in self.samples]
        if not sample_ids:
            raise ValueError("A calibration manifest must contain at least one sample.")
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("Calibration sample IDs must be unique.")
        return self


class ArtifactEvaluationStatus(StrEnum):
    available = "AVAILABLE"
    missing = "MISSING"
    stale = "STALE"
    not_referenced = "NOT_REFERENCED"
    invalid = "INVALID"


class ArtifactEvaluation(StrictCalibrationModel):
    artifact: str
    reference: str | None
    status: ArtifactEvaluationStatus
    schema_or_engine_version: str | None = None
    expected_version: str | None = None
    compatibility: ArtifactReadiness = ArtifactReadiness.ready
    message: str


class SampleEvaluationStatus(StrEnum):
    evaluated = "EVALUATED"
    partial = "PARTIAL"
    failed = "FAILED"


class SampleCalibrationResult(StrictCalibrationModel):
    sample_id: str
    status: SampleEvaluationStatus
    review_status: ReviewStatus
    system_recording_quality: CalibrationQualityLabel | None = None
    expected_recording_quality: CalibrationQualityLabel
    recording_quality_delta: int | None = None
    exact_quality_agreement: bool | None = None
    acceptable_quality_agreement: bool | None = None
    system_insight_eligibility: ExpectedInsightEligibility | None = None
    expected_insight_eligibility: ExpectedInsightEligibility
    insight_eligibility_agreement: bool | None = None
    candidate_count: int | None = None
    selectable_candidate_count: int | None = None
    selected_candidate_id: str | None = None
    active_play_generated: bool = False
    active_play_policy_version: str | None = None
    active_play_interval_count: int = Field(default=0, ge=0)
    active_play_candidate_schema_version: int | None = Field(default=None, ge=1)
    active_play_state_seconds: dict[str, float] = Field(default_factory=dict)
    active_play_unknown_coverage: float | None = Field(default=None, ge=0, le=1)
    artifacts: list[ArtifactEvaluation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    inference_recomputed: bool = False
    artifact_readiness: ArtifactReadiness = ArtifactReadiness.missing


class CountMetric(StrictCalibrationModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
    provisional: bool
    note: str | None = None


class RecordingQualityMetrics(StrictCalibrationModel):
    exact_agreement: CountMetric
    acceptable_agreement: CountMetric
    overestimation_count: int = Field(ge=0)
    underestimation_count: int = Field(ge=0)
    confusion_matrix: dict[str, dict[str, int]]
    per_expected_status_count: dict[str, int]


class EvidenceGateMetrics(StrictCalibrationModel):
    valid_insights_correctly_allowed: CountMetric
    weak_insights_correctly_measurement_only: CountMetric
    unsuitable_insights_correctly_suppressed: CountMetric
    valid_insights_incorrectly_suppressed: int = Field(ge=0)
    weak_insights_incorrectly_allowed: int = Field(ge=0)
    unsuitable_insights_incorrectly_allowed: int = Field(ge=0)


class CandidateReliabilityMetrics(StrictCalibrationModel):
    expected_player_recall: CountMetric
    duplicate_candidate_count: int | None = Field(default=None, ge=0)
    missed_player_count: int | None = Field(default=None, ge=0)
    spectator_promotion_count: int | None = Field(default=None, ge=0)
    selected_player_identity_accuracy: CountMetric
    candidate_precision: CountMetric
    candidate_to_player_mapping_accuracy: CountMetric
    duplicate_candidates_per_sample: CountMetric
    missed_players_per_sample: CountMetric
    labeled_sample_counts: dict[str, int]


class TrackingContinuityMetrics(StrictCalibrationModel):
    reviewed_interval_count: int = Field(ge=0)
    correctly_maintained_identity_intervals: CountMetric
    identity_switch_intervals: int = Field(ge=0)
    fragmented_intervals: int = Field(ge=0)
    valid_observed_time_agreement: CountMetric
    gap_label_agreement: CountMetric


class DurationMetric(StrictCalibrationModel):
    seconds: float = Field(ge=0)
    interval_count: int = Field(ge=0)


class DurationRateMetric(StrictCalibrationModel):
    numerator_seconds: float = Field(ge=0)
    denominator_seconds: float = Field(ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
    interval_count: int = Field(ge=0)
    provisional: bool = True
    note: str | None = None


class BoundaryErrorMetric(StrictCalibrationModel):
    boundary_count: int = Field(ge=0)
    mean_absolute_seconds: float | None = Field(default=None, ge=0)
    maximum_absolute_seconds: float | None = Field(default=None, ge=0)
    within_tolerance_count: int = Field(ge=0)


class ActivePlayCalibrationMetrics(StrictCalibrationModel):
    reviewed_duration: DurationMetric
    likely_active_agreement: DurationRateMetric
    likely_idle_agreement: DurationRateMetric
    false_active: DurationMetric
    false_idle: DurationMetric
    unknown: DurationMetric
    boundary_error: BoundaryErrorMetric
    abstention_rate: DurationRateMetric
    coverage_rate: DurationRateMetric


class InsightIntegrityMetrics(StrictCalibrationModel):
    fields: dict[str, CountMetric]


class ThresholdSimulationResult(StrictCalibrationModel):
    threshold: str
    current_value: float
    proposed_value: float
    affected_samples: list[str]
    improvements: list[str]
    regressions: list[str]
    unchanged_samples: int = Field(ge=0)
    excluded_samples: list[str] = Field(default_factory=list)
    exploratory: bool = True
    remaining_uncertainty: str


class BalanceCategoryResult(StrictCalibrationModel):
    category: str
    counts: dict[str, int]
    represented: list[str]
    missing: list[str]
    underrepresented: list[str]


class DatasetBalanceSummary(StrictCalibrationModel):
    sample_count: int = Field(ge=0)
    recommended_minimum_samples: int = Field(ge=1)
    recommended_maximum_samples: int = Field(ge=1)
    minimum_per_category: int = Field(ge=1)
    categories: list[BalanceCategoryResult]
    provisional_warnings: list[str]


class CalibrationDisagreement(StrictCalibrationModel):
    sample_id: str
    category: DisagreementCategory
    court4_output: str
    human_expectation: str
    artifact_evidence: list[str]
    reason: str
    affected_threshold_or_rule: str | None = None


class CalibrationMetrics(StrictCalibrationModel):
    recording_quality: RecordingQualityMetrics
    evidence_gates: EvidenceGateMetrics
    candidate_reliability: CandidateReliabilityMetrics
    tracking_continuity: TrackingContinuityMetrics
    active_play: ActivePlayCalibrationMetrics
    insight_integrity: InsightIntegrityMetrics


class CalibrationResults(StrictCalibrationModel):
    schema_version: Literal[2] = 2
    dataset_id: str
    dataset_version: str
    manifest_sha256: str
    recording_policy_version: str | None = None
    recording_policy_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    active_play_policy_version: str | None = None
    active_play_policy_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    generated_at: datetime
    expensive_recomputation_enabled: bool
    expensive_inference_runs: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    reviewed_sample_count: int = Field(ge=0)
    unreviewed_sample_count: int = Field(ge=0)
    samples: list[SampleCalibrationResult]
    metrics: CalibrationMetrics
    common_failure_reasons: dict[str, int]
    policy_error_reasons: dict[str, dict[str, int]]
    dataset_balance: DatasetBalanceSummary
    disagreements: list[CalibrationDisagreement]
    threshold_analysis: list[ThresholdSimulationResult]
    active_play_threshold_analysis: list[ThresholdSimulationResult]
    samples_requiring_manual_review: list[str]
    dataset_limitations: list[str]


def _validate_relative_path(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    if not cleaned:
        raise ValueError("Path cannot be empty.")
    if cleaned.startswith("/") or (len(cleaned) >= 2 and cleaned[1] == ":"):
        raise ValueError("Paths must be repository-relative.")
    parts = cleaned.split("/")
    if ".." in parts:
        raise ValueError("Paths cannot leave the repository.")
    return "/".join(part for part in parts if part not in {"", "."})
