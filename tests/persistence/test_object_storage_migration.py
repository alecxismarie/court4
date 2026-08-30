from __future__ import annotations

from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.persistence.runtime import get_persistence
from app.persistence.service import ArtifactInput
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus


def test_legacy_local_artifact_locator_survives_downgrade_reupgrade() -> None:
    runtime = get_persistence()
    now = datetime.now(tz=UTC)
    job = AnalysisJob(
        analysis_id="local-object-storage-roundtrip",
        status=AnalysisStatus.processing,
        current_stage=AnalysisStage.uploaded,
        source_video="uploads/source.mp4",
        created_at=now,
        updated_at=now,
    )
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=job.analysis_id,
        idempotency_key=job.analysis_id,
        request_fingerprint="a" * 64,
        original_filename="legacy.mp4",
        content_type="video/mp4",
        size_bytes=12,
        source_checksum="b" * 64,
        job_payload=job.model_dump(mode="json"),
    )
    runtime.service.persist_job(
        owner_user_id=runtime.owner_user_id,
        payload=job.model_dump(mode="json"),
        artifacts=[
            ArtifactInput(
                storage_key="uploads/source.mp4",
                content_type="video/mp4",
                size_bytes=12,
                checksum_sha256="b" * 64,
                artifact_kind="source_video",
            )
        ],
    )

    alembic_config = Config("alembic.ini")
    try:
        command.downgrade(alembic_config, "0008_sport_architecture")
        command.upgrade(alembic_config, "head")
        with runtime.engine.connect() as connection:
            locator = connection.execute(
                text(
                    "SELECT storage_provider, storage_key, logical_key "
                    "FROM analysis_artifacts WHERE analysis_id = :analysis_id"
                ),
                {"analysis_id": job.analysis_id},
            ).one()
        assert locator == ("local", "uploads/source.mp4", "uploads/source.mp4")
    finally:
        command.upgrade(alembic_config, "head")
