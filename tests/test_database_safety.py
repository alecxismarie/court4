from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine

from app.config import get_settings
from app.config.settings import Settings
from app.persistence.database_safety import (
    DatabaseSafetyError,
    ExpectedDatabaseIdentity,
    assert_destructive_database_operation,
    assert_distinct_restore_target,
    assert_isolated_test_database_url,
)
from app.persistence.runtime import get_persistence

TEST_URL = "postgresql+psycopg://court4_test:password-never-reported@127.0.0.1:55434/court4_test"
PRIMARY_URL = "postgresql+psycopg://court4:primary-secret@127.0.0.1:55433/court4"
EXPECTED = ExpectedDatabaseIdentity(
    prefix="court4_test",
    host="127.0.0.1",
    username="court4_test",
)


def test_destructive_cleanup_guard_accepts_live_isolated_test_database() -> None:
    settings = get_settings()

    database_name = assert_destructive_database_operation(
        get_persistence().engine,
        database_url=settings.database_url,
        environment=settings.environment,
        allow_destructive_operations=settings.allow_destructive_database_operations,
        expected=ExpectedDatabaseIdentity(
            prefix=settings.expected_test_database_prefix,
            host=settings.expected_test_database_host,
            username=settings.expected_test_database_user,
        ),
        operation="guard acceptance test",
    )

    assert database_name == "court4_test"


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_destructive_cleanup_guard_refuses_non_test_environments(environment: str) -> None:
    with pytest.raises(DatabaseSafetyError, match="environment must be exactly 'test'"):
        assert_destructive_database_operation(
            cast(Engine, object()),
            database_url=TEST_URL,
            environment=environment,
            allow_destructive_operations=True,
            expected=EXPECTED,
            operation="refusal test",
        )


def test_destructive_cleanup_guard_refuses_unexpected_database_name() -> None:
    with pytest.raises(DatabaseSafetyError, match="database name"):
        assert_isolated_test_database_url(
            PRIMARY_URL,
            environment="test",
            expected=EXPECTED,
        )


def test_destructive_cleanup_guard_refuses_missing_environment() -> None:
    with pytest.raises(DatabaseSafetyError, match="environment"):
        assert_isolated_test_database_url(TEST_URL, environment=None, expected=EXPECTED)


def test_destructive_cleanup_guard_refuses_missing_opt_in() -> None:
    with pytest.raises(DatabaseSafetyError, match="explicit destructive opt-in is absent"):
        assert_destructive_database_operation(
            cast(Engine, object()),
            database_url=TEST_URL,
            environment="test",
            allow_destructive_operations=False,
            expected=EXPECTED,
            operation="refusal test",
        )


def test_test_settings_cannot_inherit_primary_database() -> None:
    with pytest.raises(ValidationError, match="database name"):
        Settings(environment="test", database_url=PRIMARY_URL)


def test_migration_rehearsal_requires_disposable_identity() -> None:
    name = assert_isolated_test_database_url(
        "postgresql+psycopg://court4_validation:secret@127.0.0.1:55434/"
        "court4_validation_migrations_20260805",
        environment="test",
        expected=ExpectedDatabaseIdentity(
            prefix="court4_validation",
            host="127.0.0.1",
            username="court4_validation",
        ),
    )

    assert name == "court4_validation_migrations_20260805"


def test_restore_validation_cannot_overwrite_source_database() -> None:
    with pytest.raises(DatabaseSafetyError, match="must differ"):
        assert_distinct_restore_target(
            source_database_url=TEST_URL,
            target_database_url=TEST_URL,
            environment="test",
            allow_destructive_operations=True,
            expected_target=EXPECTED,
        )


def test_refusal_does_not_expose_credentials() -> None:
    with pytest.raises(DatabaseSafetyError) as captured:
        assert_isolated_test_database_url(
            PRIMARY_URL,
            environment="test",
            expected=EXPECTED,
        )

    assert "primary-secret" not in str(captured.value)
