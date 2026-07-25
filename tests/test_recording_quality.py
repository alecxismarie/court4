from datetime import UTC, datetime

from app.schemas.player_candidates import (
    AverageBoundingBox,
    CandidateQuality,
    CourtSide,
    PlayerCandidate,
)
from app.schemas.video import VideoMetadataReport
from app.services.recording_quality import (
    QUALITY_THRESHOLDS,
    assess_analysis_readiness,
    assess_upload_preflight,
)

CREATED_AT = datetime(2026, 7, 25, tzinfo=UTC)


def test_upload_preflight_good_recording_has_typed_passes() -> None:
    assessment = assess_upload_preflight(_metadata(), assessed_at=CREATED_AT)

    assert assessment.status == "GOOD"
    assert assessment.stage == "UPLOAD_PREFLIGHT"
    assert assessment.blocking_failures == []
    assert {check.label for check in assessment.passed_checks} >= {
        "Video format",
        "Orientation",
        "Resolution",
        "Frame rate",
        "Duration",
    }
    assert QUALITY_THRESHOLDS.minimum_short_edge_pixels == 720


def test_upload_preflight_limited_and_unsuitable_are_distinct() -> None:
    limited = assess_upload_preflight(
        _metadata(width=1280, height=720, fps=20),
        assessed_at=CREATED_AT,
    )
    unsuitable = assess_upload_preflight(
        _metadata(width=640, height=360, duration_seconds=5),
        assessed_at=CREATED_AT,
    )

    assert limited.status == "LIMITED"
    assert limited.blocking_failures == []
    assert "fps_below_minimum" in limited.reason_codes
    assert unsuitable.status == "UNSUITABLE"
    assert {"resolution_too_low", "recording_too_short"} <= set(unsuitable.reason_codes)


def test_analysis_readiness_reports_tracking_gaps_and_candidate_quality() -> None:
    metadata = _metadata()
    upload = assess_upload_preflight(metadata, assessed_at=CREATED_AT)
    candidate = _candidate(
        quality=CandidateQuality.usable,
        first=0,
        last=30,
        observed=12,
        track_ids=[1, 2],
    )

    readiness = assess_analysis_readiness(
        upload_preflight=upload,
        calibration_completed=True,
        court_detection_status="detected",
        court_detection_confidence=0.9,
        detected_people=2,
        candidates=[candidate],
        selected_candidate_id=candidate.candidate_id,
        assessed_at=CREATED_AT,
    )

    assert readiness.status == "UNSUITABLE"
    assert readiness.analysis_signals is not None
    assert readiness.analysis_signals.candidate_quality == "USABLE"
    assert readiness.analysis_signals.fragment_count == 2
    assert readiness.analysis_signals.unobserved_gap_seconds == 18
    assert "tracking_gaps_excessive" in readiness.reason_codes
    assert readiness.guidance


def _metadata(
    *,
    width: int = 1920,
    height: int = 1080,
    fps: float = 30,
    duration_seconds: float = 30,
) -> VideoMetadataReport:
    return VideoMetadataReport(
        analysis_id="analysis-quality",
        filename="match.mp4",
        file_size_bytes=100,
        width=width,
        height=height,
        fps=fps,
        frame_count=max(1, int(fps * duration_seconds)),
        duration_seconds=duration_seconds,
        codec="mp4v",
        sample_interval_seconds=1,
        sampled_frames=2,
        created_at=CREATED_AT,
    )


def _candidate(
    *,
    quality: CandidateQuality,
    first: float,
    last: float,
    observed: float,
    track_ids: list[int],
) -> PlayerCandidate:
    return PlayerCandidate(
        candidate_id="pc_quality",
        source_raw_track_ids=track_ids,
        first_observed_timestamp=first,
        last_observed_timestamp=last,
        total_observed_duration=observed,
        total_observed_frames=120,
        court_distance_feet=30,
        court_movement_rate_feet_per_second=2.5,
        in_court_observation_ratio=0.9,
        selection_eligible=True,
        average_bounding_box=AverageBoundingBox(
            width_pixels=50,
            height_pixels=120,
            area_ratio=0.01,
        ),
        court_side_estimate=CourtSide.near,
        quality=quality,
        quality_reasons=[],
        warnings=[],
        automatic_merge_evidence=[],
    )
