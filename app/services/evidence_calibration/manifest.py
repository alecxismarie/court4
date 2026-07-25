import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.schemas.evidence_calibration import CalibrationManifest


class CalibrationManifestError(ValueError):
    """Raised when a calibration manifest cannot be read or validated."""


@dataclass(frozen=True)
class LoadedCalibrationManifest:
    manifest: CalibrationManifest
    sha256: str
    source_path: Path


def load_calibration_manifest(path: Path) -> LoadedCalibrationManifest:
    source_path = path.expanduser().resolve()
    try:
        raw_bytes = source_path.read_bytes()
    except OSError as exc:
        raise CalibrationManifestError(f"Calibration manifest could not be read: {path}") from exc

    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise CalibrationManifestError(
            f"Calibration manifest contains invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        manifest = CalibrationManifest.model_validate(payload)
    except ValidationError as exc:
        messages = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            messages.append(f"{location}: {error['msg']}")
        raise CalibrationManifestError(
            "Calibration manifest validation failed:\n- " + "\n- ".join(messages)
        ) from exc

    return LoadedCalibrationManifest(
        manifest=manifest,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        source_path=source_path,
    )
