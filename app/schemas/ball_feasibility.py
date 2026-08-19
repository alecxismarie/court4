from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CaptureEnvironment(StrEnum):
    indoor = "indoor"
    outdoor = "outdoor"


class BallVisibilityLabel(StrEnum):
    visible = "visible"
    not_visible = "not_visible"
    uncertain = "uncertain"


class EvaluationConsentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: Literal["model_evaluation"]
    agreement_version: str
    acceptance_id: str
    accepted_at: datetime
    withdrawn_at: None = None


class FeasibilityClip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    clip_id: str
    video_path: str
    labels_path: str
    video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float = Field(ge=10, le=20)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    fixed_camera: bool
    capture_environment: CaptureEnvironment
    consent: EvaluationConsentEvidence

    @field_validator("video_path", "labels_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value.strip().replace("\\", "/"))
        if not value.strip() or path.is_absolute() or ".." in path.parts:
            raise ValueError("Feasibility paths must be dataset-relative.")
        return path.as_posix()


class BallFeasibilityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    dataset_id: str
    purpose: Literal["offline_ball_visibility_feasibility"]
    clips: list[FeasibilityClip] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def validate_unique_clips(self) -> BallFeasibilityManifest:
        clip_ids = [clip.clip_id for clip in self.clips]
        if len(set(clip_ids)) != len(clip_ids):
            raise ValueError("Feasibility clip IDs must be unique.")
        return self


class ManualBallFrameLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    visibility: BallVisibilityLabel
    center_x: float | None = None
    center_y: float | None = None

    @model_validator(mode="after")
    def validate_visible_center(self) -> ManualBallFrameLabel:
        has_center = self.center_x is not None or self.center_y is not None
        if has_center and (self.center_x is None or self.center_y is None):
            raise ValueError("Manual center coordinates must be present together.")
        if self.visibility == BallVisibilityLabel.visible and not has_center:
            raise ValueError("Visible ball labels require a manual center.")
        if self.visibility != BallVisibilityLabel.visible and has_center:
            raise ValueError("Only visible ball labels may contain a center.")
        return self
