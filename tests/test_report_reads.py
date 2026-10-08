"""Report authority and bounded hydration through real API/persistence boundaries."""

import json
import shutil
from asyncio import CancelledError
from collections.abc import Iterator
from concurrent.futures import CancelledError as FutureCancelledError
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1.analyses import get_workflow_service
from app.api.v1.history import get_history_service
from app.auth import VerifiedUser
from app.config import get_settings
from app.persistence.models import Analysis, AnalysisArtifact
from app.persistence.object_storage import ObjectStorageError
from app.persistence.service import ArtifactInput
from app.persistence.storage import LocalStorage, StorageCapacityError
from app.services import report_observability
from app.services.jobs.exceptions import JobStorageCapacityError
from app.services.jobs.repository import AnalysisJobRepository
from app.services.jobs.workflow import AnalysisWorkflowService
from tests import test_candidate_evidence_lineage as lineage
from tests.test_direct_uploads import FakeMultipartStorage, _register_verified_user

lineage_case = lineage.lineage_case
AID = "candidate-test"
URL = lineage.BASE + "/analytics"
REQUIRED = {
    "tracking/player_candidates.json",
    "analytics/analytics.json",
    "analytics/match_iq.json",
}


@dataclass
class ReportCase:
    client: TestClient
    repo: AnalysisJobRepository
    storage: FakeMultipartStorage | None
    downloads: list[str]
    workspaces: list[Path]
    expected: dict[str, Any]
    settings: Any = None
    workspace_seed: dict[str, bytes] = field(default_factory=dict)

    def records(self) -> dict[str, AnalysisArtifact]:
        return {
            r.logical_key: r
            for r in self.repo.persistence.service.list_artifacts(
                owner_user_id=self.repo.owner_user_id, analysis_id=AID
            )
        }

    def remove_bytes(self, logical_key: str) -> None:
        record = self.records()[logical_key]
        if self.storage is not None:
            self.storage.objects.pop(record.storage_key, None)
        (self.repo.analysis_dir(AID) / logical_key).unlink(missing_ok=True)


