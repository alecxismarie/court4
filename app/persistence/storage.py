from __future__ import annotations

import logging
import os
import shutil
import socket
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import ClassVar, Literal

from app.persistence.errors import PersistenceConfigurationError

logger = logging.getLogger(__name__)

CapacityDecision = Literal["accepted", "warning", "active_limit", "hard_stop"]


@dataclass(frozen=True)
class StorageCapacitySnapshot:
    resolved_storage_root: str
    storage_root_exists: bool
    filesystem_total_bytes: int | None
    filesystem_used_bytes: int | None
    filesystem_free_bytes: int | None
    existing_reserved_bytes: int
    requested_reservation_bytes: int
    free_after_reservations: int | None
    warning_free_bytes: int
    hard_stop_free_bytes: int
    active_upload_count: int
    max_active_uploads: int
    decision: CapacityDecision
    pid: int
    hostname: str
    railway_deployment_id: str | None
    railway_replica_id: str | None
    railway_environment_id: str | None
    railway_environment_name: str | None
    railway_service_id: str | None
    railway_service_name: str | None
    railway_project_id: str | None
    railway_project_name: str | None
    railway_volume_mount_path: str | None
    software_commit_identifier: str | None
    deployment_build_identifier: str | None

    def log_context(self) -> dict[str, object]:
        return asdict(self)


class StorageCapacityError(RuntimeError):
    def __init__(
        self,
        reason: Literal["hard_stop", "active_limit"],
        *,
        snapshot: StorageCapacitySnapshot,
    ) -> None:
        self.reason = reason
        self.snapshot = snapshot
        super().__init__("Storage capacity is unavailable for a new upload.")


@dataclass(frozen=True)
class StorageCapacityStatus:
    state: Literal["available", "warning", "hard_stop"]
    free_bytes: int
    reserved_bytes: int
    requested_bytes: int


@dataclass
class StorageReservation:
    storage: LocalStorage
    reserved_bytes: int
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self.storage._release_capacity(self.reserved_bytes)
        self._released = True


