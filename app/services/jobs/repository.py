from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

from pydantic import ValidationError

from app.persistence.errors import (
    OwnershipMismatchError,
    ResourceNotFoundError,
)
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.persistence.service import ArtifactInput, DuplicateVideoMatch, PlayerSelectionInput
from app.persistence.storage import LocalStorage
from app.schemas.jobs import AnalysisArtifact, AnalysisJob
from app.services.jobs.exceptions import JobNotFoundError, JobRequestError

ANALYSIS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class AnalysisJobRepository:
    """Compatibility façade whose authority is PostgreSQL, not ``job.json``."""

    def __init__(
        self,
        *,
        output_dir: Path,
        api_base_path: str,
        owner_user_id: UUID | None = None,
        persistence: PersistenceRuntime | None = None,
    ) -> None:
        self.output_dir = output_dir.expanduser().resolve()
        self.storage = LocalStorage(self.output_dir)
        self.api_base_path = api_base_path.rstrip("/")
        self.persistence = persistence or get_persistence()
        self.owner_user_id = owner_user_id or self.persistence.owner_user_id

    def create_or_replace_job(self, job: AnalysisJob) -> AnalysisJob:
        return self.save_job(job)

    def save_job(self, job: AnalysisJob) -> AnalysisJob:
        filesystem_artifacts = self._filesystem_artifacts(job.analysis_id)
        projected = job.model_copy(
            update={
                "available_artifacts": [
                    AnalysisArtifact(
                        path=artifact.storage_key,
                        url=(
                            f"{self.api_base_path}/analyses/{job.analysis_id}/artifacts/"
                            f"{artifact.storage_key}"
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
        return self.refresh_artifacts(self.load_job_metadata(analysis_id))

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
        return self.persistence.service.list_analysis_ids(
            owner_user_id=self.owner_user_id
        )

    def find_uploaded_video_by_owner_and_checksum(
        self, checksum_sha256: str
    ) -> DuplicateVideoMatch | None:
        return self.persistence.service.find_uploaded_video_by_owner_and_checksum(
            owner_user_id=self.owner_user_id,
            checksum_sha256=checksum_sha256,
        )

    def update_job(self, job: AnalysisJob, **updates: object) -> AnalysisJob:
        now = datetime.now(tz=UTC)
        updated = job.model_copy(update={**updates, "updated_at": now})
        return self.save_job(updated)

    def analysis_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        return self.storage.analysis_root(analysis_id)

    def staging_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        path = (self.output_dir / "_uploads" / analysis_id).resolve()
        self._ensure_inside_base(path)
        return path

    def resolve_artifact(self, analysis_id: str, artifact_path: str) -> Path:
        analysis_dir = self.analysis_dir(analysis_id)
        relative_path = validate_relative_artifact_path(artifact_path)
        try:
            self.persistence.service.get_artifact(
                owner_user_id=self.owner_user_id,
                analysis_id=analysis_id,
                storage_key=relative_path,
            )
        except (ResourceNotFoundError, OwnershipMismatchError):
            raise JobNotFoundError("Artifact was not found.") from None
        resolved = self.storage.resolve(analysis_id, relative_path)
        if not _is_relative_to(resolved, analysis_dir):
            raise JobRequestError("unsafe_artifact_path", "Artifact path is outside the analysis.")
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
                path=record.storage_key,
                url=(
                    f"{self.api_base_path}/analyses/{analysis_id}/artifacts/"
                    f"{record.storage_key}"
                ),
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
            artifacts.append(
                ArtifactInput(
                    storage_key=relative,
                    content_type=mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    size_bytes=path.stat().st_size,
                    checksum_sha256=_file_sha256(path),
                    artifact_kind=_artifact_kind(relative),
                )
            )
        return artifacts

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
    }.get(first, "metadata")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
