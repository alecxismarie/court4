from __future__ import annotations

import argparse

from alembic import command
from alembic.config import Config

from app.config import get_settings
from app.persistence.database_safety import (
    ExpectedDatabaseIdentity,
    assert_isolated_test_database_url,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an Alembic rehearsal only against an approved disposable database."
    )
    parser.add_argument("action", choices=("upgrade", "downgrade", "check"))
    parser.add_argument("revision", nargs="?", default="head")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.allow_destructive_database_operations:
        raise ValueError("Migration safety refusal: explicit destructive opt-in is absent.")
    assert_isolated_test_database_url(
        settings.database_url,
        environment=settings.environment,
        expected=ExpectedDatabaseIdentity(
            prefix=settings.expected_test_database_prefix,
            host=settings.expected_test_database_host,
            username=settings.expected_test_database_user,
        ),
    )
    config = Config("alembic.ini")
    if args.action == "upgrade":
        command.upgrade(config, args.revision)
    elif args.action == "downgrade":
        command.downgrade(config, args.revision)
    else:
        command.check(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
