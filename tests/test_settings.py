from pathlib import Path

import pytest

from app.config.settings import Settings


def test_court4_detector_model_path_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PICKLEBALL_AI_DETECTOR_MODEL_PATH", "models/legacy.pt")
    monkeypatch.setenv("COURT4_DETECTOR_MODEL_PATH", "models/canonical.pt")

    settings = Settings()

    assert settings.detector_model_path == Path("models/canonical.pt")
