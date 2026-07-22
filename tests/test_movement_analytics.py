import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import cv2
import pytest

from app.schemas.analytics import TimelinePosition
from app.schemas.player_tracking import (
    BoundingBox,
    PlayerObservation,
    PlayerTrackingReport,
    TrackingArtifacts,
    TrackingPerformanceSummary,
    TrackSummary,
)
from app.services.analytics import (
    AnalyticsOutputExistsError,
    MissingCalibrationForAnalyticsError,
    MissingSelectedPlayerError,
    MissingTrackingForAnalyticsError,
    NoPlayerTrajectoryError,
    generate_match_analytics,
)
from app.services.analytics.movement import calculate_distance_metrics
from app.services.analytics.zones import calculate_zone_occupancy, classify_court_zone
from app.sports.pickleball.calibration import calibrate_court
from app.sports.pickleball.geometry import Point2D
from scripts.analyze_match import main as analyze_match_cli_main

VALID_IMAGE_POINTS: tuple[Point2D, Point2D, Point2D, Point2D] = (
    (80.0, 760.0),
    (720.0, 760.0),
    (600.0, 120.0),
    (200.0, 120.0),
)


def test_distance_metrics() -> None:
    positions = _timeline_positions([(0.0, 0.0, 0.0), (1.0, 3.0, 4.0), (3.0, 6.0, 8.0)])

    metrics = calculate_distance_metrics(positions)

    assert metrics.total_distance_feet == pytest.approx(10.0)
    assert metrics.total_distance_meters == pytest.approx(3.048)
    assert metrics.average_movement_feet_per_second == pytest.approx(10.0 / 3.0)
    assert metrics.average_movement_meters_per_second == pytest.approx(3.048 / 3.0)


def test_zone_classification_and_occupancy() -> None:
    observations = _selected_observations(
        [
            (0.0, 10.0, 22.0),
            (1.0, 10.0, 10.0),
            (2.0, 10.0, 5.0),
            (3.0, 10.0, 15.0),
        ]
    )

    occupancy = calculate_zone_occupancy(observations, transition_area_depth_feet=8.0)

    assert classify_court_zone((10.0, 22.0), transition_area_depth_feet=8.0) == "kitchen"
    assert classify_court_zone((10.0, 10.0), transition_area_depth_feet=8.0) == "transition_zone"
    assert classify_court_zone((10.0, 5.0), transition_area_depth_feet=8.0) == "baseline_area"
    assert occupancy.kitchen.seconds == pytest.approx(1.0)
    assert occupancy.transition_zone.seconds == pytest.approx(1.0)
    assert occupancy.baseline_area.seconds == pytest.approx(1.0)
    assert occupancy.kitchen.percentage == pytest.approx(100.0 / 3.0)


def test_generate_match_analytics_outputs(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory)

    result = generate_match_analytics(
        analysis_id="analytics-case",
        output_dir=tmp_path / "output",
        transition_area_depth_feet=8.0,
        image_width_pixels=500,
    )

    assert result.report.analysis_id == "analytics-case"
    assert result.report.selected_player_track_id == 1
    assert result.report.distance.total_distance_feet == pytest.approx(27.0)
    assert result.report.average_court_position == pytest.approx((10.0, 13.0))
    assert result.timeline.observation_count == 4
    assert result.movement_summary.total_processed_observations == 4
    assert result.movement_summary.valid_court_observation_count == 4

    assert result.analytics_path.exists()
    assert result.movement_summary_path.exists()
    assert result.timeline_path.exists()
    assert result.trajectory_path.exists()
    assert result.heatmap_path.exists()

    assert cv2.imread(str(result.trajectory_path), cv2.IMREAD_COLOR) is not None
    assert cv2.imread(str(result.heatmap_path), cv2.IMREAD_COLOR) is not None

    analytics = json.loads(result.analytics_path.read_text(encoding="utf-8"))
    summary = json.loads(result.movement_summary_path.read_text(encoding="utf-8"))
    timeline = json.loads(result.timeline_path.read_text(encoding="utf-8"))
    assert analytics["artifacts"]["heatmap_png"] == "heatmap.png"
    assert summary["zone_occupancy"]["kitchen"]["seconds"] == pytest.approx(1.0)
    assert len(timeline["positions"]) == 4


def test_missing_tracking_report(tmp_path: Path) -> None:
    with pytest.raises(MissingTrackingForAnalyticsError, match="does not exist"):
        generate_match_analytics(
            analysis_id="missing",
            output_dir=tmp_path / "output",
            transition_area_depth_feet=8.0,
            image_width_pixels=500,
        )


def test_missing_selected_player(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory, selected_track_id=None)

    with pytest.raises(MissingSelectedPlayerError, match="selected player"):
        generate_match_analytics(
            analysis_id="analytics-case",
            output_dir=tmp_path / "output",
            transition_area_depth_feet=8.0,
            image_width_pixels=500,
        )


def test_missing_calibration(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory, create_calibration=False)

    with pytest.raises(MissingCalibrationForAnalyticsError, match="does not exist"):
        generate_match_analytics(
            analysis_id="analytics-case",
            output_dir=tmp_path / "output",
            transition_area_depth_feet=8.0,
            image_width_pixels=500,
        )


def test_no_player_trajectory(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory, observations=[])

    with pytest.raises(NoPlayerTrajectoryError, match="no observations"):
        generate_match_analytics(
            analysis_id="analytics-case",
            output_dir=tmp_path / "output",
            transition_area_depth_feet=8.0,
            image_width_pixels=500,
        )


