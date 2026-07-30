import hashlib
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.config.settings import Settings
from app.persistence.errors import IdempotencyConflictError, OperationInProgressError
from app.schemas.active_play import ActivePlayReport
from app.schemas.analytics import AnalyticsReport
from app.schemas.calibration import CourtCalibrationReport
from app.schemas.jobs import (
    AnalysisArtifact,
    AnalysisJob,
    AnalysisJobResponse,
    AnalysisStage,
    AnalysisStatus,
    AnalyticsGenerationResponse,
    AnalyticsResponse,
    CalibrationPointRequest,
    CalibrationRequest,
    CalibrationResponse,
    CourtDetectionOutcome,
    CourtDetectionResponse,
    DetectedCourtCorners,
    DuplicateUploadResponse,
    PlayerSelectionRequest,
    PlayerSelectionResponse,
    PlayersResponse,
    SampledFrameArtifact,
    SampledFramesResponse,
    TrackingBackend,
    TrackingRequest,
    TrackingResponse,
    UploadAnalysisResponse,
    UploadVideoResponse,
)
from app.schemas.match_iq import MatchIQReport
from app.schemas.player_candidates import PlayerCandidateCollection
from app.schemas.player_tracking import PlayerTrackingReport
from app.services.active_play import (
    ActivePlayError,
    ActivePlayNotReadyError,
    load_active_play_report,
)
from app.services.active_play import (
    generate_active_play as generate_shadow_active_play,
)
from app.services.analytics import (
    AnalyticsError,
    AnalyticsOutputExistsError,
    MissingSelectedPlayerError,
    generate_match_analytics,
)
from app.services.candidates import (
    CANDIDATE_SCHEMA_VERSION,
    CandidateError,
    CandidateImpossibleMergeError,
    build_player_candidates,
    load_player_candidates,
    merge_player_candidates,
    reject_player_candidate,
    restore_player_candidate,
    select_player_candidate,
    unmerge_player_candidates,
)
from app.services.court_detection import detect_pickleball_court
from app.services.jobs.exceptions import (
    JobConflictError,
    JobNotFoundError,
    JobRequestError,
    JobTooLargeError,
)
from app.services.jobs.repository import AnalysisJobRepository
from app.services.match_iq import (
    MATCH_IQ_FILENAME,
    MatchIQPersistenceError,
    generate_and_write_match_iq,
    load_match_iq_report,
)
from app.services.recording_quality import assess_analysis_readiness
from app.services.tracking import (
    DetectorModelMissingError,
    DetectorRuntimeUnavailableError,
    DetectorUnavailableError,
    JsonTrackingBackend,
    TrackingError,
    UltralyticsByteTrackBackend,
)
from app.services.video import VideoInspectionError, inspect_video
from app.services.video.player_analysis import (
    EligibilityConfig,
    analyze_players,
    ensure_player_preview_images,
    load_calibration_report,
    refresh_player_selection_metrics,
)
from app.services.video.player_selection import load_tracking_report, select_player_track
from app.sports.pickleball import (
    CalibrationOutputExistsError,
    CourtCalibrationError,
    calibrate_court,
)

logger = logging.getLogger(__name__)

SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
FRAME_NAME_PATTERN = re.compile(r"^frame_(\d{6})\.jpg$")


@dataclass(frozen=True)
class ArtifactFile:
    path: Path
    content_type: str


