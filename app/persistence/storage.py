from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.persistence.errors import PersistenceConfigurationError


@dataclass(frozen=True)
class LocalStorage:
    root: Path

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

    def _inside(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise PersistenceConfigurationError("Local storage path escaped its configured root.")
        return resolved
