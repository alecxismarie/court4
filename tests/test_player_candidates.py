import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

import cv2
import numpy as np
import pytest

from app.schemas.player_candidates import (
    CandidateQuality,
    CandidateReviewStatus,
    CourtSide,
    PlayerCandidate,
    PlayerCandidateCollection,
)
from app.schemas.player_tracking import (
    BoundingBox,
    PlayerObservation,
    PlayerTrackingReport,
    TrackingArtifacts,
    TrackingPerformanceSummary,
)
from app.schemas.video import VideoMetadataReport
from app.services.candidates.service import (
    CandidateImpossibleMergeError,
    _association_evidence,
    _Fragment,
    build_player_candidates,
    merge_player_candidates,
    reject_player_candidate,
    restore_player_candidate,
    select_player_candidate,
    unmerge_player_candidates,
)


class _CandidateCase(TypedDict):
    tracking_dir: Path
    candidate: Path
    tracking: Path
    observations: Path
    video: Path
    metadata: Path
    report: PlayerTrackingReport


def test_fragment_association_is_deterministic_and_blocks_simultaneous_people(
    tmp_path: Path,
) -> None:
    case = _candidate_case(
        tmp_path,
        [
            *_track(1, start_frame=0, positions=[(10.0, 10.0), (10.2, 10.1), (10.4, 10.2)]),
            *_track(2, start_frame=4, positions=[(10.8, 10.3), (11.0, 10.4), (11.2, 10.5)]),
            *_track(3, start_frame=0, positions=[(16.0, 11.0), (16.1, 11.1), (16.2, 11.2)]),
        ],
    )

    first = _build(case)
    second = _build(case)

    first_candidates = _all_candidates(first)
    second_candidates = _all_candidates(second)
    memberships = [candidate.source_raw_track_ids for candidate in first_candidates]
    assert [1, 2] in memberships
    assert [3] in memberships
    assert [1, 2, 3] not in memberships
    assert [candidate.candidate_id for candidate in first_candidates] == [
        candidate.candidate_id for candidate in second_candidates
    ]
    merged = next(
        candidate for candidate in first_candidates if len(candidate.source_raw_track_ids) == 2
    )
    assert merged.automatic_merge_evidence[0].reasons == [
        "non_overlapping_fragments",
        "short_temporal_gap",
        "plausible_endpoint_distance",
        "plausible_movement_speed",
        "similar_bounding_box_size",
        "court_side_consistent",
        "appearance_histogram_consistent",
    ]


def test_fragment_association_blocks_opposite_side_and_impossible_movement(
    tmp_path: Path,
) -> None:
    case = _candidate_case(
        tmp_path,
        [
            *_track(1, start_frame=0, positions=[(5.0, 10.0), (5.1, 10.1)]),
            *_track(2, start_frame=3, positions=[(5.0, 34.0), (5.1, 34.1)]),
            *_track(3, start_frame=6, positions=[(19.0, 10.0), (19.1, 10.1)]),
        ],
    )

    collection = _build(case)

    assert {tuple(candidate.source_raw_track_ids) for candidate in _all_candidates(collection)} == {
        (1,),
        (2,),
        (3,),
    }


def test_long_gap_fragment_association_requires_strong_appearance_match() -> None:
    first_observation = _track(
        1,
        start_frame=0,
        positions=[(10.0, 10.0), (10.2, 10.0)],
    )
    second_observation = _track(
        2,
        start_frame=12,
        positions=[(10.4, 10.0), (10.6, 10.0)],
    )
    first = _Fragment(
        track_id=1,
        observations=tuple(first_observation),
        first_timestamp=0.0,
        last_timestamp=0.1,
        first_position=(10.0, 10.0),
        last_position=(10.2, 10.0),
        average_area=4800,
        court_side=CourtSide.near,
        appearance_descriptor=(1.0, 0.0),
    )
    second = _Fragment(
        track_id=2,
        observations=tuple(second_observation),
        first_timestamp=1.2,
        last_timestamp=1.3,
        first_position=(10.4, 10.0),
        last_position=(10.6, 10.0),
        average_area=4800,
        court_side=CourtSide.near,
        appearance_descriptor=(0.94, math.sqrt(1 - 0.94**2)),
    )

    assert _association_evidence(first, second) is None


