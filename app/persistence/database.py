from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    if settings.persistence_backend != "postgresql":
        raise ValueError("Only the PostgreSQL persistence backend is supported.")
    engine = create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        pool_recycle=settings.database_pool_recycle_seconds,
        pool_pre_ping=settings.database_pool_pre_ping,
    )

    @event.listens_for(engine, "connect")
    def configure_timeouts(dbapi_connection: object, connection_record: object) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute(f"SET statement_timeout = '{settings.database_statement_timeout_ms}ms'")
            cursor.execute(f"SET lock_timeout = '{settings.database_lock_timeout_ms}ms'")
            cursor.execute(
                "SET idle_in_transaction_session_timeout = "
                f"'{settings.database_idle_transaction_timeout_ms}ms'"
            )
            dbapi_connection.commit()  # type: ignore[attr-defined]
        except Exception:
            dbapi_connection.rollback()  # type: ignore[attr-defined]
            raise
        finally:
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


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
