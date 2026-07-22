from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    created_at: datetime