def test_candidate_quality_and_vertical_suitability_are_factual(tmp_path: Path) -> None:
    case = _candidate_case(
        tmp_path,
        _track(7, start_frame=0, positions=[(30.0, 50.0), (30.0, 50.0)]),
        width=360,
        height=640,
    )

    collection = _build(case)

    assert collection.recording_suitability.status == "UNSUITABLE"
    assert "vertical_video_limitation" in collection.recording_suitability.reasons
    candidate = collection.excluded_candidates[0]
    assert candidate.quality == CandidateQuality.uncertain
    assert candidate.selection_eligible is False
    assert "short_track_duration" in candidate.quality_reasons
    assert "low_in_court_ratio" in candidate.quality_reasons
    assert "mostly_outside_detected_court" in candidate.selection_exclusion_reasons


def test_strong_quality_requires_meaningful_court_coverage(tmp_path: Path) -> None:
    moving = _track(
        7,
        start_frame=0,
        positions=[(5.0 + index * 0.1, 8.0 + index * 0.12) for index in range(60)],
    )
    stationary = _track(
        8,
        start_frame=0,
        positions=[(18.0 + (index % 2) * 0.02, 18.0) for index in range(60)],
    )
    collection = _build(_candidate_case(tmp_path, [*moving, *stationary]))
    by_track = {
        candidate.source_raw_track_ids[0]: candidate for candidate in _all_candidates(collection)
    }

    assert by_track[7].quality == CandidateQuality.strong
    assert by_track[8].quality == CandidateQuality.usable
    assert "limited_court_movement" in by_track[8].quality_reasons
    assert by_track[7].selection_eligible is True
    assert by_track[8].selection_eligible is False
    assert "limited_court_movement" in by_track[8].selection_exclusion_reasons


def test_legacy_raw_track_selection_maps_to_generated_candidate(tmp_path: Path) -> None:
    case = _candidate_case(
        tmp_path,
        _track(
            7,
            start_frame=0,
            positions=[(5.0 + index * 0.2, 10.0) for index in range(30)],
        ),
    )
    case["report"] = case["report"].model_copy(update={"selected_player_track_id": 7})

    collection = _build(case)

    assert collection.selected_candidate_id == collection.candidates[0].candidate_id
    assert collection.candidates[0].review_status == CandidateReviewStatus.selected


