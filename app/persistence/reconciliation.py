from __future__ import annotations

import hashlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Analysis, AnalysisArtifact
from app.persistence.storage import LocalStorage


@dataclass(frozen=True)
class StorageReconciliationReport:
    scanned_database_records: int
    scanned_files: int
    matched_records: int
    missing_files: tuple[str, ...]
    orphan_files: tuple[str, ...]
    duplicate_storage_keys: tuple[str, ...]
    checksum_mismatches: tuple[str, ...]
    size_mismatches: tuple[str, ...]
    unavailable_marked_available: tuple[str, ...]
    temporary_files: tuple[str, ...]
    abandoned_upload_directories: tuple[str, ...]
    legacy_files: tuple[str, ...]
    invalid_relative_paths: tuple[str, ...]
    cross_owner_inconsistencies: tuple[str, ...]
    database_bytes: int
    filesystem_bytes: int
    recommended_action: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StorageReconciler:
    """Read-only comparison of PostgreSQL artifact metadata and local bytes."""

    def __init__(self, session_factory: sessionmaker[Session], root: Path) -> None:
        self.session_factory = session_factory
        self.storage = LocalStorage(root)

    def reconcile(self) -> StorageReconciliationReport:
        root = self.storage.root
        root.mkdir(parents=True, exist_ok=True)
        with self.session_factory() as session:
            artifacts = list(session.scalars(select(AnalysisArtifact)).all())
            owners: dict[str, UUID] = {
                analysis_id: owner_id
                for analysis_id, owner_id in session.execute(
                    select(Analysis.id, Analysis.owner_user_id)
                ).all()
            }

        checksum_paths = sorted(
            {
                self.storage.resolve(artifact.analysis_id, artifact.storage_key)
                for artifact in artifacts
                if artifact.storage_provider == "local"
                and self._is_safe_key(artifact.analysis_id, artifact.storage_key)
                and self.storage.resolve(artifact.analysis_id, artifact.storage_key).is_file()
            }
        )
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(checksum_paths)))) as executor:
            checksums = dict(
                zip(checksum_paths, executor.map(_sha256, checksum_paths), strict=True)
            )

        filesystem_files = sorted(path for path in root.rglob("*") if path.is_file())
        filesystem_bytes = sum(path.stat().st_size for path in filesystem_files)
        temporary_files = sorted(
            self._relative(path)
            for path in filesystem_files
            if self._relative(path).startswith("_uploads/")
        )
        legacy_files = sorted(
            self._relative(path) for path in filesystem_files if path.name == "job.json"
        )
        abandoned_upload_directories = (
            tuple(
                sorted(
                    self._relative(path) for path in (root / "_uploads").glob("*") if path.is_dir()
                )
            )
            if (root / "_uploads").is_dir()
            else ()
        )

        missing: list[str] = []
        checksum_mismatches: list[str] = []
        size_mismatches: list[str] = []
        unavailable_available: list[str] = []
        invalid_paths: list[str] = []
        cross_owner: list[str] = []
        matched = 0
        expected_files: set[str] = set()
        keys: list[str] = []
        database_bytes = 0

        for artifact in sorted(
            artifacts,
            key=lambda item: (item.analysis_id, item.storage_provider, item.storage_key),
        ):
            reference = self._reference(artifact.analysis_id, artifact.storage_key)
            keys.append(
                f"{artifact.analysis_id}/{artifact.storage_provider}/{artifact.storage_key}"
            )
            database_bytes += artifact.size_bytes
            if owners.get(artifact.analysis_id) != artifact.owner_user_id:
                cross_owner.append(reference)
            if artifact.storage_provider != "local":
                continue
            if not self._is_safe_key(artifact.analysis_id, artifact.storage_key):
                invalid_paths.append(reference)
                continue
            path = self.storage.resolve(artifact.analysis_id, artifact.storage_key)
            relative = self._relative(path)
            expected_files.add(relative)
            if not path.is_file():
                missing.append(reference)
                if artifact.state == "available":
                    unavailable_available.append(reference)
                continue
            mismatch = False
            if path.stat().st_size != artifact.size_bytes:
                size_mismatches.append(reference)
                mismatch = True
            if checksums[path] != artifact.checksum_sha256:
                checksum_mismatches.append(reference)
                mismatch = True
            if not mismatch:
                matched += 1

        counted_keys = Counter(keys)
        duplicate_keys = sorted(key for key, count in counted_keys.items() if count > 1)
        excluded = set(temporary_files) | set(legacy_files)
        orphan_files = sorted(
            self._relative(path)
            for path in filesystem_files
            if self._relative(path) not in expected_files
            and self._relative(path) not in excluded
            and not self._relative(path).startswith("_quarantine/")
        )
        discrepancy_count = sum(
            len(items)
            for items in (
                missing,
                orphan_files,
                duplicate_keys,
                checksum_mismatches,
                size_mismatches,
                invalid_paths,
                cross_owner,
                temporary_files,
            )
        )
        recommendation = (
            "No action required; retain the report with deployment evidence."
            if discrepancy_count == 0
            else "Review every finding; reconcile or quarantine explicitly before any deletion."
        )
        return StorageReconciliationReport(
            scanned_database_records=len(artifacts),
            scanned_files=len(filesystem_files),
            matched_records=matched,
            missing_files=tuple(sorted(missing)),
            orphan_files=tuple(orphan_files),
            duplicate_storage_keys=tuple(duplicate_keys),
            checksum_mismatches=tuple(sorted(checksum_mismatches)),
            size_mismatches=tuple(sorted(size_mismatches)),
            unavailable_marked_available=tuple(sorted(unavailable_available)),
            temporary_files=tuple(temporary_files),
            abandoned_upload_directories=abandoned_upload_directories,
            legacy_files=tuple(legacy_files),
            invalid_relative_paths=tuple(sorted(invalid_paths)),
            cross_owner_inconsistencies=tuple(sorted(cross_owner)),
            database_bytes=database_bytes,
            filesystem_bytes=filesystem_bytes,
            recommended_action=recommendation,
        )

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.storage.root).as_posix()

    @staticmethod
    def _reference(analysis_id: str, storage_key: str) -> str:
        return f"{analysis_id}/{storage_key}"

    @staticmethod
    def _is_safe_key(analysis_id: str, storage_key: str) -> bool:
        if not analysis_id or "/" in analysis_id or "\\" in analysis_id:
            return False
        key = PurePosixPath(storage_key.replace("\\", "/"))
        return bool(key.parts) and not key.is_absolute() and ".." not in key.parts


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