@dataclass(frozen=True)
class LocalStorage:
    root: Path
    _capacity_lock: ClassVar[Lock] = Lock()
    _reserved_by_root: ClassVar[dict[Path, int]] = {}
    _active_by_root: ClassVar[dict[Path, int]] = {}

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser().resolve())

    def analysis_root(self, analysis_id: str) -> Path:
        if not analysis_id or any(part in analysis_id for part in ("/", "\\")):
            raise PersistenceConfigurationError("Analysis identifier is unsafe.")
        return self._inside(self.root / analysis_id)

    def resolve(self, analysis_id: str, storage_key: str) -> Path:
        key = PurePosixPath(storage_key.replace("\\", "/"))
        if key.is_absolute() or not key.parts or ".." in key.parts:
            raise PersistenceConfigurationError("Artifact storage key is unsafe.")
        return self._inside(self.analysis_root(analysis_id).joinpath(*key.parts))

    def relative_key(self, analysis_id: str, path: Path) -> str:
        return path.expanduser().resolve().relative_to(self.analysis_root(analysis_id)).as_posix()

    def ready(self) -> bool:
        """Confirm the configured persistence root exists and accepts durable writes."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                dir=self.root,
                prefix=".court4-readiness-",
                delete=True,
            ) as probe:
                probe.write(b"ready")
                probe.flush()
        except OSError:
            return False
        return True

    def capacity_status(
        self,
        *,
        requested_bytes: int,
        warning_free_bytes: int,
        hard_stop_free_bytes: int,
    ) -> StorageCapacityStatus:
        if requested_bytes < 0:
            raise ValueError("Requested storage reservation cannot be negative.")
        self.root.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(self.root).free
        with self._capacity_lock:
            reserved_bytes = self._reserved_by_root.get(self.root, 0)
        free_after_reservations = free_bytes - reserved_bytes - requested_bytes
        if free_after_reservations < hard_stop_free_bytes:
            state: Literal["available", "warning", "hard_stop"] = "hard_stop"
        elif free_after_reservations < warning_free_bytes:
            state = "warning"
        else:
            state = "available"
        return StorageCapacityStatus(
            state=state,
            free_bytes=free_bytes,
            reserved_bytes=reserved_bytes,
            requested_bytes=requested_bytes,
        )

    def reserve_capacity(
        self,
        *,
        requested_bytes: int,
        warning_free_bytes: int,
        hard_stop_free_bytes: int,
        max_active_uploads: int,
        software_commit_identifier: str | None = None,
        deployment_build_identifier: str | None = None,
    ) -> tuple[StorageReservation, StorageCapacityStatus]:
        if max_active_uploads < 1:
            raise ValueError("Maximum active uploads must be positive.")
        self.root.mkdir(parents=True, exist_ok=True)
        with self._capacity_lock:
            active = self._active_by_root.get(self.root, 0)
            reserved_bytes = self._reserved_by_root.get(self.root, 0)
            if active >= max_active_uploads:
                snapshot = self._capacity_snapshot(
                    filesystem_total_bytes=None,
                    filesystem_used_bytes=None,
                    filesystem_free_bytes=None,
                    existing_reserved_bytes=reserved_bytes,
                    requested_reservation_bytes=requested_bytes,
                    free_after_reservations=None,
                    warning_free_bytes=warning_free_bytes,
                    hard_stop_free_bytes=hard_stop_free_bytes,
                    active_upload_count=active,
                    max_active_uploads=max_active_uploads,
                    decision="active_limit",
                    software_commit_identifier=software_commit_identifier,
                    deployment_build_identifier=deployment_build_identifier,
                )
                self._log_capacity_decision(snapshot)
                raise StorageCapacityError("active_limit", snapshot=snapshot)
            filesystem = shutil.disk_usage(self.root)
            free_bytes = filesystem.free
            free_after_reservations = free_bytes - reserved_bytes - requested_bytes
            if free_after_reservations < hard_stop_free_bytes:
                snapshot = self._capacity_snapshot(
                    filesystem_total_bytes=filesystem.total,
                    filesystem_used_bytes=filesystem.used,
                    filesystem_free_bytes=free_bytes,
                    existing_reserved_bytes=reserved_bytes,
                    requested_reservation_bytes=requested_bytes,
                    free_after_reservations=free_after_reservations,
                    warning_free_bytes=warning_free_bytes,
                    hard_stop_free_bytes=hard_stop_free_bytes,
                    active_upload_count=active,
                    max_active_uploads=max_active_uploads,
                    decision="hard_stop",
                    software_commit_identifier=software_commit_identifier,
                    deployment_build_identifier=deployment_build_identifier,
                )
                self._log_capacity_decision(snapshot)
                raise StorageCapacityError("hard_stop", snapshot=snapshot)
            decision: Literal["accepted", "warning"] = (
                "warning" if free_after_reservations < warning_free_bytes else "accepted"
            )
            state: Literal["available", "warning"] = (
                "warning" if decision == "warning" else "available"
            )
            snapshot = self._capacity_snapshot(
                filesystem_total_bytes=filesystem.total,
                filesystem_used_bytes=filesystem.used,
                filesystem_free_bytes=free_bytes,
                existing_reserved_bytes=reserved_bytes,
                requested_reservation_bytes=requested_bytes,
                free_after_reservations=free_after_reservations,
                warning_free_bytes=warning_free_bytes,
                hard_stop_free_bytes=hard_stop_free_bytes,
                active_upload_count=active,
                max_active_uploads=max_active_uploads,
                decision=decision,
                software_commit_identifier=software_commit_identifier,
                deployment_build_identifier=deployment_build_identifier,
            )
            self._reserved_by_root[self.root] = reserved_bytes + requested_bytes
            self._active_by_root[self.root] = active + 1
            self._log_capacity_decision(snapshot)
        return (
            StorageReservation(storage=self, reserved_bytes=requested_bytes),
            StorageCapacityStatus(
                state=state,
                free_bytes=free_bytes,
                reserved_bytes=reserved_bytes,
                requested_bytes=requested_bytes,
            ),
        )

    def _capacity_snapshot(
        self,
        *,
        filesystem_total_bytes: int | None,
        filesystem_used_bytes: int | None,
        filesystem_free_bytes: int | None,
        existing_reserved_bytes: int,
        requested_reservation_bytes: int,
        free_after_reservations: int | None,
        warning_free_bytes: int,
        hard_stop_free_bytes: int,
        active_upload_count: int,
        max_active_uploads: int,
        decision: CapacityDecision,
        software_commit_identifier: str | None,
        deployment_build_identifier: str | None,
    ) -> StorageCapacitySnapshot:
        return StorageCapacitySnapshot(
            resolved_storage_root=str(self.root),
            storage_root_exists=self.root.is_dir(),
            filesystem_total_bytes=filesystem_total_bytes,
            filesystem_used_bytes=filesystem_used_bytes,
            filesystem_free_bytes=filesystem_free_bytes,
            existing_reserved_bytes=existing_reserved_bytes,
            requested_reservation_bytes=requested_reservation_bytes,
            free_after_reservations=free_after_reservations,
            warning_free_bytes=warning_free_bytes,
            hard_stop_free_bytes=hard_stop_free_bytes,
            active_upload_count=active_upload_count,
            max_active_uploads=max_active_uploads,
            decision=decision,
            pid=os.getpid(),
            hostname=socket.gethostname(),
            railway_deployment_id=os.environ.get("RAILWAY_DEPLOYMENT_ID"),
            railway_replica_id=os.environ.get("RAILWAY_REPLICA_ID"),
            railway_environment_id=os.environ.get("RAILWAY_ENVIRONMENT_ID"),
            railway_environment_name=os.environ.get("RAILWAY_ENVIRONMENT_NAME"),
            railway_service_id=os.environ.get("RAILWAY_SERVICE_ID"),
            railway_service_name=os.environ.get("RAILWAY_SERVICE_NAME"),
            railway_project_id=os.environ.get("RAILWAY_PROJECT_ID"),
            railway_project_name=os.environ.get("RAILWAY_PROJECT_NAME"),
            railway_volume_mount_path=os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"),
            software_commit_identifier=software_commit_identifier,
            deployment_build_identifier=deployment_build_identifier,
        )

    @staticmethod
    def _log_capacity_decision(snapshot: StorageCapacitySnapshot) -> None:
        log = logger.info if snapshot.decision == "accepted" else logger.warning
        log("storage_capacity_admission_decision", extra=snapshot.log_context())

    def _release_capacity(self, reserved_bytes: int) -> None:
        with self._capacity_lock:
            remaining = max(0, self._reserved_by_root.get(self.root, 0) - reserved_bytes)
            active = max(0, self._active_by_root.get(self.root, 0) - 1)
            if remaining:
                self._reserved_by_root[self.root] = remaining
            else:
                self._reserved_by_root.pop(self.root, None)
            if active:
                self._active_by_root[self.root] = active
            else:
                self._active_by_root.pop(self.root, None)

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise PersistenceConfigurationError("Local storage path escaped its configured root.")
        return resolved
