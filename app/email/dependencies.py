from functools import lru_cache

from app.config import get_settings
from app.email.development import DevelopmentEmailSink
from app.email.models import EmailSender
from app.email.service import AccountEmailService


@lru_cache
def get_development_email_sink() -> DevelopmentEmailSink:
    return DevelopmentEmailSink()


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if (
        settings.auth_email_backend == "development"
        and settings.auth_development_email_sink_enabled
        and settings.environment in {"development", "test"}
    ):
        return get_development_email_sink()
    raise RuntimeError("Configured production email provider adapter is not installed.")


def get_account_email_service() -> AccountEmailService:
    return AccountEmailService(get_email_sender(), get_settings())
