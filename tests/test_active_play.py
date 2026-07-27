import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.schemas.active_play import (
    ActivePlayConfidence,
    ActivePlayReasonCode,
    ActivePlayState,
    ActivePlayWindow,
)
from app.schemas.player_candidates import (
    AverageBoundingBox,
    CandidateBuildPerformance,
    CandidateQuality,
    CourtSide,
    PlayerCandidate,
    PlayerCandidateCollection,
    RecordingSuitability,
    RecordingSuitabilityStatus,
)
from app.schemas.player_tracking import (
    BoundingBox,
    PlayerObservation,
    PlayerTrackingReport,
    TrackingArtifacts,
    TrackingPerformanceSummary,
)
from app.services.active_play.engine import (
    classify_motion_windows,
    merge_active_play_windows,
)
from app.services.active_play.features import (
    build_motion_feature_windows,
    calculate_direction_change_times,
    calculate_speed_change_samples,
    calculate_velocity_samples,
    smooth_track_positions,
)
from app.services.active_play.persistence import (
    ActivePlayPersistenceError,
    generate_active_play,
)
from app.services.active_play.policy import ACTIVE_PLAY_POLICY

FIXED_TIME = datetime(2026, 7, 27, tzinfo=UTC)


def test_time_based_smoothing_velocity_speed_change_and_direction() -> None:
    observations = [
        _observation(1, 0, 0.0, (0.0, 0.0)),
        _observation(1, 1, 0.1, (0.2, 0.0)),
        _observation(1, 2, 0.3, (0.6, 0.0)),
        _observation(1, 3, 0.5, (0.6, 0.6)),
    ]

    smoothed = smooth_track_positions(
        observations,
        policy=replace(ACTIVE_PLAY_POLICY, smoothing_seconds=0.01),
    )
    velocity = calculate_velocity_samples(smoothed)
    changes = calculate_speed_change_samples(velocity)
    directions = calculate_direction_change_times(velocity)

    assert [sample.speed_feet_per_second for sample in velocity] == pytest.approx([2.0, 2.0, 3.0])
    assert changes[-1][1] == pytest.approx(5.0)
    assert directions == (0.5,)


def test_long_gap_and_raw_track_change_are_not_bridged() -> None:
    observations = [
        _observation(1, 0, 0.0, (0.0, 0.0)),
        _observation(1, 1, 0.1, (0.1, 0.0)),
        _observation(1, 20, 2.0, (10.0, 0.0)),
        _observation(2, 21, 2.1, (10.1, 0.0)),
    ]

    velocity = calculate_velocity_samples(smooth_track_positions(observations))

    assert len(velocity) == 1
    assert velocity[0].start_seconds == 0.0
    assert velocity[0].end_seconds == 0.1


def test_motion_windows_report_multi_player_coverage_and_simultaneous_movement() -> None:
    tracking, candidates, observations = _case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
        ]
    )

    windows = build_motion_feature_windows(
        tracking_report=tracking,
        candidates=candidates,
        observations=observations,
    )

    assert windows[0].coverage.reliable_player_count == 2
    assert windows[0].coverage.observed_ratio > 0.9
    assert windows[0].signals.moving_player_count == 2
    assert windows[0].signals.simultaneous_movement is True
    assert windows[0].signals.movement_intensity > 0.25


def test_policy_classifies_likely_active_and_likely_idle() -> None:
    active = _classified_case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
        ]
    )
    idle = _classified_case(
        [
            _stationary_observations(1, position=(3.0, 10.0)),
            _stationary_observations(2, position=(15.0, 34.0)),
        ]
    )

    assert {window.state for window in active} == {ActivePlayState.likely_active}
    assert all(
        ActivePlayReasonCode.sustained_multi_player_movement in window.reason_codes
        for window in active
    )
    assert {window.state for window in idle} == {ActivePlayState.likely_idle}
    assert all(
        ActivePlayReasonCode.sustained_low_movement in window.reason_codes for window in idle
    )


