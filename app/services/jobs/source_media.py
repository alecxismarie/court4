from sqlalchemy import select

from app.persistence.models import Analysis, AnalysisArtifact, UploadedVideo, UploadSession, utc_now
from app.persistence.object_storage import LocalObjectStorage, ObjectStorageError
from app.services.jobs.exceptions import JobConflictError, JobNotFoundError, JobStorageBackendError
from app.services.jobs.repository import AnalysisJobRepository


class SourceMediaService:
    def __init__(self, repository: AnalysisJobRepository) -> None:
        self.repository = repository

    def delete(self, analysis_id: str) -> None:
        repo = self.repository
        with repo.media_operation(analysis_id, exclusive=True, wait=True):
            with repo.persistence.session_factory.begin() as session:
                analysis = session.scalar(
                    select(Analysis)
                    .where(Analysis.id == analysis_id, Analysis.owner_user_id == repo.owner_user_id)
                    .with_for_update()
                )
                if analysis is None:
                    raise JobNotFoundError()
                video = session.get(UploadedVideo, analysis.uploaded_video_id)
                if video is None or video.owner_user_id != repo.owner_user_id:
                    raise JobNotFoundError()
                if video.state == "deleted":
                    return
                if video.state not in {"available", "deleting"}:
                    raise JobConflictError(
                        "source_video_unavailable", "No established source recording is available."
                    )
                shared = session.scalar(
                    select(Analysis.id)
                    .where(Analysis.uploaded_video_id == video.id, Analysis.id != analysis_id)
                    .limit(1)
                )
                if shared is not None:
                    raise JobConflictError(
                        "source_media_shared", "This recording is shared by another analysis."
                    )
                if not (
                    analysis.state == "completed"
                    and analysis.job_payload.get("analytics_completed")
                    or analysis.sport == "padel"
                    and analysis.job_payload.get("inspection_completed")
                ):
                    raise JobConflictError(
                        "analysis_not_complete", "Finish the analysis before deleting its video."
                    )
                active = session.scalar(
                    select(UploadSession.id).where(
                        UploadSession.analysis_id == analysis_id,
                        UploadSession.status != "completed",
                    )
                )
                if active is not None:
                    raise JobConflictError(
                        "upload_not_complete",
                        "The upload must finish before its video can be deleted.",
                    )
                if not video.storage_key:
                    raise JobConflictError(
                        "source_video_unavailable", "No established source recording is available."
                    )
                provider, key = video.storage_provider, video.storage_key
                logical_key = str(analysis.job_payload.get("source_video") or "")
                video_id = video.id
                video.state = "deleting"
                video.metadata_payload = {
                    **video.metadata_payload,
                    "source_delete_requested_at": video.metadata_payload.get(
                        "source_delete_requested_at"
                    )
                    or utc_now().isoformat(),
                }
                video.row_version += 1

            # Intent survives process failure. Never claim successful deletion until
            # exact provider deletion succeeds. Missing bytes are idempotent success.
            try:
                if provider == "local":
                    root = repo.legacy_storage.analysis_root(analysis_id)
                    LocalObjectStorage(root).delete(key=key)
                elif provider == repo.object_storage.provider:
                    repo.object_storage.delete(key=key)
                else:
                    raise JobStorageBackendError()
                if logical_key:
                    repo.delete_local_source_copies(analysis_id, logical_key)
            except (ObjectStorageError, OSError) as exc:
                raise JobStorageBackendError(
                    "The source recording could not be deleted. Please retry."
                ) from exc

            with repo.persistence.session_factory.begin() as session:
                video = session.get(UploadedVideo, video_id, with_for_update=True)
                assert video is not None
                video.state = "deleted"
                video.metadata_payload = {
                    **video.metadata_payload,
                    "source_deleted_at": utc_now().isoformat(),
                }
                video.row_version += 1
                for artifact in session.scalars(
                    select(AnalysisArtifact).where(
                        AnalysisArtifact.analysis_id == analysis_id,
                        AnalysisArtifact.owner_user_id == repo.owner_user_id,
                        AnalysisArtifact.artifact_kind == "source_video",
                    )
                ):
                    artifact.state = "deleted"
