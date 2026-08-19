from pathlib import Path

import pytest

from app.config import get_settings
from app.main import create_app
from app.services.tracking.exceptions import (
    DetectorModelInvalidError,
    DetectorModelMissingError,
)
from app.services.tracking.model_provisioning import detector_model_sha256, verify_detector_model


def test_detector_model_verification_accepts_only_expected_bytes(tmp_path: Path) -> None:
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"pinned-model-bytes")
    expected = detector_model_sha256(model_path)

    assert verify_detector_model(model_path, expected) == expected

    model_path.write_bytes(b"tampered-model-bytes")
    with pytest.raises(DetectorModelInvalidError, match="checksum mismatch"):
        verify_detector_model(model_path, expected)


def test_detector_model_verification_fails_clearly_when_missing(tmp_path: Path) -> None:
    with pytest.raises(DetectorModelMissingError, match="Provision the pinned"):
        verify_detector_model(tmp_path / "missing.pt", "0" * 64)


def test_ultralytics_default_fails_application_start_without_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PICKLEBALL_AI_DEFAULT_TRACKING_BACKEND", "ultralytics")
    monkeypatch.setenv("COURT4_DETECTOR_MODEL_PATH", str(tmp_path / "missing.pt"))
    get_settings.cache_clear()
    try:
        with pytest.raises(DetectorModelMissingError, match="Provision the pinned"):
            create_app()
    finally:
        get_settings.cache_clear()
