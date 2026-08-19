import json
from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.schemas.calibration import CourtCalibrationReport
from app.schemas.player_tracking import BoundingBox, TrackedPersonDetection
from app.services.detection.interfaces import ImageArray, PersonDetectionBackend
from app.services.tracking import (
    CalibrationReportNotFoundError,
    CalibrationReportReadError,
    DetectorUnavailableError,
    IneligibleTrackSelectionError,
    JsonTrackingBackend,
    TrackingVideoNotFoundError,
    TrackingVideoReadError,
    UltralyticsByteTrackBackend,
    UnknownTrackSelectionError,
)
from app.services.tracking.json_tracking_backend import build_controlled_detection_line
from app.services.video.player_analysis import (
    PlayerTrackingResult,
    analyze_players,
    ground_contact_point,
    is_inside_court,
    is_inside_extended_court,
    load_calibration_report,
)
from app.services.video.player_selection import select_player_track
from app.sports.pickleball.calibration import calibrate_court, court_point_to_image
from app.sports.pickleball.geometry import Point2D
from scripts.select_player import main as select_player_cli_main
from scripts.track_players import main as track_players_cli_main

VALID_IMAGE_POINTS: tuple[Point2D, Point2D, Point2D, Point2D] = (
    (80.0, 760.0),
    (720.0, 760.0),
    (600.0, 120.0),
    (200.0, 120.0),
)


class FakeTrackingBackend(PersonDetectionBackend):
    def __init__(self) -> None:
        self.closed = False

    @property
    def model_name(self) -> str:
        return "fake"

    def track_frame(
        self,
        frame: ImageArray,
        *,
        frame_index: int,
        timestamp_seconds: float,
    ) -> Sequence[TrackedPersonDetection]:
        del frame, frame_index, timestamp_seconds
        return (
            TrackedPersonDetection(
                track_id=1,
                bounding_box=BoundingBox(x1=10, y1=20, x2=30, y2=60),
                confidence=0.9,
            ),
        )

    def close(self) -> None:
        self.closed = True


def test_detector_interface_behavior() -> None:
    backend = FakeTrackingBackend()
    frame = np.zeros((80, 80, 3), dtype=np.uint8)

    detections = backend.track_frame(frame, frame_index=0, timestamp_seconds=0.0)
    backend.close()

    assert backend.model_name == "fake"
    assert detections[0].track_id == 1
    assert backend.closed is True


def test_json_tracker_interface_behavior(tmp_path: Path) -> None:
    detections_path = tmp_path / "detections.jsonl"
    detections_path.write_text(
        build_controlled_detection_line(
            frame_index=0,
            track_id=4,
            x1=10,
            y1=20,
            x2=30,
            y2=60,
            confidence=0.88,
        )
        + "\n",
        encoding="utf-8",
    )
    backend = JsonTrackingBackend(detections_path)

    detections = backend.track_frame(
        np.zeros((80, 80, 3), dtype=np.uint8),
        frame_index=0,
        timestamp_seconds=0.0,
    )

    assert backend.model_name == "controlled-json"
    assert detections[0].track_id == 4
    assert detections[0].confidence == pytest.approx(0.88)


def test_bounding_box_validation_and_ground_contact_point() -> None:
    box = BoundingBox(x1=100.0, y1=200.0, x2=180.0, y2=420.0)

    assert box.width == 80.0
    assert box.height == 220.0
    assert box.area == 17_600.0
    assert ground_contact_point(box) == (140.0, 420.0)

    with pytest.raises(ValueError, match="x2"):
        BoundingBox(x1=10.0, y1=0.0, x2=10.0, y2=20.0)


def test_court_inclusion_filtering() -> None:
    assert is_inside_court((10.0, 20.0)) is True
    assert is_inside_court((-0.1, 20.0)) is False
    assert is_inside_extended_court((-2.5, 20.0), margin_feet=3.0) is True
    assert is_inside_extended_court((-3.5, 20.0), margin_feet=3.0) is False