def test_stationary_player_with_active_peers_does_not_make_window_idle() -> None:
    windows = _classified_case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
            _stationary_observations(3, position=(17.0, 20.0)),
        ]
    )

    assert {window.state for window in windows} == {ActivePlayState.likely_active}
    assert ActivePlayReasonCode.stationary_player_with_active_peers in windows[0].reason_codes


def test_low_movement_at_kitchen_abstains_instead_of_assuming_idle() -> None:
    windows = _classified_case(
        [
            _stationary_observations(1, position=(3.0, 18.0)),
            _stationary_observations(2, position=(15.0, 26.0)),
        ]
    )

    assert {window.state for window in windows} == {ActivePlayState.unknown}
    assert all(
        ActivePlayReasonCode.kitchen_low_movement_safeguard in window.reason_codes
        for window in windows
    )


def test_one_player_occlusion_and_gaps_abstain_instead_of_idle() -> None:
    one_player = _classified_case([_moving_observations(1, x_offset=1.0)])
    sparse = _classified_case(
        [
            _sparse_observations(1, position=(3.0, 10.0)),
            _sparse_observations(2, position=(15.0, 34.0)),
        ]
    )

    assert {window.state for window in one_player} == {ActivePlayState.unknown}
    assert all(ActivePlayReasonCode.one_player_only in window.reason_codes for window in one_player)
    assert {window.state for window in sparse} == {ActivePlayState.unknown}
    assert all(
        ActivePlayReasonCode.insufficient_tracked_coverage in window.reason_codes
        for window in sparse
    )
    assert all(window.state != ActivePlayState.likely_idle for window in sparse)


def test_short_clip_abstains() -> None:
    tracking, candidates, observations = _case(
        [
            _moving_observations(1, x_offset=1.0, duration_seconds=3.0),
            _moving_observations(2, x_offset=8.0, duration_seconds=3.0),
        ],
        source_duration_seconds=3.0,
    )
    features = build_motion_feature_windows(
        tracking_report=tracking,
        candidates=candidates,
        observations=observations,
    )

    windows = classify_motion_windows(
        features,
        source_duration_seconds=3.0,
        recording_quality=None,
    )

    assert [window.state for window in windows] == [ActivePlayState.unknown]
    assert ActivePlayReasonCode.short_context in windows[0].reason_codes


def test_interval_merging_is_conservative_and_preserves_lineage() -> None:
    active = _classified_case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
        ]
    )
    first = active[0]
    weaker_second = active[1].model_copy(update={"confidence": ActivePlayConfidence.low})
    unknown_middle = active[1].model_copy(
        update={
            "state": ActivePlayState.unknown,
            "confidence": ActivePlayConfidence.not_available,
        }
    )

    merged = merge_active_play_windows([first, weaker_second])
    separated = merge_active_play_windows([first, unknown_middle, active[2]])

    assert len(merged) == 1
    assert merged[0].confidence == ActivePlayConfidence.low
    assert merged[0].source_window_count == 2
    assert merged[0].lineage.candidate_ids == sorted(first.lineage.candidate_ids)
    assert [item.state for item in separated] == [
        ActivePlayState.likely_active,
        ActivePlayState.unknown,
        ActivePlayState.likely_active,
    ]