def test_existing_analytics_output_is_rejected(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory)
    generate_match_analytics(
        analysis_id="analytics-case",
        output_dir=tmp_path / "output",
        transition_area_depth_feet=8.0,
        image_width_pixels=500,
    )

    with pytest.raises(AnalyticsOutputExistsError, match="already exists"):
        generate_match_analytics(
            analysis_id="analytics-case",
            output_dir=tmp_path / "output",
            transition_area_depth_feet=8.0,
            image_width_pixels=500,
        )


def test_analyze_match_cli_generates_match_iq_and_reuses_existing_outputs(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _create_analytics_case(tmp_path, synthetic_court_image_factory)

    success_code = analyze_match_cli_main(
        ["--analysis-id", "analytics-case", "--output-dir", str(tmp_path / "output")]
    )
    success = capsys.readouterr()
    repeated_code = analyze_match_cli_main(
        ["--analysis-id", "analytics-case", "--output-dir", str(tmp_path / "output")]
    )
    repeated = capsys.readouterr()
    failure_code = analyze_match_cli_main(
        ["--analysis-id", "missing", "--output-dir", str(tmp_path / "output")]
    )
    failure = capsys.readouterr()
    match_iq_path = tmp_path / "output" / "analytics-case" / "analytics" / "match_iq.json"

    assert success_code == 0
    assert '"analysis_id": "analytics-case"' in success.out
    assert "Match IQ written to:" in success.err
    assert match_iq_path.is_file()
    match_iq = json.loads(match_iq_path.read_text(encoding="utf-8"))
    assert match_iq["status"] == "generated"
    assert repeated_code == 0
    assert repeated.out == success.out
    assert "Match IQ written to:" in repeated.err
    assert failure_code == 1
    assert "Error:" in failure.err


def _create_analytics_case(
    tmp_path: Path,
    synthetic_court_image_factory: Callable[..., Path],
    *,
    selected_track_id: int | None = 1,
    create_calibration: bool = True,
    observations: list[PlayerObservation] | None = None,
) -> None:
    output_dir = tmp_path / "output"
    analysis_dir = output_dir / "analytics-case"
    tracking_dir = analysis_dir / "tracking"
    tracking_dir.mkdir(parents=True)

    if create_calibration:
        image_path = synthetic_court_image_factory(tmp_path / "court.jpg", width=800, height=900)
        calibrate_court(
            image_path=image_path,
            output_dir=output_dir,
            image_points=VALID_IMAGE_POINTS,
            calibration_id="analytics-calibration",
            analysis_id="analytics-case",
            numeric_tolerance=0.000001,
            min_polygon_area_pixels=1000.0,
            transition_area_depth_feet=8.0,
            top_down_width_pixels=500,
        )

    selected_observations = (
        _selected_observations(
            [
                (0.0, 10.0, 22.0),
                (1.0, 10.0, 10.0),
                (2.0, 10.0, 5.0),
                (3.0, 10.0, 15.0),
            ]
        )
        if observations is None
        else observations
    )
    _write_observations(tracking_dir / "observations.jsonl", selected_observations)
    _write_tracking_report(tracking_dir / "tracking.json", selected_track_id=selected_track_id)


def _write_tracking_report(tracking_path: Path, *, selected_track_id: int | None) -> None:
    created_at = datetime.now(tz=UTC)
    report = PlayerTrackingReport(
        analysis_id="analytics-case",
        source_video="match.avi",
        calibration_id="analytics-calibration",
        model_name="controlled-json",
        processed_frame_count=4,
        source_frame_count=4,
        frame_interval=1,
        track_count=1,
        eligible_player_track_ids=[1],
        selected_player_track_id=selected_track_id,
        selected_player_saved_at=created_at if selected_track_id is not None else None,
        court_inclusion_margin_feet=3.0,
        track_summaries=[
            TrackSummary(
                track_id=1,
                first_frame=0,
                last_frame=3,
                observation_count=4,
                first_timestamp_seconds=0.0,
                last_timestamp_seconds=3.0,
                duration_seconds=3.0,
                average_confidence=0.9,
                court_observation_count=4,
                extended_court_observation_count=4,
                inside_extended_court_ratio=1.0,
                eligible_for_selection=True,
                rejection_reasons=[],
            )
        ],
        artifacts=TrackingArtifacts(
            tracking_json="tracking.json",
            observations_jsonl="observations.jsonl",
            player_selection_image="player_selection.jpg",
            annotated_video="tracked_players.mp4",
        ),
        performance=TrackingPerformanceSummary(
            source_duration_seconds=4.0,
            source_frame_count=4,
            processed_frame_count=4,
            skipped_frame_count=0,
            processing_time_seconds=1.0,
            average_processing_fps=4.0,
            detector_time_seconds=0.1,
        ),
        created_at=created_at,
    )
    tracking_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _write_observations(observations_path: Path, observations: list[PlayerObservation]) -> None:
    observations_path.write_text(
        "\n".join(json.dumps(observation.model_dump(mode="json")) for observation in observations)
        + ("\n" if observations else ""),
        encoding="utf-8",
    )


def _selected_observations(points: list[tuple[float, float, float]]) -> list[PlayerObservation]:
    return [
        PlayerObservation(
            frame_index=index,
            timestamp_seconds=timestamp_seconds,
            track_id=1,
            bounding_box=BoundingBox(x1=100.0, y1=100.0, x2=140.0, y2=180.0),
            confidence=0.9,
            image_ground_point=(120.0, 180.0),
            court_position=(x, y),
            inside_court=True,
            inside_extended_court=True,
            excluded_from_player_tracks=False,
        )
        for index, (timestamp_seconds, x, y) in enumerate(points)
    ]


def _timeline_positions(points: list[tuple[float, float, float]]) -> tuple[TimelinePosition, ...]:
    return tuple(
        TimelinePosition(timestamp_seconds=timestamp_seconds, x=x, y=y)
        for timestamp_seconds, x, y in points
    )
