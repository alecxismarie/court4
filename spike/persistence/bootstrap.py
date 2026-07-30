from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from spike.persistence.errors import BootstrapUserDisabledError

_ALLOWED_ENVIRONMENTS = frozenset({"development", "test"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class SpikeBootstrapSettings:
    environment: str = ""
    enabled_value: str = ""
    user_id_value: str = ""
    identity_label: str = ""


@dataclass(frozen=True)
class BootstrapUserPolicy:
    """Fail-closed gate for a temporary development/test identity."""

    settings: SpikeBootstrapSettings

    def validated_identity(self) -> tuple[UUID, str]:
        environment = self.settings.environment.strip().lower()
        if environment not in _ALLOWED_ENVIRONMENTS:
            raise BootstrapUserDisabledError(
                "The spike bootstrap user is allowed only in development or test."
            )
        if self.settings.enabled_value.strip().lower() not in _TRUE_VALUES:
            raise BootstrapUserDisabledError(
                "The spike bootstrap user requires explicit enablement."
            )
        try:
            user_id = UUID(self.settings.user_id_value.strip())
        except (ValueError, AttributeError):
            raise BootstrapUserDisabledError(
                "The spike bootstrap user ID must be an explicit UUID."
            ) from None
        label = self.settings.identity_label.strip()
        if not label or len(label) > 120:
            raise BootstrapUserDisabledError(
                "The spike bootstrap identity label must be 1-120 characters."
            )
        return user_id, label
