from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.persistence.runtime import get_persistence
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.sports import SportType


def test_existing_pickleball_record_backfills_through_downgrade_upgrade_cycle() -> None:
    runtime = get_persistence()
    now = datetime.now(tz=UTC)
    job = AnalysisJob(
        analysis_id="known-pickleball-history",
        sport=SportType.PICKLEBALL,
        status=AnalysisStatus.processing,
        current_stage=AnalysisStage.uploaded,
        created_at=now,
        updated_at=now,
    )
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=job.analysis_id,
        idempotency_key="known-pickleball-history",
        request_fingerprint="a" * 64,
        original_filename="historical-pickleball.mp4",
        content_type="video/mp4",
        size_bytes=1,
        source_checksum="b" * 64,
        job_payload=job.model_dump(mode="json"),
        sport=SportType.PICKLEBALL,
    )
    padel_job = job.model_copy(update={"analysis_id": "padel-roundtrip", "sport": SportType.PADEL})
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=padel_job.analysis_id,
        idempotency_key="padel-roundtrip",
        request_fingerprint="c" * 64,
        original_filename="padel.mp4",
        content_type="video/mp4",
        size_bytes=1,
        source_checksum="d" * 64,
        job_payload=padel_job.model_dump(mode="json"),
        sport=SportType.PADEL,
    )

    alembic_config = Config("alembic.ini")
    try:
        command.downgrade(alembic_config, "0007_stage_evidence")
        command.upgrade(alembic_config, "head")
        with runtime.engine.connect() as connection:
            analysis = connection.execute(
                text(
                    "SELECT sport, job_payload->>'sport' FROM analyses "
                    "WHERE id = 'known-pickleball-history'"
                )
            ).one()
            run = connection.execute(
                text(
                    "SELECT sport, sport_config_version, court_definition_version "
                    "FROM analysis_runs WHERE analysis_id = 'known-pickleball-history'"
                )
            ).one()
        assert analysis == ("pickleball", "pickleball")
        assert run == (
            "pickleball",
            "pickleball-analysis-v1",
            "pickleball-court-v1",
        )
        with runtime.engine.connect() as connection:
            padel_analysis = connection.execute(
                text(
                    "SELECT sport, job_payload->>'sport' FROM analyses WHERE id = 'padel-roundtrip'"
                )
            ).one()
            padel_run = connection.execute(
                text(
                    "SELECT sport, sport_config_version, court_definition_version "
                    "FROM analysis_runs WHERE analysis_id = 'padel-roundtrip'"
                )
            ).one()
        assert padel_analysis == ("padel", "padel")
        assert padel_run == ("padel", "padel-experimental-v1", "padel-court-v1")
    finally:
        command.upgrade(alembic_config, "head")
