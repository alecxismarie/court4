"""Synthetic-only stress and failure tests for the disabled diagnostic stream path."""

from __future__ import annotations

import hashlib
import json
import os
import time
from asyncio import CancelledError
from collections import defaultdict
from collections.abc import Callable, Collection, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier, Event, Lock, Thread
from typing import BinaryIO, cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.persistence.models import AnalysisArtifact
from app.persistence.object_storage import ObjectMetadata, ObjectStreamLimitError, S3ObjectStorage
from app.persistence.runtime import PersistenceRuntime
from app.persistence.service import PlayerSelectionInput
from app.persistence.storage import LocalStorage
from app.schemas.jobs import AnalysisJob
from app.schemas.player_tracking import PlayerObservation
from app.services.jobs.exceptions import (
    JobConflictError,
    JobNotFoundError,
    JobStorageBackendError,
    JobStorageCapacityError,
)
from app.services.jobs.repository import AnalysisJobRepository
from app.services.tracking.diagnostic import _StreamingAccumulator, tracking_evidence_diagnostic
from tests import test_candidate_evidence_lineage as lineage
from tests import test_report_reads as reads
from tests.test_report_reads import AID, ReportCase

lineage_case = lineage.lineage_case
report_case = reads.report_case
OBSERVATIONS = "tracking/observations.jsonl"
STRUCTURED = (
    "tracking/tracking.json",
    "tracking/player_candidates.json",
    "analytics/analytics.json",
    "metadata.json",
)
ALL_KEYS = (*STRUCTURED, OBSERVATIONS)
CEILING = 18 * 1024 * 1024


@dataclass
class _Spec:
    path: Path
    size: int
    checksum: str
    content_type: str


class _Registry:
    def __init__(self, owner: UUID) -> None:
        self.owner = owner
        self.specs: dict[str, dict[str, _Spec]] = {}
        self.selections: dict[str, PlayerSelectionInput] = {}

    def get_artifacts(
        self, *, owner_user_id: UUID, analysis_id: str, logical_keys: Collection[str]
    ) -> list[AnalysisArtifact]:
        if owner_user_id != self.owner or analysis_id not in self.specs:
            return []
        return [
            AnalysisArtifact(
                owner_user_id=self.owner,
                analysis_id=analysis_id,
                artifact_kind="structured",
                storage_provider="s3",
                storage_key=_key(analysis_id, logical_key),
                logical_key=logical_key,
                content_type=self.specs[analysis_id][logical_key].content_type,
                size_bytes=self.specs[analysis_id][logical_key].size,
                checksum_sha256=self.specs[analysis_id][logical_key].checksum,
                state="available",
                is_current=True,
            )
            for logical_key in logical_keys
            if logical_key in self.specs[analysis_id]
        ]


class _Persistence:
    def __init__(self, service: _Registry) -> None:
        self.service = service


def _key(analysis_id: str, logical_key: str) -> str:
    return f"synthetic/{analysis_id}/{logical_key}"


