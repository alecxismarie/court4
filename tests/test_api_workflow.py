import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.config import get_settings
from app.main import create_app
from app.persistence.models import User
from app.persistence.runtime import get_persistence
from app.schemas.jobs import AnalysisJob
from app.services.jobs import AnalysisJobRepository
from app.services.tracking.json_tracking_backend import build_controlled_detection_line
from app.services.video.player_analysis import load_calibration_report
from app.sports.pickleball.calibration import court_point_to_image

API_TEST_OWNERS: dict[Path, UUID] = {}


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_video_upload_job_retrieval_frames_and_safe_filename(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "unsafe upload.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )

    upload = _upload_video(client, video_path, filename="../../unsafe upload.avi")

    assert upload.status_code == 201
    job = upload.json()
    analysis_id = job["analysis_id"]
    assert job["status"] == "processing"
    assert job["current_stage"] == "inspected"
    assert job["source_video"] == "uploads/source.avi"
    assert (output_dir / analysis_id / "uploads" / "source.avi").is_file()

    retrieved = client.get(f"/api/v1/analyses/{analysis_id}")
    frames = client.get(f"/api/v1/analyses/{analysis_id}/frames")

    assert retrieved.status_code == 200
    assert retrieved.json()["inspection_completed"] is True
    assert retrieved.json()["court_detection_status"] is None
    assert retrieved.json()["court_detection_confidence"] is None
    assert retrieved.json()["court_detection_selected_frame"] is None
    assert retrieved.json()["court_detection_detected_corners"] is None
    assert frames.status_code == 200
    assert len(frames.json()["frames"]) == 3
    assert frames.json()["frames"][0]["url"].startswith(
        f"/api/v1/analyses/{analysis_id}/artifacts/frames/"
    )


def test_upload_rejects_invalid_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/v1/analyses",
        files={"file": ("notes.txt", b"not a video", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_extension"


def test_upload_rejects_oversized_file(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch, max_upload_size_bytes=16)
    video_path = synthetic_video_factory(tmp_path / "match.avi", width=800, height=900)

    response = _upload_video(client, video_path)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_exact_duplicate_renamed_retry_and_analyze_again(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "original.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )

    first = _upload_video(client, video_path, idempotency_key="first-upload")
    retry = _upload_video(client, video_path, idempotency_key="first-upload")
    renamed = _upload_video(
        client,
        video_path,
        filename="renamed-copy.avi",
        idempotency_key="renamed-upload",
    )

    assert first.status_code == 201
    first_analysis_id = first.json()["analysis_id"]
    assert retry.status_code == 201
    assert retry.json()["analysis_id"] == first_analysis_id
    assert renamed.status_code == 200
    assert renamed.json() == {
        "status": "duplicate",
        "duplicate_type": "exact",
        "existing_analysis_id": first_analysis_id,
        "uploaded_at": renamed.json()["uploaded_at"],
        "actions": {"open_existing": True, "reanalyze": True},
    }
    assert {
        path.name for path in output_dir.iterdir() if path.is_dir() and path.name != "_uploads"
    } == {first_analysis_id}

    reanalyzed = _upload_video(
        client,
        video_path,
        filename="renamed-copy.avi",
        idempotency_key="reanalyze-upload",
        reanalyze=True,
    )

    assert reanalyzed.status_code == 201
    assert reanalyzed.json()["analysis_id"] != first_analysis_id
    history = client.get("/api/v1/analyses")
    assert history.status_code == 200
    assert {item["analysis_id"] for item in history.json()["items"]} == {
        first_analysis_id,
        reanalyzed.json()["analysis_id"],
    }


def test_missing_analysis_returns_404(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)

    response = client.get("/api/v1/analyses/missing-analysis")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "analysis_not_found"


def test_artifact_retrieval_missing_and_traversal_rejection(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    frame = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/frames/frame_000001.jpg")
    missing = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/missing.jpg")
    traversal = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/frames/%2e%2e/job.json")

    assert frame.status_code == 200
    assert frame.headers["content-type"].startswith("image/jpeg")
    assert missing.status_code == 404
    assert traversal.status_code in {400, 404}


def test_calibration_success_invalid_calibration_and_tracking_order(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    tracking_before_calibration = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking",
        json={"calibration_id": "api-calibration", "backend": "controlled-json"},
    )
    invalid_calibration = client.post(
        f"/api/v1/analyses/{analysis_id}/calibration",
        json=_calibration_payload(
            calibration_id="bad-calibration",
            near_left={"x": 100.0, "y": 100.0},
            near_right={"x": 200.0, "y": 100.0},
            far_right={"x": 300.0, "y": 100.0},
            far_left={"x": 400.0, "y": 100.0},
        ),
    )
    failed_job = client.get(f"/api/v1/analyses/{analysis_id}")
    calibration = client.post(
        f"/api/v1/analyses/{analysis_id}/calibration",
        json=_calibration_payload(calibration_id="api-calibration"),
    )

    assert tracking_before_calibration.status_code == 409
    assert invalid_calibration.status_code == 400
    assert failed_job.json()["status"] == "failed"
    assert failed_job.json()["error"] == "Calibration failed."
    assert calibration.status_code == 200
    assert calibration.json()["job"]["status"] == "processing"
    assert calibration.json()["job"]["calibration_completed"] is True
    assert calibration.json()["calibration"]["calibration_id"] == "api-calibration"


def test_automatic_court_detection_success_updates_job(
    tmp_path: Path,
    synthetic_court_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_court_video_factory(tmp_path / "court-match.avi")
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    detection = client.post(f"/api/v1/analyses/{analysis_id}/court-detection")
    job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert detection.status_code == 200
    payload = detection.json()
    assert payload["status"] == "detected"
    assert payload["confidence"] >= 0.72
    assert payload["selected_frame"].startswith("frames/frame_")
    near_left_y = payload["detected_corners"]["near_left"]["y"]
    far_left_y = payload["detected_corners"]["far_left"]["y"]
    assert near_left_y > far_left_y
    assert payload["manual_calibration_required"] is False
    assert payload["calibration"]["calibration_id"] == "auto-court-detection"
    assert payload["job"]["calibration_completed"] is True
    assert payload["job"]["manual_calibration_required"] is False
    assert payload["job"]["court_detection_status"] == "detected"
    assert payload["job"]["court_detection_confidence"] == payload["confidence"]
    assert payload["job"]["court_detection_selected_frame"] == payload["selected_frame"]
    assert payload["job"]["court_detection_detected_corners"] == payload["detected_corners"]
    assert {artifact["path"].split("/")[-1] for artifact in payload["artifacts"]} == {
        "calibration.json",
        "top_down.jpg",
        "verification.jpg",
    }
    loaded_job = job.json()
    assert loaded_job["current_stage"] == "calibrated"
    assert loaded_job["calibration_completed"] is True
    assert loaded_job["court_detection_status"] == "detected"
    assert loaded_job["court_detection_confidence"] == payload["confidence"]
    assert loaded_job["court_detection_selected_frame"] == payload["selected_frame"]
    assert loaded_job["court_detection_detected_corners"] == payload["detected_corners"]

    reloaded_job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert reloaded_job.status_code == 200
    assert reloaded_job.json()["court_detection_status"] == "detected"
    assert reloaded_job.json()["court_detection_confidence"] == payload["confidence"]


def test_automatic_court_detection_low_confidence_requires_manual_calibration(
    tmp_path: Path,
    synthetic_court_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_court_video_factory(tmp_path / "small-court.avi", court_scale=0.20)
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    detection = client.post(f"/api/v1/analyses/{analysis_id}/court-detection")
    job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert detection.status_code == 200
    payload = detection.json()
    assert payload["status"] == "low_confidence"
    assert 0.25 <= payload["confidence"] < 0.72
    assert payload["selected_frame"].startswith("frames/frame_")
    assert payload["detected_corners"] is not None
    assert payload["manual_calibration_required"] is True
    assert payload["calibration"] is None
    assert payload["artifacts"] == []
    assert payload["job"]["court_detection_status"] == "low_confidence"
    assert payload["job"]["court_detection_confidence"] == payload["confidence"]
    assert payload["job"]["court_detection_selected_frame"] == payload["selected_frame"]
    assert payload["job"]["court_detection_detected_corners"] == payload["detected_corners"]
    loaded_job = job.json()
    assert loaded_job["current_stage"] == "inspected"
    assert loaded_job["calibration_completed"] is False
    assert loaded_job["manual_calibration_required"] is True
    assert loaded_job["court_detection_status"] == "low_confidence"
    assert loaded_job["court_detection_confidence"] == payload["confidence"]
    assert loaded_job["court_detection_selected_frame"] == payload["selected_frame"]
    assert loaded_job["court_detection_detected_corners"] == payload["detected_corners"]


def test_automatic_court_detection_failure_requires_manual_calibration(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "no-court.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    detection = client.post(f"/api/v1/analyses/{analysis_id}/court-detection")
    job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert detection.status_code == 200
    payload = detection.json()
    assert payload["status"] == "failed"
    assert payload["confidence"] == 0.0
    assert payload["selected_frame"] is None
    assert payload["detected_corners"] is None
    assert payload["manual_calibration_required"] is True
    assert payload["job"]["court_detection_status"] == "failed"
    assert payload["job"]["court_detection_confidence"] == 0.0
    assert payload["job"]["court_detection_selected_frame"] is None
    assert payload["job"]["court_detection_detected_corners"] is None
    loaded_job = job.json()
    assert loaded_job["calibration_completed"] is False
    assert loaded_job["manual_calibration_required"] is True
    assert loaded_job["court_detection_status"] == "failed"
    assert loaded_job["court_detection_confidence"] == 0.0
    assert loaded_job["court_detection_selected_frame"] is None
    assert loaded_job["court_detection_detected_corners"] is None


def test_full_controlled_api_workflow(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    calibration = client.post(
        f"/api/v1/analyses/{analysis_id}/calibration",
        json=_calibration_payload(calibration_id="api-calibration"),
    )
    _write_controlled_api_detections(output_dir, analysis_id)
    tracking = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking",
        json={
            "calibration_id": "api-calibration",
            "backend": "controlled-json",
            "detections_jsonl": "uploads/detections.jsonl",
            "frame_interval": 1,
        },
    )
    active_play = client.post(f"/api/v1/analyses/{analysis_id}/debug/active-play")
    retrieved_active_play = client.get(f"/api/v1/analyses/{analysis_id}/debug/active-play")
    players = client.get(f"/api/v1/analyses/{analysis_id}/players")
    candidates = client.get(f"/api/v1/analyses/{analysis_id}/player-candidates")
    candidate_id = candidates.json()["candidates"][0]["candidate_id"]
    invalid_selection = client.post(
        f"/api/v1/analyses/{analysis_id}/players/select",
        json={"track_id": 99},
    )
    analytics_before_selection = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    selection = client.post(
        f"/api/v1/analyses/{analysis_id}/player-candidates/{candidate_id}/select"
    )
    analytics = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    retrieved_analytics = client.get(f"/api/v1/analyses/{analysis_id}/analytics")
    repeated_analytics = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    heatmap = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/analytics/heatmap.png")
    trajectory = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/analytics/trajectory.png")
    final_job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert calibration.status_code == 200
    assert tracking.status_code == 200
    assert active_play.status_code == 200
    assert active_play.json()["shadow_mode"] is True
    assert active_play.json()["validated"] is False
    assert active_play.json()["policy_version"] == "active-play-v1"
    assert {window["state"] for window in active_play.json()["windows"]} <= {
        "LIKELY_ACTIVE",
        "LIKELY_IDLE",
        "UNKNOWN",
    }
    assert retrieved_active_play.status_code == 200
    assert retrieved_active_play.json() == active_play.json()
    assert tracking.json()["tracking"]["eligible_player_track_ids"] == [1]
    assert players.status_code == 200
    assert players.json()["track_summaries"][0]["eligible_for_selection"] is True
    assert players.json()["track_summaries"][0]["preview_image"] == (
        "tracking/player_previews/track_1.jpg"
    )
    assert candidates.status_code == 200
    assert candidates.json()["candidates"][0]["source_raw_track_ids"] == [1]
    assert candidates.json()["candidates"][0]["candidate_id"].startswith("pc_")
    assert candidates.json()["candidates"][0]["representative_crop_artifact"] is not None
    assert invalid_selection.status_code == 400
    assert analytics_before_selection.status_code == 409
    assert selection.status_code == 200
    assert selection.json()["selected_candidate_id"] == candidate_id
    assert analytics.status_code == 200
    assert "active_play" not in analytics.json()
    assert analytics.json()["analytics"]["timeline_observation_count"] == 15
    assert analytics.json()["analytics"]["selected_player_candidate_id"] == candidate_id
    assert analytics.json()["analytics"]["source_raw_track_ids"] == [1]
    assert analytics.json()["match_iq"]["status"] == "insufficient_data"
    assert analytics.json()["match_iq"]["quality_gate"] == "INSUFFICIENT_EVIDENCE"
    assert analytics.json()["match_iq"]["insights"] == []
    assert tracking.json()["job"]["upload_preflight"]["status"] == "UNSUITABLE"
    assert tracking.json()["job"]["analysis_readiness"]["status"] == "UNSUITABLE"
    assert (output_dir / analysis_id / "analytics" / "match_iq.json").is_file()
    assert retrieved_analytics.status_code == 200
    assert retrieved_analytics.json()["analytics"]["artifacts"]["heatmap_png"] == "heatmap.png"
    assert retrieved_analytics.json()["match_iq"] == analytics.json()["match_iq"]
    assert repeated_analytics.status_code == 200
    assert repeated_analytics.json()["match_iq"] == analytics.json()["match_iq"]
    assert heatmap.status_code == 200
    assert heatmap.headers["content-type"].startswith("image/png")
    assert heatmap.headers["content-disposition"].startswith("inline")
    assert trajectory.status_code == 200
    assert trajectory.headers["content-type"].startswith("image/png")
    assert trajectory.headers["content-disposition"].startswith("inline")
    assert final_job.json()["status"] == "completed"
    assert final_job.json()["analytics_completed"] is True


def test_full_controlled_api_workflow_with_automatic_court_detection(
    tmp_path: Path,
    synthetic_court_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_court_video_factory(
        tmp_path / "auto-detected-match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    detection = client.post(f"/api/v1/analyses/{analysis_id}/court-detection")
    _write_controlled_api_detections(
        output_dir,
        analysis_id,
        calibration_id="auto-court-detection",
    )
    tracking = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking",
        json={
            "calibration_id": "auto-court-detection",
            "backend": "controlled-json",
            "detections_jsonl": "uploads/detections.jsonl",
            "frame_interval": 1,
        },
    )
    players = client.get(f"/api/v1/analyses/{analysis_id}/players")
    selection = client.post(
        f"/api/v1/analyses/{analysis_id}/players/select",
        json={"track_id": 1},
    )
    analytics = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    retrieved_analytics = client.get(f"/api/v1/analyses/{analysis_id}/analytics")
    final_job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert detection.status_code == 200
    assert detection.json()["status"] == "detected"
    assert tracking.status_code == 200
    assert players.status_code == 200
    assert players.json()["track_summaries"][0]["eligible_for_selection"] is True
    assert selection.status_code == 200
    assert selection.json()["selected_player_track_id"] == 1
    assert analytics.status_code == 200
    assert retrieved_analytics.status_code == 200
    assert final_job.json()["status"] == "completed"
    assert final_job.json()["analytics_completed"] is True
    assert final_job.json()["court_detection_status"] == "detected"
    assert final_job.json()["court_detection_confidence"] == detection.json()["confidence"]
    assert final_job.json()["court_detection_selected_frame"] == detection.json()["selected_frame"]
    assert (
        final_job.json()["court_detection_detected_corners"] == detection.json()["detected_corners"]
    )


def test_ultralytics_tracking_missing_model_returns_typed_error(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(
        tmp_path,
        monkeypatch,
        detector_model_path=tmp_path / "models" / "missing.pt",
    )
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]
    calibration = client.post(
        f"/api/v1/analyses/{analysis_id}/calibration",
        json=_calibration_payload(calibration_id="api-calibration"),
    )

    response = client.post(
        f"/api/v1/analyses/{analysis_id}/tracking",
        json={
            "calibration_id": "api-calibration",
            "backend": "ultralytics",
            "frame_interval": 1,
        },
    )
    job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert calibration.status_code == 200
    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "detector_model_missing",
        "message": "Player detection is not available because the detector model is missing.",
    }
    assert job.json()["status"] == "processing"
    assert job.json()["tracking_completed"] is False


def test_legacy_job_without_court_detection_fields_still_loads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    analysis_id = "legacy-analysis"
    analysis_dir = output_dir / analysis_id
    analysis_dir.mkdir(parents=True)
    (analysis_dir / "job.json").write_text(
        json.dumps(
            {
                "analysis_id": analysis_id,
                "status": "processing",
                "current_stage": "inspected",
                "created_at": "2026-07-21T00:00:00Z",
                "updated_at": "2026-07-21T00:01:00Z",
                "inspection_completed": True,
                "calibration_completed": False,
                "tracking_completed": False,
                "player_selected": False,
                "analytics_completed": False,
                "manual_calibration_required": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    repository = _api_repository(output_dir)
    repository.save_job(
        AnalysisJob.model_validate(
            json.loads((analysis_dir / "job.json").read_text(encoding="utf-8"))
        )
    )

    response = client.get(f"/api/v1/analyses/{analysis_id}")
    active_play = client.get(f"/api/v1/analyses/{analysis_id}/debug/active-play")

    assert response.status_code == 200
    assert active_play.status_code == 409
    assert active_play.json()["error"]["code"] == "active_play_not_ready"
    assert response.json()["court_detection_status"] is None
    assert response.json()["court_detection_confidence"] is None
    assert response.json()["court_detection_selected_frame"] is None
    assert response.json()["court_detection_detected_corners"] is None


def test_legacy_analytics_without_match_iq_returns_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, output_dir = _api_client(tmp_path, monkeypatch)
    analysis_id = "legacy-analytics"
    analytics_dir = output_dir / analysis_id / "analytics"
    analytics_dir.mkdir(parents=True)
    (output_dir / analysis_id / "job.json").write_text(
        json.dumps(
            {
                "analysis_id": analysis_id,
                "status": "completed",
                "current_stage": "analyzed",
                "created_at": "2026-07-21T00:00:00Z",
                "updated_at": "2026-07-21T00:01:00Z",
                "inspection_completed": True,
                "calibration_completed": True,
                "tracking_completed": True,
                "player_selected": True,
                "analytics_completed": True,
                "manual_calibration_required": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (analytics_dir / "analytics.json").write_text(
        json.dumps(
            {
                "analysis_id": analysis_id,
                "source_tracking_report": "tracking/tracking.json",
                "source_observations": "tracking/observations.jsonl",
                "calibration_id": "legacy-calibration",
                "selected_player_track_id": 1,
                "distance": {
                    "total_distance_feet": 12.0,
                    "total_distance_meters": 3.6576,
                    "average_movement_feet_per_second": 2.4,
                    "average_movement_meters_per_second": 0.73152,
                },
                "timeline_observation_count": 5,
                "average_court_position": [10.0, 20.0],
                "zone_occupancy": {
                    "kitchen": {"seconds": 1.0, "percentage": 20.0},
                    "transition_zone": {"seconds": 3.0, "percentage": 60.0},
                    "baseline_area": {"seconds": 1.0, "percentage": 20.0},
                    "tracked_time_seconds": 5.0,
                },
                "artifacts": {
                    "analytics_json": "analytics.json",
                    "movement_summary_json": "movement_summary.json",
                    "timeline_json": "timeline.json",
                    "trajectory_png": "trajectory.png",
                    "heatmap_png": "heatmap.png",
                },
                "created_at": "2026-07-21T00:02:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    repository = _api_repository(output_dir)
    repository.save_job(
        AnalysisJob.model_validate(
            json.loads((output_dir / analysis_id / "job.json").read_text(encoding="utf-8"))
        )
    )

    response = client.get(f"/api/v1/analyses/{analysis_id}/analytics")

    assert response.status_code == 200
    assert response.json()["analytics"]["analysis_id"] == analysis_id
    assert response.json()["match_iq"] is None


def test_analytics_retrieval_before_generation_returns_conflict(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=15,
        fps=10.0,
        width=800,
        height=900,
    )
    analysis_id = _upload_video(client, video_path).json()["analysis_id"]

    response = client.get(f"/api/v1/analyses/{analysis_id}/analytics")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "analytics_not_ready"


def test_openapi_docs_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _output_dir = _api_client(tmp_path, monkeypatch)

    response = client.get("/docs")

    assert response.status_code == 200


def _api_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_upload_size_bytes: int = 5_000_000,
    detector_model_path: Path | None = None,
) -> tuple[TestClient, Path]:
    output_dir = tmp_path / "api-output"
    monkeypatch.setenv("PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("PICKLEBALL_AI_DEFAULT_SAMPLE_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES", str(max_upload_size_bytes))
    monkeypatch.setenv("PICKLEBALL_AI_MIN_ELIGIBLE_TRACK_DURATION_SECONDS", "0.2")
    monkeypatch.setenv("PICKLEBALL_AI_MIN_ELIGIBLE_COURT_MOVEMENT_RATE_FEET_PER_SECOND", "0.5")
    if detector_model_path is not None:
        monkeypatch.setenv("COURT4_DETECTOR_MODEL_PATH", str(detector_model_path))
    get_settings.cache_clear()
    client = TestClient(create_app())
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "workflow@example.com", "password": "a sufficiently long password"},
    )
    assert registered.status_code == 201
    client.headers["Authorization"] = f"Bearer {registered.json()['access_token']}"
    owner_id = UUID(registered.json()["user"]["id"])
    with get_persistence().session_factory.begin() as session:
        user = session.get(User, owner_id)
        assert user is not None
        user.email_verified_at = datetime.now(tz=UTC)
    API_TEST_OWNERS[output_dir] = owner_id
    return client, output_dir


def _upload_video(
    client: TestClient,
    video_path: Path,
    *,
    filename: str | None = None,
    idempotency_key: str | None = None,
    reanalyze: bool = False,
) -> Response:
    with video_path.open("rb") as video:
        response = client.post(
            "/api/v1/analyses",
            headers=({"Idempotency-Key": idempotency_key} if idempotency_key is not None else None),
            data={"reanalyze": "true"} if reanalyze else None,
            files={
                "file": (
                    filename or video_path.name,
                    video.read(),
                    "video/x-msvideo",
                )
            },
        )
    return cast(Response, response)


def _calibration_payload(
    *,
    calibration_id: str,
    near_left: dict[str, float] | None = None,
    near_right: dict[str, float] | None = None,
    far_right: dict[str, float] | None = None,
    far_left: dict[str, float] | None = None,
) -> dict[str, object]:
    return {
        "calibration_id": calibration_id,
        "source_frame": "frames/frame_000001.jpg",
        "near_left": near_left or {"x": 80.0, "y": 760.0},
        "near_right": near_right or {"x": 720.0, "y": 760.0},
        "far_right": far_right or {"x": 600.0, "y": 120.0},
        "far_left": far_left or {"x": 200.0, "y": 120.0},
    }


def _write_controlled_api_detections(
    output_dir: Path,
    analysis_id: str,
    *,
    calibration_id: str = "api-calibration",
) -> None:
    calibration = load_calibration_report(
        output_dir / analysis_id / "calibrations" / calibration_id / "calibration.json"
    )
    lines = []
    for frame_index in range(15):
        ground = court_point_to_image((10.0 + frame_index * 0.1, 12.0), calibration)
        lines.append(_line_from_ground_point(frame_index, 1, ground, confidence=0.92))
    detections_path = output_dir / analysis_id / "uploads" / "detections.jsonl"
    detections_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    repository = _api_repository(output_dir)
    repository.register_current_artifacts(analysis_id)


def _api_repository(output_dir: Path) -> AnalysisJobRepository:
    return AnalysisJobRepository(
        output_dir=output_dir,
        api_base_path="/api/v1",
        owner_user_id=API_TEST_OWNERS[output_dir],
    )


def _line_from_ground_point(
    frame_index: int,
    track_id: int,
    ground_point: tuple[float, float],
    *,
    confidence: float,
) -> str:
    x, y = ground_point
    return build_controlled_detection_line(
        frame_index=frame_index,
        track_id=track_id,
        x1=x - 20,
        y1=y - 80,
        x2=x + 20,
        y2=y,
        confidence=confidence,
    )
