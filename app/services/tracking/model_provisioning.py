from __future__ import annotations

import hmac
import shutil
import tempfile
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.services.tracking.exceptions import (
    DetectorModelInvalidError,
    DetectorModelMissingError,
)

DETECTOR_MODEL_IDENTIFIER = "ultralytics-yolo11n-assets-v8.3.0"
DETECTOR_MODEL_FILENAME = "yolo11n.pt"
DETECTOR_MODEL_SOURCE_URL = (
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
)
DETECTOR_MODEL_SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"


class DetectorModelProvisioningError(RuntimeError):
    """Raised when the pinned detector artifact cannot be provisioned safely."""


def detector_model_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_detector_model(path: Path, expected_sha256: str) -> str:
    resolved = path.expanduser()
    if not resolved.exists():
        raise DetectorModelMissingError(
            "Detector model file does not exist. Provision the pinned Court4 detector model at "
            f"{resolved}."
        )
    if not resolved.is_file():
        raise DetectorModelMissingError(f"Detector model path is not a file: {resolved}")
    actual_sha256 = detector_model_sha256(resolved)
    if not hmac.compare_digest(actual_sha256, expected_sha256.casefold()):
        raise DetectorModelInvalidError(
            "Detector model checksum mismatch. Refusing to load unverified model bytes at "
            f"{resolved}."
        )
    return actual_sha256


def provision_pinned_detector_model(destination: Path) -> str:
    """Download the one pinned Court4 model and atomically install verified bytes."""
    resolved = destination.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=resolved.parent,
            prefix=f".{resolved.name}.",
            suffix=".download",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with urlopen(DETECTOR_MODEL_SOURCE_URL, timeout=60) as response:  # noqa: S310
                shutil.copyfileobj(response, temporary)
        verify_detector_model(temporary_path, DETECTOR_MODEL_SHA256)
        temporary_path.replace(resolved)
    except (OSError, URLError, DetectorModelInvalidError) as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise DetectorModelProvisioningError(
            f"Could not provision {DETECTOR_MODEL_IDENTIFIER} with its pinned checksum."
        ) from exc
    return verify_detector_model(resolved, DETECTOR_MODEL_SHA256)