class _MissingObject(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class _Body:
    def __init__(
        self,
        source: BinaryIO,
        *,
        fail_after: int | None = None,
        failure: BaseException | None = None,
        on_progress: Callable[[], None] | None = None,
    ) -> None:
        self.source = source
        self.fail_after = fail_after
        self.failure = failure
        self.on_progress = on_progress
        self.bytes_read = 0
        self.closed = False
        self.notified = False

    def read(self, size: int = -1) -> bytes:
        if self.fail_after is not None and self.bytes_read >= self.fail_after:
            assert self.failure is not None
            raise self.failure
        data = self.source.read(size)
        self.bytes_read += len(data)
        if data and self.on_progress is not None and not self.notified:
            self.notified = True
            self.on_progress()
        return data

    def close(self) -> None:
        self.closed = True
        self.source.close()


class _Client:
    def __init__(self, registry: _Registry) -> None:
        self.registry = registry
        self.bodies: list[_Body] = []
        self.lock = Lock()
        self.get_missing = False
        self.fail_after: int | None = None
        self.failure: BaseException | None = None
        self.on_progress: Callable[[], None] | None = None
        self.barrier: Barrier | None = None
        self.head_size_override: int | None = None

    def _spec(self, key: str) -> _Spec:
        _, analysis_id, logical_key = key.split("/", 2)
        return self.registry.specs[analysis_id][logical_key]

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "test"
        spec = self._spec(Key)
        size = self.head_size_override if Key.endswith(OBSERVATIONS) else None
        return {
            "ContentLength": spec.size if size is None else size,
            "ContentType": spec.content_type,
            "Metadata": {"court4-sha256": spec.checksum},
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _Body]:
        assert Bucket == "test"
        observation = Key.endswith(OBSERVATIONS)
        if observation and self.get_missing:
            raise _MissingObject()
        if observation and self.barrier is not None:
            self.barrier.wait(timeout=30)
        spec = self._spec(Key)
        body = _Body(
            spec.path.open("rb"),
            fail_after=self.fail_after if observation else None,
            failure=self.failure if observation else None,
            on_progress=self.on_progress if observation else None,
        )
        with self.lock:
            self.bodies.append(body)
        return {"Body": body}


class _Repository(AnalysisJobRepository):
    def __init__(
        self,
        *,
        analysis_id: str,
        registry: _Registry,
        storage: S3ObjectStorage,
        workspace: Path,
        capacity: Path,
    ) -> None:
        super().__init__(
            output_dir=workspace,
            api_base_path="/api/v1",
            owner_user_id=registry.owner,
            persistence=cast(PersistenceRuntime, _Persistence(registry)),
            object_storage=storage,
            capacity_root=capacity,
            cleanup_workspace=True,
        )
        self.synthetic_id = analysis_id
        self.registry = registry

    def load_job_metadata(self, analysis_id: str) -> AnalysisJob:
        if analysis_id != self.synthetic_id or analysis_id not in self.registry.specs:
            raise JobNotFoundError("Synthetic match unavailable.")
        return cast(AnalysisJob, object())

    @contextmanager
    def media_operation(
        self, analysis_id: str, *, exclusive: bool = False, wait: bool = False
    ) -> Iterator[None]:
        del exclusive, wait
        self.load_job_metadata(analysis_id)
        yield

    def current_diagnostic_selection(self, analysis_id: str) -> PlayerSelectionInput | None:
        return self.registry.selections.get(analysis_id)


def _write(path: Path, data: bytes) -> _Spec:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _Spec(path, len(data), hashlib.sha256(data).hexdigest(), "application/json")


def _large_observations(source: bytes, path: Path, target_size: int) -> tuple[_Spec, int]:
    original = [json.loads(line) for line in source.splitlines() if line.strip()]
    groups: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in original:
        row["frame_index"] = int(row["frame_index"]) * 2000
        groups[int(row["frame_index"])].append(row)
    frames = sorted(groups)
    assert len(frames) >= 2
    timestamp = {frame: float(str(groups[frame][0]["timestamp_seconds"])) for frame in frames}
    assert all(timestamp[b] > timestamp[a] for a, b in zip(frames, frames[1:], strict=False))
    template = dict(original[0])
    filler_id = 10_000
    digest = hashlib.sha256()
    size = 0
    count = 0
    next_group = 1

    def emit(output: BinaryIO, row: dict[str, object]) -> None:
        nonlocal size, count
        line = json.dumps(row, separators=(",", ":")).encode() + b"\n"
        output.write(line)
        digest.update(line)
        size += len(line)
        count += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        for frame in range(frames[0], frames[-1] + 1):
            while next_group < len(frames) - 1 and frame >= frames[next_group]:
                next_group += 1
            if frame in groups:
                for row in groups[frame]:
                    emit(output, row)
            elif size < target_size - 100_000:
                left, right = frames[next_group - 1], frames[next_group]
                fraction = (frame - left) / (right - left)
                filler = dict(template)
                filler["frame_index"] = frame
                filler["timestamp_seconds"] = round(
                    timestamp[left] + (timestamp[right] - timestamp[left]) * fraction, 8
                )
                filler["track_id"] = filler_id
                emit(output, filler)
    assert 16 * 1024 * 1024 < size <= CEILING
    assert count <= 100_000
    return _Spec(path, size, digest.hexdigest(), "application/octet-stream"), count


def _synthetic_setup(
    case: ReportCase, tmp_path: Path, *, copies: int
) -> tuple[_Registry, _Client, S3ObjectStorage, list[str], int, int]:
    assert case.storage is not None
    originals = case.records()
    source = case.storage.objects[originals[OBSERVATIONS].storage_key]["data"]
    obs_spec, rows = _large_observations(
        source, tmp_path / "source" / "observations.jsonl", CEILING - 1024
    )
    owner = uuid4()
    registry = _Registry(owner)
    selection = case.repo.current_diagnostic_selection(AID)
    assert selection is not None
    names = [f"synthetic-stream-{index}" for index in range(copies)]
    for analysis_id in names:
        registry.specs[analysis_id] = {}
        registry.selections[analysis_id] = selection
        for logical_key in STRUCTURED:
            data = case.storage.objects[originals[logical_key].storage_key]["data"]
            report = json.loads(data)
            report["analysis_id"] = analysis_id
            if logical_key == "tracking/tracking.json":
                report["processed_frame_count"] = 120_001
            encoded = json.dumps(report, separators=(",", ":")).encode()
            registry.specs[analysis_id][logical_key] = _write(
                tmp_path / "source" / analysis_id / logical_key, encoded
            )
        registry.specs[analysis_id][OBSERVATIONS] = obs_spec
    client = _Client(registry)
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    return registry, client, storage, names, obs_spec.size, rows


def _repo(tmp_path: Path, name: str, registry: _Registry, storage: S3ObjectStorage) -> _Repository:
    return _Repository(
        analysis_id=name,
        registry=registry,
        storage=storage,
        workspace=tmp_path / "workspaces" / name,
        capacity=tmp_path / "capacity",
    )


def _rss_bytes() -> int:
    with Path("/proc/self/statm").open(encoding="ascii") as status:
        pages = int(status.read().split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE")


def _workspace_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:
            # Diagnostic cleanup can remove a file between directory scan and stat.
            continue
    return total


class _Sampler:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.baseline_rss = _rss_bytes()
        self.peak_rss = self.baseline_rss
        self.peak_workspace = 0
        self.stop_event = Event()
        self.thread = Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop_event.wait(0.005):
            self.peak_rss = max(self.peak_rss, _rss_bytes())
            self.peak_workspace = max(self.peak_workspace, _workspace_bytes(self.workspace))

    def __enter__(self) -> _Sampler:
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)
        self.peak_rss = max(self.peak_rss, _rss_bytes())
        self.peak_workspace = max(self.peak_workspace, _workspace_bytes(self.workspace))


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_profile_single_near_18_mib(
    report_case: ReportCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, client, storage, names, size, rows = _synthetic_setup(report_case, tmp_path, copies=1)
    monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", CEILING)
    repo = _repo(tmp_path, names[0], registry, storage)
    started = time.monotonic()
    with _Sampler(tmp_path / "workspaces") as sample:
        try:
            summary = tracking_evidence_diagnostic(repo, names[0])
            elapsed = time.monotonic() - started
            assert summary["analysis_id"] == names[0]
            assert summary["identity_of_other_raw_ids"] == "Unknown"
            assert not (repo.analysis_dir(names[0]) / OBSERVATIONS).exists()
        finally:
            repo.close()
    assert all(body.closed for body in client.bodies)
    assert (
        sum(body.bytes_read for body in client.bodies if body.bytes_read > 16 * 1024 * 1024) == size
    )
    assert not repo.output_dir.exists()
    capacity = LocalStorage(tmp_path / "capacity")
    assert capacity.root not in LocalStorage._active_reads_by_root
    assert capacity.root not in LocalStorage._reserved_by_root
    print(
        "PROFILE_SINGLE",
        json.dumps(
            {
                "artifact_bytes": size,
                "rows": rows,
                "elapsed_seconds": round(elapsed, 3),
                "rss_baseline_bytes": sample.baseline_rss,
                "rss_peak_bytes": sample.peak_rss,
                "workspace_peak_bytes": sample.peak_workspace,
                "workspace_after_bytes": _workspace_bytes(tmp_path / "workspaces"),
                "bodies": len(client.bodies),
            }
        ),
    )


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_profile_four_concurrent_near_18_mib(
    report_case: ReportCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, client, storage, names, size, rows = _synthetic_setup(report_case, tmp_path, copies=4)
    monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", CEILING)
    client.barrier = Barrier(4)
    repos = [_repo(tmp_path, name, registry, storage) for name in names]

    def run(repo: _Repository) -> tuple[dict[str, object], float]:
        started = time.monotonic()
        try:
            result = tracking_evidence_diagnostic(repo, repo.synthetic_id)
            return result, time.monotonic() - started
        finally:
            repo.close()

    started = time.monotonic()
    with _Sampler(tmp_path / "workspaces") as sample, ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, repos))
    elapsed = time.monotonic() - started
    assert {result[0]["analysis_id"] for result in results} == set(names)
    assert all(body.closed for body in client.bodies)
    assert (
        sum(body.bytes_read for body in client.bodies if body.bytes_read > 16 * 1024 * 1024)
        == 4 * size
    )
    assert all(not repo.output_dir.exists() for repo in repos)
    capacity = LocalStorage(tmp_path / "capacity")
    assert capacity.root not in LocalStorage._active_reads_by_root
    assert capacity.root not in LocalStorage._reserved_by_root
    print(
        "PROFILE_FOUR",
        json.dumps(
            {
                "artifact_bytes_each": size,
                "rows_each": rows,
                "elapsed_seconds": round(elapsed, 3),
                "request_seconds": [round(duration, 3) for _, duration in results],
                "rss_baseline_bytes": sample.baseline_rss,
                "rss_peak_bytes": sample.peak_rss,
                "workspace_peak_bytes": sample.peak_workspace,
                "workspace_after_bytes": _workspace_bytes(tmp_path / "workspaces"),
                "bodies": len(client.bodies),
            }
        ),
    )


def _failure_request(
    tmp_path: Path,
    registry: _Registry,
    client: _Client,
    storage: S3ObjectStorage,
    name: str,
    error: type[BaseException],
) -> BaseException:
    repo = _repo(tmp_path, name, registry, storage)
    try:
        with pytest.raises(error) as failure:
            tracking_evidence_diagnostic(repo, name)
        assert not (repo.analysis_dir(name) / OBSERVATIONS).exists()
    finally:
        repo.close()
    assert all(body.closed for body in client.bodies)
    assert not repo.output_dir.exists()
    capacity = LocalStorage(tmp_path / "capacity")
    assert capacity.root not in LocalStorage._active_reads_by_root
    assert capacity.root not in LocalStorage._reserved_by_root
    assert _workspace_bytes(tmp_path / "workspaces") == 0
    return failure.value


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_stream_transfer_failures_close_bodies_and_leave_no_summary(
    report_case: ReportCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, client, storage, names, size, _ = _synthetic_setup(report_case, tmp_path, copies=1)
    monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", CEILING)
    name = names[0]
    source = registry.specs[name][OBSERVATIONS].path

    client.get_missing = True
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, JobNotFoundError),
        JobNotFoundError,
    )
    client.get_missing = False

    client.fail_after = 1024 * 1024
    client.failure = OSError("synthetic mid-body read error")
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, JobStorageBackendError),
        JobStorageBackendError,
    )
    client.failure = CancelledError()
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, CancelledError),
        CancelledError,
    )
    client.fail_after = None
    client.failure = None

    with source.open("ab") as output:
        output.write(b" ")
    extra = _failure_request(tmp_path, registry, client, storage, name, JobStorageCapacityError)
    assert isinstance(extra, JobStorageCapacityError) and extra.code == "diagnostic_stream_limit"
    with source.open("r+b") as output:
        output.truncate(size)

    with source.open("r+b") as output:
        output.seek(-1, 2)
        output.write(b" ")
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, JobStorageBackendError),
        JobStorageBackendError,
    )
    with source.open("r+b") as output:
        output.seek(-1, 2)
        output.write(b"\n")

    with source.open("r+b") as output:
        output.truncate(size - 1)
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, JobStorageBackendError),
        JobStorageBackendError,
    )
    with source.open("ab") as output:
        output.write(b"\n")

    client.head_size_override = size - 1
    assert isinstance(
        _failure_request(tmp_path, registry, client, storage, name, JobNotFoundError),
        JobNotFoundError,
    )
    client.head_size_override = None


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_registry_and_selection_changes_during_stream_reject_stale_result(
    report_case: ReportCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, client, storage, names, _, _ = _synthetic_setup(report_case, tmp_path, copies=1)
    monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", CEILING)
    name = names[0]
    spec = registry.specs[name][OBSERVATIONS]
    original_checksum = spec.checksum
    client.on_progress = lambda: setattr(spec, "checksum", "0" * 64)
    failure = _failure_request(tmp_path, registry, client, storage, name, JobConflictError)
    assert isinstance(failure, JobConflictError) and failure.code == "diagnostic_lineage_changed"
    spec.checksum = original_checksum

    selection = registry.selections[name]
    client.on_progress = lambda: registry.selections.__setitem__(
        name,
        PlayerSelectionInput(
            candidate_id="different-selection",
            track_id=selection.track_id,
            source_track_ids=selection.source_track_ids,
        ),
    )
    failure = _failure_request(tmp_path, registry, client, storage, name, JobConflictError)
    assert isinstance(failure, JobConflictError) and failure.code == "diagnostic_lineage_changed"
    client.on_progress = None


def _row(frame: int, seconds: float, raw_id: int) -> PlayerObservation:
    return PlayerObservation.model_validate(
        {
            "frame_index": frame,
            "timestamp_seconds": seconds,
            "track_id": raw_id,
            "bounding_box": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
            "confidence": 0.9,
            "image_ground_point": [0, 0],
            "court_position": [0, 0],
            "inside_court": True,
            "inside_extended_court": True,
            "excluded_from_player_tracks": False,
        }
    )


def test_distinct_id_frame_group_interval_and_segment_boundaries() -> None:
    ids = _StreamingAccumulator({0}, time.monotonic() + 15)
    for raw_id in range(4096):
        ids.add(_row(raw_id, raw_id / 100, raw_id))
    ids.add(_row(4096, 40.96, 0))
    assert len(ids.finish().other_spans) == 4095
    with pytest.raises(JobStorageCapacityError) as over_ids:
        ids.add(_row(4097, 40.97, 4096))
    assert over_ids.value.code == "diagnostic_stream_limit"

    group = _StreamingAccumulator({1}, time.monotonic() + 15)
    group.add(_row(0, 0.0, 1))
    for _ in range(127):
        group.add(_row(0, 0.0, 2))
    group.add(_row(1, 0.1, 1))
    assert group.finish().valid_frames == 2
    too_many = _StreamingAccumulator({1}, time.monotonic() + 15)
    too_many.add(_row(0, 0.0, 1))
    for _ in range(127):
        too_many.add(_row(0, 0.0, 2))
    with pytest.raises(JobStorageCapacityError) as over_frame:
        too_many.add(_row(0, 0.0, 2))
    assert over_frame.value.code == "diagnostic_stream_limit"

    intervals = _StreamingAccumulator({1, 2}, time.monotonic() + 15)
    for frame in range(2049):
        intervals.add(_row(frame, frame * 2.0, 1 if frame % 512 < 256 else 2))
    supported = intervals.finish()
    assert len(supported.rejected) == 2048
    assert {"raw_id_changed", "gap_over_one_second"}.issubset(
        {reason for item in supported.rejected for reason in item["reasons"]}
    )
    with pytest.raises(JobStorageCapacityError) as over_intervals:
        intervals.add(_row(2049, 4098.0, 1))
        intervals.finish()
    assert over_intervals.value.code == "diagnostic_stream_limit"


def test_stream_line_and_byte_boundaries_with_valid_json(tmp_path: Path) -> None:
    row = _row(0, 0.0, 1)
    compact = json.dumps(row.model_dump(mode="json"), separators=(",", ":")).encode()
    exact = compact + b" " * (16 * 1024 - len(compact) - 1) + b"\n"
    assert len(exact) == 16 * 1024
    owner = uuid4()
    registry = _Registry(owner)
    name = "line-boundary"
    spec = _write(tmp_path / "exact.jsonl", exact)
    registry.specs[name] = {OBSERVATIONS: spec}
    client = _Client(registry)
    storage = S3ObjectStorage(client=client, diagnostic_client=client, bucket="test")
    key = _key(name, OBSERVATIONS)

    def stream(max_bytes: int) -> list[bytes]:
        expected = ObjectMetadata(key, spec.size, spec.checksum, spec.content_type)
        with storage.diagnostic_stream_lines(
            key=key,
            expected=expected,
            max_bytes=max_bytes,
            max_line_bytes=16 * 1024,
            deadline=time.monotonic() + 5,
        ) as lines:
            return list(lines)

    assert stream(spec.size) == [exact]
    assert PlayerObservation.model_validate_json(exact).track_id == 1
    with pytest.raises(ObjectStreamLimitError):
        stream(spec.size - 1)
    assert all(body.closed for body in client.bodies)

    over = compact + b" " * (16 * 1024 - len(compact)) + b"\n"
    assert len(over) == 16 * 1024 + 1
    spec.path.write_bytes(over)
    spec.size = len(over)
    spec.checksum = hashlib.sha256(over).hexdigest()
    with pytest.raises(ObjectStreamLimitError):
        stream(spec.size)
    assert all(body.closed for body in client.bodies)


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_row_and_response_boundaries_use_complete_stream(
    report_case: ReportCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.tracking import diagnostic

    registry, client, storage, names, size, rows = _synthetic_setup(report_case, tmp_path, copies=1)
    monkeypatch.setattr(AnalysisJobRepository, "MAX_DIAGNOSTIC_STREAM_BYTES", CEILING)
    name = names[0]
    spec = registry.specs[name][OBSERVATIONS]
    blank_rows = 100_000 - rows
    assert blank_rows > 0
    with spec.path.open("ab") as output:
        output.write(b"\n" * blank_rows)
    spec.size = size + blank_rows
    assert spec.size <= CEILING
    spec.checksum = hashlib.sha256(spec.path.read_bytes()).hexdigest()

    repo = _repo(tmp_path, name, registry, storage)
    try:
        result = tracking_evidence_diagnostic(repo, name)
        response_bytes = len(json.dumps(result, separators=(",", ":")).encode())
    finally:
        repo.close()
    monkeypatch.setattr(diagnostic, "MAX_RESPONSE_BYTES", response_bytes)
    repo = _repo(tmp_path, name, registry, storage)
    try:
        assert tracking_evidence_diagnostic(repo, name) == result
    finally:
        repo.close()
    monkeypatch.setattr(diagnostic, "MAX_RESPONSE_BYTES", response_bytes - 1)
    response_failure = _failure_request(
        tmp_path, registry, client, storage, name, JobStorageCapacityError
    )
    assert isinstance(response_failure, JobStorageCapacityError)
    assert response_failure.code == "diagnostic_response_limit"
    monkeypatch.setattr(diagnostic, "MAX_RESPONSE_BYTES", 512 * 1024)

    with spec.path.open("ab") as output:
        output.write(b"\n")
    spec.size += 1
    assert spec.size <= CEILING
    spec.checksum = hashlib.sha256(spec.path.read_bytes()).hexdigest()
    row_failure = _failure_request(
        tmp_path, registry, client, storage, name, JobStorageCapacityError
    )
    assert isinstance(row_failure, JobStorageCapacityError)
    assert row_failure.code == "diagnostic_execution_limit"


def test_execution_deadline_boundary() -> None:
    from app.services.tracking import diagnostic

    with patch.object(diagnostic.time, "monotonic", return_value=10.0):
        diagnostic._check_limits(10.0, 100_000)
        with pytest.raises(JobStorageCapacityError):
            diagnostic._check_limits(10.0, 100_001)
    with (
        patch.object(diagnostic.time, "monotonic", return_value=10.000_001),
        pytest.raises(JobStorageCapacityError),
    ):
        diagnostic._check_limits(10.0, 0)
