from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.config.settings import Settings
from app.email.brevo import BREVO_TRANSACTIONAL_EMAIL_URL, BrevoEmailSender
from app.email.dependencies import (
    get_account_email_service,
    get_development_email_sink,
    get_email_sender,
)
from app.email.development import DevelopmentEmailSink
from app.email.models import DeliveryResult, EmailMessage
from app.email.resend import ResendEmailSender
from app.email.service import AccountEmailService
from app.main import create_app
from app.persistence.models import User
from app.persistence.runtime import get_persistence

API_KEY = "test-brevo-api-key-not-a-secret"
RAW_SECURITY_TOKEN = "raw-security-token-must-not-be-logged"


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "auth_email_backend": "brevo",
        "allow_external_email_in_tests": True,
        "brevo_api_key": SecretStr(API_KEY),
        "email_from_address": "no-reply@lexora.ltd",
        "email_from_name": "Court4",
        "auth_frontend_base_url": "http://localhost:3000",
    }
    values.update(updates)
    return Settings.model_validate(values)


def _production_settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "auth_access_token_secret": SecretStr(
            "production-test-secret-value-at-least-32-characters"
        ),
        "auth_email_backend": "brevo",
        "brevo_api_key": SecretStr(API_KEY),
        "email_from_address": "no-reply@lexora.ltd",
        "email_from_name": "Court4",
        "auth_frontend_base_url": "https://alpha.court4.example",
        "auth_development_email_sink_enabled": False,
        "auth_cookie_secure": True,
        "registration_enabled": False,
        "frontend_allowed_origins": ("https://alpha.court4.example",),
    }
    values.update(updates)
    return Settings.model_validate(values)


def _message() -> EmailMessage:
    return EmailMessage(
        recipient="player@example.com",
        subject="Verify your Court4 email",
        text_body=f"Open the verification link containing {RAW_SECURITY_TOKEN}",
        html_body=f"<p>Open the verification link containing {RAW_SECURITY_TOKEN}</p>",
        category="email_verification",
        correlation_id="correlation-id",
    )


def _sender(handler: Callable[[httpx.Request], httpx.Response]) -> BrevoEmailSender:
    return BrevoEmailSender(_settings(), transport=httpx.MockTransport(handler))


def _capture_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, object]]]:
    records: list[tuple[str, dict[str, object]]] = []

    def warning(message: str, *, extra: dict[str, object]) -> None:
        records.append((message, extra))

    monkeypatch.setattr("app.email.brevo.logger.warning", warning)
    return records


def test_provider_selection_returns_brevo_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.email.dependencies.get_settings", _settings)
    assert isinstance(get_email_sender(), BrevoEmailSender)


def test_brevo_request_maps_court4_message_and_preserves_message_id() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["payload"] = json.loads(request.content)
        return httpx.Response(201, json={"messageId": "brevo-message-1"})

    result = _sender(handler).send(_message())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert str(request.url) == BREVO_TRANSACTIONAL_EMAIL_URL
    assert request.headers["api-key"] == API_KEY
    assert request.headers["Content-Type"] == "application/json"
    assert request.headers["Accept"] == "application/json"
    assert captured["payload"] == {
        "sender": {"name": "Court4", "email": "no-reply@lexora.ltd"},
        "to": [{"email": "player@example.com"}],
        "subject": "Verify your Court4 email",
        "textContent": f"Open the verification link containing {RAW_SECURITY_TOKEN}",
        "htmlContent": f"<p>Open the verification link containing {RAW_SECURITY_TOKEN}</p>",
        "headers": {"X-Court4-Correlation-ID": "correlation-id"},
    }
    assert result.status == "sent"
    assert result.provider_message_id == "brevo-message-1"


@pytest.mark.parametrize(
    ("status_code", "failure_category"),
    [
        (400, "validation"),
        (401, "authentication"),
        (403, "forbidden"),
        (429, "throttled"),
        (500, "unavailable"),
    ],
)
def test_brevo_http_failures_are_classified_safely(
    status_code: int,
    failure_category: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _capture_warnings(monkeypatch)
    sender = _sender(
        lambda request: httpx.Response(
            status_code,
            headers={"Retry-After": "12"},
            json={"message": f"provider body containing {RAW_SECURITY_TOKEN}"},
        )
    )

    result = sender.send(_message())

    assert result.status == "failed"
    _, metadata = records[-1]
    assert metadata["failure_category"] == failure_category
    assert metadata["status_code"] == status_code
    if status_code == 429:
        assert metadata["retry_after"] == "12"
    assert API_KEY not in repr(records)
    assert RAW_SECURITY_TOKEN not in repr(records)


@pytest.mark.parametrize("failure", ["timeout", "network"])
def test_brevo_transport_failures_are_classified_safely(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _capture_warnings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout", request=request)
        raise httpx.ConnectError("test network error", request=request)

    result = _sender(handler).send(_message())

    assert result.status == "failed"
    assert records[-1][1]["failure_category"] == failure
    assert API_KEY not in repr(records)
    assert RAW_SECURITY_TOKEN not in repr(records)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(201, text="not-json"),
        httpx.Response(201, json={}),
        httpx.Response(201, json={"messageId": ""}),
        httpx.Response(201, json=[]),
    ],
)
def test_brevo_malformed_success_response_fails_safely(
    response: httpx.Response,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = _capture_warnings(monkeypatch)
    result = _sender(lambda request: response).send(_message())
    assert result.status == "failed"
    assert records[-1][1]["failure_category"] == "malformed_response"


@pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("   ")])
def test_brevo_selection_requires_nonempty_credentials(key: SecretStr | None) -> None:
    with pytest.raises(ValidationError, match="BREVO_API_KEY"):
        _settings(brevo_api_key=key)


