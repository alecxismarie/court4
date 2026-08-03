from __future__ import annotations

import html
import logging
from urllib.parse import quote

from app.config.settings import Settings
from app.email.models import DeliveryResult, EmailMessage, EmailSender

logger = logging.getLogger(__name__)


class AccountEmailService:
    def __init__(self, sender: EmailSender, settings: Settings) -> None:
        self._sender = sender
        self._settings = settings

    def send_verification_email(
        self, email: str, raw_token: str, *, correlation_id: str
    ) -> DeliveryResult:
        url = self._link("/verify-email", raw_token)
        hours = self._settings.auth_verification_token_hours
        return self._deliver(
            EmailMessage(
                recipient=email,
                subject="Verify your Court4 email",
                text_body=(
                    "Welcome to Court4.\n\n"
                    f"Verify your email: {url}\n\n"
                    f"This link expires in {hours} hours. "
                    "If you did not create this account, ignore this message."
                ),
                html_body=self._html(
                    "Verify your Court4 email",
                    "Confirm your email before uploading match videos.",
                    "Verify email",
                    url,
                    f"This link expires in {hours} hours.",
                ),
                category="email_verification",
                correlation_id=correlation_id,
            )
        )

    def send_password_reset_email(
        self, email: str, raw_token: str, *, correlation_id: str
    ) -> DeliveryResult:
        url = self._link("/reset-password", raw_token)
        minutes = self._settings.auth_password_reset_token_minutes
        return self._deliver(
            EmailMessage(
                recipient=email,
                subject="Reset your Court4 password",
                text_body=(
                    f"Reset your Court4 password: {url}\n\n"
                    f"This link expires in {minutes} minutes. "
                    "If you did not request a reset, ignore this message."
                ),
                html_body=self._html(
                    "Reset your Court4 password",
                    "Use this secure link to choose a new password.",
                    "Reset password",
                    url,
                    f"This link expires in {minutes} minutes.",
                ),
                category="password_reset",
                correlation_id=correlation_id,
            )
        )

    def send_password_changed_email(self, email: str, *, correlation_id: str) -> DeliveryResult:
        return self._deliver(
            EmailMessage(
                recipient=email,
                subject="Your Court4 password was changed",
                text_body=(
                    "Your Court4 password was changed. Existing sessions were revoked. "
                    "If this was not you, contact Court4 support immediately."
                ),
                html_body=self._html_notice(
                    "Your Court4 password was changed",
                    "Existing sessions were revoked. If this was not you, contact support.",
                ),
                category="password_changed",
                correlation_id=correlation_id,
            )
        )

    def send_sessions_revoked_email(self, email: str, *, correlation_id: str) -> DeliveryResult:
        return self._deliver(
            EmailMessage(
                recipient=email,
                subject="Court4 sessions were revoked",
                text_body=(
                    "One or more Court4 sessions were signed out. "
                    "If this was not you, change your password immediately."
                ),
                html_body=self._html_notice(
                    "Court4 sessions were revoked",
                    "If this was not you, change your password immediately.",
                ),
                category="sessions_revoked",
                correlation_id=correlation_id,
            )
        )

    def _deliver(self, message: EmailMessage) -> DeliveryResult:
        try:
            result = self._sender.send(message)
        except Exception:
            logger.exception(
                "account_email_delivery_failed",
                extra={"category": message.category, "correlation_id": message.correlation_id},
            )
            return DeliveryResult(status="failed")
        if result.status == "failed":
            logger.warning(
                "account_email_delivery_failed",
                extra={"category": message.category, "correlation_id": message.correlation_id},
            )
        return result

    def _link(self, path: str, raw_token: str) -> str:
        return f"{self._settings.auth_frontend_base_url}{path}?token={quote(raw_token, safe='')}"

    @staticmethod
    def _html(title: str, purpose: str, label: str, url: str, expiry: str) -> str:
        return (
            "<div style='font-family:Arial,sans-serif'>"
            "<strong style='color:#176b4d'>Court4 &mdash; Know Your Game</strong>"
            f"<h1>{html.escape(title)}</h1><p>{html.escape(purpose)}</p>"
            f"<p><a href='{html.escape(url, quote=True)}'>{html.escape(label)}</a></p>"
            f"<p>{html.escape(expiry)}</p>"
            "<p>If you did not request this, you can ignore this email.</p></div>"
        )

    @staticmethod
    def _html_notice(title: str, detail: str) -> str:
        return (
            "<div style='font-family:Arial,sans-serif'>"
            "<strong style='color:#176b4d'>Court4 &mdash; Know Your Game</strong>"
            f"<h1>{html.escape(title)}</h1><p>{html.escape(detail)}</p></div>"
        )
