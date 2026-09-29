import io
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError

import pytest

from app.config import get_settings
from app.main import create_app
from app.services.tracking import model_provisioning
from app.services.tracking.exceptions import (
    DetectorModelInvalidError,
    DetectorModelMissingError,
)
from app.services.tracking.model_provisioning import detector_model_sha256, verify_detector_model
from scripts.provision_detector_model import main as provision_model


def test_provisioning_downloads_and_verifies_pinned_bytes_at_custom_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"verified model fixture"
    expected = sha256(payload).hexdigest()
    monkeypatch.setattr(model_provisioning, "DETECTOR_MODEL_SHA256", expected)

    def download(url: str, timeout: int) -> io.BytesIO:
        assert url == model_provisioning.DETECTOR_MODEL_SOURCE_URL
        assert timeout == 60
        return io.BytesIO(payload)

    monkeypatch.setattr(model_provisioning, "urlopen", download)
    destination = tmp_path / "custom models" / "detector.pt"
    assert provision_model(["--destination", str(destination)]) == 0
    assert destination.read_bytes() == payload
    assert verify_detector_model(destination, expected) == expected
    assert list(destination.parent.iterdir()) == [destination]


@pytest.mark.parametrize("failure", ["checksum", "network"])
@pytest.mark.parametrize("existing", [False, True])
def test_provisioning_failure_never_installs_unverified_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, existing: bool
) -> None:
    destination = tmp_path / "model.pt"
    original = b"previously verified model fixture"
    monkeypatch.setattr(model_provisioning, "DETECTOR_MODEL_SHA256", sha256(original).hexdigest())
    if existing:
        destination.write_bytes(original)

    def download(url: str, timeout: int) -> io.BytesIO:
        if failure == "network":
            raise URLError("model download unavailable")
        return io.BytesIO(b"wrong model bytes")

    monkeypatch.setattr(model_provisioning, "urlopen", download)
    with pytest.raises(model_provisioning.DetectorModelProvisioningError):
        provision_model(["--destination", str(destination)])
    if existing:
        assert destination.read_bytes() == original
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob("*.download"))


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