@pytest.mark.parametrize(
    "sender",
    [
        "court4@localhost.invalid",
        "sender@example.com",
        "sender@example.net",
        "sender@court4.example",
        "",
    ],
)
def test_production_rejects_invalid_or_placeholder_sender(sender: str) -> None:
    with pytest.raises(ValidationError, match="EMAIL_FROM_ADDRESS"):
        _production_settings(email_from_address=sender)


def test_development_allows_localhost_frontend_url() -> None:
    settings = Settings(
        environment="development",
        auth_email_backend="development",
        auth_frontend_base_url="http://localhost:3000",
    )
    assert settings.auth_frontend_base_url == "http://localhost:3000"


def test_production_rejects_insecure_frontend_url() -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        _production_settings(auth_frontend_base_url="http://alpha.court4.example")


@pytest.mark.parametrize("key", [None, SecretStr(""), SecretStr("   ")])
def test_production_rejects_missing_or_empty_brevo_credentials(key: SecretStr | None) -> None:
    with pytest.raises(ValidationError, match="BREVO_API_KEY"):
        _production_settings(brevo_api_key=key)


def test_production_accepts_structurally_valid_brevo_configuration() -> None:
    settings = _production_settings()
    assert settings.auth_email_backend == "brevo"
    assert settings.email_from_address == "no-reply@lexora.ltd"


def test_unsupported_provider_is_rejected() -> None:
    with pytest.raises(ValidationError, match="development.*resend.*brevo"):
        Settings.model_validate({"auth_email_backend": "unsupported"})


def test_existing_resend_and_development_selection_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resend = Settings(
        environment="test",
        auth_email_backend="resend",
        allow_external_email_in_tests=True,
        resend_api_key=SecretStr("re_test_configuration_only"),
        email_from_address="alpha@court4.example",
    )
    monkeypatch.setattr("app.email.dependencies.get_settings", lambda: resend)
    assert isinstance(get_email_sender(), ResendEmailSender)

    development = Settings(environment="test", auth_email_backend="development")
    monkeypatch.setattr("app.email.dependencies.get_settings", lambda: development)
    assert get_email_sender() is get_development_email_sink()
    assert isinstance(get_email_sender(), DevelopmentEmailSink)


def test_registration_rolls_back_when_brevo_delivery_is_unavailable() -> None:
    settings = _settings(registration_enabled=True)
    sender = BrevoEmailSender(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={})),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_email_service] = lambda: AccountEmailService(
        sender, settings
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "brevo-failure@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMAIL_DELIVERY_UNAVAILABLE"
    with get_persistence().session_factory() as session:
        assert session.scalar(select(User).where(User.email == "brevo-failure@example.com")) is None


def test_brevo_registration_reports_only_external_delivery_mode() -> None:
    settings = _settings(registration_enabled=True)
    sender = BrevoEmailSender(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(201, json={"messageId": "mocked-message"})
        ),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_account_email_service] = lambda: AccountEmailService(
        sender, settings
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "external-success@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 201
    assert response.json()["user"]["verification_delivery_mode"] == "external"
    assert "brevo" not in response.text.casefold()


def test_resend_delivery_failure_never_claims_success() -> None:
    development = Settings(environment="test", auth_email_backend="development")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: development
    client = TestClient(app)
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "resend-failure@example.com", "password": "correct horse battery staple"},
    )
    assert registration.status_code == 201
    app.dependency_overrides[get_account_email_service] = lambda: AccountEmailService(
        _AlwaysFailingSender(), development
    )

    resent = client.post(
        "/api/v1/auth/resend-verification",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
    )

    assert resent.status_code == 503
    assert resent.json()["error"]["code"] == "EMAIL_DELIVERY_UNAVAILABLE"
    assert "sent" not in resent.text.casefold()


class _AlwaysFailingSender:
    def send(self, message: EmailMessage) -> DeliveryResult:
        del message
        return DeliveryResult(status="failed")
