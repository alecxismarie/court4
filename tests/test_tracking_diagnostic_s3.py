"""Diagnostic storage admission, transfer bounds, and evidence consistency."""

import hashlib
import io
import json
import time
from asyncio import CancelledError
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest

from app.config.settings import Settings
from app.persistence.object_storage import ObjectMetadata, ObjectStorageError, S3ObjectStorage
from app.persistence.service import PlayerSelectionInput
from app.persistence.storage import LocalStorage
from app.services.jobs.exceptions import (
    JobConflictError,
    JobNotFoundError,
    JobStorageBackendError,
    JobStorageCapacityError,
)
from app.services.jobs.repository import AnalysisJobRepository
from app.services.tracking.diagnostic import tracking_evidence_diagnostic
from tests import test_candidate_evidence_lineage as lineage
from tests import test_report_reads as reads
from tests.test_report_reads import AID, ReportCase

lineage_case = lineage.lineage_case
report_case = reads.report_case


class DiagnosticClient:
    def __init__(self, objects: dict[str, dict[str, Any]]) -> None:
        self.objects = objects
        self.head_calls = 0
        self.get_calls = 0
        self.entered = Event()
        self.release = Event()
        self.block_head = False
        self.fail_head = False
        self.body: io.BytesIO | None = None

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        self.head_calls += 1
        self.entered.set()
        if self.block_head and not self.release.wait(5):
            raise TimeoutError("slow metadata")
        if self.fail_head:
            raise TimeoutError("metadata failed")
        item = self.objects[Key]
        return {
            "ContentLength": len(item["data"]),
            "ContentType": item["content_type"],
            "Metadata": item["metadata"],
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        self.get_calls += 1
        self.body = io.BytesIO(self.objects[Key]["data"])
        return {"Body": self.body}


def test_diagnostic_s3_client_has_bounded_socket_timeouts_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import boto3

    configs: list[Any] = []

    def client_factory(service: str, **kwargs: Any) -> object:
        assert service == "s3"
        configs.append(kwargs["config"])
        return object()

    monkeypatch.setattr(boto3, "client", client_factory)
    settings = Settings.model_validate(
        {
            "storage_backend": "s3",
            "storage_s3_endpoint": "https://objects.example.test",
            "storage_s3_region": "test-region",
            "storage_s3_bucket": "private",
            "storage_s3_access_key_id": "access-id",
            "storage_s3_secret_access_key": "secret",
        }
    )
    S3ObjectStorage.from_settings(settings)
    assert len(configs) == 2
    assert configs[1].connect_timeout == 3
    assert configs[1].read_timeout == 5
    assert configs[1].retries["total_max_attempts"] == 2


@pytest.fixture
def diagnostic_s3(report_case: ReportCase) -> tuple[ReportCase, DiagnosticClient, S3ObjectStorage]:
    assert report_case.storage is not None
    client = DiagnosticClient(report_case.storage.objects)
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    return report_case, client, storage


def _repository(case: ReportCase, storage: S3ObjectStorage) -> AnalysisJobRepository:
    return AnalysisJobRepository.from_settings(
        settings=case.settings,
        owner_user_id=case.repo.owner_user_id,
        persistence=case.repo.persistence,
        object_storage=storage,
    )


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_diagnostic_s3_success_does_not_change_saved_evidence(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
) -> None:
    case, client, storage = diagnostic_s3
    assert case.storage is not None
    saved_bytes = {key: item["data"] for key, item in case.storage.objects.items()}
    before_job = case.repo.load_job_metadata(AID).model_dump(mode="json")
    repo = _repository(case, storage)
    try:
        summary = tracking_evidence_diagnostic(repo, AID)
    finally:
        repo.close()
    assert summary["analysis_id"] == AID
    assert summary["identity_of_other_raw_ids"] == "Unknown"
    assert client.head_calls == client.get_calls == 5
    assert {key: item["data"] for key, item in case.storage.objects.items()} == saved_bytes
    assert case.repo.load_job_metadata(AID).model_dump(mode="json") == before_job


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_diagnostic_s3_admission_precedes_preflight_and_releases(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
) -> None:
    case, client, storage = diagnostic_s3
    capacity = LocalStorage(case.settings.processing_workspace_root)
    held = [
        capacity.reserve_capacity(
            requested_bytes=0,
            warning_free_bytes=0,
            hard_stop_free_bytes=0,
            max_active_uploads=1,
            admission="read",
            max_active_reads=4,
        )[0]
        for _ in range(4)
    ]
    try:
        repo = _repository(case, storage)
        try:
            with pytest.raises(JobStorageCapacityError) as failure:
                tracking_evidence_diagnostic(repo, AID)
            assert failure.value.status_code == 429
            assert client.head_calls == client.get_calls == 0
        finally:
            repo.close()
    finally:
        for reservation in held:
            reservation.release()
    assert capacity.root not in LocalStorage._active_reads_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_concurrent_diagnostics_do_not_multiply_s3_preflight(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
) -> None:
    case, client, storage = diagnostic_s3
    client.block_head = True

    def run() -> dict[str, Any] | Exception:
        repo = _repository(case, storage)
        try:
            return tracking_evidence_diagnostic(repo, AID)
        except Exception as exc:
            return exc
        finally:
            repo.close()

    with ThreadPoolExecutor(max_workers=5) as pool:
        first = pool.submit(run)
        assert client.entered.wait(5)
        others = [pool.submit(run) for _ in range(4)]
        time.sleep(0.1)
        assert 1 <= client.head_calls <= 4
        client.release.set()
        results = [first.result(timeout=15), *(future.result(timeout=15) for future in others)]
    assert all(
        isinstance(item, dict | JobConflictError | JobStorageCapacityError) for item in results
    )
    assert client.head_calls <= 4 * 5
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
@pytest.mark.parametrize("failure", ["slow", "failed"])
def test_diagnostic_s3_metadata_failure_releases_read_slot(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage], failure: str
) -> None:
    case, client, storage = diagnostic_s3
    client.block_head = failure == "slow"
    client.fail_head = failure == "failed"
    repo = _repository(case, storage)
    try:
        with pytest.raises(JobStorageBackendError):
            tracking_evidence_diagnostic(repo, AID)
    finally:
        repo.close()
    assert client.head_calls == 1
    assert client.get_calls == 0
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root


