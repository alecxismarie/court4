from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.config import Settings
from app.persistence.errors import PersistenceConfigurationError


@dataclass(frozen=True)
class BootstrapIdentity:
    user_id: UUID
    identity_label: str


def configured_bootstrap_identity(settings: Settings) -> BootstrapIdentity:
    if settings.environment not in {"development", "test"}:
        raise PersistenceConfigurationError(
            "Bootstrap identity is forbidden outside development and test."
        )
    if not settings.bootstrap_user_enabled:
        raise PersistenceConfigurationError(
            "Authentication is not configured and bootstrap identity is disabled."
        )
    if settings.bootstrap_user_id is None or not settings.bootstrap_user_identity:
        raise PersistenceConfigurationError(
            "Bootstrap identity requires both bootstrap_user_id and bootstrap_user_identity."
        )
    return BootstrapIdentity(
        user_id=settings.bootstrap_user_id,
        identity_label=settings.bootstrap_user_identity.strip(),
    )
