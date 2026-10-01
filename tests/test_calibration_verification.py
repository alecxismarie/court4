from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1.analyses import get_workflow_service
from app.auth import VerifiedUser
from app.persistence.errors import OptimisticConcurrencyError, OwnershipMismatchError
from app.persistence.models import AnalysisArtifact as PersistedAnalysisArtifact
from app.persistence.runtime import get_persistence
from app.schemas.jobs import AnalysisJob
from app.services.jobs import AnalysisJobRepository, AnalysisWorkflowService
from app.services.jobs.exceptions import JobConflictError
from tests.test_api_workflow import (
    _api_client,
    _calibration_payload,
    _upload_video,
    _write_controlled_api_detections,
)
from tests.test_direct_uploads import _client, _direct_round_trip


def _confirm(client: TestClient, aid: str) -> None:
    job = client.get(f"/api/v1/analyses/{aid}").json()
    response = client.post(
        f"/api/v1/analyses/{aid}/calibration/confirm",
        json={
            "calibration_id": job["active_calibration_id"],
            "calibration_checksum_sha256": job["calibration_checksum_sha256"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["calibration_verified"] is True


def test_generated_court_confirmation_reload_and_correction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_court_video_factory: Callable[..., Path],
) -> None:
    client, output = _api_client(tmp_path, monkeypatch)
    video = synthetic_court_video_factory(
        tmp_path / "match.avi", frame_count=15, fps=10, width=800, height=900
    )
    aid = _upload_video(client, video).json()["analysis_id"]
    base = f"/api/v1/analyses/{aid}"
    generated = client.post(base + "/court-detection")
    assert generated.status_code == 200
    assert generated.json()["job"]["calibration_completed"] is True
    assert generated.json()["job"]["calibration_verified"] is False
    _write_controlled_api_detections(output, aid, calibration_id="auto-court-detection")
    tracking_request = {
        "calibration_id": "auto-court-detection",
        "backend": "controlled-json",
        "detections_jsonl": "uploads/detections.jsonl",
        "frame_interval": 1,
    }
    for response in [
        client.post(base + "/tracking", json=tracking_request),
        client.post(base + "/analytics"),
        client.get(base + "/analytics"),
        client.get(base + "/player-candidates"),
    ]:
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "calibration_verification_required"
    stale = client.post(
        base + "/calibration/confirm",
        json={
            "calibration_id": "auto-court-detection",
            "calibration_checksum_sha256": "0" * 64,
        },
    )
    assert stale.status_code == 409
    _confirm(client, aid)
    assert client.get(base).json()["calibration_verified"] is True
    tracked = client.post(base + "/tracking", json=tracking_request)
    assert tracked.status_code == 200, tracked.text
    selected = client.post(base + "/players/select", json={"track_id": 1})
    assert selected.status_code == 200, selected.text
    analytics = client.post(base + "/analytics")
    assert analytics.status_code == 200, analytics.text
    assert client.get(base + "/analytics").status_code == 200
    # A changed artifact checksum revokes trust and hides legacy measurements.
    owner = UUID(client.get("/api/v1/auth/me").json()["id"])
    repository = AnalysisJobRepository(
        output_dir=output, api_base_path="/api/v1", owner_user_id=owner
    )
    calibration_path = output / aid / "calibrations" / "auto-court-detection" / "calibration.json"
    calibration_path.write_bytes(calibration_path.read_bytes() + b"\n")
    repository.register_current_artifacts(aid)
    assert client.get(base).json()["calibration_verified"] is False
    assert client.get(base + "/analytics").status_code == 409
    for artifact in ("analytics/analytics.json", "analytics%5Canalytics.json"):
        response = client.get(base + "/artifacts/" + artifact)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "calibration_verification_required"
    history = client.get("/api/v1/analyses").json()["items"][0]
    assert history["measurement_available"] is False
    assert history["match_iq_available"] is False
    assert client.get("/api/v1/play-history").json()["eligible_count"] == 0
    # A confirmation retry must not remove the persisted player selection.
    _confirm(client, aid)
    assert client.get(base).json()["player_selected"] is True

    # Request 1 holds A and its measurements while request 2 replaces it with B.
    stale_job = repository.load_job(aid)
    stale_artifacts = repository._filesystem_artifacts(aid)

    corrected = client.post(
        base + "/calibration", json=_calibration_payload(calibration_id="corrected")
    )
    assert corrected.status_code == 200, corrected.text
    job = client.get(base).json()
    assert job["active_calibration_id"] == "corrected"
    assert job["calibration_verified"] is False
    assert not job["tracking_completed"] and not job["analytics_completed"]
    assert not any(
        a["path"].startswith(("tracking/", "analytics/")) for a in job["available_artifacts"]
    )
    assert client.get(base + "/analytics").status_code == 409
    with repository.persistence.session_factory() as session:
        artifact_rows_before = list(
            session.scalars(
                select(PersistedAnalysisArtifact).where(
                    PersistedAnalysisArtifact.analysis_id == aid
                )
            )
        )
    with pytest.raises(JobConflictError) as conflict:
        repository.save_job(stale_job)
    assert conflict.value.code == "analysis_changed"
    with pytest.raises(JobConflictError):
        repository.save_job(stale_job.model_copy(update={"persistence_version": None}))
    # Also exercise the transactional check, independently of the early repository check.
    with pytest.raises(OptimisticConcurrencyError):
        repository.persistence.service.persist_job(
            owner_user_id=owner,
            payload=stale_job.model_dump(mode="json"),
            artifacts=stale_artifacts,
            expected_row_version=stale_job.persistence_version,
        )
    with pytest.raises(OwnershipMismatchError):
        repository.persistence.service.persist_job(
            owner_user_id=uuid4(),
            payload=stale_job.model_dump(mode="json"),
            artifacts=stale_artifacts,
            expected_row_version=stale_job.persistence_version,
        )
    with repository.persistence.session_factory() as session:
        artifact_rows_after = list(
            session.scalars(
                select(PersistedAnalysisArtifact).where(
                    PersistedAnalysisArtifact.analysis_id == aid
                )
            )
        )
    assert [(a.id, a.is_current) for a in artifact_rows_after] == [
        (a.id, a.is_current) for a in artifact_rows_before
    ]
    after_stale_save = client.get(base).json()
    assert after_stale_save["active_calibration_id"] == "corrected"
    assert after_stale_save["calibration_verified"] is False
    assert "persistence_version" not in after_stale_save
    assert not after_stale_save["analytics_completed"]
    assert not any(
        a["path"].startswith(("tracking/", "analytics/"))
        for a in after_stale_save["available_artifacts"]
    )
    assert (
        client.post(
            base + "/calibration", json=_calibration_payload(calibration_id="corrected")
        ).status_code
        == 409
    )
    _confirm(client, aid)
    assert client.post(base + "/tracking", json=tracking_request).status_code == 409
    _write_controlled_api_detections(output, aid, calibration_id="corrected")
    tracking_request["calibration_id"] = "corrected"
    assert client.post(base + "/tracking", json=tracking_request).status_code == 200


def test_manual_calibration_uses_s3_workspace_and_reload(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
) -> None:
    client, service, storage, owner = _client(tmp_path)
    legacy = tmp_path / "old-output"
    service.settings.analysis_output_dir = legacy
    video = synthetic_video_factory(tmp_path / "manual.avi", width=800, height=900)
    aid = _direct_round_trip(client, storage, video.read_bytes(), "manual-calibration")[
        "analysis_id"
    ]
    workspaces: list[Path] = []

    def workflow(user: VerifiedUser) -> Iterator[AnalysisWorkflowService]:
        repo = AnalysisJobRepository.from_settings(
            settings=service.settings,
            owner_user_id=user.id,
            persistence=get_persistence(),
            object_storage=storage,
        )
        workspaces.append(repo.output_dir)
        instance = AnalysisWorkflowService(settings=service.settings, repository=repo)
        try:
            yield instance
        finally:
            instance.close()

    cast(FastAPI, client.app).dependency_overrides[get_workflow_service] = workflow
    base = f"/api/v1/analyses/{aid}"
    response = client.post(
        base + "/calibration", json=_calibration_payload(calibration_id="manual")
    )
    assert response.status_code == 200, response.text
    assert response.json()["job"]["calibration_verified"] is False
    records = get_persistence().service.list_artifacts(owner_user_id=owner, analysis_id=aid)
    calibration_records = [r for r in records if r.logical_key.startswith("calibrations/manual/")]
    assert len(calibration_records) == 3
    assert all(r.storage_provider == "s3" for r in calibration_records)
    assert client.get(base + "/artifacts/calibrations/manual/verification.jpg").status_code == 200
    _confirm(client, aid)
    assert client.get(base).json()["calibration_verified"] is True
    assert not legacy.exists()
    assert all(not path.exists() for path in workspaces)


@pytest.mark.parametrize("operation", ["confirmation", "analytics"])
def test_calibration_mutations_exclude_concurrent_correction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_court_video_factory: Callable[..., Path],
    operation: str,
) -> None:
    client, output = _api_client(tmp_path, monkeypatch)
    video = synthetic_court_video_factory(
        tmp_path / "race.avi", frame_count=15, fps=10, width=800, height=900
    )
    aid = _upload_video(client, video).json()["analysis_id"]
    base = f"/api/v1/analyses/{aid}"
    generated = client.post(base + "/court-detection")
    assert generated.status_code == 200
    job = generated.json()["job"]
    confirmation = {
        "calibration_id": job["active_calibration_id"],
        "calibration_checksum_sha256": job["calibration_checksum_sha256"],
    }
    if operation == "analytics":
        _confirm(client, aid)
        _write_controlled_api_detections(output, aid, calibration_id="auto-court-detection")
        assert (
            client.post(
                base + "/tracking",
                json={
                    "calibration_id": "auto-court-detection",
                    "backend": "controlled-json",
                    "detections_jsonl": "uploads/detections.jsonl",
                    "frame_interval": 1,
                },
            ).status_code
            == 200
        )
        assert client.post(base + "/players/select", json={"track_id": 1}).status_code == 200

    entered, release = Event(), Event()
    original_update = AnalysisJobRepository.update_job

    def paused_save(self: AnalysisJobRepository, job: AnalysisJob, **updates: Any) -> AnalysisJob:
        if (
            "calibration_verification" in updates
            and updates["calibration_verification"] is not None
            or updates.get("analytics_completed") is True
        ):
            entered.set()
            assert release.wait(15), "Concurrent correction did not finish"
        return original_update(self, job, **updates)

    monkeypatch.setattr(AnalysisJobRepository, "update_job", paused_save)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            client.post,
            base + ("/calibration/confirm" if operation == "confirmation" else "/analytics"),
            **({"json": confirmation} if operation == "confirmation" else {}),
        )
        try:
            assert entered.wait(15), "Request did not reach its save"
            busy = client.post(base + "/calibration", json=_calibration_payload(calibration_id="B"))
            assert busy.status_code == 409
            assert busy.json()["error"]["code"] == "source_media_busy"
        finally:
            release.set()
        assert future.result(timeout=15).status_code == 200

    correction = client.post(base + "/calibration", json=_calibration_payload(calibration_id="B"))
    assert correction.status_code == 200, correction.text
    stale_confirmation = client.post(base + "/calibration/confirm", json=confirmation)
    assert stale_confirmation.status_code == 409
    assert stale_confirmation.json()["error"]["code"] == "calibration_changed"
    final = client.get(base).json()
    assert final["active_calibration_id"] == "B"
    assert not final["calibration_verified"] and not final["analytics_completed"]
    assert not any(
        a["path"].startswith(("analytics/", "tracking/")) for a in final["available_artifacts"]
    )