@pytest.mark.parametrize("payload", [b"123456", b"1234"])
def test_diagnostic_s3_download_rejects_oversize_or_corruption_and_cleans(
    tmp_path: Path, payload: bytes
) -> None:
    key = "artifact.json"
    client = DiagnosticClient(
        {key: {"data": payload, "content_type": "application/json", "metadata": {}}}
    )
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    destination = tmp_path / key
    expected = ObjectMetadata(key, 4, hashlib.sha256(b"good").hexdigest(), "application/json")
    with pytest.raises(ObjectStorageError):
        storage.diagnostic_download_file(
            key=key, destination=destination, max_bytes=4, expected=expected
        )
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []
    assert client.body is not None and client.body.closed


def test_diagnostic_s3_cancelled_stream_cleans_temporary_file(tmp_path: Path) -> None:
    class Interrupted(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            del size
            raise CancelledError()

    key = "artifact.json"
    client = DiagnosticClient({key: {"data": b"good", "content_type": "", "metadata": {}}})
    body = Interrupted()
    client.get_object = lambda **kwargs: {"Body": body}  # type: ignore[method-assign]
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    destination = tmp_path / key
    expected = ObjectMetadata(key, 4, hashlib.sha256(b"good").hexdigest(), "")
    with pytest.raises(CancelledError):
        storage.diagnostic_download_file(
            key=key, destination=destination, max_bytes=4, expected=expected
        )
    assert body.closed
    assert list(tmp_path.iterdir()) == []


def test_diagnostic_s3_cancelled_close_does_not_publish_file(tmp_path: Path) -> None:
    class InterruptedClose(io.BytesIO):
        def close(self) -> None:
            super().close()
            raise CancelledError()

    key = "artifact.json"
    client = DiagnosticClient({key: {"data": b"good", "content_type": "", "metadata": {}}})
    body = InterruptedClose(b"good")
    client.get_object = lambda **kwargs: {"Body": body}  # type: ignore[method-assign]
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    destination = tmp_path / key
    expected = ObjectMetadata(key, 4, hashlib.sha256(b"good").hexdigest(), "")
    with pytest.raises(CancelledError):
        storage.diagnostic_download_file(
            key=key, destination=destination, max_bytes=4, expected=expected
        )
    assert body.closed
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_diagnostic_s3_owner_isolation_before_preflight(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
) -> None:
    case, client, storage = diagnostic_s3
    repo = AnalysisJobRepository.from_settings(
        settings=case.settings,
        owner_user_id=uuid4(),
        persistence=case.repo.persistence,
        object_storage=storage,
    )
    try:
        with pytest.raises(JobNotFoundError):
            tracking_evidence_diagnostic(repo, AID)
    finally:
        repo.close()
    assert client.head_calls == client.get_calls == 0


@pytest.mark.parametrize("report_case", ["local"], indirect=True)
@pytest.mark.parametrize(
    ("artifact", "change"),
    [
        ("tracking/tracking.json", {"artifacts": {"observations_jsonl": "other.jsonl"}}),
        ("analytics/analytics.json", {"source_observations": "tracking/other.jsonl"}),
        ("tracking/player_candidates.json", {"schema_version": 2}),
    ],
)
def test_diagnostic_rejects_mismatched_saved_references(
    report_case: ReportCase, tmp_path: Path, artifact: str, change: dict[str, Any]
) -> None:
    root = report_case.repo.analysis_dir(AID)
    paths: dict[str, Path] = {}
    for key in (
        "tracking/tracking.json",
        "tracking/observations.jsonl",
        "tracking/player_candidates.json",
        "analytics/analytics.json",
        "metadata.json",
    ):
        target = tmp_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / key).read_bytes())
        paths[key] = target
    payload = json.loads(paths[artifact].read_text(encoding="utf-8"))
    for field, value in change.items():
        if isinstance(value, dict):
            payload[field].update(value)
        else:
            payload[field] = value
    paths[artifact].write_text(json.dumps(payload), encoding="utf-8")

    class SavedEvidence:
        @contextmanager
        def verified_diagnostic_artifacts(self, analysis_id: str) -> Iterator[dict[str, Path]]:
            assert analysis_id == AID
            yield paths

        def current_diagnostic_selection(self, analysis_id: str) -> PlayerSelectionInput:
            return report_case.repo.current_diagnostic_selection(analysis_id)  # type: ignore[return-value]

    with pytest.raises(JobConflictError):
        tracking_evidence_diagnostic(SavedEvidence(), AID)  # type: ignore[arg-type]


@pytest.mark.parametrize("report_case", ["local"], indirect=True)
def test_diagnostic_rejects_persisted_selection_mismatch(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        report_case.repo,
        "current_diagnostic_selection",
        lambda analysis_id: PlayerSelectionInput("wrong-candidate", 1, [1]),
    )
    with pytest.raises(JobConflictError) as failure:
        tracking_evidence_diagnostic(report_case.repo, AID)
    assert failure.value.code == "diagnostic_lineage_changed"
