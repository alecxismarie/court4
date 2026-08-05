from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import ClassVar, Literal

from app.persistence.errors import PersistenceConfigurationError


class StorageCapacityError(RuntimeError):
    def __init__(self, reason: Literal["hard_stop", "active_limit"]) -> None:
        self.reason = reason
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
    ) -> tuple[StorageReservation, StorageCapacityStatus]:
        if max_active_uploads < 1:
            raise ValueError("Maximum active uploads must be positive.")
        self.root.mkdir(parents=True, exist_ok=True)
        with self._capacity_lock:
            active = self._active_by_root.get(self.root, 0)
            if active >= max_active_uploads:
                raise StorageCapacityError("active_limit")
            free_bytes = shutil.disk_usage(self.root).free
            reserved_bytes = self._reserved_by_root.get(self.root, 0)
            free_after_reservations = free_bytes - reserved_bytes - requested_bytes
            if free_after_reservations < hard_stop_free_bytes:
                raise StorageCapacityError("hard_stop")
            state: Literal["available", "warning", "hard_stop"] = (
                "warning" if free_after_reservations < warning_free_bytes else "available"
            )
            self._reserved_by_root[self.root] = reserved_bytes + requested_bytes
            self._active_by_root[self.root] = active + 1
        return (
            StorageReservation(storage=self, reserved_bytes=requested_bytes),
            StorageCapacityStatus(
                state=state,
                free_bytes=free_bytes,
                reserved_bytes=reserved_bytes,
                requested_bytes=requested_bytes,
            ),
        )

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
