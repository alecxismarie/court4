from __future__ import annotations

from uuid import UUID

import pytest

from spike.persistence.bootstrap import BootstrapUserPolicy, SpikeBootstrapSettings
from spike.persistence.errors import BootstrapUserDisabledError

_USER_ID = "37de0fc7-b7d2-47b9-917c-48d2b882d6db"


@pytest.mark.parametrize(
    "settings",
    [
        SpikeBootstrapSettings(),
        SpikeBootstrapSettings(
            environment="production",
            enabled_value="true",
            user_id_value=_USER_ID,
            identity_label="developer",
        ),
        SpikeBootstrapSettings(
            environment="staging",
            enabled_value="true",
            user_id_value=_USER_ID,
            identity_label="developer",
        ),
        SpikeBootstrapSettings(
            environment="preview",
            enabled_value="true",
            user_id_value=_USER_ID,
            identity_label="developer",
        ),
        SpikeBootstrapSettings(
            environment="development",
            enabled_value="false",
            user_id_value=_USER_ID,
            identity_label="developer",
        ),
        SpikeBootstrapSettings(
            environment="development",
            enabled_value="true",
            user_id_value="not-a-uuid",
            identity_label="developer",
        ),
        SpikeBootstrapSettings(
            environment="development",
            enabled_value="true",
            user_id_value=_USER_ID,
            identity_label="",
        ),
    ],
)
def test_bootstrap_user_policy_fails_closed(settings: SpikeBootstrapSettings) -> None:
    with pytest.raises(BootstrapUserDisabledError):
        BootstrapUserPolicy(settings).validated_identity()


@pytest.mark.parametrize("environment", ["development", "test"])
def test_bootstrap_user_policy_allows_explicit_safe_environment(
    environment: str,
) -> None:
    identity = BootstrapUserPolicy(
        SpikeBootstrapSettings(
            environment=environment,
            enabled_value="true",
            user_id_value=_USER_ID,
            identity_label="local-developer",
        )
    ).validated_identity()

    assert identity == (UUID(_USER_ID), "local-developer")
