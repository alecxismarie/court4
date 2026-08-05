from __future__ import annotations

import logging

import httpx

from app.config.settings import Settings
from app.email.models import DeliveryResult, EmailMessage

logger = logging.getLogger(__name__)

BREVO_TRANSACTIONAL_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailSender:
    """Thin Brevo transactional-email adapter with sanitized failure reporting."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        if settings.brevo_api_key is None or not settings.brevo_api_key.get_secret_value().strip():
            raise ValueError("Brevo API key is required.")
        self._api_key = settings.brevo_api_key.get_secret_value()
        self._sender_name = settings.email_from_name
        self._sender_address = settings.email_from_address
        self._timeout = settings.email_request_timeout_seconds
        self._transport = transport

    def send(self, message: EmailMessage) -> DeliveryResult:
        payload = {
            "sender": {"name": self._sender_name, "email": self._sender_address},
            "to": [{"email": message.recipient}],
            "subject": message.subject,
            "textContent": message.text_body,
            "htmlContent": message.html_body,
            "headers": {"X-Court4-Correlation-ID": message.correlation_id},
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    BREVO_TRANSACTIONAL_EMAIL_URL,
                    headers={
                        "api-key": self._api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException:
            return self._failed(message, "timeout")
        except httpx.RequestError:
            return self._failed(message, "network")

        if response.status_code == 429:
            return self._failed(
                message,
                "throttled",
                status_code=response.status_code,
                retry_after=_safe_retry_after(response.headers.get("Retry-After")),
            )
        if response.status_code == 401:
            return self._failed(message, "authentication", status_code=response.status_code)
        if response.status_code == 403:
            return self._failed(message, "forbidden", status_code=response.status_code)
        if response.status_code == 400:
            return self._failed(message, "validation", status_code=response.status_code)
        if response.status_code >= 500:
            return self._failed(message, "unavailable", status_code=response.status_code)
        if not 200 <= response.status_code < 300:
            return self._failed(message, "provider_error", status_code=response.status_code)

        try:
            response_payload = response.json()
        except (ValueError, TypeError):
            return self._failed(message, "malformed_response", status_code=response.status_code)
        if not isinstance(response_payload, dict):
            return self._failed(message, "malformed_response", status_code=response.status_code)
        provider_id = response_payload.get("messageId")
        if not isinstance(provider_id, str) or not provider_id.strip():
            return self._failed(message, "malformed_response", status_code=response.status_code)

        logger.info(
            "brevo_email_sent",
            extra={
                "provider": "brevo",
                "category": message.category,
                "correlation_id": message.correlation_id,
                "provider_message_id": provider_id,
            },
        )
        return DeliveryResult(status="sent", provider_message_id=provider_id)

    @staticmethod
    def _failed(
        message: EmailMessage,
        failure_category: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
    ) -> DeliveryResult:
        logger.warning(
            "brevo_email_delivery_failed",
            extra={
                "provider": "brevo",
                "category": message.category,
                "correlation_id": message.correlation_id,
                "failure_category": failure_category,
                "status_code": status_code,
                "retry_after": retry_after,
            },
        )
        return DeliveryResult(status="failed")


def _safe_retry_after(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned[:128] if cleaned else None
