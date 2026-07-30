from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.persistence.errors import MigrationDataInvalidError, ResourceNotFoundError
from app.persistence.service import ArtifactInput, PersistenceService
from app.schemas.jobs import AnalysisJob


@dataclass(frozen=True)
class LegacyRecord:
    analysis_id: str
    classification: str
    status: str | None
    stage: str | None
    artifact_count: int
    size_bytes: int
    issue: str | None = None


@dataclass(frozen=True)
class LegacyInventory:
    source: str
    records: tuple[LegacyRecord, ...]
    non_analysis_directories: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.classification] = counts.get(record.classification, 0) + 1
        return {
            "source": self.source,
            "record_count": len(self.records),
            "classifications": counts,
            "non_analysis_directory_count": len(self.non_analysis_directories),
            "records": [asdict(record) for record in self.records],
            "non_analysis_directories": list(self.non_analysis_directories),
        }


def inventory_legacy_source(source: Path) -> LegacyInventory:
    resolved = source.expanduser().resolve()
    if not resolved.is_dir():
        raise MigrationDataInvalidError("Legacy source must be an existing directory.")
    records: list[LegacyRecord] = []
    non_analysis: list[str] = []
    for directory in sorted(item for item in resolved.iterdir() if item.is_dir()):
        job_path = directory / "job.json"
        if not job_path.is_file():
            non_analysis.append(directory.name)
            continue
        files = [item for item in directory.rglob("*") if item.is_file()]
        size_bytes = sum(item.stat().st_size for item in files)
        try:
            payload = json.loads(job_path.read_text(encoding="utf-8"))
            job = AnalysisJob.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            records.append(
                LegacyRecord(
                    analysis_id=directory.name,
                    classification="malformed",
                    status=None,
                    stage=None,
                    artifact_count=max(0, len(files) - 1),
                    size_bytes=size_bytes,
                    issue=type(exc).__name__,
                )
            )
            continue
        classification = (
            "valuable"
            if job.status.value == "completed" and job.current_stage.value == "analyzed"
            else "incomplete"
        )
        records.append(
            LegacyRecord(
                analysis_id=job.analysis_id,
                classification=classification,
                status=job.status.value,
                stage=job.current_stage.value,
                artifact_count=max(0, len(files) - 1),
                size_bytes=size_bytes,
            )
        )
    return LegacyInventory(str(resolved), tuple(records), tuple(non_analysis))


def import_legacy_source(
    *,
    source: Path,
    service: PersistenceService,
    owner_user_id: UUID,
    dry_run: bool,
) -> dict[str, Any]:
    inventory = inventory_legacy_source(source)
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "owner_user_id": str(owner_user_id),
        **inventory.summary(),
        "imported": [],
        "already_present": [],
        "skipped": [],
    }
    if dry_run:
        return result
    source_root = Path(inventory.source)
    for record in inventory.records:
        if record.classification == "malformed":
            result["skipped"].append({"analysis_id": record.analysis_id, "reason": "malformed"})
            continue
        directory = source_root / record.analysis_id
        payload = json.loads((directory / "job.json").read_text(encoding="utf-8"))
        try:
            service.load_job(owner_user_id=owner_user_id, analysis_id=record.analysis_id)
        except ResourceNotFoundError:
            already_present = False
        else:
            already_present = True
        artifacts = [
            _artifact_input(directory, path)
            for path in sorted(item for item in directory.rglob("*") if item.is_file())
            if path.name != "job.json"
        ]
        service.persist_job(
            owner_user_id=owner_user_id,
            payload=payload,
            artifacts=artifacts,
            compatibility_import=True,
        )
        destination = "already_present" if already_present else "imported"
        result[destination].append(record.analysis_id)
    return result


def _artifact_input(root: Path, path: Path) -> ArtifactInput:
    relative = path.relative_to(root).as_posix()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return ArtifactInput(
        storage_key=relative,
        content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        size_bytes=path.stat().st_size,
        checksum_sha256=digest.hexdigest(),
        artifact_kind=relative.split("/", 1)[0],
    )
