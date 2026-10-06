from __future__ import annotations

import errno
import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.analyses import get_workflow_service
from app.auth import VerifiedUser
from app.config import get_settings
from app.persistence.models import AnalysisArtifact
from app.persistence.runtime import get_persistence
from app.services.jobs.repository import AnalysisJobRepository
from app.services.jobs.workflow import AnalysisWorkflowService
from tests.test_direct_uploads import _client, _direct_round_trip, _register_verified_user
from tests.test_movement_analytics import _create_analytics_case


@pytest.mark.parametrize("legacy_inputs", [False, True])
def test_s3_analytics_workspace_registration_cleanup_and_retry(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    synthetic_court_image_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    legacy_inputs: bool,
) -> None:
    client, service, storage, owner = _client(tmp_path)
    legacy_root = tmp_path / "app" / "data" / "output"
    service.settings.analysis_output_dir = legacy_root
    uploaded = _direct_round_trip(
        client,
        storage,
        synthetic_video_factory(tmp_path / "match.avi").read_bytes(),
        "analytics-workspace",
    )
    analysis_id = uploaded["analysis_id"]
    _create_analytics_case(tmp_path, synthetic_court_image_factory)
    seed = tmp_path / "output" / "analytics-case"
    for path in seed.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["analysis_id"] = analysis_id
        path.write_text(json.dumps(payload), encoding="utf-8")

    def repository_for(user_id: UUID) -> AnalysisJobRepository:
        return AnalysisJobRepository.from_settings(
            settings=service.settings,
            owner_user_id=user_id,
            persistence=get_persistence(),
            object_storage=storage,
        )

    repository = repository_for(owner)
    try:
        job = repository.load_job(analysis_id)
        shutil.copytree(seed, repository.analysis_dir(analysis_id), dirs_exist_ok=True)
        repository.update_job(
            job, calibration_completed=True, tracking_completed=True, player_selected=True
        )
    finally:
        repository.close()
    assert not repository.output_dir.exists()

    if legacy_inputs:
        shutil.copytree(seed, legacy_root / analysis_id)
        # A stale legacy selection must never override the current persisted selection.
        tracking_path = legacy_root / analysis_id / "tracking" / "tracking.json"
        payload = json.loads(tracking_path.read_text(encoding="utf-8"))
        payload["selected_player_track_id"] = None
        tracking_path.write_text(json.dumps(payload), encoding="utf-8")
    legacy_before = {
        p.relative_to(legacy_root): p.read_bytes() for p in legacy_root.rglob("*") if p.is_file()
    }
    workspaces: list[Path] = []

    def workflow_for_user(user: VerifiedUser) -> Iterator[AnalysisWorkflowService]:
        repository = repository_for(user.id)
        workspaces.append(repository.output_dir)
        assert repository.storage.root == service.settings.processing_workspace_root.resolve()
        assert repository.output_dir.parent == repository.storage.root
        workflow = AnalysisWorkflowService(settings=service.settings, repository=repository)
        try:
            yield workflow
        finally:
            workflow.close()

    cast(FastAPI, client.app).dependency_overrides[get_workflow_service] = workflow_for_user
    proposed = client.get(f"/api/v1/analyses/{analysis_id}").json()
    confirmed = client.post(
        f"/api/v1/analyses/{analysis_id}/calibration/confirm",
        json={
            "calibration_id": proposed["active_calibration_id"],
            "calibration_checksum_sha256": proposed["calibration_checksum_sha256"],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    candidates = client.post(f"/api/v1/analyses/{analysis_id}/player-candidates/generate")
    assert candidates.status_code == 200, candidates.text
    assert candidates.json()["selected_candidate_id"] is not None
    original_write = Path.write_text

    def disk_full(path: Path, *args: Any, **kwargs: Any) -> int:
        if path.name == "match_iq.json":
            assert path.is_relative_to(workspaces[-1])
            assert (path.parent / "analytics.json").is_file()
            raise OSError(errno.ENOSPC, "private disk path")
        return original_write(path, *args, **kwargs)

    origin = get_settings().frontend_allowed_origins[0]
    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", disk_full)
        failed = client.post(
            f"/api/v1/analyses/{analysis_id}/analytics", headers={"Origin": origin}
        )
    assert failed.status_code == 507, failed.text
    assert failed.json()["error"]["code"] == "storage_capacity_unavailable"
    assert failed.headers["access-control-allow-origin"] == origin
    assert "private disk path" not in failed.text
    assert not workspaces[-1].exists()
    state = client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert state["tracking_completed"] and state["player_selected"]
    assert not state["analytics_completed"]
    with get_persistence().session_factory() as session:
        assert not list(
            session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.analysis_id == analysis_id,
                    AnalysisArtifact.logical_key.startswith("analytics/"),
                )
            )
        )

    response = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job"]["analytics_completed"]
    assert body["analytics"]["selected_player_track_id"] == 1
    assert body["analytics"]["calibration_id"] == "analytics-calibration"
    assert body["analytics"]["timeline_observation_count"] == 4
    expected = {
        f"analytics/{name}"
        for name in (
            "analytics.json",
            "movement_summary.json",
            "timeline.json",
            "trajectory.png",
            "heatmap.png",
            "match_iq.json",
        )
    }
    assert {a["path"] for a in body["artifacts"]} == expected
    with get_persistence().session_factory() as session:
        records = list(
            session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.analysis_id == analysis_id,
                    AnalysisArtifact.is_current.is_(True),
                    AnalysisArtifact.logical_key.startswith("analytics/"),
                )
            )
        )
    assert {r.logical_key for r in records} == expected
    assert all(r.owner_user_id == owner and r.storage_provider == "s3" for r in records)
    assert all(r.storage_key in storage.objects for r in records)

    def forbid_generation(**kwargs: Any) -> None:
        pytest.fail("Registered analytics must load without regeneration.")

    monkeypatch.setattr("app.services.jobs.workflow.generate_match_analytics", forbid_generation)
    for method in (client.get, client.post):
        reloaded = method(f"/api/v1/analyses/{analysis_id}/analytics")
        assert reloaded.status_code == 200, reloaded.text
        assert reloaded.json()["analytics"] == body["analytics"]
        assert reloaded.json()["match_iq"] == body["match_iq"]
    assert all(not workspace.exists() for workspace in workspaces)
    assert {
        p.relative_to(legacy_root): p.read_bytes() for p in legacy_root.rglob("*") if p.is_file()
    } == legacy_before
    assert legacy_root.exists() == legacy_inputs
    client.headers["Authorization"] = (
        f"Bearer {_register_verified_user(client, 'other@example.com')}"
    )
    assert client.post(f"/api/v1/analyses/{analysis_id}/analytics").status_code == 404
