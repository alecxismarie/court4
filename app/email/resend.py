from __future__ import annotations

import httpx

from app.config.settings import Settings
from app.email.models import DeliveryResult, EmailMessage


class ResendEmailSender:
    """Thin transactional adapter; Court4 retains ownership of message templates."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        if settings.resend_api_key is None:
            raise ValueError("Resend API key is required.")
        self._api_key = settings.resend_api_key.get_secret_value()
        self._from = f"{settings.email_from_name} <{settings.email_from_address}>"
        self._timeout = settings.email_request_timeout_seconds
        self._transport = transport

    def send(self, message: EmailMessage) -> DeliveryResult:
        try:
            with httpx.Client(
                base_url="https://api.resend.com",
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.post(
                    "/emails",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": self._from,
                        "to": [message.recipient],
                        "subject": message.subject,
                        "text": message.text_body,
                        "html": message.html_body,
                        "headers": {"X-Entity-Ref-ID": message.correlation_id},
                    },
                )
                response.raise_for_status()
                provider_id = response.json().get("id")
                if not isinstance(provider_id, str) or not provider_id:
                    return DeliveryResult(status="failed")
                return DeliveryResult(status="sent", provider_message_id=provider_id)
        except (httpx.HTTPError, ValueError, TypeError):
            return DeliveryResult(status="failed")
