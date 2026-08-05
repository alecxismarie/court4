from pathlib import Path
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.persistence.bootstrap import configured_bootstrap_identity
from app.persistence.errors import PersistenceConfigurationError
from app.persistence.storage import LocalStorage


def test_bootstrap_is_rejected_in_production() -> None:
    settings = Settings(
        environment="production",
        bootstrap_user_enabled=True,
        bootstrap_user_id=UUID("00000000-0000-4000-8000-000000000099"),
        bootstrap_user_identity="unsafe@example.invalid",
        auth_access_token_secret=SecretStr("production-test-secret-value-at-least-32-characters"),
        auth_frontend_base_url="https://court4.example",
        frontend_allowed_origins=("https://court4.example",),
        auth_email_backend="resend",
        resend_api_key=SecretStr("re_test_configuration_only"),
        email_from_address="no-reply@lexora.ltd",
        registration_enabled=False,
        auth_development_email_sink_enabled=False,
        auth_cookie_secure=True,
    )
    with pytest.raises(PersistenceConfigurationError):
        configured_bootstrap_identity(settings)


def test_bootstrap_requires_explicit_identity() -> None:
    settings = Settings(environment="test", bootstrap_user_enabled=False)
    with pytest.raises(PersistenceConfigurationError):
        configured_bootstrap_identity(settings)


def test_local_storage_rejects_escape(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    with pytest.raises(PersistenceConfigurationError):
        storage.resolve("analysis", "../outside")
