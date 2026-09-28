"""Durable owner-scoped deletion. Registry rows are the retry manifest until finalization."""

from pathlib import PurePosixPath

from sqlalchemy import delete, select, update

from app.persistence.models import (
    Analysis,
    AnalysisArtifact,
    AnalysisRun,
    AnalysisStageExecution,
    AnalysisStateEvent,
    CalibrationVerification,
    IdempotencyRecord,
    PlayerSelection,
    UploadedVideo,
    UploadSession,
    utc_now,
)
from app.persistence.object_storage import (
    LocalObjectStorage,
    ObjectStorageError,
    artifact_object_key,
    source_object_key,
)
from app.services.jobs.exceptions import JobConflictError, JobNotFoundError, JobStorageBackendError
from app.services.jobs.repository import AnalysisJobRepository


def delete_registered_object(
    repo: AnalysisJobRepository,
    analysis_id: str,
    *,
    provider: str,
    key: str,
    logical_key: str,
    checksum: str | None = None,
    source: bool = False,
) -> None:
    # Keys come exclusively from the owner-scoped registry, then are reconstructed.
    if provider == "local":
        if key != logical_key:
            raise JobConflictError("unsafe_media_key", "Match cleanup needs review.")
        LocalObjectStorage(repo.legacy_storage.analysis_root(analysis_id)).delete(key=key)
    elif provider == repo.object_storage.provider:
        expected = (
            {source_object_key(repo.owner_user_id, analysis_id, PurePosixPath(logical_key).suffix)}
            if source
            else {
                artifact_object_key(repo.owner_user_id, analysis_id, logical_key, checksum),
                artifact_object_key(repo.owner_user_id, analysis_id, logical_key),
            }
        )
        if key not in expected:
            raise JobConflictError("unsafe_media_key", "Match cleanup needs review.")
        repo.object_storage.delete(key=key)
    else:
        raise JobStorageBackendError()
    repo.delete_local_source_copies(analysis_id, logical_key)


class MatchLifecycleService:
    def __init__(self, repository: AnalysisJobRepository) -> None:
        self.repository = repository

    def status(self, analysis_id: str) -> dict[str, str]:
        repo = self.repository
        repo.validate_analysis_id(analysis_id)
        with repo.persistence.session_factory() as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None or analysis.owner_user_id != repo.owner_user_id:
                raise JobNotFoundError()
            return {"analysis_id": analysis_id, "state": analysis.lifecycle_state}

    def delete(self, analysis_id: str) -> None:
        repo = self.repository
        # Busy processing/materialization is rejected, never purged underneath a writer.
        with repo.media_operation(analysis_id, exclusive=True):
            with repo.persistence.session_factory.begin() as session:
                analysis = session.scalar(
                    select(Analysis)
                    .where(Analysis.id == analysis_id, Analysis.owner_user_id == repo.owner_user_id)
                    .with_for_update()
                )
                if analysis is None:
                    raise JobNotFoundError()
                if analysis.lifecycle_state == "deleted":
                    return
                video = session.get(UploadedVideo, analysis.uploaded_video_id)
                if video is None or video.owner_user_id != repo.owner_user_id:
                    raise JobNotFoundError()
                shared = session.scalar(
                    select(Analysis.id)
                    .where(Analysis.uploaded_video_id == video.id, Analysis.id != analysis_id)
                    .limit(1)
                )
                if shared:
                    raise JobConflictError(
                        "source_media_shared", "This recording is shared by another analysis."
                    )
                if session.scalar(
                    select(UploadSession.id)
                    .where(
                        UploadSession.analysis_id == analysis_id,
                        UploadSession.status.in_(
                            ("initiated", "uploading", "completing", "verifying", "analyzing")
                        ),
                    )
                    .limit(1)
                ):
                    raise JobConflictError(
                        "match_busy",
                        "This upload is still finalizing. Please retry when it finishes.",
                    )
                # The exclusive operation lock proves no CV/materialization is active.
                # Runs remain 'processing' between interactive setup steps; retire
                # these idle reservations so incomplete/failed matches are removable.
                for model in (AnalysisRun, AnalysisStageExecution):
                    session.execute(
                        update(model)
                        .where(
                            model.analysis_id == analysis_id,
                            model.state.in_(("queued", "processing")),
                        )
                        .values(state="cancelled", cancelled_at=utc_now())
                    )
                analysis.lifecycle_state = "deletion_pending"
                analysis.deletion_requested_at = analysis.deletion_requested_at or utc_now()
                analysis.row_version += 1
                video.state = "deleting"
                artifacts = list(
                    session.scalars(
                        select(AnalysisArtifact).where(
                            AnalysisArtifact.analysis_id == analysis_id,
                            AnalysisArtifact.owner_user_id == repo.owner_user_id,
                        )
                    )
                )
                source = (
                    video.storage_provider,
                    video.storage_key,
                    str(analysis.job_payload.get("source_video") or ""),
                )
                video_id = video.id
            # All readers now deny access; these records survive any provider/DB failure.
            try:
                if source[1] and not source[2]:
                    raise JobConflictError("unsafe_media_key", "Match cleanup needs review.")
                if source[1] and source[2]:
                    delete_registered_object(
                        repo,
                        analysis_id,
                        provider=source[0],
                        key=source[1],
                        logical_key=source[2],
                        source=True,
                    )
                for artifact in artifacts:
                    delete_registered_object(
                        repo,
                        analysis_id,
                        provider=artifact.storage_provider,
                        key=artifact.storage_key,
                        logical_key=artifact.logical_key,
                        checksum=artifact.checksum_sha256,
                        source=artifact.artifact_kind == "source_video",
                    )
                repo.purge_local_match_copies(analysis_id)
            except (ObjectStorageError, OSError) as exc:
                raise JobStorageBackendError("Match deletion is unfinished. Please retry.") from exc
            with repo.persistence.session_factory.begin() as session:
                analysis = session.get(Analysis, analysis_id, with_for_update=True)
                assert analysis is not None
                analysis.promoted_run_id = None
                session.flush()
                for content_model in (
                    AnalysisArtifact,
                    PlayerSelection,
                    CalibrationVerification,
                    AnalysisStageExecution,
                    AnalysisStateEvent,
                ):
                    session.execute(
                        delete(content_model).where(content_model.analysis_id == analysis_id)
                    )
                session.execute(
                    update(AnalysisRun)
                    .where(AnalysisRun.analysis_id == analysis_id)
                    .values(previous_run_id=None)
                )
                session.execute(delete(AnalysisRun).where(AnalysisRun.analysis_id == analysis_id))
                # Idempotency reservations retain only identity, never report content.
                session.execute(
                    update(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.owner_user_id == repo.owner_user_id,
                        IdempotencyRecord.resource_id == analysis_id,
                    )
                    .values(response_payload=None)
                )
                session.execute(
                    update(UploadSession)
                    .where(
                        UploadSession.owner_user_id == repo.owner_user_id,
                        UploadSession.analysis_id == analysis_id,
                    )
                    .values(
                        result_payload=None,
                        original_filename="deleted",
                        client_metadata={},
                        expected_sha256=None,
                        verified_sha256=None,
                        provider_upload_id="deleted",
                    )
                )
                analysis.job_payload = {}
                analysis.lifecycle_state = "deleted"
                analysis.deleted_at = utc_now()
                analysis.row_version += 1
                video = session.get(UploadedVideo, video_id)
                assert video is not None
                video.state = "deleted"
                video.original_filename = "deleted"
                video.storage_key = None
                video.content_type = None
                video.size_bytes = None
                video.source_checksum = None
                video.metadata_payload = {}
