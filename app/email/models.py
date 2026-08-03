from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    text_body: str
    html_body: str
    category: Literal[
        "email_verification",
        "password_reset",
        "password_changed",
        "sessions_revoked",
    ]
    correlation_id: str


@dataclass(frozen=True)
class DeliveryResult:
    status: Literal["recorded", "sent", "failed"]
    provider_message_id: str | None = None


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> DeliveryResult: ...
