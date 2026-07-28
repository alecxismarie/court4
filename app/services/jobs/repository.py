import json
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from app.schemas.jobs import AnalysisArtifact, AnalysisJob
from app.services.jobs.exceptions import JobNotFoundError, JobRequestError

ANALYSIS_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class AnalysisJobRepository:
    def __init__(self, *, output_dir: Path, api_base_path: str) -> None:
        self.output_dir = output_dir.expanduser().resolve()
        self.api_base_path = api_base_path.rstrip("/")

    def create_or_replace_job(self, job: AnalysisJob) -> AnalysisJob:
        self._write_job(job)
        return self.refresh_artifacts(job)

    def save_job(self, job: AnalysisJob) -> AnalysisJob:
        refreshed = self.refresh_artifacts(job)
        self._write_job(refreshed)
        return refreshed

    def load_job(self, analysis_id: str) -> AnalysisJob:
        return self.refresh_artifacts(self.load_job_metadata(analysis_id))

    def load_job_metadata(self, analysis_id: str) -> AnalysisJob:
        """Read persisted job metadata without rescanning the artifact tree."""
        job_path = self.job_path(analysis_id)
        if not job_path.exists() or not job_path.is_file():
            raise JobNotFoundError()
        try:
            payload = json.loads(job_path.read_text(encoding="utf-8"))
            job = AnalysisJob.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError):
            raise JobRequestError(
                "invalid_job", "Analysis job metadata could not be read."
            ) from None
        return job

    def list_job_ids(self) -> list[str]:
        """List persisted analysis IDs without relying on browser-local history."""
        if not self.output_dir.exists():
            return []
        analysis_ids: list[str] = []
        for path in self.output_dir.iterdir():
            if (
                path.is_dir()
                and ANALYSIS_ID_PATTERN.fullmatch(path.name)
                and (path / "job.json").is_file()
            ):
                analysis_ids.append(path.name)
        return sorted(analysis_ids)

    def update_job(self, job: AnalysisJob, **updates: object) -> AnalysisJob:
        now = datetime.now(tz=UTC)
        updated = job.model_copy(update={**updates, "updated_at": now})
        return self.save_job(updated)

    def analysis_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        path = (self.output_dir / analysis_id).resolve()
        self._ensure_inside_base(path)
        return path

    def staging_dir(self, analysis_id: str) -> Path:
        self.validate_analysis_id(analysis_id)
        path = (self.output_dir / "_uploads" / analysis_id).resolve()
        self._ensure_inside_base(path)
        return path

    def job_path(self, analysis_id: str) -> Path:
        return self.analysis_dir(analysis_id) / "job.json"

    def resolve_artifact(self, analysis_id: str, artifact_path: str) -> Path:
        analysis_dir = self.analysis_dir(analysis_id)
        relative_path = validate_relative_artifact_path(artifact_path)
        resolved = (analysis_dir / Path(relative_path)).resolve()
        if not _is_relative_to(resolved, analysis_dir.resolve()):
            raise JobRequestError("unsafe_artifact_path", "Artifact path is outside the analysis.")
        return resolved

    def artifact_from_path(self, analysis_id: str, path: Path) -> AnalysisArtifact:
        analysis_dir = self.analysis_dir(analysis_id)
        relative_path = path.resolve().relative_to(analysis_dir.resolve()).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return AnalysisArtifact(
            path=relative_path,
            url=f"{self.api_base_path}/analyses/{analysis_id}/artifacts/{relative_path}",
            content_type=content_type,
            size_bytes=path.stat().st_size,
        )

    def list_artifacts(self, analysis_id: str) -> list[AnalysisArtifact]:
        analysis_dir = self.analysis_dir(analysis_id)
        if not analysis_dir.exists():
            return []
        artifacts = []
        for path in sorted(item for item in analysis_dir.rglob("*") if item.is_file()):
            if path.name == "job.json":
                continue
            artifacts.append(self.artifact_from_path(analysis_id, path))
        return artifacts

    def refresh_artifacts(self, job: AnalysisJob) -> AnalysisJob:
        return job.model_copy(update={"available_artifacts": self.list_artifacts(job.analysis_id)})

    def validate_analysis_id(self, analysis_id: str) -> str:
        if not ANALYSIS_ID_PATTERN.fullmatch(analysis_id):
            raise JobRequestError("invalid_analysis_id", "Analysis ID is invalid.")
        return analysis_id

    def _write_job(self, job: AnalysisJob) -> None:
        analysis_dir = self.analysis_dir(job.analysis_id)
        analysis_dir.mkdir(parents=True, exist_ok=True)
        job_path = analysis_dir / "job.json"
        job_path.write_text(
            json.dumps(job.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