def test_tracking_pipeline_outputs_and_eligibility(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)

    result = _run_tracking(case)

    assert result.report.analysis_id == "tracking-test"
    assert result.report.processed_frame_count == 5
    assert result.report.source_frame_count == 5
    assert result.report.track_count == 3
    assert result.report.eligible_player_track_ids == [1]

    summaries = {summary.track_id: summary for summary in result.report.track_summaries}
    assert summaries[1].eligible_for_selection is True
    assert summaries[1].preview_image == "tracking/player_previews/track_1.jpg"
    assert summaries[1].court_distance_feet > 0
    assert summaries[1].court_movement_rate_feet_per_second > 0
    assert summaries[1].observation_count == 5
    assert summaries[2].eligible_for_selection is False
    assert summaries[2].preview_image is None
    assert "mostly_outside_court" in summaries[2].rejection_reasons
    assert summaries[3].eligible_for_selection is False
    assert "limited_court_movement" in summaries[3].rejection_reasons

    assert result.tracking_path.exists()
    assert result.observations_path.exists()
    assert (result.tracking_dir.parent / "tracking/player_previews/track_1.jpg").exists()
    assert result.player_selection_image_path.exists()
    assert result.annotated_video_path.exists()

    observation_lines = result.observations_path.read_text(encoding="utf-8").splitlines()
    assert len(observation_lines) == 15
    first_observation = json.loads(observation_lines[0])
    assert first_observation["track_id"] == 1
    assert first_observation["inside_court"] is True
    assert first_observation["excluded_from_player_tracks"] is False

    excluded_observation = json.loads(observation_lines[1])
    assert excluded_observation["track_id"] == 2
    assert excluded_observation["inside_extended_court"] is False
    assert excluded_observation["excluded_from_player_tracks"] is True


def test_contact_sheet_and_annotated_video_are_readable(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)

    result = _run_tracking(case)

    contact_sheet = cv2.imread(str(result.player_selection_image_path), cv2.IMREAD_COLOR)
    preview_path = result.tracking_dir.parent / "tracking/player_previews/track_1.jpg"
    preview = cv2.imread(str(preview_path), cv2.IMREAD_COLOR)
    annotated = cv2.VideoCapture(str(result.annotated_video_path))
    try:
        success, frame = annotated.read()
    finally:
        annotated.release()

    assert contact_sheet is not None
    assert preview is not None
    assert preview.shape[:2] == (180, 320)
    assert success is True
    assert frame is not None


def test_player_selection_success(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)
    result = _run_tracking(case)

    updated = select_player_track(tracking_report_path=result.tracking_path, track_id=1)
    saved = json.loads(result.tracking_path.read_text(encoding="utf-8"))

    assert updated.selected_player_track_id == 1
    assert saved["selected_player_track_id"] == 1
    assert saved["selected_player_saved_at"] is not None


def test_player_selection_failure_for_unknown_track(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)
    result = _run_tracking(case)

    with pytest.raises(UnknownTrackSelectionError, match="does not exist"):
        select_player_track(tracking_report_path=result.tracking_path, track_id=99)


def test_player_selection_failure_for_ineligible_track(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)
    result = _run_tracking(case)

    with pytest.raises(IneligibleTrackSelectionError, match="not eligible"):
        select_player_track(tracking_report_path=result.tracking_path, track_id=2)


def test_missing_video_handling(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "court.jpg")
    calibration = _create_calibration(tmp_path, image_path)

    with pytest.raises(TrackingVideoNotFoundError, match="does not exist"):
        analyze_players(
            video_path=tmp_path / "missing.avi",
            calibration=calibration,
            output_dir=tmp_path / "output",
            tracking_backend=FakeTrackingBackend(),
            analysis_id="missing-video",
            frame_interval=1,
            court_inclusion_margin_feet=3.0,
            min_eligible_track_duration_seconds=0.0,
            min_eligible_observation_count=1,
            min_eligible_inside_extended_ratio=0.0,
            min_eligible_average_confidence=0.0,
            annotated_video_codec="mp4v",
            annotated_video_fps=10.0,
        )