@pytest.fixture(params=["local", "s3"])
def report_case(
    lineage_case: lineage.LineageCase,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ReportCase:
    client, repo, case = lineage_case
    lineage._select_and_analyze(client, case)
    expected = client.get(URL).json()
    storage = FakeMultipartStorage() if request.param == "s3" else None
    if storage is not None:
        repo = AnalysisJobRepository(
            output_dir=repo.output_dir,
            api_base_path="/api/v1",
            owner_user_id=repo.owner_user_id,
            persistence=repo.persistence,
            object_storage=storage,
        )
        repo.save_job(repo.load_job_metadata(AID))
    settings = get_settings().model_copy(
        update={
            "processing_workspace_root": tmp_path / "report-workspaces",
            "analysis_output_dir": repo.output_dir,
            "storage_warning_free_bytes": 2,
            "storage_hard_stop_free_bytes": 1,
        }
    )
    result = ReportCase(client, repo, storage, [], [], expected, settings)
    if storage is not None:
        original_download = storage.download_file

        def download(*, key: str, destination: Path) -> Any:
            result.downloads.append(key)
            # The fake storage normally raises KeyError for missing bytes, whereas
            # the real adapter raises ObjectNotFoundError. Check its metadata first.
            storage.stat(key=key)
            return original_download(key=key, destination=destination)

        monkeypatch.setattr(storage, "download_file", download)

    def workflow(user: VerifiedUser) -> Iterator[AnalysisWorkflowService]:
        instance = AnalysisJobRepository.from_settings(
            settings=settings,
            owner_user_id=user.id,
            persistence=repo.persistence,
            object_storage=storage or repo.object_storage,
        )
        if storage is not None:
            result.workspaces.append(instance.output_dir)
            for logical_key, data in result.workspace_seed.items():
                path = instance.analysis_dir(AID) / logical_key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        try:
            yield AnalysisWorkflowService(settings=settings, repository=instance)
        finally:
            instance.close()

    cast(FastAPI, client.app).dependency_overrides[get_workflow_service] = workflow

    def history(user: VerifiedUser) -> Iterator[Any]:
        instance = AnalysisJobRepository.from_settings(
            settings=settings,
            owner_user_id=user.id,
            persistence=repo.persistence,
            object_storage=storage or repo.object_storage,
        )
        try:
            from app.services.history import HistoryProjectionService

            yield HistoryProjectionService(repository=instance)
        finally:
            instance.close()

    cast(FastAPI, client.app).dependency_overrides[get_history_service] = history
    return result


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_processing_slot_does_not_block_bounded_authorized_reads(
    report_case: ReportCase,
) -> None:
    case = report_case
    storage = LocalStorage(case.settings.processing_workspace_root)
    reservation, _ = storage.reserve_capacity(
        requested_bytes=1_024,
        warning_free_bytes=2,
        hard_stop_free_bytes=1,
        max_active_uploads=1,
    )
    try:
        analyses = case.client.get("/api/v1/analyses")
        assert analyses.status_code == 200, analyses.text
        assert any(item["analysis_id"] == AID for item in analyses.json()["items"])
        play = case.client.get("/api/v1/play-history")
        assert play.status_code == 200, play.text
        artifact = case.client.get(lineage.BASE + "/artifacts/analytics/analytics.json")
        assert artifact.status_code == 200, artifact.text
        with pytest.raises(StorageCapacityError) as rejected:
            storage.reserve_capacity(
                requested_bytes=1,
                warning_free_bytes=2,
                hard_stop_free_bytes=1,
                max_active_uploads=1,
            )
        assert rejected.value.reason == "active_limit"
    finally:
        reservation.release()
    assert storage.root not in LocalStorage._active_by_root
    assert storage.root not in LocalStorage._active_reads_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_read_admission_rejection_is_typed_and_releases_on_cleanup(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = report_case
    storage = LocalStorage(case.settings.processing_workspace_root)
    held = [
        storage.reserve_capacity(
            requested_bytes=1,
            warning_free_bytes=2,
            hard_stop_free_bytes=1,
            max_active_uploads=1,
            admission="read",
            max_active_reads=4,
        )[0]
        for _ in range(4)
    ]
    try:
        response = case.client.get("/api/v1/analyses")
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "processing_workspace_unavailable"
        assert response.headers["retry-after"] == "5"
    finally:
        for reservation in held:
            reservation.release()

    repository = AnalysisJobRepository.from_settings(
        settings=case.settings,
        owner_user_id=case.repo.owner_user_id,
        persistence=case.repo.persistence,
        object_storage=case.storage,
    )
    reservation, _ = storage.reserve_capacity(
        requested_bytes=100,
        warning_free_bytes=2,
        hard_stop_free_bytes=1,
        max_active_uploads=1,
    )
    repository._workspace_reservation = reservation
    original_cleanup = shutil.rmtree

    def cleanup(path: Path) -> None:
        assert LocalStorage._active_by_root[storage.root] == 1
        original_cleanup(path)

    monkeypatch.setattr("app.services.jobs.repository.shutil.rmtree", cleanup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: repository.close(), range(2)))
    repository.close()
    assert storage.root not in LocalStorage._active_by_root
    assert storage.root not in LocalStorage._reserved_by_root

    failed_repository = AnalysisJobRepository.from_settings(
        settings=case.settings,
        owner_user_id=case.repo.owner_user_id,
        persistence=case.repo.persistence,
        object_storage=case.storage,
    )
    failed_reservation, _ = storage.reserve_capacity(
        requested_bytes=100,
        warning_free_bytes=2,
        hard_stop_free_bytes=1,
        max_active_uploads=1,
    )
    failed_repository._workspace_reservation = failed_reservation

    def failed_cleanup(path: Path) -> None:
        assert path == failed_repository.output_dir
        assert LocalStorage._active_by_root[storage.root] == 1
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr("app.services.jobs.repository.shutil.rmtree", failed_cleanup)
    failed_repository.close()
    assert failed_repository.output_dir.exists()
    assert storage.root not in LocalStorage._active_by_root
    assert storage.root not in LocalStorage._reserved_by_root
    monkeypatch.setattr("app.services.jobs.repository.shutil.rmtree", original_cleanup)
    failed_repository.close()
    assert not failed_repository.output_dir.exists()
    assert storage.root not in LocalStorage._active_by_root
    assert storage.root not in LocalStorage._reserved_by_root


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_read_artifact_limit_preserves_processing_admission_for_large_artifacts(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = report_case
    record = case.records()["analytics/analytics.json"]
    assert AnalysisJobRepository.MAX_READ_ARTIFACT_BYTES == 16 * 1024 * 1024
    storage = LocalStorage(case.settings.processing_workspace_root)
    processing, _ = storage.reserve_capacity(
        requested_bytes=1,
        warning_free_bytes=2,
        hard_stop_free_bytes=1,
        max_active_uploads=1,
    )
    try:
        accepted_repository = AnalysisJobRepository.from_settings(
            settings=case.settings,
            owner_user_id=case.repo.owner_user_id,
            persistence=case.repo.persistence,
            object_storage=case.storage,
        )
        monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", record.size_bytes)
        assert not accepted_repository._requires_processing_admission(record)
        with accepted_repository.bounded_artifact_read():
            accepted_repository._reserve_workspace(
                [record],
                processing=accepted_repository._requires_processing_admission(record),
            )
        assert LocalStorage._active_reads_by_root[storage.root] == 1
        assert LocalStorage._active_by_root[storage.root] == 1
        accepted_repository.close()

        rejected_repository = AnalysisJobRepository.from_settings(
            settings=case.settings,
            owner_user_id=case.repo.owner_user_id,
            persistence=case.repo.persistence,
            object_storage=case.storage,
        )
        monkeypatch.setattr(AnalysisJobRepository, "MAX_READ_ARTIFACT_BYTES", record.size_bytes - 1)
        assert rejected_repository._requires_processing_admission(record)
        with (
            rejected_repository.bounded_artifact_read(),
            pytest.raises(JobStorageCapacityError) as rejected,
        ):
            rejected_repository._reserve_workspace(
                [record],
                processing=rejected_repository._requires_processing_admission(record),
            )
        assert rejected.value.code == "processing_workspace_unavailable"
        assert rejected.value.status_code == 429
        rejected_repository.close()
    finally:
        processing.release()


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_history_cumulative_read_limit_fails_safely_and_releases(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = report_case
    records = case.records()
    candidates = records["tracking/player_candidates.json"]
    analytics = records["analytics/analytics.json"]
    assert AnalysisJobRepository.MAX_READ_WORKSPACE_BYTES == 128 * 1024 * 1024
    monkeypatch.setattr(
        AnalysisJobRepository,
        "MAX_READ_WORKSPACE_BYTES",
        candidates.size_bytes + analytics.size_bytes - 1,
    )

    response = case.client.get("/api/v1/analyses")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "read_workspace_limit"
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root
    assert all(not path.exists() for path in case.workspaces)


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
@pytest.mark.parametrize("failure", ["backend", "cancelled"])
def test_read_hydration_failure_releases_admission_at_dependency_teardown(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    case = report_case
    assert case.storage is not None

    def fail_download(*, key: str, destination: Path) -> Any:
        if failure == "cancelled":
            raise CancelledError()
        raise ObjectStorageError("simulated download failure")

    monkeypatch.setattr(case.storage, "download_file", fail_download)
    if failure == "cancelled":
        with pytest.raises((CancelledError, FutureCancelledError)):
            case.client.get("/api/v1/analyses")
    else:
        response = case.client.get("/api/v1/analyses")
        assert response.status_code == 503
    root = LocalStorage(case.settings.processing_workspace_root).root
    assert root not in LocalStorage._active_reads_by_root
    assert root not in LocalStorage._reserved_by_root
    assert all(not path.exists() for path in case.workspaces)


def test_report_hydration_is_bounded_and_independent_of_visuals(
    report_case: ReportCase,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    case = report_case
    job = case.repo.load_job_metadata(AID)
    # A thousand registered but unavailable preview objects must not be read.
    case.repo.persistence.service.persist_job(
        owner_user_id=case.repo.owner_user_id,
        payload=job.model_dump(mode="json"),
        artifacts=[
            ArtifactInput(
                storage_key=f"tracking/previews/unused-{i}.jpg",
                content_type="image/jpeg",
                size_bytes=1_000_000,
                checksum_sha256="0" * 64,
                artifact_kind="tracking",
            )
            for i in range(1000)
        ],
        expected_row_version=job.persistence_version,
    )
    for key in list(case.records()):
        if key not in REQUIRED and not key.startswith("tracking/previews/unused-"):
            case.remove_bytes(key)
    monkeypatch.setattr(report_observability.logger, "disabled", False)
    caplog.set_level("INFO", logger=report_observability.__name__)
    records = case.records()
    expected_bytes = sum(records[key].size_bytes for key in REQUIRED)
    calibration_key = f"calibrations/{job.active_calibration_id}/calibration.json"
    service = case.repo.persistence.service
    original_get_artifact = service.get_artifact
    original_get_artifacts = service.get_artifacts
    exact_keys: list[str] = []
    batches: list[tuple[set[str], set[str]]] = []

    def forbid_registry_enumeration(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("report resolution must not enumerate the artifact registry")

    def get_artifact(**kwargs: Any) -> AnalysisArtifact:
        exact_keys.append(kwargs["logical_key"])
        return original_get_artifact(**kwargs)

    def get_artifacts(**kwargs: Any) -> list[AnalysisArtifact]:
        requested = set(kwargs["logical_keys"])
        resolved = original_get_artifacts(**kwargs)
        batches.append((requested, {record.logical_key for record in resolved}))
        return resolved

    monkeypatch.setattr(service, "list_artifacts", forbid_registry_enumeration)
    monkeypatch.setattr(service, "get_artifact", get_artifact)
    monkeypatch.setattr(service, "get_artifacts", get_artifacts)
    for _ in range(2):
        case.downloads.clear()
        caplog.clear()
        exact_keys.clear()
        batches.clear()
        response = case.client.get(URL)
        assert response.status_code == 200, response.text
        assert response.json() == case.expected
        assert exact_keys == [calibration_key]
        assert batches == [(REQUIRED, REQUIRED)]
        if case.storage is not None:
            assert set(case.downloads) == {records[key].storage_key for key in REQUIRED}
            assert len(case.downloads) == 3
        events = [r for r in caplog.records if r.getMessage() == "report_read_completed"]
        assert len(events) == 1
        fields = events[0].__dict__
        assert fields["selected_artifact_count"] == 3
        assert fields["selected_bytes"] == expected_bytes
        assert fields["hydrated_artifact_count"] == (3 if case.storage else 0)
        assert fields["hydrated_bytes"] == (expected_bytes if case.storage else 0)
        assert fields["outcome"] == "success"
        assert {"registry", "persistence", "evidence", "analytics_json", "match_iq_json"} <= fields[
            "phase_duration_ms"
        ].keys()
    assert all(not p.exists() for p in case.workspaces)


def test_unavailable_match_iq_reduces_resolved_and_hydrated_dependencies(
    report_case: ReportCase,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    case = report_case
    records = case.records()
    match_iq = records["analytics/match_iq.json"]
    with case.repo.persistence.session_factory.begin() as session:
        current = session.get(AnalysisArtifact, match_iq.id)
        assert current is not None
        current.is_current = False
    service = case.repo.persistence.service
    original_get_artifacts = service.get_artifacts
    resolved_batches: list[set[str]] = []

    def forbid_registry_enumeration(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("report resolution must not enumerate the artifact registry")

    def get_artifacts(**kwargs: Any) -> list[AnalysisArtifact]:
        resolved = original_get_artifacts(**kwargs)
        resolved_batches.append({record.logical_key for record in resolved})
        return resolved

    monkeypatch.setattr(service, "list_artifacts", forbid_registry_enumeration)
    monkeypatch.setattr(service, "get_artifacts", get_artifacts)
    monkeypatch.setattr(report_observability.logger, "disabled", False)
    caplog.set_level("INFO", logger=report_observability.__name__)
    response = case.client.get(URL)
    assert response.status_code == 200, response.text
    assert response.json()["match_iq"] is None
    expected = REQUIRED - {"analytics/match_iq.json"}
    assert resolved_batches == [expected]
    if case.storage is not None:
        assert set(case.downloads) == {records[key].storage_key for key in expected}
        assert len(case.downloads) == 2
    event = next(r for r in caplog.records if r.getMessage() == "report_read_completed")
    assert event.__dict__["selected_artifact_count"] == 2
    assert event.__dict__["hydrated_artifact_count"] == (2 if case.storage else 0)


@pytest.mark.parametrize("key", ["analytics/analytics.json", "analytics/match_iq.json"])
def test_retired_artifacts_cannot_regain_authority_from_present_bytes(
    report_case: ReportCase,
    key: str,
) -> None:
    case = report_case
    record = case.records()[key]
    assert (case.repo.analysis_dir(AID) / key).is_file()
    with case.repo.persistence.session_factory.begin() as session:
        current = session.get(AnalysisArtifact, record.id)
        assert current is not None
        current.is_current = False
    response = case.client.get(URL)
    if key.endswith("match_iq.json"):
        assert response.status_code == 200, response.text
        assert response.json()["match_iq"] is None
    else:
        assert response.status_code == 409, response.text
    assert record.storage_key not in case.downloads


@pytest.mark.parametrize(
    "key",
    ["analytics/analytics.json", "analytics/match_iq.json", "tracking/player_candidates.json"],
)
def test_missing_report_dependencies_keep_existing_contract(
    report_case: ReportCase, key: str
) -> None:
    report_case.remove_bytes(key)
    response = report_case.client.get(URL)
    if key.endswith("match_iq.json"):
        assert response.status_code == 200
        assert response.json()["match_iq"] is None
    else:
        assert response.status_code == 409


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_candidates_cannot_authorize_report(report_case: ReportCase, version: int) -> None:
    case = report_case
    path = case.repo.analysis_dir(AID) / "tracking/player_candidates.json"
    payload = json.loads(path.read_text())
    payload["schema_version"] = version
    path.write_text(json.dumps(payload), encoding="utf-8")
    case.repo.save_job(case.repo.load_job_metadata(AID))
    case.downloads.clear()
    assert case.client.get(URL).status_code == 409
    assert not set(case.downloads) & {
        case.records()[key].storage_key for key in REQUIRED if key.startswith("analytics/")
    }


@pytest.mark.parametrize(
    "fault", ["unverified", "calibration_changed", "lineage_changed", "deletion_pending"]
)
def test_report_authority_failures_precede_hydration(report_case: ReportCase, fault: str) -> None:
    case = report_case
    if fault == "lineage_changed":
        job = case.repo.load_job_metadata(AID)
        # The production transaction retires analytics even if stale bytes remain.
        case.repo.update_job(job, selected_evidence_signature="changed", analytics_completed=False)
    else:
        with case.repo.persistence.session_factory.begin() as session:
            analysis = session.get(Analysis, AID)
            assert analysis is not None
            if fault == "deletion_pending":
                analysis.lifecycle_state = "deletion_pending"
            elif fault == "unverified":
                analysis.job_payload = {**analysis.job_payload, "calibration_verification": None}
            else:
                calibration = session.scalar(
                    select(AnalysisArtifact).where(
                        AnalysisArtifact.analysis_id == AID,
                        AnalysisArtifact.logical_key.endswith("/calibration.json"),
                        AnalysisArtifact.is_current.is_(True),
                    )
                )
                assert calibration is not None
                calibration.checksum_sha256 = "0" * 64
    case.downloads.clear()
    assert case.client.get(URL).status_code == (404 if fault == "deletion_pending" else 409)
    assert not case.downloads


def test_report_auth_and_owner_isolation(report_case: ReportCase) -> None:
    case = report_case
    case.client.headers.pop("Authorization")
    assert case.client.get(URL).status_code == 401
    token = _register_verified_user(case.client, "report-other@example.com")
    case.client.headers["Authorization"] = f"Bearer {token}"
    assert case.client.get(URL).status_code == 404
    assert not case.downloads


def test_report_survives_supported_media_deletion(report_case: ReportCase) -> None:
    case = report_case
    deleted = case.client.delete(lineage.BASE + "/source-video")
    assert deleted.status_code == 204, deleted.text
    case.downloads.clear()
    response = case.client.get(URL)
    assert response.status_code == 200, response.text
    assert response.json() == case.expected
    assert all(not p.exists() for p in case.workspaces)


def test_report_lock_excludes_evidence_mutations(
    report_case: ReportCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = report_case
    entered, release = Event(), Event()
    original = AnalysisWorkflowService._load_analytics

    def paused(self: AnalysisWorkflowService, path: Path) -> Any:
        entered.set()
        assert release.wait(15)
        return original(self, path)

    monkeypatch.setattr(AnalysisWorkflowService, "_load_analytics", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(case.client.get, URL)
        try:
            assert entered.wait(15)
            mutation = case.client.post(lineage.BASE + "/player-candidates/generate")
            assert mutation.status_code == 409
            assert mutation.json()["error"]["code"] == "source_media_busy"
        finally:
            release.set()
        assert future.result(timeout=15).status_code == 200


@pytest.mark.parametrize("key", sorted(REQUIRED))
@pytest.mark.parametrize("corruption", ["size", "checksum"])
@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_s3_integrity_failure_never_returns_corrupt_report(
    report_case: ReportCase,
    key: str,
    corruption: str,
) -> None:
    case = report_case
    assert case.storage is not None
    stored = case.storage.objects[case.records()[key].storage_key]
    if corruption == "size":
        stored["data"] += b" "
    else:
        stored["metadata"]["court4-sha256"] = "0" * 64
    response = case.client.get(URL)
    if key.endswith("match_iq.json"):
        assert response.status_code == 200
        assert response.json()["match_iq"] is None
    else:
        assert response.status_code == 409
    assert all(not p.exists() for p in case.workspaces)


@pytest.mark.parametrize("key", ["analytics/analytics.json", "analytics/match_iq.json"])
@pytest.mark.parametrize("corruption", ["size", "checksum"])
@pytest.mark.parametrize("report_case", ["local"], indirect=True)
def test_local_existing_report_bytes_must_match_registration(
    report_case: ReportCase,
    key: str,
    corruption: str,
) -> None:
    case = report_case
    record = case.records()[key]
    path = case.repo.analysis_dir(AID) / key
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["analysis_id"] = "candidate-tesu"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if corruption == "checksum":
        with case.repo.persistence.session_factory.begin() as session:
            current = session.get(AnalysisArtifact, record.id)
            assert current is not None
            current.size_bytes = path.stat().st_size
    response = case.client.get(URL)
    if key.endswith("match_iq.json"):
        assert response.status_code == 200
        assert response.json()["match_iq"] is None
    else:
        assert response.status_code == 409
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("report_case", ["s3"], indirect=True)
def test_corrupt_disposable_s3_workspace_hit_is_rehydrated(
    report_case: ReportCase,
) -> None:
    case = report_case
    assert case.storage is not None
    records = case.records()
    key = "analytics/analytics.json"
    original = case.storage.objects[records[key].storage_key]["data"]
    case.workspace_seed[key] = bytes([original[0] ^ 1]) + original[1:]
    assert len(case.workspace_seed[key]) == records[key].size_bytes
    response = case.client.get(URL)
    assert response.status_code == 200, response.text
    assert response.json() == case.expected
    assert records[key].storage_key in case.downloads
    assert all(not p.exists() for p in case.workspaces)


@pytest.mark.parametrize("report_case", ["local"], indirect=True)
def test_telemetry_failure_does_not_change_report_http_outcomes(
    report_case: ReportCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = report_case

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(report_observability.logger, "info", fail)
    success = case.client.get(URL)
    assert success.status_code == 200, success.text
    assert success.json() == case.expected
    analytics = case.records()["analytics/analytics.json"]
    with case.repo.persistence.session_factory.begin() as session:
        current = session.get(AnalysisArtifact, analytics.id)
        assert current is not None
        current.is_current = False
    failure = case.client.get(URL)
    assert failure.status_code == 409, failure.text
    assert failure.json()["error"]["code"] == "analytics_not_ready"
