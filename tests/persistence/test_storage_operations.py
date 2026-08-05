from __future__ import annotations

import hashlib
import io
import os
from collections import namedtuple
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.config import get_settings
from app.persistence.reconciliation import StorageReconciler
from app.persistence.runtime import get_persistence
from app.persistence.service import ArtifactInput
from app.persistence.storage import LocalStorage, StorageCapacityError
from app.services.jobs import AnalysisWorkflowService, JobStorageCapacityError
from scripts.storage_cleanup import CONFIRMATION, run_cleanup

DiskUsage = namedtuple("DiskUsage", "total used free")
GIB = 1024**3


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


@pytest.mark.asyncio
async def test_low_disk_upload_is_rejected_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    with pytest.raises(JobStorageCapacityError) as captured:
        await service.create_analysis(upload)

    assert captured.value.code == "storage_capacity_unavailable"
    assert captured.value.status_code == 507
    assert not (tmp_path / "output" / "_uploads").exists()


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
