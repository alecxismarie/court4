from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config.settings import Settings
from app.persistence.service import (
    ArtifactInput,
    PersistenceService,
    StageExecutionResult,
    stage_artifact_prefix,
)
from app.schemas.calibration import CalibrationVerificationRecord, CourtCalibrationReport
from app.schemas.stage_execution import ArtifactReference, StageProvenance
from app.services.ball_tracking.detector import (
    OpenCVBallDetectorConfig,
    OpenCVColorMotionBallDetector,
)
from app.services.ball_tracking.pipeline import (
    BallPipelineConfig,
    BallPipelineResult,
    ExperimentalBallPipeline,
)
from app.services.ball_tracking.tracker import TemporalBallTracker, TemporalBallTrackerConfig
from app.services.ball_tracking.visualization import BallVisualizationError
from app.services.stages.configuration import (
    effective_stage_configuration,
    stage_configuration_fingerprint,
)
from app.services.video.frame_source import FrameSourceError


class BallTrackingDisabledError(RuntimeError):
    pass


class BallStageExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class BallStageRunResult:
    stage: StageExecutionResult
    pipeline: BallPipelineResult | None


class BallShadowStageService:
    """Internal-only, optional experimental ball evidence stage."""

    STAGE_TYPE = "ball_tracking"
    STAGE_VERSION = "experimental-ball-evidence-v1"

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
        effective_configuration = self._effective_configuration(request_overrides)
        fingerprint = stage_configuration_fingerprint(effective_configuration)
        provenance = StageProvenance(
            stage_name=self.STAGE_TYPE,
            stage_version=self.STAGE_VERSION,
            detector_name=OpenCVColorMotionBallDetector.name,
            detector_version=OpenCVColorMotionBallDetector.version,
            model_identifier=None,
            model_sha256=None,
            tracker_name=TemporalBallTracker.name,
            tracker_version=TemporalBallTracker.version,
            confidence_threshold=float(
                effective_configuration["detector"]["acceptance_confidence"]
            ),
            interpolation_policy_version=TemporalBallTracker.interpolation_policy_version,
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

    def run_for_analysis(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        analysis_run_id: UUID,
        video_path: Path,
        analysis_output_dir: Path,
        source_video_checksum: str | None,
        input_artifacts: list[ArtifactReference],
        request_overrides: Mapping[str, Any] | None = None,
        calibration: CourtCalibrationReport | None = None,
        calibration_verification: CalibrationVerificationRecord | None = None,
        court_calibration_artifact_checksum: str | None = None,
    ) -> BallStageRunResult:
        stage = self.start_for_analysis(
            owner_user_id=owner_user_id,
            analysis_id=analysis_id,
            analysis_run_id=analysis_run_id,
            source_video_checksum=source_video_checksum,
            input_artifacts=input_artifacts,
            request_overrides=request_overrides,
            court_calibration_artifact_checksum=court_calibration_artifact_checksum,
            calibration_schema_version=calibration.schema_version if calibration else None,
        )
        if not stage.created:
            return BallStageRunResult(stage=stage, pipeline=None)

        effective_configuration = self._effective_configuration(request_overrides)
        provenance = self._provenance(
            effective_configuration=effective_configuration,
            source_video_checksum=source_video_checksum,
            court_calibration_artifact_checksum=court_calibration_artifact_checksum,
            calibration_schema_version=calibration.schema_version if calibration else None,
        )
        detector = OpenCVColorMotionBallDetector(
            OpenCVBallDetectorConfig(**effective_configuration["detector"])
        )
        tracker = TemporalBallTracker(
            TemporalBallTrackerConfig(**effective_configuration["tracker"])
        )
        pipeline = ExperimentalBallPipeline(
            detector=detector,
            tracker=tracker,
            config=BallPipelineConfig(
                max_processed_frames=int(effective_configuration["max_processed_frames"]),
                minimum_observations=int(effective_configuration["minimum_observations"]),
            ),
        )
        prefix = stage_artifact_prefix(self.STAGE_TYPE, stage.attempt_number)
        output_dir = analysis_output_dir.joinpath(*prefix.rstrip("/").split("/"))
        try:
            pipeline_result = pipeline.run(
                video_path=video_path,
                output_dir=output_dir,
                analysis_id=analysis_id,
                stage_attempt=stage.attempt_number,
                storage_prefix=prefix,
                provenance=provenance,
                calibration=calibration,
                calibration_verification=calibration_verification,
                calibration_checksum_sha256=court_calibration_artifact_checksum,
            )
            self._persistence.register_stage_artifacts(
                owner_user_id=owner_user_id,
                stage_execution_id=stage.stage_execution_id,
                artifacts=[
                    ArtifactInput(
                        storage_key=f"{prefix}{artifact.path.name}",
                        content_type=artifact.content_type,
                        size_bytes=artifact.path.stat().st_size,
                        checksum_sha256=self._file_sha256(artifact.path),
                        artifact_kind=artifact.kind.value,
                        schema_version=artifact.schema_version,
                    )
                    for artifact in pipeline_result.artifacts
                ],
            )
            completed = self._persistence.transition_stage_execution(
                owner_user_id=owner_user_id,
                stage_execution_id=stage.stage_execution_id,
                expected_row_version=stage.row_version,
                new_state="completed",
            )
            return BallStageRunResult(stage=completed, pipeline=pipeline_result)
        except Exception as error:
            self._persistence.transition_stage_execution(
                owner_user_id=owner_user_id,
                stage_execution_id=stage.stage_execution_id,
                expected_row_version=stage.row_version,
                new_state="failed",
                failure_category=self._failure_category(error),
            )
            raise BallStageExecutionError("Experimental ball stage failed safely.") from error

    def _effective_configuration(
        self, request_overrides: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        validated_overrides = self._validate_overrides(request_overrides)
        return effective_stage_configuration(
            {
                "mode": "shadow",
                "stage_version": self.STAGE_VERSION,
                "detector": OpenCVBallDetectorConfig().as_dict(),
                "tracker": TemporalBallTrackerConfig().as_dict(),
                "max_processed_frames": BallPipelineConfig().max_processed_frames,
                "minimum_observations": BallPipelineConfig().minimum_observations,
            },
            validated_overrides,
        )

    @staticmethod
    def _validate_overrides(
        request_overrides: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if request_overrides is None:
            return None
        allowed_scalar = {"max_processed_frames", "minimum_observations"}
        allowed_nested = {
            "detector": set(OpenCVBallDetectorConfig().as_dict()),
            "tracker": set(TemporalBallTrackerConfig().as_dict()),
        }
        unknown_top_level = set(request_overrides) - allowed_scalar - set(allowed_nested)
        if unknown_top_level:
            raise ValueError("Unknown experimental ball-stage configuration override.")
        for section, allowed_keys in allowed_nested.items():
            value = request_overrides.get(section)
            if value is None:
                continue
            if not isinstance(value, Mapping) or set(value) - allowed_keys:
                raise ValueError(f"Invalid {section} configuration override.")
        return request_overrides

    def _provenance(
        self,
        *,
        effective_configuration: dict[str, Any],
        source_video_checksum: str | None,
        court_calibration_artifact_checksum: str | None,
        calibration_schema_version: int | None,
    ) -> StageProvenance:
        return StageProvenance(
            stage_name=self.STAGE_TYPE,
            stage_version=self.STAGE_VERSION,
            detector_name=OpenCVColorMotionBallDetector.name,
            detector_version=OpenCVColorMotionBallDetector.version,
            model_identifier=None,
            model_sha256=None,
            tracker_name=TemporalBallTracker.name,
            tracker_version=TemporalBallTracker.version,
            confidence_threshold=float(
                effective_configuration["detector"]["acceptance_confidence"]
            ),
            interpolation_policy_version=TemporalBallTracker.interpolation_policy_version,
            source_video_checksum=source_video_checksum,
            court_calibration_artifact_checksum=court_calibration_artifact_checksum,
            calibration_schema_version=calibration_schema_version,
            software_commit=self._settings.software_commit_identifier,
            build_id=self._settings.deployment_build_identifier,
            environment=self._settings.environment,
            effective_configuration=effective_configuration,
            configuration_fingerprint=stage_configuration_fingerprint(effective_configuration),
            output_schema_version=1,
        )

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _failure_category(error: Exception) -> str:
        if isinstance(error, FrameSourceError | FileNotFoundError):
            return "unsupported_video"
        if isinstance(error, BallVisualizationError):
            return "artifact_render_failed"
        if isinstance(error, FileExistsError):
            return "attempt_output_conflict"
        return "ball_analysis_failed"
