from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSafetyError(ValueError):
    """Raised before a database operation when the target is not provably disposable."""


@dataclass(frozen=True)
class ExpectedDatabaseIdentity:
    prefix: str
    host: str
    username: str


def assert_isolated_test_database_url(
    database_url: str,
    *,
    environment: str | None,
    expected: ExpectedDatabaseIdentity,
) -> str:
    """Validate a test URL without returning or exposing credentials."""
    if environment != "test":
        raise DatabaseSafetyError("Database safety refusal: environment must be exactly 'test'.")
    try:
        parsed = make_url(database_url)
    except ArgumentError as exc:
        raise DatabaseSafetyError("Database safety refusal: database URL is invalid.") from exc
    if parsed.get_backend_name() != "postgresql":
        raise DatabaseSafetyError("Database safety refusal: PostgreSQL is required.")

    database_name = parsed.database or ""
    if not _matches_prefix(database_name, expected.prefix):
        raise DatabaseSafetyError(
            "Database safety refusal: database name does not match the approved test identity."
        )
    if (parsed.host or "").casefold() != expected.host.casefold():
        raise DatabaseSafetyError(
            "Database safety refusal: database host does not match the approved test host."
        )
    if (parsed.username or "") != expected.username:
        raise DatabaseSafetyError(
            "Database safety refusal: database user does not match the approved test identity."
        )
    return database_name


def assert_destructive_database_operation(
    engine: Engine,
    *,
    database_url: str,
    environment: str | None,
    allow_destructive_operations: bool,
    expected: ExpectedDatabaseIdentity,
    operation: str,
) -> str:
    """Recheck both configured and live identities immediately before mutation."""
    if not allow_destructive_operations:
        raise DatabaseSafetyError(
            f"Database safety refusal for {operation}: explicit destructive opt-in is absent."
        )
    configured_name = assert_isolated_test_database_url(
        database_url,
        environment=environment,
        expected=expected,
    )
    with engine.connect() as connection:
        live_name, live_user = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()
    if live_name != configured_name or live_user != expected.username:
        raise DatabaseSafetyError(
            f"Database safety refusal for {operation}: live connection identity does not match."
        )
    return configured_name


def assert_distinct_restore_target(
    *,
    source_database_url: str,
    target_database_url: str,
    environment: str | None,
    allow_destructive_operations: bool,
    expected_target: ExpectedDatabaseIdentity,
) -> str:
    """Refuse restore validation when source and target resolve to the same database."""
    if not allow_destructive_operations:
        raise DatabaseSafetyError(
            "Database safety refusal for restore validation: explicit destructive opt-in is absent."
        )
    target_name = assert_isolated_test_database_url(
        target_database_url,
        environment=environment,
        expected=expected_target,
    )
    try:
        source = make_url(source_database_url)
        target = make_url(target_database_url)
    except ArgumentError as exc:
        raise DatabaseSafetyError("Database safety refusal: database URL is invalid.") from exc
    source_identity = (source.host, source.port, source.database)
    target_identity = (target.host, target.port, target.database)
    if source_identity == target_identity:
        raise DatabaseSafetyError(
            "Database safety refusal: restore target must differ from the source database."
        )
    return target_name


def _matches_prefix(database_name: str, expected_prefix: str) -> bool:
    prefix = expected_prefix.strip()
    return bool(prefix) and (database_name == prefix or database_name.startswith(f"{prefix}_"))
