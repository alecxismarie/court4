"""Persistence/evidence regressions for the Phase 1.3B precommit blockers."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AnalysisArtifact, PlayerSelection
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.schemas.player_tracking import PlayerObservation, TrackSummary
from app.services.candidates.service import (
    CandidateError,
    load_player_candidates,
    merge_player_candidates,
    restore_player_candidate,
    select_player_candidate,
    unmerge_player_candidates,
)
from app.services.jobs.exceptions import JobConflictError, JobNotFoundError
from app.services.jobs.repository import AnalysisJobRepository
from app.services.video.player_selection import load_tracking_report
from app.sports.pickleball.calibration import calibrate_court
from tests.test_api_workflow import _api_client
from tests.test_calibration_verification import _confirm
from tests.test_player_candidates import _build, _candidate_case, _CandidateCase, _track
from tests.test_player_tracking import VALID_IMAGE_POINTS

BASE = "/api/v1/analyses/candidate-test"
LineageCase = tuple[TestClient, AnalysisJobRepository, _CandidateCase]


@pytest.fixture
def lineage_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_court_image_factory: Callable[..., Path],
) -> LineageCase:
    client, output = _api_client(tmp_path, monkeypatch)
    case = _candidate_case(
        output,
        [
            *_track(1, start_frame=0, positions=[(2 + i * 0.2, 10.0) for i in range(61)]),
            *_track(2, start_frame=0, positions=[(2 + i * 0.2, 34.0) for i in range(61)]),
            *_track(3, start_frame=0, positions=[(15.0, 10.0) for i in range(61)]),
        ],
    )
    summaries = [
        TrackSummary(
            track_id=i,
            first_frame=0,
            last_frame=60,
            observation_count=61,
            first_timestamp_seconds=0,
            last_timestamp_seconds=6.0,
            duration_seconds=6.0,
            average_confidence=0.9,
            court_observation_count=61,
            extended_court_observation_count=61,
            inside_extended_court_ratio=1,
            eligible_for_selection=True,
            rejection_reasons=[],
        )
        for i in (1, 2, 3, 99)
    ]
    tracking = case["report"].model_copy(update={"track_summaries": summaries})
    case["tracking"].write_text(tracking.model_dump_json(), encoding="utf-8")
    _build(case)
    calibrate_court(
        image_path=synthetic_court_image_factory(tmp_path / "court.jpg"),
        output_dir=output,
        image_points=VALID_IMAGE_POINTS,
        calibration_id="calibration",
        analysis_id="candidate-test",
        numeric_tolerance=0.000001,
        min_polygon_area_pixels=1000,
        transition_area_depth_feet=8,
        top_down_width_pixels=500,
    )
    repo = AnalysisJobRepository(
        output_dir=output,
        api_base_path="/api/v1",
        owner_user_id=UUID(client.get("/api/v1/auth/me").json()["id"]),
    )
    now = datetime.now(tz=UTC)
    repo.save_job(
        AnalysisJob(
            analysis_id="candidate-test",
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.tracked,
            source_video="source.avi",
            created_at=now,
            updated_at=now,
            inspection_completed=True,
            calibration_completed=True,
            tracking_completed=True,
        )
    )
    _confirm(client, "candidate-test")
    return client, repo, case


def _select_and_analyze(client: TestClient, case: _CandidateCase, track_id: int = 1) -> str:
    candidate = next(
        c
        for c in load_player_candidates(case["candidate"]).candidates
        if c.source_raw_track_ids == [track_id]
    )
    response = client.post(BASE + f"/player-candidates/{candidate.candidate_id}/select")
    assert response.status_code == 200, response.text
    response = client.post(BASE + "/analytics")
    assert response.status_code == 200, response.text
    assert response.json()["match_iq"] is not None
    return candidate.candidate_id


def _assert_no_current_results(client: TestClient, repo: AnalysisJobRepository) -> None:
    job = repo.load_job_metadata("candidate-test")
    assert not job.analytics_completed
    assert client.get(BASE + "/analytics").status_code == 409
    for key in ("analytics/analytics.json", "analytics/match_iq.json"):
        with pytest.raises(JobNotFoundError):
            repo.resolve_artifact("candidate-test", key)
    history = client.get("/api/v1/analyses").json()["items"][0]
    assert not history["measurement_available"]
    assert not history["match_iq_available"]
    play = client.get("/api/v1/play-history").json()
    assert play["eligible_count"] == 0
    assert play["recent_eligible_analyses"] == []
    assert play["progress"]["qualified_analysis_count"] == 0
    assert play["progress"]["qualified_observation_seconds"] == 0
    assert play["progress"]["contributing_analysis_ids"] == []
    assert repo.resolve_artifact("candidate-test", "source.avi").is_file()


def test_regeneration_retires_results_and_allows_fresh_selection(lineage_case: LineageCase) -> None:
    client, repo, case = lineage_case
    selected_id = _select_and_analyze(client, case)
    prior_progress = client.get("/api/v1/play-history").json()
    assert prior_progress["eligible_count"] == 1
    assert prior_progress["progress"]["qualified_observation_seconds"] == pytest.approx(6)
    before = repo.load_job("candidate-test")
    analytics_bytes = repo.resolve_artifact(
        "candidate-test", "analytics/analytics.json"
    ).read_bytes()
    unchanged = client.post(BASE + "/player-candidates/generate")
    assert unchanged.status_code == 200, unchanged.text
    assert repo.load_job_metadata("candidate-test").analytics_completed
    assert (
        repo.resolve_artifact("candidate-test", "analytics/analytics.json").read_bytes()
        == analytics_bytes
    )
    rows = [
        PlayerObservation.model_validate_json(row)
        for row in case["observations"].read_text().splitlines()
    ]
    case["observations"].write_text(
        "\n".join(
            o.model_copy(update={"interpolated": True}).model_dump_json()
            if o.track_id == 1
            else o.model_dump_json()
            for o in rows
        ),
        encoding="utf-8",
    )
    repo.register_current_artifacts("candidate-test")
    rebuilt = client.post(BASE + "/player-candidates/generate")
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["selected_candidate_id"] is None
    assert selected_id not in [c["candidate_id"] for c in rebuilt.json()["candidates"]]
    assert not repo.load_job_metadata("candidate-test").player_selected
    assert load_tracking_report(case["tracking"]).selected_player_track_id is None
    _assert_no_current_results(client, repo)
    with repo.persistence.session_factory() as session:
        assert session.scalar(select(PlayerSelection).where(PlayerSelection.is_current)) is None
        retired = list(
            session.scalars(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.logical_key.startswith("analytics/")
                )
            )
        )
        assert retired and all(not item.is_current for item in retired)
    with pytest.raises(JobConflictError, match="Analysis changed"):
        repo.save_job(before)
    assert client.post(BASE + "/analytics").status_code == 409
    _select_and_analyze(client, case, track_id=2)
    assert repo.load_job_metadata("candidate-test").analytics_completed
    assert client.get(BASE + "/analytics").json()["analytics"]["source_raw_track_ids"] == [2]


@pytest.mark.parametrize("raw_id", [2, 3, 99])
def test_raw_selection_requires_compatible_current_candidate(
    lineage_case: LineageCase,
    raw_id: int,
) -> None:
    client, repo, case = lineage_case
    original = _select_and_analyze(client, case)
    stale = repo.load_job("candidate-test")
    response = client.post(BASE + "/players/select", json={"track_id": raw_id})
    if raw_id == 2:
        assert response.status_code == 200, response.text
        _assert_no_current_results(client, repo)
        tracking = load_tracking_report(case["tracking"])
        collection = load_player_candidates(case["candidate"])
        assert tracking.selected_player_track_id == 2
        assert tracking.selected_player_source_track_ids == [2]
        assert tracking.selected_player_candidate_id == collection.selected_candidate_id != original
        reloaded = AnalysisJobRepository(
            output_dir=repo.output_dir, api_base_path="/api/v1", owner_user_id=repo.owner_user_id
        ).load_job("candidate-test")
        assert reloaded.analysis_readiness == collection.analysis_readiness
        with pytest.raises(JobConflictError):
            repo.save_job(stale)
    else:
        assert response.status_code in (400, 409), response.text
        assert load_tracking_report(case["tracking"]).selected_player_track_id == 1
        assert load_player_candidates(case["candidate"]).selected_candidate_id == original
        assert repo.load_job_metadata("candidate-test").analytics_completed
    analyzed = client.post(BASE + "/analytics")
    assert analyzed.status_code == 200, analyzed.text
    assert analyzed.json()["analytics"]["source_raw_track_ids"] == ([2] if raw_id == 2 else [1])


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_api_requires_explicit_regeneration(lineage_case: LineageCase, version: int) -> None:
    client, repo, case = lineage_case
    selected = _select_and_analyze(client, case)
    payload = json.loads(case["candidate"].read_text())
    payload["schema_version"] = version
    payload["candidates"][0]["total_observed_duration"] = 90
    case["candidate"].write_text(json.dumps(payload), encoding="utf-8")
    repo.register_current_artifacts("candidate-test")
    loaded = client.get(BASE + "/player-candidates")
    assert loaded.status_code == 200
    assert loaded.json()["schema_version"] == version
    assert loaded.json()["candidates"][0]["total_observed_duration"] == 90
    assert loaded.json()["analysis_readiness"] is None
    assert client.post(BASE + f"/player-candidates/{selected}/select").status_code == 409
    assert client.post(BASE + "/analytics").status_code == 409
    assert client.get(BASE + "/analytics").status_code == 409
    history = client.get("/api/v1/analyses").json()["items"][0]
    assert not history["measurement_available"] and not history["match_iq_available"]
    for action in (
        lambda: restore_player_candidate(candidate_path=case["candidate"], candidate_id=selected),
        lambda: merge_player_candidates(
            candidate_path=case["candidate"],
            candidate_ids=[c["candidate_id"] for c in payload["candidates"]],
            tracking_report_path=case["tracking"],
            observations_path=case["observations"],
            source_video_path=case["video"],
            metadata_path=case["metadata"],
        ),
        lambda: unmerge_player_candidates(
            candidate_path=case["candidate"],
            candidate_id=selected,
            tracking_report_path=case["tracking"],
            observations_path=case["observations"],
            source_video_path=case["video"],
            metadata_path=case["metadata"],
        ),
    ):
        with pytest.raises(CandidateError, match="Regenerate"):
            action()
        assert load_player_candidates(case["candidate"]).schema_version == version
    regenerated = client.post(BASE + "/player-candidates/generate")
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["schema_version"] == 4
    assert regenerated.json()["selected_candidate_id"] is None
    assert all(c["total_observed_duration"] < 90 for c in regenerated.json()["candidates"])
    _assert_no_current_results(client, repo)
    _select_and_analyze(client, case)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_large_gap_is_recomputed_not_relabelled(tmp_path: Path, version: int) -> None:
    case = _candidate_case(
        tmp_path,
        [
            *_track(1, start_frame=0, positions=[(2 + i * 0.2, 10.0) for i in range(15)]),
            *_track(1, start_frame=100, positions=[(5 + i * 0.2, 10.0) for i in range(15)]),
        ],
    )
    current = _build(case)
    selected = current.candidates[0].candidate_id
    select_player_candidate(
        candidate_path=case["candidate"],
        candidate_id=selected,
        tracking_report_path=case["tracking"],
    )
    payload = json.loads(case["candidate"].read_text())
    payload["schema_version"] = version
    payload["candidates"][0]["total_observed_duration"] = 11.4
    case["candidate"].write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_player_candidates(case["candidate"])
    assert loaded.schema_version == version
    assert loaded.candidates[0].total_observed_duration == 11.4
    with pytest.raises(CandidateError, match="Regenerate"):
        select_player_candidate(
            candidate_path=case["candidate"],
            candidate_id=selected,
            tracking_report_path=case["tracking"],
        )
    rebuilt = _build(case)
    assert rebuilt.schema_version == 4 and rebuilt.selected_candidate_id is None
    assert rebuilt.candidates[0].total_observed_duration == pytest.approx(2.8)
    assert load_tracking_report(case["tracking"]).selected_player_track_id is None
