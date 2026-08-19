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
        "http://localhost:3000",
    )

    settings = Settings()

    assert settings.supported_extensions == (".mp4", ".mov", ".avi")
    assert settings.frontend_allowed_origins == ("http://localhost:3000",)


def test_mixed_local_frontend_origins_are_rejected() -> None:
    with pytest.raises(ValidationError, match="exact frontend origin"):
        Settings(
            frontend_allowed_origins=(
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            )
        )


def test_canonical_local_and_staging_origin_topologies() -> None:
    local = Settings()
    assert local.auth_frontend_base_url == "http://localhost:3000"
    assert local.frontend_allowed_origins == ("http://localhost:3000",)
    assert local.refresh_cookie_secure is False

    staging = Settings(
        environment="staging",
        auth_access_token_secret=SecretStr("staging-secret-value-at-least-32-characters"),
        auth_frontend_base_url="https://court4.lexora.ltd",
        frontend_allowed_origins=("https://court4.lexora.ltd",),
        auth_email_backend="brevo",
        brevo_api_key=SecretStr("configuration-validation-only"),
        email_from_address="no-reply@lexora.ltd",
        auth_development_email_sink_enabled=False,
        auth_cookie_secure=True,
        registration_enabled=False,
    )
    assert staging.refresh_cookie_secure is True
    assert staging.auth_cookie_samesite == "lax"


def test_court4_detector_model_path_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PICKLEBALL_AI_DETECTOR_MODEL_PATH", "models/legacy.pt")
    monkeypatch.setenv("COURT4_DETECTOR_MODEL_PATH", "models/canonical.pt")

    settings = Settings()

    assert settings.detector_model_path == Path("models/canonical.pt")


def test_court4_detector_model_checksum_alias_is_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COURT4_DETECTOR_MODEL_SHA256", "a" * 64)
    assert Settings().detector_model_sha256 == "a" * 64

    monkeypatch.setenv("COURT4_DETECTOR_MODEL_SHA256", "unversioned-latest")
    with pytest.raises(ValidationError):
        Settings()


def test_external_email_providers_fail_closed_in_tests() -> None:
    with pytest.raises(ValidationError, match="Tests require EMAIL_PROVIDER=development"):
        Settings(
            environment="test",
            auth_email_backend="brevo",
            brevo_api_key=SecretStr("test-key-that-must-never-be-used"),
        )


def test_test_environment_never_loads_root_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".env").write_text(
        "EMAIL_PROVIDER=brevo\n"
        "BREVO_API_KEY=must-not-be-read\n"
        "NEXT_PUBLIC_API_BASE_URL=https://must-not-be-parsed.example\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert settings.environment == "test"
    assert settings.auth_email_backend == "development"
    assert settings.brevo_api_key is not None
    assert settings.brevo_api_key.get_secret_value() == ""


def test_test_email_provider_requires_the_development_sink() -> None:
    with pytest.raises(ValidationError, match="development email sink"):
        Settings(
            environment="test",
            auth_email_backend="development",
            auth_development_email_sink_enabled=False,
        )


def test_compose_uses_runtime_env_and_isolates_test_email_configuration() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "- .env.example" not in compose
    assert "path: .env" in compose
    assert "required: true" in compose
    api_test = compose.split("  api-test:", 1)[1].split("volumes:", 1)[0]
    assert "env_file:" not in api_test
    assert "EMAIL_PROVIDER: development" in api_test
    assert 'ALLOW_EXTERNAL_EMAIL_IN_TESTS: "false"' in api_test
    assert 'BREVO_API_KEY: ""' in api_test
    assert 'RESEND_API_KEY: ""' in api_test
