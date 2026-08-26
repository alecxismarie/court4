from __future__ import annotations

import hashlib
import io
import logging
import os
from collections import namedtuple
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.config import get_settings
from app.config.settings import Settings
from app.core.logging import JsonFormatter
from app.persistence.reconciliation import StorageReconciler
from app.persistence.runtime import get_persistence
from app.persistence.service import ArtifactInput
from app.persistence.storage import LocalStorage, StorageCapacityError
from app.services.jobs import AnalysisWorkflowService, JobStorageCapacityError
from scripts.storage_cleanup import CONFIRMATION, run_cleanup

DiskUsage = namedtuple("DiskUsage", "total used free")
GIB = 1024**3


def test_healthy_capacity_decision_records_numerically_correct_safe_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalStorage(tmp_path / "persistent-volume" / "output")
    observed_paths: list[Path] = []
    logged: list[tuple[str, dict[str, object]]] = []

    def disk_usage(path: Path) -> DiskUsage:
        observed_paths.append(path)
        assert path.is_dir()
        return DiskUsage(30 * GIB, 8 * GIB, 22 * GIB)

    monkeypatch.setattr("app.persistence.storage.shutil.disk_usage", disk_usage)
    for name, value in {
        "RAILWAY_DEPLOYMENT_ID": "deployment-safe",
        "RAILWAY_REPLICA_ID": "replica-safe",
        "RAILWAY_ENVIRONMENT_ID": "environment-safe",
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_SERVICE_ID": "service-safe",
        "RAILWAY_SERVICE_NAME": "court4-api",
        "RAILWAY_PROJECT_ID": "project-safe",
        "RAILWAY_PROJECT_NAME": "court4",
        "RAILWAY_VOLUME_MOUNT_PATH": str(tmp_path / "persistent-volume"),
        "DATABASE_URL": "postgresql://secret-database-value",
        "BREVO_API_KEY": "secret-brevo-value",
        "JWT_SECRET": "secret-jwt-value",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "app.persistence.storage.logger.info",
        lambda message, *, extra: logged.append((message, extra)),
    )

    reservation, capacity = storage.reserve_capacity(
        requested_bytes=2 * GIB,
        warning_free_bytes=10 * GIB,
        hard_stop_free_bytes=5 * GIB,
        max_active_uploads=1,
        software_commit_identifier="commit-safe",
        deployment_build_identifier="build-safe",
    )
    try:
        assert capacity.state == "available"
        assert observed_paths == [storage.root]
        message, context = logged[0]
        assert message == "storage_capacity_admission_decision"
        expected = {
            "resolved_storage_root": str(storage.root),
            "storage_root_exists": True,
            "filesystem_total_bytes": 30 * GIB,
            "filesystem_used_bytes": 8 * GIB,
            "filesystem_free_bytes": 22 * GIB,
            "existing_reserved_bytes": 0,
            "requested_reservation_bytes": 2 * GIB,
            "free_after_reservations": 20 * GIB,
            "warning_free_bytes": 10 * GIB,
            "hard_stop_free_bytes": 5 * GIB,
            "active_upload_count": 0,
            "max_active_uploads": 1,
            "decision": "accepted",
            "railway_deployment_id": "deployment-safe",
            "railway_replica_id": "replica-safe",
            "railway_environment_id": "environment-safe",
            "railway_environment_name": "staging",
            "railway_service_id": "service-safe",
            "railway_service_name": "court4-api",
            "railway_project_id": "project-safe",
            "railway_project_name": "court4",
            "railway_volume_mount_path": str(tmp_path / "persistent-volume"),
            "software_commit_identifier": "commit-safe",
            "deployment_build_identifier": "build-safe",
        }
        for key, expected_value in expected.items():
            assert context[key] == expected_value
        assert isinstance(context["pid"], int)
        assert isinstance(context["hostname"], str) and context["hostname"]

        record = logging.makeLogRecord(
            {
                "name": "app.persistence.storage",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "msg": message,
                **context,
            }
        )
        structured_log = JsonFormatter().format(record)
        assert "secret-database-value" not in structured_log
        assert "secret-brevo-value" not in structured_log
        assert "secret-jwt-value" not in structured_log
        assert "DATABASE_URL" not in structured_log
        assert "BREVO_API_KEY" not in structured_log
        assert "JWT_SECRET" not in structured_log
    finally:
        reservation.release()


def test_capacity_reports_available_warning_and_hard_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorage(tmp_path / "storage")

    monkeypatch.setattr(
        "app.persistence.storage.shutil.disk_usage", lambda _: DiskUsage(30, 10, 20 * GIB)
    )
    assert (
        storage.capacity_status(
            requested_bytes=2 * GIB,
            warning_free_bytes=10 * GIB,
            hard_stop_free_bytes=5 * GIB,
        ).state
        == "available"
    )

    monkeypatch.setattr(
        "app.persistence.storage.shutil.disk_usage", lambda _: DiskUsage(30, 18, 12 * GIB)
    )
    assert (
        storage.capacity_status(
            requested_bytes=3 * GIB,
            warning_free_bytes=10 * GIB,
            hard_stop_free_bytes=5 * GIB,
        ).state
        == "warning"
    )

    monkeypatch.setattr(
        "app.persistence.storage.shutil.disk_usage", lambda _: DiskUsage(30, 23, 7 * GIB)
    )
    assert (
        storage.capacity_status(
            requested_bytes=3 * GIB,
            warning_free_bytes=10 * GIB,
            hard_stop_free_bytes=5 * GIB,
        ).state
        == "hard_stop"
    )


