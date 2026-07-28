from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recording_quality import RecordingQualityLevel


class ContributionStatus(StrEnum):
    included = "INCLUDED"
    excluded = "EXCLUDED"
    provisional = "PROVISIONAL"
    not_evaluated = "NOT_EVALUATED"


class AnalysisHistoryStatus(StrEnum):
    processing = "PROCESSING"
    ready = "READY"
    limited = "LIMITED"
    unsuitable = "UNSUITABLE"
    failed = "FAILED"
    legacy = "LEGACY"


class ContributionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ContributionStatus
    reason_codes: list[str]
    explanation: str
    policy_version: str
    evaluated_at: datetime
    source_analysis_version: str
    limitations: list[str] = Field(default_factory=list)
    source_versions: dict[str, str | None] = Field(default_factory=dict)


class AnalysisHistoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    status: AnalysisHistoryStatus
    processing_status: str
    recording_quality: RecordingQualityLevel | None
    observation_coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    reliable_observation_seconds: float | None = Field(default=None, ge=0)
    measurement_available: bool
    match_iq_available: bool
    contribution: ContributionDecision
    limitation: str | None
    report_url: str
    thumbnail_url: str | None


class AnalysisHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[AnalysisHistoryItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlayHistoryZoneSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    zone: str
    label: str
    seconds: float = Field(ge=0)
    denominator_seconds: float = Field(gt=0)
    percentage: float = Field(ge=0, le=100)
    contributing_analyses: int = Field(ge=1)


class VerifiedMatchIQSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    title: str
    created_at: datetime
    summary: str
    report_url: str


class PlayHistoryReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    explanation: str
    eligible_analyses_required: int = Field(ge=1)
    eligible_analyses_available: int = Field(ge=0)


class PlayHistoryTrendDirection(StrEnum):
    increased = "HIGHER"
    decreased = "LOWER"
    stable = "STABLE"


class ProgressEligibilityStatus(StrEnum):
    eligible = "ELIGIBLE"
    provisional = "PROVISIONAL"
    ineligible = "INELIGIBLE"
    not_evaluated = "NOT_EVALUATED"


class ProgressSourceVersions(BaseModel):
    model_config = ConfigDict(frozen=True)

    analytics_schema: str
    zone_definition: str
    court_geometry: str
    units: str
    contribution_policy: str
    match_iq_engine: str | None


class ProgressEligibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: ProgressEligibilityStatus
    reasons: list[str]
    limitations: list[str]
    source_versions: list[ProgressSourceVersions]
    policy_version: str


class PlayHistoryContributingAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    title: str
    created_at: datetime
    report_url: str
    contribution_status: ContributionStatus
    comparability: ProgressEligibilityDecision
    qualified_observation_seconds: float | None = Field(default=None, ge=0)
    qualified_movement_seconds: float | None = Field(default=None, ge=0)


class PlayHistoryComparisonGroup(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    period_start: datetime
    period_end: datetime
    analysis_count: int = Field(ge=1)
    qualified_observation_seconds: float = Field(ge=0)
    qualified_movement_seconds: float = Field(ge=0)
    analyses: list[PlayHistoryContributingAnalysis]


class PlayHistoryTrendMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    unit: str
    earlier_value: float | None = Field(default=None, ge=0)
    recent_value: float | None = Field(default=None, ge=0)
    change_value: float | None
    direction: PlayHistoryTrendDirection | None
    context: str
    aggregation_method: str
    normalization: str
    earlier_contributing_count: int = Field(ge=0)
    recent_contributing_count: int = Field(ge=0)
    earlier_qualified_observation_seconds: float = Field(ge=0)
    recent_qualified_observation_seconds: float = Field(ge=0)
    contributing_analysis_ids: list[str]
    provisional: bool
    limitations: list[str]


class PlayStyleSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    metric_key: str | None
    metric_label: str | None
    earlier_value: float | None = Field(default=None, ge=0, le=100)
    recent_value: float | None = Field(default=None, ge=0, le=100)
    unit: str
    summary: str
    qualified_analysis_count: int = Field(ge=0)
    qualified_observation_seconds: float = Field(ge=0)
    provisional: bool
    limitations: list[str]


class PlayHistoryPolicyVersions(BaseModel):
    model_config = ConfigDict(frozen=True)

    contribution: str
    comparability: str
    trend: str
    interpretation: str
    grouping: str
    aggregation: str


class PlayHistoryProgressSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    baseline_status: str
    answer: str
    explanation: str
    qualified_analysis_count: int = Field(ge=0)
    comparable_analysis_count: int = Field(ge=0)
    qualified_observation_seconds: float = Field(ge=0)
    comparison_period_start: datetime | None
    comparison_period_end: datetime | None
    provisional: bool
    limitations: list[str]
    earlier_analysis_count: int = Field(ge=0)
    recent_analysis_count: int = Field(ge=0)
    earlier_group: PlayHistoryComparisonGroup | None
    recent_group: PlayHistoryComparisonGroup | None
    trend_eligibility: ProgressEligibilityDecision
    interpretation_eligibility: ProgressEligibilityDecision
    contributing_analysis_ids: list[str]
    aggregation_methods: list[str]
    trend_metrics: list[PlayHistoryTrendMetric]
    play_style: PlayStyleSummary | None


class PlayHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str
    policy_versions: PlayHistoryPolicyVersions
    total_analyses: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    comparable_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    provisional_count: int = Field(ge=0)
    not_evaluated_count: int = Field(ge=0)
    reliable_observation_seconds: float | None = Field(default=None, ge=0)
    qualified_movement_seconds: float | None = Field(default=None, ge=0)
    most_common_zone: PlayHistoryZoneSummary | None
    latest_verified_match_iq: list[VerifiedMatchIQSummary]
    recent_eligible_analyses: list[AnalysisHistoryItem]
    contributions: list[AnalysisHistoryItem]
    comparison_candidates: list[PlayHistoryContributingAnalysis]
    readiness: PlayHistoryReadiness
    progress: PlayHistoryProgressSummary
