from __future__ import annotations

import logging
from threading import Lock
from uuid import uuid4

from app.email.models import DeliveryResult, EmailMessage

logger = logging.getLogger(__name__)


class DevelopmentEmailSink:
    """Development/test-only in-memory delivery sink; never use in a deployment."""

    def __init__(self) -> None:
        self._messages: list[EmailMessage] = []
        self._lock = Lock()

    def send(self, message: EmailMessage) -> DeliveryResult:
        with self._lock:
            self._messages.append(message)
        logger.info(
            "development_email_recorded",
            extra={"category": message.category, "correlation_id": message.correlation_id},
        )
        return DeliveryResult(status="recorded", provider_message_id=f"dev-{uuid4().hex}")

    def messages_for(self, recipient: str) -> list[EmailMessage]:
        with self._lock:
            return [message for message in self._messages if message.recipient == recipient]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