def test_capacity_reservation_prevents_single_instance_overcommit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = LocalStorage(tmp_path / "storage")
    monkeypatch.setattr(
        "app.persistence.storage.shutil.disk_usage", lambda _: DiskUsage(30, 10, 20 * GIB)
    )
    reservation, _ = storage.reserve_capacity(
        requested_bytes=2 * GIB,
        warning_free_bytes=10 * GIB,
        hard_stop_free_bytes=5 * GIB,
        max_active_uploads=1,
    )
    try:
        with pytest.raises(StorageCapacityError) as captured:
            storage.reserve_capacity(
                requested_bytes=2 * GIB,
                warning_free_bytes=10 * GIB,
                hard_stop_free_bytes=5 * GIB,
                max_active_uploads=1,
            )
        assert captured.value.reason == "active_limit"
    finally:
        reservation.release()

    next_reservation, capacity = storage.reserve_capacity(
        requested_bytes=2 * GIB,
        warning_free_bytes=10 * GIB,
        hard_stop_free_bytes=5 * GIB,
        max_active_uploads=1,
    )
    assert capacity.reserved_bytes == 0
    next_reservation.release()


@pytest.mark.asyncio
async def test_low_disk_upload_is_rejected_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, dict[str, object]]] = []
    settings = get_settings().model_copy(
        update={
            "analysis_output_dir": tmp_path / "output",
            "max_upload_size_bytes": 512,
            "storage_upload_reservation_multiplier": 2.0,
            "storage_warning_free_bytes": 2_000,
            "storage_hard_stop_free_bytes": 1_000,
        }
    )
    monkeypatch.setattr(
        "app.persistence.storage.shutil.disk_usage",
        lambda _: DiskUsage(2_000, 1_500, 500),
    )
    service = AnalysisWorkflowService(
        settings=settings,
        owner_user_id=get_persistence().owner_user_id,
    )
    upload = UploadFile(
        filename="sample.mp4",
        file=io.BytesIO(b"video"),
        headers=Headers({"content-type": "video/mp4"}),
    )
    monkeypatch.setattr(
        "app.persistence.storage.logger.warning",
        lambda message, *, extra: logged.append((message, extra)),
    )

    with pytest.raises(JobStorageCapacityError) as captured:
        await service.create_analysis(upload)

    assert captured.value.code == "storage_capacity_unavailable"
    assert captured.value.status_code == 507
    assert not (tmp_path / "output" / "_uploads").exists()
    cause = captured.value.__cause__
    assert isinstance(cause, StorageCapacityError)
    assert cause.snapshot.decision == "hard_stop"
    assert cause.snapshot.filesystem_total_bytes == 2_000
    assert cause.snapshot.filesystem_used_bytes == 1_500
    assert cause.snapshot.filesystem_free_bytes == 500
    assert cause.snapshot.existing_reserved_bytes == 0
    assert cause.snapshot.requested_reservation_bytes == 1_024
    assert cause.snapshot.free_after_reservations == -524
    assert cause.snapshot.warning_free_bytes == 2_000
    assert cause.snapshot.hard_stop_free_bytes == 1_000
    assert cause.snapshot.active_upload_count == 0
    assert cause.snapshot.max_active_uploads == 1
    assert logged == [
        (
            "storage_capacity_admission_decision",
            cause.snapshot.log_context(),
        )
    ]


