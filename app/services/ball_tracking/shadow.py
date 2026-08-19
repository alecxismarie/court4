from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.config.settings import Settings
from app.persistence.service import PersistenceService, StageExecutionResult
from app.schemas.stage_execution import ArtifactReference, StageProvenance
from app.services.stages.configuration import (
    effective_stage_configuration,
    stage_configuration_fingerprint,
)


class BallTrackingDisabledError(RuntimeError):
    pass


class BallShadowStageService:
    """Internal-only boundary for a future explicitly selected ball-stage invocation."""

    STAGE_TYPE = "ball_tracking"
    STAGE_VERSION = "ball-evidence-foundation-v1"

    def __init__(self, *, persistence: PersistenceService, settings: Settings) -> None:
        self._persistence = persistence
        self._settings = settings

    def start_for_analysis(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        analysis_run_id: UUID,
        source_video_checksum: str | None,
        input_artifacts: list[ArtifactReference],
        request_overrides: Mapping[str, Any] | None = None,
        court_calibration_artifact_checksum: str | None = None,
        calibration_schema_version: int | None = None,
    ) -> StageExecutionResult:
        if not self._settings.ball_tracking_enabled:
            raise BallTrackingDisabledError("Ball tracking is disabled.")
        effective_configuration = effective_stage_configuration(
            {
                "mode": "shadow",
                "stage_version": self.STAGE_VERSION,
            },
            request_overrides,
        )
        fingerprint = stage_configuration_fingerprint(effective_configuration)
        provenance = StageProvenance(
            stage_name=self.STAGE_TYPE,
            stage_version=self.STAGE_VERSION,
            detector_name=None,
            detector_version=None,
            model_identifier=None,
            model_sha256=None,
            tracker_name=None,
            tracker_version=None,
            confidence_threshold=None,
            interpolation_policy_version=None,
            source_video_checksum=source_video_checksum,
            court_calibration_artifact_checksum=court_calibration_artifact_checksum,
            calibration_schema_version=calibration_schema_version,
            software_commit=self._settings.software_commit_identifier,
            build_id=self._settings.deployment_build_identifier,
            environment=self._settings.environment,
            effective_configuration=effective_configuration,
            configuration_fingerprint=fingerprint,
            output_schema_version=1,
        )
        return self._persistence.start_stage_execution(
            owner_user_id=owner_user_id,
            analysis_id=analysis_id,
            analysis_run_id=analysis_run_id,
            stage_type=self.STAGE_TYPE,
            configuration_fingerprint=fingerprint,
            provenance_payload=provenance.model_dump(mode="json"),
            input_artifact_references=[
                reference.model_dump(mode="json") for reference in input_artifacts
            ],
            state="processing",
            is_optional=True,
            shadow_mode=True,
        )
