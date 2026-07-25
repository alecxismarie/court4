from pathlib import Path

import pytest

from app.config.settings import Settings


def test_comma_separated_sequence_settings_are_parsed_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PICKLEBALL_AI_SUPPORTED_EXTENSIONS", "mp4, .MOV,avi")
    monkeypatch.setenv(
        "PICKLEBALL_AI_FRONTEND_ALLOWED_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:3000",
    )

    settings = Settings()

    assert settings.supported_extensions == (".mp4", ".mov", ".avi")
    assert settings.frontend_allowed_origins == (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def test_court4_detector_model_path_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PICKLEBALL_AI_DETECTOR_MODEL_PATH", "models/legacy.pt")
    monkeypatch.setenv("COURT4_DETECTOR_MODEL_PATH", "models/canonical.pt")

    settings = Settings()

    assert settings.detector_model_path == Path("models/canonical.pt")