class AnalysisWorkflowService:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.repository = AnalysisJobRepository(
            output_dir=settings.analysis_output_dir,
            api_base_path=settings.api_base_path,
        )

    async def create_analysis(
        self,
        upload: UploadFile,
        *,
        idempotency_key: str | None = None,
        reanalyze: bool = False,
    ) -> UploadAnalysisResponse:
        if idempotency_key is not None and (
            not idempotency_key.strip() or len(idempotency_key) > 256
        ):
            raise JobRequestError(
                "invalid_idempotency_key",
                "Idempotency-Key must contain 1 to 256 characters.",
            )
        analysis_id = uuid4().hex
        staging_path, source_checksum, upload_size_bytes = await self._save_upload_to_staging(
            upload, analysis_id
        )
        source_video_path: Path | None = None
        now = datetime.now(tz=UTC)
        filename = upload.filename or "upload"
        request_fingerprint = hashlib.sha256(
            f"{filename}\0{source_checksum}\0reanalyze={reanalyze}".encode()
        ).hexdigest()
        initial_job = AnalysisJob(
            analysis_id=analysis_id,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.uploaded,
            created_at=now,
            updated_at=now,
        )

        try:
            try:
                reservation = self.repository.persistence.service.reserve_analysis(
                    owner_user_id=self.repository.persistence.owner_user_id,
                    analysis_id=analysis_id,
                    idempotency_key=idempotency_key or analysis_id,
                    request_fingerprint=request_fingerprint,
                    original_filename=filename,
                    content_type=upload.content_type,
                    size_bytes=upload_size_bytes,
                    source_checksum=source_checksum,
                    job_payload=initial_job.model_dump(mode="json"),
                    allow_duplicate=reanalyze,
                )
            except IdempotencyConflictError as exc:
                raise JobConflictError("idempotency_conflict", str(exc)) from exc
            except OperationInProgressError as exc:
                raise JobConflictError("operation_in_progress", str(exc)) from exc
            if reservation.duplicate is not None:
                return DuplicateUploadResponse(
                    existing_analysis_id=reservation.duplicate.existing_analysis_id,
                    uploaded_at=reservation.duplicate.uploaded_at,
                )
            if not reservation.created:
                return UploadVideoResponse.model_validate(
                    self.repository.load_job(reservation.analysis_id).model_dump(mode="json")
                )
            inspection = inspect_video(
                input_path=staging_path,
                output_dir=self.settings.analysis_output_dir,
                sample_interval_seconds=self.settings.default_sample_interval_seconds,
                supported_extensions=self.settings.supported_extensions,
                max_file_size_bytes=self.settings.max_upload_size_bytes,
                analysis_id=analysis_id,
            )
            source_video_path = self._move_upload_to_analysis(analysis_id, staging_path)
            job = AnalysisJob(
                analysis_id=analysis_id,
                status=AnalysisStatus.processing,
                current_stage=AnalysisStage.inspected,
                source_video=source_video_path.relative_to(
                    self.repository.analysis_dir(analysis_id)
                ).as_posix(),
                created_at=now,
                updated_at=datetime.now(tz=UTC),
                inspection_completed=True,
                upload_preflight=inspection.report.upload_preflight,
            )
            saved = self.repository.save_job(job)
            return UploadVideoResponse.model_validate(saved.model_dump(mode="json"))
        except VideoInspectionError as exc:
            logger.info(
                "api_video_inspection_failed",
                extra={"analysis_id": analysis_id, "error": str(exc)},
            )
            source_video_path = self._move_upload_to_analysis(analysis_id, staging_path)
            failed_job = AnalysisJob(
                analysis_id=analysis_id,
                status=AnalysisStatus.failed,
                current_stage=AnalysisStage.uploaded,
                source_video=source_video_path.relative_to(
                    self.repository.analysis_dir(analysis_id)
                ).as_posix(),
                created_at=now,
                updated_at=datetime.now(tz=UTC),
                error="Video could not be inspected.",
            )
            self.repository.save_job(failed_job)
            raise JobRequestError(
                "video_inspection_failed", "Video could not be inspected."
            ) from exc
        finally:
            self._cleanup_staging_dir(analysis_id)

    def get_job(self, analysis_id: str) -> AnalysisJobResponse:
        return AnalysisJobResponse.model_validate(
            self.repository.load_job(analysis_id).model_dump(mode="json")
        )

    def list_sampled_frames(self, analysis_id: str) -> SampledFramesResponse:
        job = self.repository.load_job(analysis_id)
        frames = []
        for artifact in job.available_artifacts:
            path = Path(artifact.path)
            if path.parent.as_posix() != "frames":
                continue
            match = FRAME_NAME_PATTERN.fullmatch(path.name)
            if match is not None:
                frames.append(
                    SampledFrameArtifact(
                        frame_number=int(match.group(1)),
                        **artifact.model_dump(),
                    )
                )
        return SampledFramesResponse(analysis_id=analysis_id, frames=frames)

    def get_artifact_file(self, analysis_id: str, artifact_path: str) -> ArtifactFile:
        self.repository.load_job(analysis_id)
        resolved = self.repository.resolve_artifact(analysis_id, artifact_path)
        if not resolved.exists() or not resolved.is_file():
            raise JobNotFoundError("Artifact not found.")
        artifact = self.repository.artifact_from_path(analysis_id, resolved)
        return ArtifactFile(path=resolved, content_type=artifact.content_type)

    def submit_calibration(
        self,
        analysis_id: str,
        request: CalibrationRequest,
    ) -> CalibrationResponse:
        job = self.repository.load_job(analysis_id)
        self._require(
            job.inspection_completed, "inspection_required", "Upload inspection is required."
        )
        source_frame = self.repository.resolve_artifact(analysis_id, request.source_frame)
        self._require_frame_artifact(source_frame, analysis_id)
        calibration_id = self._validate_output_id(
            request.calibration_id or uuid4().hex, "calibration"
        )
        calibration_path = (
            self.repository.analysis_dir(analysis_id)
            / "calibrations"
            / calibration_id
            / "calibration.json"
        )

        if calibration_path.exists():
            calibration = self._load_calibration(calibration_path)
        else:
            try:
                result = calibrate_court(
                    image_path=source_frame,
                    output_dir=self.settings.analysis_output_dir,
                    image_points=(
                        (request.near_left.x, request.near_left.y),
                        (request.near_right.x, request.near_right.y),
                        (request.far_right.x, request.far_right.y),
                        (request.far_left.x, request.far_left.y),
                    ),
                    calibration_id=calibration_id,
                    analysis_id=analysis_id,
                    numeric_tolerance=self.settings.numeric_validation_tolerance,
                    min_polygon_area_pixels=self.settings.min_calibration_polygon_area_pixels,
                    transition_area_depth_feet=self.settings.transition_area_depth_feet,
                    top_down_width_pixels=self.settings.calibration_top_down_width_pixels,
                )
                calibration = result.report
            except CalibrationOutputExistsError as exc:
                raise JobConflictError(
                    "calibration_exists",
                    "Calibration output already exists.",
                ) from exc
            except CourtCalibrationError as exc:
                self._mark_failed(job, "Calibration failed.")
                raise JobRequestError("calibration_failed", "Calibration failed.") from exc

        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.calibrated,
            error=None,
            calibration_completed=True,
            manual_calibration_required=False,
        )
        artifacts = self._artifacts_under(analysis_id, calibration_path.parent)
        return CalibrationResponse(
            analysis_id=analysis_id,
            calibration=calibration,
            artifacts=artifacts,
            job=AnalysisJobResponse.model_validate(updated.model_dump(mode="json")),
        )

    def detect_court(self, analysis_id: str) -> CourtDetectionResponse:
        job = self.repository.load_job(analysis_id)
        self._require(
            job.inspection_completed, "inspection_required", "Upload inspection is required."
        )
        self._require(
            not job.calibration_completed,
            "calibration_already_completed",
            "Calibration has already been completed.",
        )

        frame_paths = tuple(self._sampled_frame_paths(analysis_id))
        result = detect_pickleball_court(
            frame_paths=frame_paths,
            output_dir=self.settings.analysis_output_dir,
            analysis_id=analysis_id,
            calibration_id=self.settings.court_detection_calibration_id,
            min_confidence=self.settings.court_detection_min_confidence,
            low_confidence_threshold=self.settings.court_detection_low_confidence_threshold,
            numeric_tolerance=self.settings.numeric_validation_tolerance,
            min_polygon_area_pixels=self.settings.min_calibration_polygon_area_pixels,
            transition_area_depth_feet=self.settings.transition_area_depth_feet,
            top_down_width_pixels=self.settings.calibration_top_down_width_pixels,
        )

        detection_succeeded = result.outcome == CourtDetectionOutcome.detected
        manual_required = not detection_succeeded
        selected_frame = (
            self.repository.artifact_from_path(analysis_id, result.selected_frame_path).path
            if result.selected_frame_path is not None
            else None
        )
        detected_corners = _detected_corners_model(result.image_points)
        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.processing,
            current_stage=(
                AnalysisStage.calibrated if detection_succeeded else AnalysisStage.inspected
            ),
            error=None,
            calibration_completed=detection_succeeded,
            manual_calibration_required=manual_required,
            court_detection_status=result.outcome,
            court_detection_confidence=result.confidence,
            court_detection_selected_frame=selected_frame,
            court_detection_detected_corners=detected_corners,
        )
        artifacts = [
            self.repository.artifact_from_path(analysis_id, path)
            for path in result.artifacts
            if path.is_file()
        ]
        return CourtDetectionResponse(
            analysis_id=analysis_id,
            status=result.outcome,
            confidence=result.confidence,
            selected_frame=selected_frame,
            detected_corners=detected_corners,
            manual_calibration_required=manual_required,
            calibration=result.calibration,
            artifacts=artifacts,
            job=AnalysisJobResponse.model_validate(updated.model_dump(mode="json")),
        )

    def start_tracking(self, analysis_id: str, request: TrackingRequest) -> TrackingResponse:
        job = self.repository.load_job(analysis_id)
        self._require(job.calibration_completed, "calibration_required", "Calibration is required.")
        calibration_id = self._validate_output_id(request.calibration_id, "calibration")
        tracking_path = self.repository.analysis_dir(analysis_id) / "tracking" / "tracking.json"
        try:
            registered_tracking = self.repository.resolve_artifact(
                analysis_id, "tracking/tracking.json"
            )
        except JobNotFoundError:
            registered_tracking = None

        if registered_tracking is not None:
            tracking = self._load_tracking(registered_tracking)
        else:
            calibration_path = self.repository.resolve_artifact(
                analysis_id,
                f"calibrations/{calibration_id}/calibration.json",
            )
            if job.source_video is None:
                raise JobConflictError("source_video_missing", "Source video is missing.")

            video_path = self.repository.resolve_artifact(analysis_id, job.source_video)
            if not video_path.is_file():
                raise JobNotFoundError("Source video not found.")

            try:
                calibration = self._load_calibration(calibration_path)
                backend = self._build_tracking_backend(analysis_id, request)
                result = analyze_players(
                    video_path=video_path,
                    calibration=calibration,
                    output_dir=self.settings.analysis_output_dir,
                    tracking_backend=backend,
                    analysis_id=analysis_id,
                    frame_interval=request.frame_interval
                    or self.settings.frame_processing_interval,
                    court_inclusion_margin_feet=self.settings.court_inclusion_margin_feet,
                    min_eligible_track_duration_seconds=(
                        self.settings.min_eligible_track_duration_seconds
                    ),
                    min_eligible_observation_count=self.settings.min_eligible_observation_count,
                    min_eligible_inside_extended_ratio=(
                        self.settings.min_eligible_inside_extended_ratio
                    ),
                    min_eligible_inside_court_ratio=(self.settings.min_eligible_inside_court_ratio),
                    min_eligible_court_movement_rate_feet_per_second=(
                        self.settings.min_eligible_court_movement_rate_feet_per_second
                    ),
                    max_selectable_player_tracks=self.settings.max_selectable_player_tracks,
                    min_eligible_average_confidence=self.settings.min_eligible_average_confidence,
                    annotated_video_codec=self.settings.annotated_video_codec,
                    annotated_video_fps=self.settings.annotated_video_fps,
                )
                tracking = result.report
            except DetectorModelMissingError as exc:
                raise JobRequestError(
                    "detector_model_missing",
                    "Player detection is not available because the detector model is missing.",
                ) from exc
            except DetectorRuntimeUnavailableError as exc:
                raise JobRequestError(
                    "detector_runtime_unavailable",
                    "Player detection is not available because the detector runtime "
                    "is not installed.",
                ) from exc
            except DetectorUnavailableError as exc:
                raise JobRequestError(
                    "detector_unavailable",
                    "Player detection is not available with the current detector configuration.",
                ) from exc
            except TrackingError as exc:
                self._mark_failed(job, "Tracking failed.")
                raise JobRequestError("tracking_failed", "Tracking failed.") from exc

        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.tracked,
            error=None,
            tracking_completed=True,
        )
        artifacts = self._artifacts_under(analysis_id, tracking_path.parent)
        candidates = self._ensure_player_candidates(
            analysis_id,
            job=updated,
            tracking=tracking,
            preserve_review=True,
        )
        candidates, updated = self._refresh_analysis_readiness(updated, candidates)
        return TrackingResponse(
            analysis_id=analysis_id,
            tracking=tracking,
            artifacts=artifacts,
            job=AnalysisJobResponse.model_validate(updated.model_dump(mode="json")),
            player_candidates=candidates,
        )

    def list_player_candidates(self, analysis_id: str) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_path = self.repository.resolve_artifact(
            analysis_id, "tracking/tracking.json"
        )
        collection = self._ensure_player_candidates(
            analysis_id,
            job=job,
            tracking=self._load_tracking(tracking_path),
            preserve_review=True,
        )
        collection, _ = self._refresh_analysis_readiness(job, collection)
        return collection

    def generate_player_candidates(self, analysis_id: str) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_path = self.repository.resolve_artifact(
            analysis_id, "tracking/tracking.json"
        )
        collection = self._build_player_candidates(
            analysis_id,
            job=job,
            tracking=self._load_tracking(tracking_path),
            preserve_review=True,
        )
        collection, _ = self._refresh_analysis_readiness(job, collection)
        return collection

    def select_player_candidate(
        self,
        analysis_id: str,
        candidate_id: str,
    ) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_dir = self.repository.analysis_dir(analysis_id) / "tracking"
        self._ensure_player_candidates(
            analysis_id,
            job=job,
            tracking=self._load_tracking(tracking_dir / "tracking.json"),
            preserve_review=True,
        )
        try:
            collection = select_player_candidate(
                candidate_path=tracking_dir / "player_candidates.json",
                candidate_id=candidate_id,
                tracking_report_path=tracking_dir / "tracking.json",
            )
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_selection_failed", "Player candidate selection failed."
            ) from exc
        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.player_selected,
            error=None,
            player_selected=True,
        )
        collection, _ = self._refresh_analysis_readiness(updated, collection)
        return collection

    def reject_player_candidate(
        self,
        analysis_id: str,
        candidate_id: str,
        reason: str,
    ) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_dir = self.repository.analysis_dir(analysis_id) / "tracking"
        self._ensure_player_candidates(
            analysis_id,
            job=job,
            tracking=self._load_tracking(tracking_dir / "tracking.json"),
            preserve_review=True,
        )
        try:
            collection = reject_player_candidate(
                candidate_path=tracking_dir / "player_candidates.json",
                candidate_id=candidate_id,
                reason=reason,
                tracking_report_path=tracking_dir / "tracking.json",
            )
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_rejection_failed", "Player candidate could not be excluded."
            ) from exc
        updated_job = job
        if collection.selected_candidate_id is None and job.player_selected:
            updated_job = self.repository.update_job(
                job,
                status=AnalysisStatus.processing,
                current_stage=AnalysisStage.tracked,
                player_selected=False,
                analytics_completed=False,
            )
        collection, _ = self._refresh_analysis_readiness(updated_job, collection)
        return collection

    def restore_player_candidate(
        self,
        analysis_id: str,
        candidate_id: str,
    ) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        candidate_path = (
            self.repository.analysis_dir(analysis_id) / "tracking" / "player_candidates.json"
        )
        self.list_player_candidates(analysis_id)
        try:
            collection = restore_player_candidate(
                candidate_path=candidate_path,
                candidate_id=candidate_id,
            )
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_restore_failed", "Excluded candidate could not be restored."
            ) from exc
        collection, _ = self._refresh_analysis_readiness(job, collection)
        return collection

    def merge_player_candidates(
        self,
        analysis_id: str,
        candidate_ids: list[str],
    ) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        paths = self._candidate_paths(analysis_id, job)
        self.list_player_candidates(analysis_id)
        try:
            collection = merge_player_candidates(
                candidate_path=paths["candidate"],
                candidate_ids=candidate_ids,
                tracking_report_path=paths["tracking"],
                observations_path=paths["observations"],
                source_video_path=paths["source"],
                metadata_path=paths["metadata"],
            )
        except CandidateImpossibleMergeError as exc:
            raise JobConflictError("impossible_candidate_merge", str(exc)) from exc
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_merge_failed", "Player candidates could not be merged."
            ) from exc
        collection, _ = self._refresh_analysis_readiness(job, collection)
        return collection

    def unmerge_player_candidates(
        self,
        analysis_id: str,
        candidate_id: str,
    ) -> PlayerCandidateCollection:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        paths = self._candidate_paths(analysis_id, job)
        try:
            collection = unmerge_player_candidates(
                candidate_path=paths["candidate"],
                candidate_id=candidate_id,
                tracking_report_path=paths["tracking"],
                observations_path=paths["observations"],
                source_video_path=paths["source"],
                metadata_path=paths["metadata"],
            )
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_unmerge_failed", "Manual candidate merge could not be undone."
            ) from exc
        updated_job = job
        if collection.selected_candidate_id is None and job.player_selected:
            updated_job = self.repository.update_job(
                job,
                status=AnalysisStatus.processing,
                current_stage=AnalysisStage.tracked,
                player_selected=False,
                analytics_completed=False,
            )
        collection, _ = self._refresh_analysis_readiness(updated_job, collection)
        return collection

    def list_players(self, analysis_id: str) -> PlayersResponse:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_path = self.repository.resolve_artifact(
            analysis_id, "tracking/tracking.json"
        )
        tracking = self._load_tracking(tracking_path)
        tracking = self._refresh_player_selection_metrics(tracking_path, tracking)
        tracking = self._ensure_player_previews(job, tracking_path, tracking)
        selection_artifact = self._optional_artifact(
            analysis_id,
            self.repository.analysis_dir(analysis_id)
            / "tracking"
            / tracking.artifacts.player_selection_image,
        )
        return PlayersResponse(
            analysis_id=analysis_id,
            track_summaries=tracking.track_summaries,
            player_selection_artifact=selection_artifact,
            selected_player_track_id=tracking.selected_player_track_id,
        )

    def select_player(
        self,
        analysis_id: str,
        request: PlayerSelectionRequest,
    ) -> PlayerSelectionResponse:
        job = self.repository.load_job(analysis_id)
        self._require(job.tracking_completed, "tracking_required", "Player tracking is required.")
        tracking_path = self.repository.analysis_dir(analysis_id) / "tracking" / "tracking.json"
        self._refresh_player_selection_metrics(tracking_path, self._load_tracking(tracking_path))
        try:
            tracking = select_player_track(
                tracking_report_path=tracking_path, track_id=request.track_id
            )
            candidates = self._ensure_player_candidates(
                analysis_id,
                job=job,
                tracking=tracking,
                preserve_review=True,
            )
            candidate = next(
                (
                    item
                    for item in candidates.candidates
                    if request.track_id in item.source_raw_track_ids
                ),
                None,
            )
            if candidate is not None:
                select_player_candidate(
                    candidate_path=tracking_path.parent / "player_candidates.json",
                    candidate_id=candidate.candidate_id,
                    tracking_report_path=tracking_path,
                )
                tracking = self._load_tracking(tracking_path)
        except TrackingError as exc:
            raise JobRequestError("player_selection_failed", "Player selection failed.") from exc
        except CandidateError as exc:
            raise JobRequestError("player_selection_failed", "Player selection failed.") from exc

        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.player_selected,
            error=None,
            player_selected=True,
        )
        selection_artifact = self._optional_artifact(
            analysis_id,
            tracking_path.parent / tracking.artifacts.player_selection_image,
        )
        tracking = self._ensure_player_previews(job, tracking_path, tracking)
        return PlayerSelectionResponse(
            analysis_id=analysis_id,
            track_summaries=tracking.track_summaries,
            player_selection_artifact=selection_artifact,
            selected_player_track_id=tracking.selected_player_track_id,
            job=AnalysisJobResponse.model_validate(updated.model_dump(mode="json")),
        )

    def generate_analytics(self, analysis_id: str) -> AnalyticsGenerationResponse:
        job = self.repository.load_job(analysis_id)
        self._require(
            job.player_selected, "player_selection_required", "Player selection is required."
        )
        analytics_path = self.repository.analysis_dir(analysis_id) / "analytics" / "analytics.json"
        match_iq_path = analytics_path.parent / MATCH_IQ_FILENAME

        if analytics_path.exists():
            analytics = self._load_analytics(analytics_path)
            match_iq = self._load_optional_match_iq(match_iq_path)
        else:
            try:
                result = generate_match_analytics(
                    analysis_id=analysis_id,
                    output_dir=self.settings.analysis_output_dir,
                    transition_area_depth_feet=self.settings.transition_area_depth_feet,
                    image_width_pixels=self.settings.analytics_image_width_pixels,
                )
                analytics = result.report
                match_iq = generate_and_write_match_iq(
                    analytics=analytics,
                    timeline=result.timeline,
                    analytics_dir=result.analytics_dir,
                    recording_quality=job.analysis_readiness,
                )
            except AnalyticsOutputExistsError as exc:
                raise JobConflictError(
                    "analytics_exists",
                    "Analytics output already exists.",
                ) from exc
            except MissingSelectedPlayerError as exc:
                raise JobConflictError(
                    "player_selection_required",
                    "Player selection is required.",
                ) from exc
            except AnalyticsError as exc:
                self._mark_failed(job, "Analytics generation failed.")
                raise JobRequestError("analytics_failed", "Analytics generation failed.") from exc

        updated = self.repository.update_job(
            job,
            status=AnalysisStatus.completed,
            current_stage=AnalysisStage.analyzed,
            error=None,
            analytics_completed=True,
        )
        artifacts = self._artifacts_under(analysis_id, analytics_path.parent)
        return AnalyticsGenerationResponse(
            analysis_id=analysis_id,
            analytics=analytics,
            match_iq=match_iq,
            artifacts=artifacts,
            job=AnalysisJobResponse.model_validate(updated.model_dump(mode="json")),
        )

    def generate_active_play(self, analysis_id: str) -> ActivePlayReport:
        """Generate internal shadow evidence without changing job or analytics state."""

        job = self.repository.load_job(analysis_id)
        self._require(
            job.tracking_completed,
            "tracking_required",
            "Player tracking is required.",
        )
        try:
            report = generate_shadow_active_play(
                analysis_id=analysis_id,
                analysis_dir=self.repository.analysis_dir(analysis_id),
            )
            self.repository.save_job(job)
            return report
        except ActivePlayNotReadyError as exc:
            raise JobConflictError("active_play_not_ready", str(exc)) from exc
        except ActivePlayError as exc:
            raise JobRequestError(
                "active_play_generation_failed",
                "Shadow Active Play evidence could not be generated.",
            ) from exc

    def get_active_play(self, analysis_id: str) -> ActivePlayReport:
        """Load an existing internal shadow artifact without legacy migration."""

        self.repository.load_job(analysis_id)
        try:
            report_path = self.repository.resolve_artifact(
                analysis_id, "active_play/active_play.json"
            )
        except JobNotFoundError:
            raise JobConflictError(
                "active_play_not_ready",
                "Shadow Active Play evidence has not been generated.",
            ) from None
        try:
            return load_active_play_report(report_path)
        except ActivePlayError as exc:
            raise JobRequestError(
                "invalid_active_play",
                "Saved shadow Active Play evidence could not be read.",
            ) from exc

    def get_analytics(self, analysis_id: str) -> AnalyticsResponse:
        job = self.repository.load_job(analysis_id)
        self._require(job.analytics_completed, "analytics_not_ready", "Analytics are not ready.")
        try:
            analytics_path = self.repository.resolve_artifact(
                analysis_id, "analytics/analytics.json"
            )
        except JobNotFoundError:
            raise JobConflictError("analytics_not_ready", "Analytics are not ready.") from None
        try:
            match_iq_path = self.repository.resolve_artifact(
                analysis_id, f"analytics/{MATCH_IQ_FILENAME}"
            )
        except JobNotFoundError:
            match_iq_path = analytics_path.parent / "__not_registered__"
        return AnalyticsResponse(
            analysis_id=analysis_id,
            analytics=self._load_analytics(analytics_path),
            match_iq=self._load_optional_match_iq(match_iq_path),
        )

    async def _save_upload_to_staging(
        self, upload: UploadFile, analysis_id: str
    ) -> tuple[Path, str, int]:
        original_name = Path(upload.filename or "").name
        suffix = self._validate_upload_filename(original_name)
        self._validate_upload_content_type(upload.content_type)

        staging_dir = self.repository.staging_dir(analysis_id)
        staging_dir.mkdir(parents=True, exist_ok=False)
        staging_path = staging_dir / f"source{suffix}"
        bytes_written = 0
        digest = hashlib.sha256()
        try:
            with staging_path.open("wb") as output:
                while chunk := await upload.read(self.settings.upload_chunk_size_bytes):
                    bytes_written += len(chunk)
                    if bytes_written > self.settings.max_upload_size_bytes:
                        raise JobTooLargeError("Uploaded video exceeds the configured size limit.")
                    digest.update(chunk)
                    output.write(chunk)
        except JobTooLargeError:
            if staging_path.exists():
                staging_path.unlink()
            raise

        if bytes_written == 0:
            raise JobRequestError("empty_upload", "Uploaded video cannot be empty.")
        return staging_path, digest.hexdigest(), bytes_written

    def _validate_upload_filename(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        supported_extensions = {
            extension.lower() for extension in self.settings.supported_extensions
        }
        if suffix not in supported_extensions:
            raise JobRequestError("unsupported_extension", "Unsupported video extension.")
        safe_name = SAFE_NAME_PATTERN.sub("_", Path(filename).stem).strip("._-")
        if not safe_name:
            raise JobRequestError("invalid_filename", "Uploaded filename is invalid.")
        return suffix

    def _validate_upload_content_type(self, content_type: str | None) -> None:
        if not content_type:
            return
        cleaned = content_type.split(";", maxsplit=1)[0].strip().lower()
        if cleaned == "application/octet-stream" or cleaned.startswith("video/"):
            return
        raise JobRequestError("unsupported_media_type", "Unsupported upload content type.")

    def _move_upload_to_analysis(self, analysis_id: str, staging_path: Path) -> Path:
        analysis_dir = self.repository.analysis_dir(analysis_id)
        upload_dir = analysis_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / staging_path.name
        if staging_path.exists() and not destination.exists():
            shutil.move(str(staging_path), str(destination))
        return destination

    def _cleanup_staging_dir(self, analysis_id: str) -> None:
        staging_dir = self.repository.staging_dir(analysis_id)
        if not staging_dir.exists():
            return
        try:
            staging_dir.rmdir()
            staging_dir.parent.rmdir()
        except OSError:
            logger.debug("api_upload_staging_cleanup_skipped", extra={"analysis_id": analysis_id})

    def _build_tracking_backend(
        self, analysis_id: str, request: TrackingRequest
    ) -> JsonTrackingBackend | UltralyticsByteTrackBackend:
        if request.backend == TrackingBackend.controlled_json:
            if request.detections_jsonl is None:
                raise JobRequestError(
                    "detections_jsonl_required",
                    "Controlled tracking requires a detections_jsonl artifact path.",
                )
            detections_path = self.repository.resolve_artifact(
                analysis_id, request.detections_jsonl
            )
            if not detections_path.is_file():
                raise JobNotFoundError("Controlled detections file not found.")
            return JsonTrackingBackend(detections_path)

        model_path = self._resolve_model_path(request.model_path)
        return UltralyticsByteTrackBackend(
            model_path=model_path,
            confidence_threshold=(
                request.confidence_threshold
                if request.confidence_threshold is not None
                else self.settings.detector_confidence_threshold
            ),
            image_size=self.settings.detector_image_size,
        )

    def _resolve_model_path(self, requested_model_path: str | None) -> Path:
        if requested_model_path is None:
            return self.settings.detector_model_path
        model_root = self.settings.detector_model_path.expanduser().parent.resolve()
        resolved = (model_root / requested_model_path).resolve()
        try:
            resolved.relative_to(model_root)
        except ValueError:
            raise JobRequestError(
                "unsafe_model_path", "Model path is outside the model directory."
            ) from None
        return resolved

    def _require(self, condition: bool, code: str, message: str) -> None:
        if not condition:
            raise JobConflictError(code, message)

    def _require_frame_artifact(self, source_frame: Path, analysis_id: str) -> None:
        frames_dir = self.repository.analysis_dir(analysis_id) / "frames"
        try:
            source_frame.relative_to(frames_dir.resolve())
        except ValueError:
            raise JobRequestError(
                "invalid_source_frame", "Source frame must be a sampled frame."
            ) from None
        if not source_frame.is_file():
            raise JobNotFoundError("Source frame not found.")

    def _sampled_frame_paths(self, analysis_id: str) -> list[Path]:
        frames_dir = self.repository.analysis_dir(analysis_id) / "frames"
        if not frames_dir.exists():
            return []
        return [
            frame_path
            for frame_path in sorted(frames_dir.glob("frame_*.jpg"))
            if frame_path.is_file() and FRAME_NAME_PATTERN.fullmatch(frame_path.name)
        ]

    def _artifacts_under(self, analysis_id: str, directory: Path) -> list[AnalysisArtifact]:
        if not directory.exists():
            return []
        return [
            self.repository.artifact_from_path(analysis_id, path)
            for path in sorted(item for item in directory.rglob("*") if item.is_file())
        ]

    def _ensure_player_candidates(
        self,
        analysis_id: str,
        *,
        job: AnalysisJob,
        tracking: PlayerTrackingReport,
        preserve_review: bool,
    ) -> PlayerCandidateCollection:
        candidate_path = (
            self.repository.analysis_dir(analysis_id) / "tracking" / "player_candidates.json"
        )
        if candidate_path.is_file():
            try:
                collection = load_player_candidates(candidate_path)
                if collection.schema_version == CANDIDATE_SCHEMA_VERSION:
                    return collection
            except CandidateError as exc:
                raise JobRequestError(
                    "candidate_persistence_failure",
                    "Saved player candidates could not be loaded.",
                ) from exc
        return self._build_player_candidates(
            analysis_id,
            job=job,
            tracking=tracking,
            preserve_review=preserve_review,
        )

    def _build_player_candidates(
        self,
        analysis_id: str,
        *,
        job: AnalysisJob,
        tracking: PlayerTrackingReport,
        preserve_review: bool,
    ) -> PlayerCandidateCollection:
        paths = self._candidate_paths(analysis_id, job)
        try:
            return build_player_candidates(
                analysis_id=analysis_id,
                tracking_report=tracking,
                observations_path=paths["observations"],
                source_video_path=paths["source"],
                metadata_path=paths["metadata"],
                tracking_dir=paths["tracking"].parent,
                preserve_review=preserve_review,
            )
        except CandidateError as exc:
            raise JobRequestError(
                "candidate_generation_failed",
                "Player candidates could not be generated from the tracking data.",
            ) from exc

    def _candidate_paths(self, analysis_id: str, job: AnalysisJob) -> dict[str, Path]:
        analysis_dir = self.repository.analysis_dir(analysis_id)
        if job.source_video is None:
            raise JobConflictError("source_video_missing", "Source video is missing.")
        source_path = self.repository.resolve_artifact(analysis_id, job.source_video)
        paths = {
            "candidate": analysis_dir / "tracking" / "player_candidates.json",
            "tracking": analysis_dir / "tracking" / "tracking.json",
            "observations": analysis_dir / "tracking" / "observations.jsonl",
            "source": source_path,
            "metadata": analysis_dir / "metadata.json",
        }
        missing = [
            name for name, path in paths.items() if name != "candidate" and not path.is_file()
        ]
        if missing:
            raise JobNotFoundError(
                f"Candidate source artifact is missing: {', '.join(sorted(missing))}."
            )
        return paths

    def _optional_artifact(self, analysis_id: str, path: Path) -> AnalysisArtifact | None:
        if not path.is_file():
            return None
        return self.repository.artifact_from_path(analysis_id, path)

    def _ensure_player_previews(
        self,
        job: AnalysisJob,
        tracking_path: Path,
        tracking: PlayerTrackingReport,
    ) -> PlayerTrackingReport:
        if job.source_video is None:
            return tracking
        try:
            source_video_path = self.repository.resolve_artifact(
                job.analysis_id,
                job.source_video,
            )
            return ensure_player_preview_images(
                tracking_report_path=tracking_path,
                source_video_path=source_video_path,
            )
        except TrackingError:
            logger.warning(
                "player_preview_generation_failed",
                extra={"analysis_id": job.analysis_id, "tracking_path": str(tracking_path)},
                exc_info=True,
            )
            return tracking

    def _refresh_player_selection_metrics(
        self,
        tracking_path: Path,
        tracking: PlayerTrackingReport,
    ) -> PlayerTrackingReport:
        try:
            return refresh_player_selection_metrics(
                tracking_report_path=tracking_path,
                eligibility=self._tracking_eligibility(),
            )
        except TrackingError:
            logger.warning(
                "player_selection_metric_refresh_failed",
                extra={
                    "analysis_id": tracking.analysis_id,
                    "tracking_path": str(tracking_path),
                },
                exc_info=True,
            )
            return tracking

    def _tracking_eligibility(self) -> EligibilityConfig:
        return EligibilityConfig(
            min_observation_count=self.settings.min_eligible_observation_count,
            min_duration_seconds=self.settings.min_eligible_track_duration_seconds,
            min_inside_court_ratio=self.settings.min_eligible_inside_court_ratio,
            min_inside_extended_ratio=self.settings.min_eligible_inside_extended_ratio,
            min_court_movement_rate_feet_per_second=(
                self.settings.min_eligible_court_movement_rate_feet_per_second
            ),
            max_selectable_tracks=self.settings.max_selectable_player_tracks,
            min_average_confidence=self.settings.min_eligible_average_confidence,
        )

    def _mark_failed(self, job: AnalysisJob, message: str) -> None:
        self.repository.update_job(job, status=AnalysisStatus.failed, error=message)

    def _validate_output_id(self, value: str, label: str) -> str:
        try:
            return self.repository.validate_analysis_id(value)
        except JobRequestError as exc:
            raise JobRequestError(f"invalid_{label}_id", f"{label.title()} ID is invalid.") from exc

    def _load_calibration(self, path: Path) -> CourtCalibrationReport:
        try:
            return load_calibration_report(path)
        except TrackingError as exc:
            raise JobRequestError("invalid_calibration", "Calibration could not be read.") from exc

    def _load_tracking(self, path: Path) -> PlayerTrackingReport:
        try:
            return load_tracking_report(path)
        except TrackingError as exc:
            raise JobRequestError("invalid_tracking", "Tracking report could not be read.") from exc

    def _load_analytics(self, path: Path) -> AnalyticsReport:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return AnalyticsReport.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise JobRequestError(
                "invalid_analytics", "Analytics report could not be read."
            ) from exc

    def _load_optional_match_iq(self, path: Path) -> MatchIQReport | None:
        if not path.is_file():
            return None
        try:
            return load_match_iq_report(path)
        except MatchIQPersistenceError as exc:
            raise JobRequestError("invalid_match_iq", "Match IQ report could not be read.") from exc

    def _refresh_analysis_readiness(
        self,
        job: AnalysisJob,
        collection: PlayerCandidateCollection,
    ) -> tuple[PlayerCandidateCollection, AnalysisJob]:
        readiness = assess_analysis_readiness(
            upload_preflight=job.upload_preflight,
            calibration_completed=job.calibration_completed,
            court_detection_status=(
                job.court_detection_status.value if job.court_detection_status is not None else None
            ),
            court_detection_confidence=job.court_detection_confidence,
            detected_people=collection.recording_suitability.detected_people,
            candidates=collection.candidates,
            selected_candidate_id=collection.selected_candidate_id,
            assessed_at=(
                collection.analysis_readiness.assessed_at
                if collection.analysis_readiness is not None
                else None
            ),
        )
        if collection.analysis_readiness == readiness and job.analysis_readiness == readiness:
            return collection, job
        updated_collection = collection.model_copy(update={"analysis_readiness": readiness})
        candidate_path = (
            self.repository.analysis_dir(job.analysis_id) / "tracking" / "player_candidates.json"
        )
        candidate_path.write_text(
            json.dumps(updated_collection.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        updated_job = self.repository.update_job(job, analysis_readiness=readiness)
        return updated_collection, updated_job


def _detected_corners_model(
    image_points: (
        tuple[
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
        ]
        | None
    ),
) -> DetectedCourtCorners | None:
    if image_points is None:
        return None
    near_left, near_right, far_right, far_left = image_points
    return DetectedCourtCorners(
        near_left=CalibrationPointRequest(x=near_left[0], y=near_left[1]),
        near_right=CalibrationPointRequest(x=near_right[0], y=near_right[1]),
        far_right=CalibrationPointRequest(x=far_right[0], y=far_right[1]),
        far_left=CalibrationPointRequest(x=far_left[0], y=far_left[1]),
    )
