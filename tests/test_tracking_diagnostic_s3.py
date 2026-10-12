"""Diagnostic storage admission, transfer bounds, and evidence consistency."""

import hashlib
import io
import json
import time
import tracemalloc
from asyncio import CancelledError
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.config.settings import Settings
from app.persistence.models import AnalysisArtifact
from app.persistence.object_storage import (
    ObjectMetadata,
    ObjectStorageError,
    ObjectStreamLimitError,
    S3ObjectStorage,
)
from app.persistence.service import PlayerSelectionInput
from app.persistence.storage import LocalStorage
from app.schemas.player_tracking import PlayerObservation
from app.services.jobs.exceptions import (
    JobConflictError,
    JobNotFoundError,
    JobStorageBackendError,
    JobStorageCapacityError,
)
from app.services.jobs.repository import AnalysisJobRepository, DiagnosticEvidence
from app.services.tracking.diagnostic import (
    _StreamingAccumulator,
    tracking_evidence_diagnostic,
)
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
def test_streaming_summary_equals_hydrated_summary_for_registered_evidence(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, client, storage = diagnostic_s3
    assert case.storage is not None
    observation_record = case.records()["tracking/observations.jsonl"]
    stored = case.storage.objects[observation_record.storage_key]
    ordered_rows = sorted(
        (json.loads(line) for line in stored["data"].splitlines()),
        key=lambda row: (row["frame_index"], row["timestamp_seconds"], row["track_id"]),
    )
    ordered_bytes = b"".join(
        json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in ordered_rows
    )
    checksum = hashlib.sha256(ordered_bytes).hexdigest()
    stored["data"] = ordered_bytes
    stored["metadata"]["court4-sha256"] = checksum
    with case.repo.persistence.session_factory.begin() as session:
        session.execute(
            update(AnalysisArtifact)
            .where(AnalysisArtifact.id == observation_record.id)
            .values(size_bytes=len(ordered_bytes), checksum_sha256=checksum)
        )
    repo = _repository(case, storage)
    try:
        expected = tracking_evidence_diagnostic(repo, AID)
        records = case.records()
        observations = records["tracking/observations.jsonl"]
        other_max = max(
            record.size_bytes
            for key, record in records.items()
            if key
            in {
                "tracking/tracking.json",
                "tracking/player_candidates.json",
                "analytics/analytics.json",
                "metadata.json",
            }
        )
        assert observations.size_bytes > other_max
        monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", other_max)
        monkeypatch.setattr(
            AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", observations.size_bytes
        )
        assert tracking_evidence_diagnostic(repo, AID) == expected
        assert client.head_calls == 10
        assert client.get_calls == 6
        assert client.body is not None and client.body.closed

        from app.services.tracking import diagnostic

        monkeypatch.setattr(diagnostic, "MAX_RESPONSE_BYTES", 8)
        with pytest.raises(JobStorageCapacityError) as response_limit:
            tracking_evidence_diagnostic(repo, AID)
        assert response_limit.value.code == "diagnostic_response_limit"
        monkeypatch.setattr(diagnostic, "MAX_RESPONSE_BYTES", 512 * 1024)

        monkeypatch.setattr(diagnostic, "MAX_OBSERVATION_ROWS", 1)
        with pytest.raises(JobStorageCapacityError) as row_limit:
            tracking_evidence_diagnostic(repo, AID)
        assert row_limit.value.code == "diagnostic_execution_limit"
        monkeypatch.setattr(diagnostic, "MAX_OBSERVATION_ROWS", 100_000)

        stored["data"] = ordered_bytes[:-1] + b" "
        with pytest.raises(JobStorageBackendError):
            tracking_evidence_diagnostic(repo, AID)
        assert client.body is not None and client.body.closed

        malformed = b"!" + ordered_bytes[1:]
        malformed_checksum = hashlib.sha256(malformed).hexdigest()
        stored["data"] = malformed
        stored["metadata"]["court4-sha256"] = malformed_checksum
        with case.repo.persistence.session_factory.begin() as session:
            session.execute(
                update(AnalysisArtifact)
                .where(AnalysisArtifact.id == observation_record.id)
                .values(checksum_sha256=malformed_checksum)
            )
        with pytest.raises(JobConflictError) as invalid:
            tracking_evidence_diagnostic(repo, AID)
        assert invalid.value.code == "diagnostic_invalid_evidence"
        root = LocalStorage(case.settings.processing_workspace_root).root
        assert root not in LocalStorage._active_reads_by_root
        assert root not in LocalStorage._reserved_by_root
    finally:
        repo.close()


@pytest.mark.parametrize("payload", [b"first\nsecond\n", b"first\n", b"first\nthird\n"])
def test_streamed_object_requires_complete_registered_size_and_checksum(payload: bytes) -> None:
    key = "tracking/observations.jsonl"
    client = DiagnosticClient({key: {"data": payload, "content_type": "", "metadata": {}}})
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    registered = b"first\nsecond\n"
    expected = ObjectMetadata(key, len(registered), hashlib.sha256(registered).hexdigest(), "")
    if payload == registered:
        with storage.diagnostic_stream_lines(
            key=key,
            expected=expected,
            max_bytes=len(registered),
            max_line_bytes=20,
            deadline=time.monotonic() + 5,
        ) as lines:
            assert list(lines) == [b"first\n", b"second\n"]
    else:
        with (
            pytest.raises(ObjectStorageError),
            storage.diagnostic_stream_lines(
                key=key,
                expected=expected,
                max_bytes=len(registered),
                max_line_bytes=20,
                deadline=time.monotonic() + 5,
            ) as lines,
        ):
            list(lines)
    assert client.body is not None and client.body.closed


@pytest.mark.parametrize("limit", ["bytes", "line", "time", "early_exit", "cancel"])
def test_streamed_object_limits_and_cleanup(limit: str) -> None:
    key = "tracking/observations.jsonl"
    payload = b"first\nsecond\n"
    client = DiagnosticClient({key: {"data": payload, "content_type": "", "metadata": {}}})
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    expected = ObjectMetadata(key, len(payload), hashlib.sha256(payload).hexdigest(), "")
    error: type[BaseException] = (
        ObjectStorageError
        if limit == "early_exit"
        else CancelledError
        if limit == "cancel"
        else ObjectStreamLimitError
    )
    with (
        pytest.raises(error),
        storage.diagnostic_stream_lines(
            key=key,
            expected=expected,
            max_bytes=len(payload) - 1 if limit == "bytes" else len(payload),
            max_line_bytes=3 if limit == "line" else 20,
            deadline=time.monotonic() - 1 if limit == "time" else time.monotonic() + 5,
        ) as lines,
    ):
        if limit == "cancel":
            raise CancelledError()
        if limit == "early_exit":
            next(lines)
        else:
            list(lines)
    assert client.body is None or client.body.closed


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_streaming_rejects_out_of_order_registered_rows_and_releases_slot(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, client, storage = diagnostic_s3
    records = case.records()
    observations = records["tracking/observations.jsonl"]
    other_max = max(
        records[key].size_bytes
        for key in (
            "tracking/tracking.json",
            "tracking/player_candidates.json",
            "analytics/analytics.json",
            "metadata.json",
        )
    )
    assert observations.size_bytes > other_max
    monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", other_max)
    monkeypatch.setattr(
        AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", observations.size_bytes
    )
    repo = _repository(case, storage)
    try:
        with pytest.raises(JobConflictError) as failure:
            tracking_evidence_diagnostic(repo, AID)
        assert failure.value.code == "diagnostic_stream_order"
    finally:
        repo.close()
    assert client.body is not None and client.body.closed
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_streaming_cancellation_closes_read_slot(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, _, storage = diagnostic_s3
    records = case.records()
    observations = records["tracking/observations.jsonl"]
    other_max = max(
        records[key].size_bytes
        for key in (
            "tracking/tracking.json",
            "tracking/player_candidates.json",
            "analytics/analytics.json",
            "metadata.json",
        )
    )
    monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", other_max)
    monkeypatch.setattr(
        AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", observations.size_bytes
    )

    def interrupted_lines() -> Iterator[bytes]:
        raise CancelledError()
        yield b""  # pragma: no cover

    @contextmanager
    def interrupted(**kwargs: Any) -> Iterator[Iterator[bytes]]:
        del kwargs
        yield interrupted_lines()

    monkeypatch.setattr(storage, "diagnostic_stream_lines", interrupted)
    repo = _repository(case, storage)
    try:
        with pytest.raises(CancelledError):
            tracking_evidence_diagnostic(repo, AID)
    finally:
        repo.close()
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
@pytest.mark.parametrize("violation", ["other_oversize", "video", "aggregate", "stream_bytes"])
def test_streaming_admission_preserves_registered_evidence_limits(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
    monkeypatch: pytest.MonkeyPatch,
    violation: str,
) -> None:
    case, client, storage = diagnostic_s3
    records = case.records()
    observations = records["tracking/observations.jsonl"]
    other_max = max(
        records[key].size_bytes
        for key in (
            "tracking/tracking.json",
            "tracking/player_candidates.json",
            "analytics/analytics.json",
            "metadata.json",
        )
    )
    if violation == "other_oversize":
        record = records["tracking/tracking.json"]
        changes: dict[str, Any] = {"size_bytes": 16 * 1024 * 1024 + 1}
    elif violation == "video":
        record = observations
        changes = {"content_type": "video/mp4"}
    elif violation == "aggregate":
        record = observations
        changes = {"size_bytes": 64 * 1024 * 1024 + 1}
        monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", 70 * 1024 * 1024)
    else:
        record = observations
        changes = {}
        monkeypatch.setattr(
            AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", observations.size_bytes - 1
        )
    if changes:
        with case.repo.persistence.session_factory.begin() as session:
            session.execute(
                update(AnalysisArtifact).where(AnalysisArtifact.id == record.id).values(**changes)
            )
    if violation != "other_oversize":
        monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", other_max)
    repo = _repository(case, storage)
    try:
        with pytest.raises(JobStorageCapacityError) as failure:
            tracking_evidence_diagnostic(repo, AID)
        assert failure.value.code == "diagnostic_evidence_limit"
    finally:
        repo.close()
    assert client.head_calls == client.get_calls == 0


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_streaming_uses_existing_concurrent_read_slots(
    diagnostic_s3: tuple[ReportCase, DiagnosticClient, S3ObjectStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, client, storage = diagnostic_s3
    records = case.records()
    observations = records["tracking/observations.jsonl"]
    other_max = max(
        records[key].size_bytes
        for key in (
            "tracking/tracking.json",
            "tracking/player_candidates.json",
            "analytics/analytics.json",
            "metadata.json",
        )
    )
    monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", other_max)
    monkeypatch.setattr(
        AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", observations.size_bytes
    )
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
            assert failure.value.code == "diagnostic_read_unavailable"
        finally:
            repo.close()
    finally:
        for reservation in held:
            reservation.release()
    assert client.head_calls == client.get_calls == 0
    assert capacity.root not in LocalStorage._active_reads_by_root


@pytest.mark.parametrize("limit", ["frame", "ids", "intervals"])
def test_streaming_accumulator_rejects_bounded_resources(
    limit: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.tracking import diagnostic

    row = PlayerObservation.model_validate(
        {
            "frame_index": 0,
            "timestamp_seconds": 0.0,
            "track_id": 1,
            "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
            "confidence": 0.9,
            "image_ground_point": [0, 0],
            "court_position": [0, 0],
            "inside_court": True,
            "inside_extended_court": True,
            "excluded_from_player_tracks": False,
        }
    )
    accumulator = _StreamingAccumulator({1, 2}, time.monotonic() + 5)
    accumulator.add(row)
    if limit == "frame":
        monkeypatch.setattr(diagnostic, "MAX_STREAM_FRAME_ROWS", 1)
        subsequent = row.model_copy(update={"track_id": 2})
        with pytest.raises(JobStorageCapacityError) as failure:
            accumulator.add(subsequent)
    elif limit == "ids":
        monkeypatch.setattr(diagnostic, "MAX_STREAM_DISTINCT_IDS", 1)
        subsequent = row.model_copy(
            update={"frame_index": 1, "timestamp_seconds": 0.1, "track_id": 2}
        )
        with pytest.raises(JobStorageCapacityError) as failure:
            accumulator.add(subsequent)
    else:
        monkeypatch.setattr(diagnostic, "MAX_STREAM_INTERVALS", 1)
        accumulator.add(row.model_copy(update={"frame_index": 1, "timestamp_seconds": 2.0}))
        accumulator.add(row.model_copy(update={"frame_index": 2, "timestamp_seconds": 4.0}))
        with pytest.raises(JobStorageCapacityError) as failure:
            accumulator.add(row.model_copy(update={"frame_index": 3, "timestamp_seconds": 6.0}))
    assert failure.value.code == "diagnostic_stream_limit"


def test_streaming_accumulator_preserves_selected_evidence_semantics() -> None:
    original = PlayerObservation.model_validate(
        {
            "frame_index": 0,
            "timestamp_seconds": 0.0,
            "track_id": 1,
            "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
            "confidence": 0.9,
            "image_ground_point": [0, 0],
            "court_position": [0, 0],
            "inside_court": True,
            "inside_extended_court": True,
            "excluded_from_player_tracks": False,
        }
    )
    rows = [
        original,
        original.model_copy(update={"confidence": 0.2}),
        original.model_copy(update={"track_id": 3}),
        original.model_copy(
            update={"frame_index": 1, "timestamp_seconds": 0.2, "excluded_from_player_tracks": True}
        ),
        original.model_copy(update={"frame_index": 1, "timestamp_seconds": 0.2, "track_id": 3}),
        original.model_copy(update={"frame_index": 2, "timestamp_seconds": 0.4}),
        original.model_copy(update={"frame_index": 3, "timestamp_seconds": 1.6, "track_id": 2}),
        original.model_copy(update={"frame_index": 3, "timestamp_seconds": 1.6, "track_id": 4}),
        original.model_copy(update={"frame_index": 4, "timestamp_seconds": 1.8, "track_id": 2}),
        original.model_copy(update={"frame_index": 5, "timestamp_seconds": 2.0, "track_id": 2}),
        original.model_copy(update={"frame_index": 6, "timestamp_seconds": 2.2, "track_id": 5}),
    ]
    accumulator = _StreamingAccumulator({1, 2}, time.monotonic() + 5)
    for row in rows:
        accumulator.add(row)
    summary = accumulator.finish()
    assert summary.raw_spans == {1: [0.0, 0.4], 2: [1.6, 2.0]}
    assert summary.counts["excluded_from_player_tracks"] == 1
    assert summary.counts["valid_court"] == 6
    assert summary.valid_frames == 5
    assert summary.observed_seconds == pytest.approx(0.4)
    assert summary.accepted == [{"start_seconds": 1.6, "end_seconds": 2.0, "raw_id": 2}]
    assert len(summary.rejected) == 3
    assert summary.rejected[2]["reasons"] == ["raw_id_changed", "gap_over_one_second"]
    assert summary.rejected[2]["other_raw_ids_present"] == [4]
    assert summary.other_before == []
    assert summary.other_after == [5]


def test_synthetic_stream_above_16_mib_profiles_memory_and_runtime(tmp_path: Path) -> None:
    key = "tracking/observations.jsonl"
    path = tmp_path / "synthetic-observations.jsonl"
    base = {
        "frame_index": 0,
        "timestamp_seconds": 0.0,
        "track_id": 1,
        "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
        "confidence": 0.9,
        "image_ground_point": [0, 0],
        "court_position": [0, 0],
        "inside_court": True,
        "inside_extended_court": True,
        "excluded_from_player_tracks": False,
        "interpolated": False,
    }
    digest = hashlib.sha256()
    size = 0
    count = 0
    with path.open("wb") as output:
        while size <= 17_610_383:
            base["frame_index"] = count
            base["timestamp_seconds"] = count / 100
            base["track_id"] = 1 if count < 2 else 2
            line = json.dumps(base, separators=(",", ":")).encode() + b"\n"
            output.write(line)
            digest.update(line)
            size += len(line)
            count += 1
    assert 16 * 1024 * 1024 < size < 64 * 1024 * 1024
    assert count < 100_000

    class FileClient:
        def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
            assert Bucket == "test" and Key == key
            return {"Body": path.open("rb")}

    client = FileClient()
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    expected = ObjectMetadata(key, size, digest.hexdigest(), "application/octet-stream")
    accumulator = _StreamingAccumulator({1}, time.monotonic() + 15)
    tracemalloc.start()
    started = time.monotonic()
    try:
        with storage.diagnostic_stream_lines(
            key=key,
            expected=expected,
            max_bytes=size,
            max_line_bytes=16 * 1024,
            deadline=started + 15,
        ) as lines:
            for line in lines:
                accumulator.add(PlayerObservation.model_validate_json(line))
        summary = accumulator.finish()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    elapsed = time.monotonic() - started
    assert summary.other_after == [2]
    print(
        f"synthetic_stream bytes={size} rows={count} seconds={elapsed:.3f} peak_python_bytes={peak}"
    )


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
        def verified_diagnostic_artifacts(self, analysis_id: str) -> Iterator[DiagnosticEvidence]:
            assert analysis_id == AID
            yield DiagnosticEvidence(paths)

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