@pytest.mark.asyncio
async def test_active_upload_limit_remains_http_429_before_disk_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, dict[str, object]]] = []
    settings = get_settings().model_copy(
        update={
            "analysis_output_dir": tmp_path / "output",
            "max_upload_size_bytes": 512,
            "storage_upload_reservation_multiplier": 2.0,
            "storage_warning_free_bytes": 2_000,
            "storage_hard_stop_free_bytes": 1_000,
            "storage_max_active_uploads": 1,
        }
    )
    disk_measurements = 0

    def disk_usage(_: Path) -> DiskUsage:
        nonlocal disk_measurements
        disk_measurements += 1
        return DiskUsage(10_000, 1_000, 9_000)

    monkeypatch.setattr("app.persistence.storage.shutil.disk_usage", disk_usage)
    service = AnalysisWorkflowService(
        settings=settings,
        owner_user_id=get_persistence().owner_user_id,
    )
    existing, _ = service.repository.storage.reserve_capacity(
        requested_bytes=1_024,
        warning_free_bytes=2_000,
        hard_stop_free_bytes=1_000,
        max_active_uploads=1,
    )
    upload = UploadFile(
        filename="sample.mp4",
        file=io.BytesIO(b"video"),
        headers=Headers({"content-type": "video/mp4"}),
    )
    monkeypatch.setattr(
        "app.persistence.storage.logger.warning",
        lambda message, *, extra: logged.append((message, extra)),
    )

    try:
        with pytest.raises(JobStorageCapacityError) as captured:
            await service.create_analysis(upload)
    finally:
        existing.release()

    assert captured.value.code == "upload_capacity_busy"
    assert captured.value.status_code == 429
    assert disk_measurements == 1
    message, active_context = logged[0]
    assert message == "storage_capacity_admission_decision"
    assert active_context["decision"] == "active_limit"
    assert active_context["filesystem_total_bytes"] is None
    assert active_context["filesystem_used_bytes"] is None
    assert active_context["filesystem_free_bytes"] is None
    assert active_context["free_after_reservations"] is None
    assert active_context["existing_reserved_bytes"] == 1_024
    assert active_context["requested_reservation_bytes"] == 1_024
    assert active_context["active_upload_count"] == 1
    assert active_context["max_active_uploads"] == 1
    assert not (tmp_path / "output" / "_uploads").exists()


def test_storage_capacity_policy_defaults_are_unchanged() -> None:
    assert Settings.model_fields["storage_warning_free_bytes"].default == 10_737_418_240
    assert Settings.model_fields["storage_hard_stop_free_bytes"].default == 5_368_709_120
    assert Settings.model_fields["storage_upload_reservation_multiplier"].default == 2.0
    assert Settings.model_fields["storage_max_active_uploads"].default == 1


def test_reconciliation_is_read_only_and_reports_deterministic_findings(tmp_path: Path) -> None:
    runtime = get_persistence()
    root = tmp_path / "storage"
    analysis_dir = root / "reconcile-analysis"
    analysis_dir.mkdir(parents=True)
    artifact_path = analysis_dir / "artifact.txt"
    artifact_path.write_text("expected", encoding="utf-8")
    checksum = hashlib.sha256(b"expected").hexdigest()
    runtime.service.persist_job(
        owner_user_id=runtime.owner_user_id,
        payload={
            "analysis_id": "reconcile-analysis",
            "status": "processing",
            "current_stage": "uploaded",
        },
        artifacts=[
            ArtifactInput(
                storage_key="artifact.txt",
                content_type="text/plain",
                size_bytes=len(b"expected"),
                checksum_sha256=checksum,
                artifact_kind="artifact",
            )
        ],
        compatibility_import=True,
    )
    (analysis_dir / "orphan.bin").write_bytes(b"orphan")
    (analysis_dir / "job.json").write_text("{}", encoding="utf-8")
    temporary = root / "_uploads" / "abandoned" / "source.mp4"
    temporary.parent.mkdir(parents=True)
    temporary.write_bytes(b"temporary")

    report = StorageReconciler(runtime.session_factory, root).reconcile()

    assert report.scanned_database_records == 1
    assert report.scanned_files == 4
    assert report.matched_records == 1
    assert report.orphan_files == ("reconcile-analysis/orphan.bin",)
    assert report.temporary_files == ("_uploads/abandoned/source.mp4",)
    assert report.legacy_files == ("reconcile-analysis/job.json",)
    assert report.abandoned_upload_directories == ("_uploads/abandoned",)
    assert artifact_path.read_text(encoding="utf-8") == "expected"

    artifact_path.write_text("changed-size", encoding="utf-8")
    mismatch = StorageReconciler(runtime.session_factory, root).reconcile()
    assert mismatch.size_mismatches == ("reconcile-analysis/artifact.txt",)
    assert mismatch.checksum_mismatches == ("reconcile-analysis/artifact.txt",)


def test_cleanup_is_dry_run_by_default_and_quarantines_only_with_confirmation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "storage"
    expired = root / "_uploads" / "expired" / "source.mp4"
    expired.parent.mkdir(parents=True)
    expired.write_bytes(b"old")
    old_timestamp = (datetime.now(tz=UTC) - timedelta(hours=48)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))

    dry_run = run_cleanup(
        root,
        older_than_hours=24,
        apply=False,
        confirmation=None,
        max_files=1,
        max_bytes=10,
    )
    assert dry_run.mode == "dry-run"
    assert expired.exists()

    with pytest.raises(ValueError, match="exact quarantine confirmation"):
        run_cleanup(
            root,
            older_than_hours=24,
            apply=True,
            confirmation=None,
            max_files=1,
            max_bytes=10,
        )

    applied = run_cleanup(
        root,
        older_than_hours=24,
        apply=True,
        confirmation=CONFIRMATION,
        max_files=1,
        max_bytes=10,
    )
    assert applied.quarantined_directories == ("_quarantine/uploads/expired",)
    assert not expired.exists()
    assert (root / "_quarantine" / "uploads" / "expired" / "source.mp4").is_file()
