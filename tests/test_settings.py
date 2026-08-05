from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

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


def test_external_email_providers_fail_closed_in_tests() -> None:
    with pytest.raises(ValidationError, match="Tests require EMAIL_PROVIDER=development"):
        Settings(
            environment="test",
            auth_email_backend="brevo",
            brevo_api_key=SecretStr("test-key-that-must-never-be-used"),
        )


def test_test_email_provider_requires_the_development_sink() -> None:
    with pytest.raises(ValidationError, match="development email sink"):
        Settings(
            environment="test",
            auth_email_backend="development",
            auth_development_email_sink_enabled=False,
        )
