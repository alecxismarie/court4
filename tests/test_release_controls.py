from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.config import get_settings
from app.config.settings import Settings
from app.email.models import EmailMessage
from app.email.resend import ResendEmailSender
from app.main import create_app

PASSWORD = "correct horse battery staple"


def test_registration_can_be_closed_without_breaking_login() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test", registration_enabled=False
    )
    client = TestClient(app)
    closed = client.post(
        "/api/v1/auth/register",
        json={"email": "closed@example.com", "password": PASSWORD},
    )
    assert closed.status_code == 403
    assert closed.json()["error"]["code"] == "REGISTRATION_CLOSED"


def test_private_alpha_allowlist_uses_normalized_email() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        registration_enabled=True,
        private_alpha_allowlist_enabled=True,
        private_alpha_allowed_emails=("player@example.com",),
    )
    client = TestClient(app)
    allowed = client.post(
        "/api/v1/auth/register",
        json={"email": " Player@EXAMPLE.com ", "password": PASSWORD},
    )
    assert allowed.status_code == 201
    denied = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": PASSWORD},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PRIVATE_ALPHA_NOT_APPROVED"


def test_production_configuration_fails_closed_without_registration_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REGISTRATION_ENABLED", raising=False)
    monkeypatch.delenv("PICKLEBALL_AI_REGISTRATION_ENABLED", raising=False)
    with pytest.raises(ValidationError, match="REGISTRATION_ENABLED"):
        Settings(
            environment="production",
            auth_access_token_secret=SecretStr("production-secret-value-at-least-32-characters"),
            auth_frontend_base_url="https://alpha.court4.example",
            frontend_allowed_origins=("https://alpha.court4.example",),
            auth_email_backend="resend",
            resend_api_key=SecretStr("re_test_configuration_only"),
            email_from_address="no-reply@lexora.ltd",
            auth_development_email_sink_enabled=False,
            auth_cookie_secure=True,
        )


def test_internal_and_email_sink_routes_are_absent_in_production_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = Settings(
        environment="production",
        auth_access_token_secret=SecretStr("production-secret-value-at-least-32-characters"),
        auth_frontend_base_url="https://alpha.court4.example",
        auth_email_backend="resend",
        resend_api_key=SecretStr("re_test_configuration_only"),
        email_from_address="no-reply@lexora.ltd",
        auth_development_email_sink_enabled=False,
        auth_cookie_secure=True,
        registration_enabled=False,
        frontend_allowed_origins=("https://alpha.court4.example",),
    )
    monkeypatch.setattr("app.main.get_settings", lambda: production)
    client = TestClient(create_app())
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/internal/calibration-readiness" not in paths
    assert "/api/v1/auth/development/emails" not in paths
    assert "/api/v1/analyses/{analysis_id}/debug/active-play" not in paths
    assert client.get("/api/v1/internal/calibration-readiness").status_code == 404
    assert client.get("/api/v1/auth/development/emails").status_code == 404
    assert client.get("/api/v1/analyses/example/debug/active-play").status_code == 404
    assert client.post("/api/v1/analyses/example/debug/active-play").status_code == 404


def test_deployment_cors_requires_the_exact_https_frontend_origin() -> None:
    common: dict[str, Any] = {
        "environment": "staging",
        "auth_access_token_secret": SecretStr("staging-secret-value-at-least-32-characters"),
        "auth_frontend_base_url": "https://court4.lexora.ltd",
        "auth_email_backend": "brevo",
        "brevo_api_key": SecretStr("configuration-validation-only"),
        "email_from_address": "no-reply@lexora.ltd",
        "auth_development_email_sink_enabled": False,
        "auth_cookie_secure": True,
        "registration_enabled": False,
    }
    with pytest.raises(ValidationError, match="exact frontend origin"):
        Settings(
            **common,
            frontend_allowed_origins=("https://other.lexora.ltd",),
        )
    with pytest.raises(ValidationError, match="exact frontend origin"):
        Settings(
            **common,
            frontend_allowed_origins=("http://court4.lexora.ltd",),
        )

    settings = Settings(
        **common,
        frontend_allowed_origins=("https://court4.lexora.ltd",),
    )
    assert settings.frontend_allowed_origins == ("https://court4.lexora.ltd",)


def test_resend_adapter_handles_success_and_provider_failure() -> None:
    settings = Settings(
        environment="test",
        auth_email_backend="resend",
        allow_external_email_in_tests=True,
        resend_api_key=SecretStr("re_test_configuration_only"),
        email_from_address="alpha@court4.example",
    )
    message = EmailMessage(
        recipient="player@example.com",
        subject="Verify",
        text_body="Text",
        html_body="<p>Text</p>",
        category="email_verification",
        correlation_id="correlation-id",
    )
    success = ResendEmailSender(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"id": "mail-1"})),
    )
    assert success.send(message).provider_message_id == "mail-1"
    throttled = ResendEmailSender(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={})),
    )
    assert throttled.send(message).status == "failed"
