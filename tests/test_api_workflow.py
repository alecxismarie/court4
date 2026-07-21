from collections.abc import Callable, Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.config import get_settings
from app.main import create_app
from app.services.tracking.json_tracking_backend import build_controlled_detection_line
from app.services.video.player_analysis import load_calibration_report
from app.sports.pickleball.calibration import court_point_to_image


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
    assert {artifact["path"].split("/")[-1] for artifact in payload["artifacts"]} == {
        "calibration.json",
        "top_down.jpg",
        "verification.jpg",
    }
    assert job.json()["current_stage"] == "calibrated"
    assert job.json()["calibration_completed"] is True


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
    assert job.json()["current_stage"] == "inspected"
    assert job.json()["calibration_completed"] is False
    assert job.json()["manual_calibration_required"] is True


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
    assert job.json()["calibration_completed"] is False
    assert job.json()["manual_calibration_required"] is True


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
    players = client.get(f"/api/v1/analyses/{analysis_id}/players")
    invalid_selection = client.post(
        f"/api/v1/analyses/{analysis_id}/players/select",
        json={"track_id": 99},
    )
    analytics_before_selection = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    selection = client.post(
        f"/api/v1/analyses/{analysis_id}/players/select",
        json={"track_id": 1},
    )
    analytics = client.post(f"/api/v1/analyses/{analysis_id}/analytics")
    retrieved_analytics = client.get(f"/api/v1/analyses/{analysis_id}/analytics")
    heatmap = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/analytics/heatmap.png")
    trajectory = client.get(f"/api/v1/analyses/{analysis_id}/artifacts/analytics/trajectory.png")
    final_job = client.get(f"/api/v1/analyses/{analysis_id}")

    assert calibration.status_code == 200
    assert tracking.status_code == 200
    assert tracking.json()["tracking"]["eligible_player_track_ids"] == [1]
    assert players.status_code == 200
    assert players.json()["track_summaries"][0]["eligible_for_selection"] is True
    assert invalid_selection.status_code == 400
    assert analytics_before_selection.status_code == 409
    assert selection.status_code == 200
    assert selection.json()["selected_player_track_id"] == 1
    assert analytics.status_code == 200
    assert analytics.json()["analytics"]["timeline_observation_count"] == 15
    assert retrieved_analytics.status_code == 200
    assert retrieved_analytics.json()["analytics"]["artifacts"]["heatmap_png"] == "heatmap.png"
    assert heatmap.status_code == 200
    assert heatmap.headers["content-type"].startswith("image/png")
    assert trajectory.status_code == 200
    assert trajectory.headers["content-type"].startswith("image/png")
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
) -> tuple[TestClient, Path]:
    output_dir = tmp_path / "api-output"
    monkeypatch.setenv("PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("PICKLEBALL_AI_DEFAULT_SAMPLE_INTERVAL_SECONDS", "0.5")
    monkeypatch.setenv("PICKLEBALL_AI_MAX_UPLOAD_SIZE_BYTES", str(max_upload_size_bytes))
    monkeypatch.setenv("PICKLEBALL_AI_MIN_ELIGIBLE_TRACK_DURATION_SECONDS", "0.2")
    get_settings.cache_clear()
    return TestClient(create_app()), output_dir


def _upload_video(
    client: TestClient,
    video_path: Path,
    *,
    filename: str | None = None,
) -> Response:
    with video_path.open("rb") as video:
        response = client.post(
            "/api/v1/analyses",
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
