from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import ReflectedColumn

from app.persistence.models import UploadedVideo
from app.persistence.runtime import PersistenceRuntime, get_persistence


def test_model_and_database_metadata_payload_contract_are_aligned() -> None:
    runtime = get_persistence()
    model_column = UploadedVideo.__table__.c.metadata_payload
    database_column = _database_column(runtime)

    assert isinstance(model_column.type, JSONB)
    assert model_column.nullable is False
    assert model_column.default is not None
    assert model_column.default.is_callable
    assert model_column.server_default is not None
    assert "'{}'::jsonb" in str(model_column.server_default.arg)

    assert isinstance(database_column["type"], JSONB)
    assert database_column["nullable"] is False
    assert "'{}'::jsonb" in str(database_column["default"])


def test_metadata_payload_insert_defaults_and_round_trips() -> None:
    runtime = get_persistence()
    owner_user_id = runtime.owner_user_id
    now = datetime.now(tz=UTC)
    omitted_id = uuid4()

    with runtime.engine.begin() as connection:
        omitted = connection.scalar(
            text(
                """
                INSERT INTO uploaded_videos (
                    id,
                    owner_user_id,
                    state,
                    original_filename,
                    storage_provider,
                    row_version,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :owner_user_id,
                    'pending',
                    'omitted.mp4',
                    'local',
                    1,
                    :created_at,
                    :updated_at
                )
                RETURNING metadata_payload
                """
            ),
            {
                "id": omitted_id,
                "owner_user_id": owner_user_id,
                "created_at": now,
                "updated_at": now,
            },
        )

    empty_id = uuid4()
    populated_id = uuid4()
    with runtime.session_factory.begin() as session:
        session.add_all(
            [
                _video(
                    video_id=empty_id,
                    owner_user_id=owner_user_id,
                    filename="empty.mp4",
                    metadata_payload={},
                ),
                _video(
                    video_id=populated_id,
                    owner_user_id=owner_user_id,
                    filename="populated.mp4",
                    metadata_payload={"source": "mobile", "rotation": 90},
                ),
            ]
        )

    with runtime.session_factory() as session:
        empty = session.get(UploadedVideo, empty_id)
        populated = session.get(UploadedVideo, populated_id)
        null_count = session.scalar(
            select(text("count(*)"))
            .select_from(UploadedVideo)
            .where(UploadedVideo.metadata_payload.is_(None))
        )

    assert omitted == {}
    assert empty is not None
    assert empty.metadata_payload == {}
    assert populated is not None
    assert populated.metadata_payload == {"source": "mobile", "rotation": 90}
    assert null_count == 0


def test_metadata_payload_migration_backfills_null_and_round_trips() -> None:
    runtime = get_persistence()
    alembic_config = Config("alembic.ini")
    legacy_video_id = uuid4()

    command.downgrade(alembic_config, "0002_exact_duplicate_video")
    try:
        downgraded_column = _database_column(runtime)
        assert downgraded_column["nullable"] is True
        assert downgraded_column["default"] is None

        now = datetime.now(tz=UTC)
        with runtime.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO uploaded_videos (
                        id,
                        owner_user_id,
                        state,
                        original_filename,
                        storage_provider,
                        metadata_payload,
                        row_version,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :owner_user_id,
                        'pending',
                        'legacy-null.mp4',
                        'local',
                        NULL,
                        1,
                        :created_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "id": legacy_video_id,
                    "owner_user_id": runtime.owner_user_id,
                    "created_at": now,
                    "updated_at": now,
                },
            )

        command.upgrade(alembic_config, "head")

        upgraded_column = _database_column(runtime)
        with runtime.engine.connect() as connection:
            backfilled = connection.scalar(
                text(
                    """
                    SELECT metadata_payload
                    FROM uploaded_videos
                    WHERE id = :id
                    """
                ),
                {"id": legacy_video_id},
            )
            null_count = connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM uploaded_videos
                    WHERE metadata_payload IS NULL
                    """
                )
            )

        assert upgraded_column["nullable"] is False
        assert "'{}'::jsonb" in str(upgraded_column["default"])
        assert backfilled == {}
        assert null_count == 0
    finally:
        command.upgrade(alembic_config, "head")


def _database_column(runtime: PersistenceRuntime) -> ReflectedColumn:
    columns = inspect(runtime.engine).get_columns("uploaded_videos")
    return next(column for column in columns if column["name"] == "metadata_payload")


def _video(
    *,
    video_id: UUID,
    owner_user_id: UUID,
    filename: str,
    metadata_payload: dict[str, object],
) -> UploadedVideo:
    return UploadedVideo(
        id=video_id,
        owner_user_id=owner_user_id,
        state="pending",
        original_filename=filename,
        metadata_payload=metadata_payload,
    )
