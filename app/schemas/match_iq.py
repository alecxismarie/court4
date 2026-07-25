from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.recording_quality import RecordingQualityAssessment

ConfidenceLevel = Literal["HIGH", "MODERATE", "LOW", "NOT_AVAILABLE"]
InsightQualityGate = Literal[
    "NORMAL",
    "CAUTIOUS",
    "MEASUREMENT_ONLY",
    "INSUFFICIENT_EVIDENCE",
]


class MatchIQConfidenceRating(BaseModel):
    model_config = ConfigDict(frozen=True)

    level: ConfidenceLevel
    rationale: str


class MatchIQConfidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    recording: MatchIQConfidenceRating
    tracking: MatchIQConfidenceRating
    measurement: MatchIQConfidenceRating
    interpretation: MatchIQConfidenceRating
    recommendation: MatchIQConfidenceRating


class MatchIQMetricEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    label: str
    value: float | int | str
    formatted_value: str
    threshold: str


class MatchIQInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    rule_id: str
    priority: int = Field(ge=0)
    title: str
    statement: str
    evidence: list[MatchIQMetricEvidence]
    observation: str = ""
    confidence: MatchIQConfidence | None = None
    interpretation: str | None = None
    limitations: list[str] = Field(default_factory=list)
    action: str | None = None
    quality_gate: InsightQualityGate = "MEASUREMENT_ONLY"


class MatchIQFocusRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    statement: str
    supporting_insight_ids: list[str]


class MatchIQReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_id: str
    status: Literal["generated", "insufficient_data"]
    engine_version: str
    summary: str
    insights: list[MatchIQInsight]
    focus: MatchIQFocusRecommendation | None
    limitations: list[str]
    metrics_used: list[str]
    quality_gate: InsightQualityGate = "MEASUREMENT_ONLY"
    confidence: MatchIQConfidence | None = None
    recording_quality: RecordingQualityAssessment | None = None
    created_at: datetime
