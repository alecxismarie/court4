from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from spike.persistence.db import create_session_factory, create_spike_engine
from spike.persistence.service import PersistenceSpikeService

_TABLES = (
    "spike_idempotency_records",
    "spike_analysis_state_events",
    "spike_analysis_runs",
    "spike_analyses",
    "spike_uploaded_videos",
    "spike_users",
)


@pytest.fixture(scope="session")
def spike_engine() -> Iterator[Engine]:
    database_url = os.getenv("COURT4_SPIKE_DATABASE_URL")
    if not database_url:
        pytest.skip("COURT4_SPIKE_DATABASE_URL is required for PostgreSQL spike tests")
    engine = create_spike_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(spike_engine: Engine) -> Iterator[sessionmaker[Session]]:
    factory = create_session_factory(spike_engine)
    with spike_engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
        )
    yield factory


@pytest.fixture
def spike_service(
    session_factory: sessionmaker[Session],
) -> PersistenceSpikeService:
    return PersistenceSpikeService(session_factory)
