from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StageExecutionState(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    stale = "stale"
    unavailable = "unavailable"


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: UUID | None = None
    storage_key: str
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    schema_version: int | None = Field(default=None, ge=1)


class StageProvenance(BaseModel):
    """Canonical provenance for a CV stage; unavailable facts remain explicit nulls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    stage_name: str
    stage_version: str
    detector_name: str | None = None
    detector_version: str | None = None
    model_identifier: str | None = None
    model_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    tracker_name: str | None = None
    tracker_version: str | None = None
    confidence_threshold: float | None = Field(default=None, ge=0, le=1)
    interpolation_policy_version: str | None = None
    source_video_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    court_calibration_artifact_checksum: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    calibration_schema_version: int | None = Field(default=None, ge=1)
    software_commit: str | None = None
    build_id: str | None = None
    environment: str | None = None
    effective_configuration: dict[str, Any]
    configuration_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_schema_version: int = Field(ge=1)


class StageExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    owner_user_id: UUID
    analysis_id: str
    analysis_run_id: UUID
    stage_type: str
    attempt_number: int = Field(ge=1)
    state: StageExecutionState
    row_version: int = Field(ge=1)
    is_optional: bool
    shadow_mode: bool
    configuration_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance: StageProvenance
    input_artifacts: list[ArtifactReference]
    output_artifacts: list[ArtifactReference]
    failure_category: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    cancelled_at: datetime | None = None
    stale_at: datetime | None = None
    unavailable_at: datetime | None = None