def test_persistence_is_deterministic_versioned_and_does_not_touch_analytics(
    tmp_path: Path,
) -> None:
    tracking, candidates, observations = _case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
        ]
    )
    analysis_dir = tmp_path / "analysis"
    tracking_dir = analysis_dir / "tracking"
    analytics_dir = analysis_dir / "analytics"
    tracking_dir.mkdir(parents=True)
    analytics_dir.mkdir()
    _write_sources(tracking_dir, tracking, candidates, observations)
    analytics = analytics_dir / "analytics.json"
    match_iq = analytics_dir / "match_iq.json"
    analytics.write_text('{"sentinel":"analytics"}\n', encoding="utf-8")
    match_iq.write_text('{"sentinel":"match-iq"}\n', encoding="utf-8")
    before = (analytics.read_bytes(), match_iq.read_bytes())

    first = generate_active_play(
        analysis_id="analysis",
        analysis_dir=analysis_dir,
        created_at=FIXED_TIME,
    )
    report_bytes = (analysis_dir / "active_play" / "active_play.json").read_bytes()
    second = generate_active_play(
        analysis_id="analysis",
        analysis_dir=analysis_dir,
        created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )

    assert first == second
    assert report_bytes == (analysis_dir / "active_play" / "active_play.json").read_bytes()
    assert first.policy_version == "active-play-v1"
    assert first.shadow_mode is True
    assert first.validated is False
    assert (analytics.read_bytes(), match_iq.read_bytes()) == before
    assert (analysis_dir / "active_play" / "features.jsonl").is_file()
    assert (analysis_dir / "active_play" / "windows.jsonl").is_file()

    with pytest.raises(ActivePlayPersistenceError, match="stale"):
        generate_active_play(
            analysis_id="analysis",
            analysis_dir=analysis_dir,
            policy=replace(ACTIVE_PLAY_POLICY, version="active-play-v2-test"),
        )


def test_stale_candidate_artifacts_force_unknown(tmp_path: Path) -> None:
    tracking, candidates, observations = _case(
        [
            _moving_observations(1, x_offset=1.0),
            _moving_observations(2, x_offset=8.0),
        ]
    )
    analysis_dir = tmp_path / "legacy"
    tracking_dir = analysis_dir / "tracking"
    tracking_dir.mkdir(parents=True)
    legacy_candidates = candidates.model_copy(update={"schema_version": 1})
    _write_sources(tracking_dir, tracking, legacy_candidates, observations)

    report = generate_active_play(
        analysis_id="legacy",
        analysis_dir=analysis_dir,
        created_at=FIXED_TIME,
    )

    assert {window.state for window in report.windows} == {ActivePlayState.unknown}
    assert all(
        ActivePlayReasonCode.stale_source_artifact in window.reason_codes
        for window in report.windows
    )
    assert report.summary.classifiable_seconds == 0


def _classified_case(
    groups: list[list[PlayerObservation]],
) -> list[ActivePlayWindow]:
    tracking, candidates, observations = _case(groups)
    features = build_motion_feature_windows(
        tracking_report=tracking,
        candidates=candidates,
        observations=observations,
    )
    return classify_motion_windows(
        features,
        source_duration_seconds=tracking.performance.source_duration_seconds,
        recording_quality=None,
    )


def _case(
    groups: list[list[PlayerObservation]],
    *,
    source_duration_seconds: float = 9.0,
) -> tuple[PlayerTrackingReport, PlayerCandidateCollection, list[PlayerObservation]]:
    observations = sorted(
        [observation for group in groups for observation in group],
        key=lambda item: (item.timestamp_seconds, item.track_id),
    )
    track_ids = sorted({item.track_id for item in observations})
    candidates = [_candidate(track_id, observations) for track_id in track_ids]
    tracking = PlayerTrackingReport(
        analysis_id="analysis",
        source_video="source.mp4",
        calibration_id="calibration",
        model_name="controlled",
        processed_frame_count=int(source_duration_seconds * 10),
        source_frame_count=int(source_duration_seconds * 10),
        frame_interval=1,
        track_count=len(track_ids),
        eligible_player_track_ids=track_ids,
        court_inclusion_margin_feet=3,
        track_summaries=[],
        artifacts=TrackingArtifacts(
            tracking_json="tracking.json",
            observations_jsonl="observations.jsonl",
            player_selection_image="player_selection.jpg",
            annotated_video="tracked_players.mp4",
        ),
        performance=TrackingPerformanceSummary(
            source_duration_seconds=source_duration_seconds,
            source_frame_count=int(source_duration_seconds * 10),
            processed_frame_count=int(source_duration_seconds * 10),
            skipped_frame_count=0,
            processing_time_seconds=1,
            average_processing_fps=90,
            detector_time_seconds=0.5,
        ),
        created_at=FIXED_TIME,
    )
    collection = PlayerCandidateCollection(
        schema_version=3,
        analysis_id="analysis",
        candidates=candidates,
        excluded_candidates=[],
        recording_suitability=RecordingSuitability(
            status=RecordingSuitabilityStatus.suitable,
            reasons=[],
            guidance=[],
            orientation="landscape",
            detected_people=len(track_ids),
            usable_candidate_count=len(track_ids),
        ),
        performance=CandidateBuildPerformance(
            candidate_build_seconds=0.1,
            preview_generation_seconds=0.1,
        ),
        generated_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )
    return tracking, collection, observations


