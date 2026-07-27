from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictReadinessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadinessDataStatus(StrEnum):
    current = "CURRENT"
    stale = "STALE"
    missing = "MISSING"
    invalid = "INVALID"


class ReadinessVerdict(StrEnum):
    not_ready = "NOT_READY"
    collecting_evidence = "COLLECTING_EVIDENCE"
    ready_for_policy_review = "READY_FOR_POLICY_REVIEW"
    ready_for_phase_1_6b = "READY_FOR_PHASE_1_6B"


class MetricAvailability(StrEnum):
    available = "AVAILABLE"
    provisional = "PROVISIONAL"
    not_reviewed = "NOT_REVIEWED"
    not_available = "NOT_AVAILABLE"
    stale = "STALE"


class DeterministicHashStatus(StrEnum):
    match = "MATCH"
    changed = "CHANGED"
    not_verified = "NOT_VERIFIED"


class ReadinessSourceStatus(StrictReadinessModel):
    manifest: ReadinessDataStatus
    report: ReadinessDataStatus
    integrity: ReadinessDataStatus
    governance: ReadinessDataStatus
    overall: ReadinessDataStatus
    messages: list[str] = Field(default_factory=list)


class DatasetOverview(StrictReadinessModel):
    total_samples: int = Field(ge=0)
    development_count: int = Field(ge=0)
    validation_count: int = Field(ge=0)
    holdout_count: int = Field(ge=0)
    reviewed_samples: int = Field(ge=0)
    partially_reviewed_samples: int = Field(ge=0)
    unreviewed_samples: int = Field(ge=0)
    last_evaluation_timestamp: datetime | None = None
    manifest_schema_version: int | None = Field(default=None, ge=1)
    manifest_version: str | None = None
    report_schema_version: int | None = Field(default=None, ge=1)


class BalanceReadinessItem(StrictReadinessModel):
    category: str
    counts: dict[str, int]
    represented: list[str]
    missing: list[str]
    underrepresented: list[str]


class DatasetBalanceReadiness(StrictReadinessModel):
    categories: list[BalanceReadinessItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ArtifactReadinessItem(StrictReadinessModel):
    readiness: str
    count: int = Field(ge=0)
    sample_ids: list[str] = Field(default_factory=list)


class ReviewCompletionItem(StrictReadinessModel):
    key: str
    label: str
    reviewed_samples: int = Field(ge=0)
    total_samples: int = Field(ge=0)
    reviewed_items: int = Field(ge=0)
    reviewed_seconds: float | None = Field(default=None, ge=0)
    availability: MetricAvailability


class DashboardMetric(StrictReadinessModel):
    key: str
    label: str
    numerator: float | None = Field(default=None, ge=0)
    denominator: float | None = Field(default=None, ge=0)
    percentage: float | None = Field(default=None, ge=0, le=100)
    raw_count: int | None = Field(default=None, ge=0)
    availability: MetricAvailability
    note: str | None = None


class ActivePlayReadinessSummary(StrictReadinessModel):
    shadow_mode: Literal[True] = True
    policy_version: str | None = None
    generated_intervals: int = Field(ge=0)
    reviewed_intervals: int = Field(ge=0)
    reviewed_duration_seconds: float = Field(ge=0)
    likely_active_seconds: float = Field(ge=0)
    likely_idle_seconds: float = Field(ge=0)
    unknown_seconds: float = Field(ge=0)
    false_active: DashboardMetric
    false_idle: DashboardMetric
    boundary_error: DashboardMetric
    abstention_rate: DashboardMetric
    coverage_rate: DashboardMetric
    current_schema_sample_count: int = Field(ge=0)
    stale_artifact_sample_count: int = Field(ge=0)


class DisagreementReadinessItem(StrictReadinessModel):
    category: str
    label: str
    count: int | None = Field(default=None, ge=0)
    sample_ids: list[str] = Field(default_factory=list)
    availability: MetricAvailability


class UnresolvedReadinessItem(StrictReadinessModel):
    sample_id: str
    category: str
    reason: str


class PolicySafetySummary(StrictReadinessModel):
    recording_policy_version: str
    active_play_policy_version: str
    readiness_policy_version: str
    recording_policy_immutable: bool
    active_play_policy_immutable: bool
    policies_frozen_for_review: bool
    threshold_simulations_exist: bool
    holdout_protection_enabled: bool
    production_thresholds_unchanged: bool | None = None
    reviewer_labels_unchanged: bool | None = None
    deterministic_report_status: DeterministicHashStatus
    calibration_report_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    false_active_budget_approved: bool
    false_idle_budget_approved: bool


class ReadinessDecision(StrictReadinessModel):
    verdict: ReadinessVerdict
    explanation: str
    reasons: list[str]
    blockers: list[str]
    warnings: list[str]
    satisfied_criteria: list[str]
    recommended_actions: list[str]
    policy_version: str


class CalibrationReadinessSummary(StrictReadinessModel):
    schema_version: Literal[1] = 1
    internal_only: Literal[True] = True
    read_only: Literal[True] = True
    source_status: ReadinessSourceStatus
    dataset: DatasetOverview
    balance: DatasetBalanceReadiness
    artifact_readiness: list[ArtifactReadinessItem]
    review_completion: list[ReviewCompletionItem]
    calibration_outcomes: list[DashboardMetric]
    active_play: ActivePlayReadinessSummary
    disagreements: list[DisagreementReadinessItem]
    unresolved_items: list[UnresolvedReadinessItem]
    policy_safety: PolicySafetySummary
    readiness: ReadinessDecision


class CalibrationReadinessGovernance(StrictReadinessModel):
    schema_version: Literal[1] = 1
    readiness_policy_version: str
    recording_policy_review_frozen: bool = False
    active_play_policy_review_frozen: bool = False
    false_active_budget_approved: bool = False
    false_idle_budget_approved: bool = False
    notes: list[str] = Field(default_factory=list)


class CalibrationReadinessIntegrity(StrictReadinessModel):
    schema_version: Literal[1] = 1
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    recording_policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    active_play_policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    calibration_results_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    calibration_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    disagreements_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    deterministic_report_status: DeterministicHashStatus
    verified_at: datetime
