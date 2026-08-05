from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


def create_spike_engine(
    database_url: str,
    *,
    pool_size: int = 25,
    max_overflow: int = 5,
    pool_timeout_seconds: int = 10,
) -> Engine:
    engine = create_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def configure_timeouts(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '10s'")
            cursor.execute("SET idle_in_transaction_session_timeout = '15s'")
            dbapi_connection.commit()  # type: ignore[attr-defined]
        except Exception:
            dbapi_connection.rollback()  # type: ignore[attr-defined]
            raise
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session, session.begin():
        yield session


def database_diagnostics(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select version(), current_setting('transaction_isolation'), "
                "current_setting('lock_timeout'), current_setting('statement_timeout'), "
                "current_setting('idle_in_transaction_session_timeout')"
            )
        ).one()
    return {
        "version": str(row[0]),
        "isolation_level": str(row[1]),
        "lock_timeout": str(row[2]),
        "statement_timeout": str(row[3]),
        "idle_in_transaction_session_timeout": str(row[4]),
    }