def _candidate(
    track_id: int,
    observations: list[PlayerObservation],
) -> PlayerCandidate:
    items = [item for item in observations if item.track_id == track_id]
    return PlayerCandidate(
        candidate_id=f"candidate-{track_id}",
        source_raw_track_ids=[track_id],
        first_observed_timestamp=items[0].timestamp_seconds,
        last_observed_timestamp=items[-1].timestamp_seconds,
        total_observed_duration=items[-1].timestamp_seconds - items[0].timestamp_seconds,
        total_observed_frames=len(items),
        court_distance_feet=10,
        court_movement_rate_feet_per_second=1,
        in_court_observation_ratio=1,
        average_bounding_box=AverageBoundingBox(
            width_pixels=20,
            height_pixels=60,
            area_ratio=0.01,
        ),
        court_side_estimate=CourtSide.near,
        quality=CandidateQuality.usable,
        quality_reasons=[],
        warnings=[],
        automatic_merge_evidence=[],
    )


def _moving_observations(
    track_id: int,
    *,
    x_offset: float,
    duration_seconds: float = 9.0,
) -> list[PlayerObservation]:
    return [
        _observation(
            track_id,
            frame,
            frame / 10,
            (x_offset + frame * 0.15, 10.0 + (frame % 10) * 0.05),
        )
        for frame in range(int(duration_seconds * 10))
    ]


def _stationary_observations(
    track_id: int,
    *,
    position: tuple[float, float],
) -> list[PlayerObservation]:
    return [_observation(track_id, frame, frame / 10, position) for frame in range(90)]


def _sparse_observations(
    track_id: int,
    *,
    position: tuple[float, float],
) -> list[PlayerObservation]:
    return [
        _observation(track_id, frame, frame / 10, position)
        for frame in (0, 1, 20, 21, 40, 41, 60, 61, 80, 81)
    ]


def _observation(
    track_id: int,
    frame: int,
    timestamp: float,
    position: tuple[float, float],
) -> PlayerObservation:
    return PlayerObservation(
        frame_index=frame,
        timestamp_seconds=timestamp,
        track_id=track_id,
        bounding_box=BoundingBox(x1=0, y1=0, x2=20, y2=60),
        confidence=0.9,
        image_ground_point=(10, 60),
        court_position=position,
        inside_court=True,
        inside_extended_court=True,
        excluded_from_player_tracks=False,
    )


def _write_sources(
    tracking_dir: Path,
    tracking: PlayerTrackingReport,
    candidates: PlayerCandidateCollection,
    observations: list[PlayerObservation],
) -> None:
    (tracking_dir / "tracking.json").write_text(
        json.dumps(tracking.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (tracking_dir / "player_candidates.json").write_text(
        json.dumps(candidates.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (tracking_dir / "observations.jsonl").write_text(
        "\n".join(json.dumps(observation.model_dump(mode="json")) for observation in observations)
        + "\n",
        encoding="utf-8",
    )