def test_manual_merge_selection_rejection_restore_and_undo_persist(tmp_path: Path) -> None:
    case = _candidate_case(
        tmp_path,
        [
            *_track(
                1,
                start_frame=0,
                positions=[(1.0 + index * 0.2, 10.0) for index in range(15)],
            ),
            *_track(
                2,
                start_frame=21,
                positions=[(18.0 + index * 0.2, 10.0) for index in range(15)],
            ),
        ],
    )
    original = _build(case)
    ids = [candidate.candidate_id for candidate in original.candidates]

    merged = merge_player_candidates(
        candidate_path=case["candidate"],
        candidate_ids=ids,
        tracking_report_path=case["tracking"],
        observations_path=case["observations"],
        source_video_path=case["video"],
        metadata_path=case["metadata"],
    )
    assert len(merged.candidates) == 1
    merged_candidate = merged.candidates[0]
    assert merged_candidate.manual_merge_id is not None

    selected = select_player_candidate(
        candidate_path=case["candidate"],
        candidate_id=merged_candidate.candidate_id,
        tracking_report_path=case["tracking"],
    )
    tracking = PlayerTrackingReport.model_validate_json(case["tracking"].read_text())
    assert selected.selected_candidate_id == merged_candidate.candidate_id
    assert tracking.selected_player_candidate_id == merged_candidate.candidate_id
    assert tracking.selected_player_source_track_ids == [1, 2]

    undone = unmerge_player_candidates(
        candidate_path=case["candidate"],
        candidate_id=merged_candidate.candidate_id,
        tracking_report_path=case["tracking"],
        observations_path=case["observations"],
        source_video_path=case["video"],
        metadata_path=case["metadata"],
    )
    assert len(undone.candidates) == 2
    assert undone.selected_candidate_id is None
    assert undone.manual_merge_decisions[-1].active is False

    rejected_id = undone.candidates[0].candidate_id
    rejected = reject_player_candidate(
        candidate_path=case["candidate"],
        candidate_id=rejected_id,
        reason="spectator",
        tracking_report_path=case["tracking"],
    )
    assert rejected.excluded_candidates[0].review_status == CandidateReviewStatus.rejected
    assert rejected.excluded_candidates[0].rejection_reason == "spectator"

    restored = restore_player_candidate(
        candidate_path=case["candidate"],
        candidate_id=rejected_id,
    )
    assert not restored.excluded_candidates
    assert len(restored.candidates) == 2


def test_manual_merge_blocks_duplicate_timestamps(tmp_path: Path) -> None:
    case = _candidate_case(
        tmp_path,
        [
            *_track(
                1,
                start_frame=0,
                positions=[(1.0 + index * 0.2, 10.0) for index in range(15)],
            ),
            *_track(
                2,
                start_frame=0,
                positions=[(10.0 + index * 0.2, 10.0) for index in range(15)],
            ),
        ],
    )
    collection = _build(case)

    with pytest.raises(CandidateImpossibleMergeError, match="same time"):
        merge_player_candidates(
            candidate_path=case["candidate"],
            candidate_ids=[candidate.candidate_id for candidate in collection.candidates],
            tracking_report_path=case["tracking"],
            observations_path=case["observations"],
            source_video_path=case["video"],
            metadata_path=case["metadata"],
        )


def test_selection_policy_exposes_only_four_active_in_court_moving_candidates(
    tmp_path: Path,
) -> None:
    observations: list[PlayerObservation] = []
    for track_id, x_position in enumerate((2.0, 6.0, 10.0, 14.0), start=1):
        observations.extend(
            _track(
                track_id,
                start_frame=0,
                positions=[(x_position, 5.0 + index * 0.2) for index in range(30)],
            )
        )
    observations.extend(_track(5, start_frame=0, positions=[(30.0, 50.0)] * 30))
    observations.extend(_track(6, start_frame=0, positions=[(18.0, 18.0)] * 30))

    collection = _build(_candidate_case(tmp_path, observations))

    assert len(collection.candidates) == 4
    assert all(candidate.selection_eligible for candidate in collection.candidates)
    assert {candidate.source_raw_track_ids[0] for candidate in collection.candidates} == {
        1,
        2,
        3,
        4,
    }
    excluded_by_track = {
        candidate.source_raw_track_ids[0]: candidate for candidate in collection.excluded_candidates
    }
    assert "mostly_outside_detected_court" in excluded_by_track[5].selection_exclusion_reasons
    assert "limited_court_movement" in excluded_by_track[6].selection_exclusion_reasons