def test_unreadable_video_handling(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    image_path = synthetic_court_image_factory(tmp_path / "court.jpg")
    calibration = _create_calibration(tmp_path, image_path)
    broken_video = tmp_path / "broken.avi"
    broken_video.write_text("not a video", encoding="utf-8")

    with pytest.raises(TrackingVideoReadError, match="OpenCV could not open"):
        analyze_players(
            video_path=broken_video,
            calibration=calibration,
            output_dir=tmp_path / "output",
            tracking_backend=FakeTrackingBackend(),
            analysis_id="broken-video",
            frame_interval=1,
            court_inclusion_margin_feet=3.0,
            min_eligible_track_duration_seconds=0.0,
            min_eligible_observation_count=1,
            min_eligible_inside_extended_ratio=0.0,
            min_eligible_average_confidence=0.0,
            annotated_video_codec="mp4v",
            annotated_video_fps=10.0,
        )


def test_missing_calibration_handling(tmp_path: Path) -> None:
    with pytest.raises(CalibrationReportNotFoundError, match="does not exist"):
        load_calibration_report(tmp_path / "missing.json")


def test_invalid_calibration_handling(tmp_path: Path) -> None:
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text("not json", encoding="utf-8")

    with pytest.raises(CalibrationReportReadError, match="could not be parsed"):
        load_calibration_report(calibration_path)


def test_unavailable_model_handling(tmp_path: Path) -> None:
    with pytest.raises(DetectorUnavailableError, match="does not exist"):
        UltralyticsByteTrackBackend(
            model_path=tmp_path / "missing.pt",
            expected_model_sha256="0" * 64,
            confidence_threshold=0.35,
            image_size=640,
        )


def test_tracking_cli_success_exit_code(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)

    exit_code = track_players_cli_main(
        [
            "--input",
            str(case["video_path"]),
            "--calibration",
            str(case["calibration_path"]),
            "--detections-jsonl",
            str(case["detections_path"]),
            "--output-dir",
            str(tmp_path / "cli-output"),
            "--analysis-id",
            "cli-tracking",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"analysis_id": "cli-tracking"' in captured.out
    assert (tmp_path / "cli-output" / "cli-tracking" / "tracking" / "tracking.json").exists()


def test_tracking_cli_failure_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = track_players_cli_main(
        [
            "--input",
            str(tmp_path / "missing.avi"),
            "--calibration",
            str(tmp_path / "missing-calibration.json"),
            "--detections-jsonl",
            str(tmp_path / "missing-detections.jsonl"),
            "--output-dir",
            str(tmp_path / "output"),
            "--analysis-id",
            "cli-failure",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Error:" in captured.err


def test_select_player_cli_success_and_failure(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    case = _create_tracking_case(tmp_path, synthetic_court_image_factory, synthetic_video_factory)
    result = _run_tracking(case)

    success_code = select_player_cli_main(
        ["--tracking-report", str(result.tracking_path), "--track-id", "1"]
    )
    success = capsys.readouterr()
    failure_code = select_player_cli_main(
        ["--tracking-report", str(result.tracking_path), "--track-id", "99"]
    )
    failure = capsys.readouterr()

    assert success_code == 0
    assert '"selected_player_track_id": 1' in success.out
    assert failure_code == 1
    assert "Error:" in failure.err


def _create_tracking_case(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    synthetic_video_factory: Callable[..., Path],
) -> dict[str, Path]:
    court_image_path = synthetic_court_image_factory(tmp_path / "court.jpg", width=800, height=900)
    calibration = _create_calibration(tmp_path, court_image_path)
    calibration_path = (
        tmp_path
        / "calibration-output"
        / "calibrations"
        / "tracking-calibration"
        / "calibration.json"
    )
    video_path = synthetic_video_factory(
        tmp_path / "tracking.avi",
        frame_count=5,
        fps=10.0,
        width=800,
        height=900,
    )
    detections_path = tmp_path / "detections.jsonl"
    _write_controlled_tracking_detections(detections_path, calibration)
    return {
        "video_path": video_path,
        "calibration_path": calibration_path,
        "detections_path": detections_path,
    }


def _create_calibration(tmp_path: Path, image_path: Path) -> CourtCalibrationReport:
    result = calibrate_court(
        image_path=image_path,
        output_dir=tmp_path / "calibration-output",
        image_points=VALID_IMAGE_POINTS,
        calibration_id="tracking-calibration",
        analysis_id=None,
        numeric_tolerance=0.000001,
        min_polygon_area_pixels=1000.0,
        transition_area_depth_feet=8.0,
        top_down_width_pixels=500,
    )
    return result.report


def _write_controlled_tracking_detections(
    detections_path: Path,
    calibration: CourtCalibrationReport,
) -> None:
    lines = []
    for frame_index in range(5):
        inside_ground = court_point_to_image((10.0 + frame_index * 0.2, 12.0), calibration)
        outside_ground = court_point_to_image((-5.0, 22.0), calibration)
        stationary_ground = court_point_to_image((16.0, 18.0), calibration)
        lines.append(_line_from_ground_point(frame_index, 1, inside_ground, confidence=0.92))
        lines.append(_line_from_ground_point(frame_index, 2, outside_ground, confidence=0.86))
        lines.append(_line_from_ground_point(frame_index, 3, stationary_ground, confidence=0.91))
    detections_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _line_from_ground_point(
    frame_index: int,
    track_id: int,
    ground_point: Point2D,
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


def _run_tracking(case: dict[str, Path]) -> PlayerTrackingResult:
    calibration = load_calibration_report(case["calibration_path"])
    backend = JsonTrackingBackend(case["detections_path"])
    return analyze_players(
        video_path=case["video_path"],
        calibration=calibration,
        output_dir=case["video_path"].parent / "output",
        tracking_backend=backend,
        analysis_id="tracking-test",
        frame_interval=1,
        court_inclusion_margin_feet=3.0,
        min_eligible_track_duration_seconds=0.2,
        min_eligible_observation_count=3,
        min_eligible_inside_extended_ratio=0.6,
        min_eligible_average_confidence=0.4,
        annotated_video_codec="mp4v",
        annotated_video_fps=10.0,
    )
