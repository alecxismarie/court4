from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

from pydantic import ValidationError

from app.persistence.errors import (
    OwnershipMismatchError,
    ResourceNotFoundError,
)
from app.persistence.models import AnalysisArtifact as PersistedArtifact
from app.persistence.object_storage import (
    LocalObjectStorage,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    artifact_object_key,
    build_object_storage,
    source_object_key,
)
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.persistence.service import ArtifactInput, DuplicateVideoMatch, PlayerSelectionInput
from app.persistence.storage import LocalStorage, StorageCapacityError, StorageReservation
from app.schemas.jobs import AnalysisArtifact, AnalysisJob
from app.services.jobs.exceptions import (
    JobNotFoundError,
    JobRequestError,
    JobStorageBackendError,
    JobStorageCapacityError,
)
from app.sports import SportType

ANALYSIS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
logger = logging.getLogger(__name__)


class AnalysisJobRepository:
    """Compatibility façade whose authority is PostgreSQL, not ``job.json``."""

    def __init__(
        self,
        *,
        output_dir: Path,
        api_base_path: str,
        owner_user_id: UUID | None = None,
        persistence: PersistenceRuntime | None = None,
        object_storage: ObjectStorage | None = None,
        capacity_root: Path | None = None,
        cleanup_workspace: bool = False,
        workspace_warning_free_bytes: int | None = None,
        workspace_hard_stop_free_bytes: int | None = None,
        workspace_max_active: int = 1,
        legacy_storage_root: Path | None = None,
    ) -> None:
        self.output_dir = output_dir.expanduser().resolve()
        self.workspace = LocalStorage(self.output_dir)
        self.storage = LocalStorage(capacity_root or self.output_dir)
        self.legacy_storage = LocalStorage(legacy_storage_root or self.output_dir)
        self.api_base_path = api_base_path.rstrip("/")
        self.persistence = persistence or get_persistence()
        self.owner_user_id = owner_user_id or self.persistence.owner_user_id
        self.object_storage = object_storage or LocalObjectStorage(self.output_dir)
        self._cleanup_workspace = cleanup_workspace
        self._workspace_warning_free_bytes = workspace_warning_free_bytes
        self._workspace_hard_stop_free_bytes = workspace_hard_stop_free_bytes
        self._workspace_max_active = workspace_max_active
        self._workspace_reservation: StorageReservation | None = None

    @classmethod
    def from_settings(
        cls,
        *,
        settings: object,
        owner_user_id: UUID | None = None,
        persistence: PersistenceRuntime | None = None,
    ) -> AnalysisJobRepository:
        from app.config.settings import Settings

        if not isinstance(settings, Settings):
            raise TypeError("Court4 settings are required.")
        object_storage = build_object_storage(settings)
        if object_storage.provider == "local":
            return cls(
                output_dir=settings.analysis_output_dir,
                api_base_path=settings.api_base_path,
                owner_user_id=owner_user_id,
                persistence=persistence,
                object_storage=object_storage,
            )
        workspace_root = settings.processing_workspace_root.expanduser().resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)
        prefix_owner = str(owner_user_id or "bootstrap")
        output_dir = Path(tempfile.mkdtemp(prefix=f"court4-{prefix_owner}-", dir=workspace_root))
        return cls(
            output_dir=output_dir,
            api_base_path=settings.api_base_path,
            owner_user_id=owner_user_id,
            persistence=persistence,
            object_storage=object_storage,
            capacity_root=workspace_root,
            cleanup_workspace=True,
            workspace_warning_free_bytes=settings.storage_warning_free_bytes,
            workspace_hard_stop_free_bytes=settings.storage_hard_stop_free_bytes,
            workspace_max_active=settings.storage_max_active_uploads,
            legacy_storage_root=settings.local_storage_root,
        )

    def close(self) -> None:
        if self._workspace_reservation is not None:
            self._workspace_reservation.release()
            self._workspace_reservation = None
        if not self._cleanup_workspace or not self.output_dir.exists():
            return
        try:
            shutil.rmtree(self.output_dir)
        except OSError:
            logger.warning(
                "processing_workspace_cleanup_failed",
                extra={"workspace_name": self.output_dir.name},
                exc_info=True,
            )

    def create_or_replace_job(self, job: AnalysisJob) -> AnalysisJob:
        return self.save_job(job)

    def save_job(self, job: AnalysisJob) -> AnalysisJob:
        filesystem_artifacts = self._filesystem_artifacts(job.analysis_id)
        projected = job.model_copy(
            update={
                "available_artifacts": [
                    AnalysisArtifact(
                        path=artifact.logical_key or artifact.storage_key,
                        url=(
                            f"{self.api_base_path}/analyses/{job.analysis_id}/artifacts/"
                            f"{artifact.logical_key or artifact.storage_key}"
                        ),
                        content_type=artifact.content_type,
                        size_bytes=artifact.size_bytes,
                    )
                    for artifact in filesystem_artifacts
                ]
            }
        )
        try:
            self.persistence.service.persist_job(
                owner_user_id=self.owner_user_id,
                payload=projected.model_dump(mode="json"),
                artifacts=filesystem_artifacts,
                player_selection=self._player_selection(job.analysis_id),
                compatibility_import=True,
            )
        except (ResourceNotFoundError, OwnershipMismatchError):
            raise JobNotFoundError() from None
        return projected

    def load_job(self, analysis_id: str) -> AnalysisJob:
        job = self.load_job_metadata(analysis_id)
        self._materialize_current_artifacts(analysis_id)
        return self.refresh_artifacts(job)

    def load_job_metadata(self, analysis_id: str) -> AnalysisJob:
        self.validate_analysis_id(analysis_id)
        try:
            payload = self.persistence.service.load_job(
                owner_user_id=self.owner_user_id,
                analysis_id=analysis_id,
            )
            return AnalysisJob.model_validate(payload)
        except (ResourceNotFoundError, OwnershipMismatchError):
            raise JobNotFoundError() from None
        except ValidationError:
            raise JobRequestError(
                "invalid_job", "Analysis job metadata could not be read."
            ) from None

    def list_job_ids(self) -> list[str]:
        return self.persistence.service.list_analysis_ids(owner_user_id=self.owner_user_id)

    def find_uploaded_video_by_owner_and_checksum(
        self,
        checksum_sha256: str,
        sport: SportType = SportType.PICKLEBALL,
    ) -> DuplicateVideoMatch | None:
        return self.persistence.service.find_uploaded_video_by_owner_and_checksum(
            owner_user_id=self.owner_user_id,
            checksum_sha256=checksum_sha256,
            sport=sport,
        )

    def update_job(self, job: AnalysisJob, **updates: object) -> AnalysisJob:
        now = datetime.now(tz=UTC)
        updated = job.model_copy(update={**updates, "updated_at": now})
        return self.save_job(updated)

    def analysis_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        return self.workspace.analysis_root(analysis_id)

    def staging_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        path = (self.output_dir / "_uploads" / analysis_id).resolve()
        self._ensure_inside_base(path)
        return path

    def resolve_artifact(self, analysis_id: str, artifact_path: str) -> Path:
        analysis_dir = self.analysis_dir(analysis_id)
        relative_path = validate_relative_artifact_path(artifact_path)
        try:
            record = self.persistence.service.get_artifact(
                owner_user_id=self.owner_user_id,
                analysis_id=analysis_id,
                logical_key=relative_path,
            )
        except (ResourceNotFoundError, OwnershipMismatchError):
            raise JobNotFoundError("Artifact was not found.") from None
        resolved = self.workspace.resolve(analysis_id, relative_path)
        if not _is_relative_to(resolved, analysis_dir):
            raise JobRequestError("unsafe_artifact_path", "Artifact path is outside the analysis.")
        if not resolved.is_file() and record.storage_provider == "local":
            legacy_path = self.legacy_storage.resolve(analysis_id, record.storage_key)
            if legacy_path.is_file() and legacy_path != resolved:
                if (
                    legacy_path.stat().st_size != record.size_bytes
                    or _file_sha256(legacy_path) != record.checksum_sha256
                ):
                    raise JobNotFoundError("Artifact bytes failed integrity verification.")
                self._reserve_workspace([record])
                resolved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(legacy_path, resolved)
        if not resolved.is_file() and record.storage_provider != "local":
            self._reserve_workspace([record])
            try:
                metadata = self.object_storage.download_file(
                    key=record.storage_key,
                    destination=resolved,
                )
            except ObjectNotFoundError:
                raise JobNotFoundError("Artifact bytes are unavailable.") from None
            except ObjectStorageError as exc:
                raise JobStorageBackendError() from exc
            if (
                metadata.size_bytes != record.size_bytes
                or metadata.checksum_sha256 != record.checksum_sha256
            ):
                resolved.unlink(missing_ok=True)
                raise JobNotFoundError("Artifact bytes failed integrity verification.")
        if not resolved.is_file():
            raise JobNotFoundError("Artifact bytes are unavailable.")
        return resolved

    def artifact_from_path(self, analysis_id: str, path: Path) -> AnalysisArtifact:
        analysis_dir = self.analysis_dir(analysis_id)
        relative_path = path.resolve().relative_to(analysis_dir).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return AnalysisArtifact(
            path=relative_path,
            url=f"{self.api_base_path}/analyses/{analysis_id}/artifacts/{relative_path}",
            content_type=content_type,
            size_bytes=path.stat().st_size,
        )

    def list_artifacts(self, analysis_id: str) -> list[AnalysisArtifact]:
        try:
            records = self.persistence.service.list_artifacts(
                owner_user_id=self.owner_user_id,
                analysis_id=analysis_id,
            )
        except (ResourceNotFoundError, OwnershipMismatchError):
            return []
        return [
            AnalysisArtifact(
                path=record.logical_key,
                url=(f"{self.api_base_path}/analyses/{analysis_id}/artifacts/{record.logical_key}"),
                content_type=record.content_type,
                size_bytes=record.size_bytes,
            )
            for record in records
        ]

    def refresh_artifacts(self, job: AnalysisJob) -> AnalysisJob:
        return job.model_copy(update={"available_artifacts": self.list_artifacts(job.analysis_id)})

    def register_current_artifacts(self, analysis_id: str) -> AnalysisJob:
        return self.save_job(self.load_job_metadata(analysis_id))

    def validate_analysis_id(self, analysis_id: str) -> str:
        if not ANALYSIS_ID_PATTERN.fullmatch(analysis_id):
            raise JobRequestError("invalid_analysis_id", "Analysis ID is invalid.")
        return analysis_id

    def _filesystem_artifacts(self, analysis_id: str) -> list[ArtifactInput]:
        analysis_dir = self.analysis_dir(analysis_id)
        if not analysis_dir.exists():
            return []
        artifacts: list[ArtifactInput] = []
        for path in sorted(item for item in analysis_dir.rglob("*") if item.is_file()):
            if path.name == "job.json":
                continue
            relative = path.relative_to(analysis_dir).as_posix()
            checksum = _file_sha256(path)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            storage_key = relative
            if self.object_storage.provider == "s3":
                storage_key = (
                    source_object_key(self.owner_user_id, analysis_id, path.suffix)
                    if _artifact_kind(relative) == "source_video"
                    else artifact_object_key(
                        self.owner_user_id,
                        analysis_id,
                        relative,
                        checksum,
                    )
                )
                try:
                    self.object_storage.put_file(
                        key=storage_key,
                        source=path,
                        content_type=content_type,
                        checksum_sha256=checksum,
                    )
                except ObjectStorageError as exc:
                    raise JobStorageBackendError(
                        "Durable object storage could not persist analysis output."
                    ) from exc
            artifacts.append(
                ArtifactInput(
                    storage_key=storage_key,
                    logical_key=relative,
                    storage_provider=self.object_storage.provider,
                    content_type=content_type,
                    size_bytes=path.stat().st_size,
                    checksum_sha256=checksum,
                    artifact_kind=_artifact_kind(relative),
                    schema_version=_artifact_schema_version(relative),
                )
            )
        return artifacts

    def _materialize_current_artifacts(self, analysis_id: str) -> None:
        if self.object_storage.provider == "local":
            return
        records = self.persistence.service.list_artifacts(
            owner_user_id=self.owner_user_id,
            analysis_id=analysis_id,
        )
        self._reserve_workspace(records)
        for record in records:
            destination = self.workspace.resolve(analysis_id, record.logical_key)
            if destination.is_file():
                continue
            if record.storage_provider == "local":
                legacy_path = self.legacy_storage.resolve(analysis_id, record.storage_key)
                if not legacy_path.is_file():
                    raise JobNotFoundError("Artifact bytes are unavailable.")
                if (
                    legacy_path.stat().st_size != record.size_bytes
                    or _file_sha256(legacy_path) != record.checksum_sha256
                ):
                    raise JobNotFoundError("Artifact bytes failed integrity verification.")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(legacy_path, destination)
                continue
            try:
                metadata = self.object_storage.download_file(
                    key=record.storage_key,
                    destination=destination,
                )
            except ObjectNotFoundError as exc:
                raise JobNotFoundError("Artifact bytes are unavailable.") from exc
            except ObjectStorageError as exc:
                raise JobStorageBackendError() from exc
            if (
                metadata.size_bytes != record.size_bytes
                or metadata.checksum_sha256 != record.checksum_sha256
            ):
                destination.unlink(missing_ok=True)
                raise JobNotFoundError("Artifact bytes failed integrity verification.")

    def _reserve_workspace(self, records: list[PersistedArtifact]) -> None:
        if self.object_storage.provider == "local" or self._workspace_reservation is not None:
            return
        if (
            self._workspace_warning_free_bytes is None
            or self._workspace_hard_stop_free_bytes is None
        ):
            return
        sizes = [record.size_bytes for record in records]
        source_sizes = [
            record.size_bytes for record in records if record.artifact_kind == "source_video"
        ]
        requested_bytes = sum(sizes) + (max(source_sizes) if source_sizes else 0)
        try:
            reservation, _status = self.storage.reserve_capacity(
                requested_bytes=requested_bytes,
                warning_free_bytes=self._workspace_warning_free_bytes,
                hard_stop_free_bytes=self._workspace_hard_stop_free_bytes,
                max_active_uploads=self._workspace_max_active,
            )
        except StorageCapacityError as exc:
            status_code = 429 if exc.reason == "active_limit" else 507
            raise JobStorageCapacityError(
                "processing_workspace_unavailable",
                "Temporary processing workspace capacity is unavailable.",
                status_code=status_code,
            ) from exc
        self._workspace_reservation = reservation

    def _player_selection(self, analysis_id: str) -> PlayerSelectionInput | None:
        tracking_path = self.analysis_dir(analysis_id) / "tracking" / "tracking.json"
        if not tracking_path.is_file():
            return None
        try:
            payload = json.loads(tracking_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        candidate_id = payload.get("selected_player_candidate_id")
        track_id = payload.get("selected_player_track_id")
        source_ids = payload.get("selected_player_source_track_ids", [])
        if candidate_id is None and track_id is None:
            return None
        if not isinstance(source_ids, list) or not all(
            isinstance(item, int) for item in source_ids
        ):
            source_ids = []
        return PlayerSelectionInput(
            candidate_id=candidate_id if isinstance(candidate_id, str) else None,
            track_id=track_id if isinstance(track_id, int) else None,
            source_track_ids=source_ids,
        )

    def _ensure_inside_base(self, path: Path) -> None:
        if not _is_relative_to(path.resolve(), self.output_dir):
            raise JobRequestError("unsafe_path", "Path is outside the analysis output directory.")


def validate_relative_artifact_path(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    if not cleaned:
        raise JobRequestError("invalid_artifact_path", "Artifact path cannot be empty.")
    pure_path = PurePosixPath(cleaned)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise JobRequestError(
            "unsafe_artifact_path",
            "Artifact path must be relative to the analysis directory.",
        )
    return pure_path.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_kind(storage_key: str) -> str:
    first = PurePosixPath(storage_key).parts[0]
    return {
        "uploads": "source_video",
        "frames": "sampled_frame",
        "calibrations": "calibration",
        "tracking": "tracking",
        "analytics": "analytics",
        "active_play": "active_play",
        "ball": "ball_tracking",
        "stages": "stage_evidence",
    }.get(first, "metadata")


def _artifact_schema_version(storage_key: str) -> int | None:
    match = re.search(r"\.v([1-9][0-9]*)\.", PurePosixPath(storage_key).name)
    return int(match.group(1)) if match is not None else None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