def _candidate_case(
    tmp_path: Path,
    observations: list[PlayerObservation],
    *,
    width: int = 640,
    height: int = 368,
) -> _CandidateCase:
    analysis_id = "candidate-test"
    analysis_dir = tmp_path / analysis_id
    tracking_dir = analysis_dir / "tracking"
    tracking_dir.mkdir(parents=True)
    video_path = analysis_dir / "source.avi"
    frame_count = max(60, max((item.frame_index for item in observations), default=0) + 1)
    _write_video(video_path, width=width, height=height, frame_count=frame_count)
    metadata_path = analysis_dir / "metadata.json"
    metadata = VideoMetadataReport(
        analysis_id=analysis_id,
        filename=video_path.name,
        file_size_bytes=video_path.stat().st_size,
        width=width,
        height=height,
        fps=10,
        frame_count=frame_count,
        duration_seconds=frame_count / 10,
        codec="MJPG",
        sample_interval_seconds=1,
        sampled_frames=6,
        created_at=datetime.now(tz=UTC),
    )
    metadata_path.write_text(json.dumps(metadata.model_dump(mode="json")), encoding="utf-8")
    observations_path = tracking_dir / "observations.jsonl"
    observations_path.write_text(
        "\n".join(json.dumps(item.model_dump(mode="json")) for item in observations) + "\n",
        encoding="utf-8",
    )
    tracking = _tracking_report(analysis_id)
    tracking_path = tracking_dir / "tracking.json"
    tracking_path.write_text(
        json.dumps(tracking.model_dump(mode="json")),
        encoding="utf-8",
    )
    return {
        "tracking_dir": tracking_dir,
        "candidate": tracking_dir / "player_candidates.json",
        "tracking": tracking_path,
        "observations": observations_path,
        "video": video_path,
        "metadata": metadata_path,
        "report": tracking,
    }


def _build(case: _CandidateCase) -> PlayerCandidateCollection:
    return build_player_candidates(
        analysis_id="candidate-test",
        tracking_report=case["report"],
        observations_path=case["observations"],
        source_video_path=case["video"],
        metadata_path=case["metadata"],
        tracking_dir=case["tracking_dir"],
    )


def _all_candidates(collection: PlayerCandidateCollection) -> list[PlayerCandidate]:
    return [*collection.candidates, *collection.excluded_candidates]


def _track(
    track_id: int,
    *,
    start_frame: int,
    positions: list[tuple[float, float]],
) -> list[PlayerObservation]:
    return [
        PlayerObservation(
            frame_index=start_frame + offset,
            timestamp_seconds=(start_frame + offset) / 10,
            track_id=track_id,
            bounding_box=BoundingBox(x1=100, y1=100, x2=140, y2=220),
            confidence=0.9,
            image_ground_point=(120, 220),
            court_position=position,
            inside_court=0 <= position[0] <= 20 and 0 <= position[1] <= 44,
            inside_extended_court=-3 <= position[0] <= 23 and -3 <= position[1] <= 47,
            excluded_from_player_tracks=not (0 <= position[0] <= 20 and 0 <= position[1] <= 44),
        )
        for offset, position in enumerate(positions)
    ]


def _tracking_report(analysis_id: str) -> PlayerTrackingReport:
    return PlayerTrackingReport(
        analysis_id=analysis_id,
        source_video="source.avi",
        calibration_id="calibration",
        model_name="controlled-json",
        processed_frame_count=60,
        source_frame_count=60,
        frame_interval=1,
        track_count=3,
        eligible_player_track_ids=[],
        court_inclusion_margin_feet=3,
        track_summaries=[],
        artifacts=TrackingArtifacts(
            tracking_json="tracking.json",
            observations_jsonl="observations.jsonl",
            player_selection_image="player_selection.jpg",
            annotated_video="tracked_players.mp4",
        ),
        performance=TrackingPerformanceSummary(
            source_duration_seconds=6,
            source_frame_count=60,
            processed_frame_count=60,
            skipped_frame_count=0,
            processing_time_seconds=1,
            average_processing_fps=60,
            detector_time_seconds=0.5,
        ),
        created_at=datetime.now(tz=UTC),
    )


def _write_video(path: Path, *, width: int, height: int, frame_count: int) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),  # type: ignore[attr-defined]
        10,
        (width, height),
    )
    assert writer.isOpened()
    for _ in range(frame_count):
        writer.write(np.zeros((height, width, 3), dtype=np.uint8))
    writer.release()
