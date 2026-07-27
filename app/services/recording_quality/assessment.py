from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.player_candidates import CandidateQuality, PlayerCandidate
from app.schemas.recording_quality import (
    AnalysisQualitySignals,
    PreflightStage,
    QualityCheck,
    QualityCheckStatus,
    RecordingQualityAssessment,
    RecordingQualityLevel,
    UploadQualitySignals,
)
from app.schemas.video import VideoMetadataReport

RECORDING_QUALITY_POLICY_VERSION = "recording-quality-v1"


@dataclass(frozen=True)
class RecordingQualityThresholds:
    """Initial engineering thresholds; not validated against labeled videos."""

    minimum_short_edge_pixels: int = 720
    blocking_short_edge_pixels: int = 480
    excellent_short_edge_pixels: int = 1080
    minimum_fps: float = 24.0
    blocking_fps: float = 15.0
    excellent_fps: float = 30.0
    minimum_duration_seconds: float = 10.0
    excellent_duration_seconds: float = 60.0
    minimum_tracked_seconds: float = 5.0
    excellent_tracked_seconds: float = 30.0
    minimum_visibility_ratio: float = 0.65
    excellent_visibility_ratio: float = 0.85
    warning_gap_ratio: float = 0.10
    blocking_gap_ratio: float = 0.50
    maximum_fragments: int = 3


QUALITY_THRESHOLDS = RecordingQualityThresholds()


def assess_upload_preflight(
    metadata: VideoMetadataReport,
    *,
    assessed_at: datetime | None = None,
    thresholds: RecordingQualityThresholds = QUALITY_THRESHOLDS,
) -> RecordingQualityAssessment:
    passed: list[QualityCheck] = []
    warnings: list[QualityCheck] = []
    failures: list[QualityCheck] = []
    orientation = "vertical" if metadata.height > metadata.width else "landscape"
    extension = Path(metadata.filename).suffix.lower() or "unknown"
    _pass(
        passed,
        "format_readable",
        "Video format",
        f"{extension} metadata was readable.",
        extension,
    )

    if orientation == "landscape":
        _pass(passed, "landscape_orientation", "Orientation", "Landscape framing detected.")
    else:
        _warn(
            warnings,
            "vertical_orientation",
            "Orientation",
            "Vertical framing may exclude important parts of the court.",
            orientation,
        )

    short_edge = min(metadata.width, metadata.height)
    if short_edge < thresholds.blocking_short_edge_pixels:
        _fail(
            failures,
            "resolution_too_low",
            "Resolution",
            "Resolution is too low for dependable player visibility.",
            f"{metadata.width}×{metadata.height}",
        )
    elif short_edge < thresholds.minimum_short_edge_pixels:
        _warn(
            warnings,
            "resolution_below_minimum",
            "Resolution",
            "Resolution is below the initial 720p minimum.",
            f"{metadata.width}×{metadata.height}",
        )
    else:
        _pass(
            passed,
            "resolution_passed",
            "Resolution",
            "Resolution meets the initial 720p minimum.",
            f"{metadata.width}×{metadata.height}",
        )

    if metadata.fps < thresholds.blocking_fps:
        _fail(
            failures,
            "fps_too_low",
            "Frame rate",
            "Frame rate is too low for dependable movement tracking.",
            f"{metadata.fps:.1f} FPS",
        )
    elif metadata.fps < thresholds.minimum_fps:
        _warn(
            warnings,
            "fps_below_minimum",
            "Frame rate",
            "Frame rate is below the initial 24 FPS minimum.",
            f"{metadata.fps:.1f} FPS",
        )
    else:
        _pass(
            passed,
            "fps_passed",
            "Frame rate",
            "Frame rate meets the initial 24 FPS minimum.",
            f"{metadata.fps:.1f} FPS",
        )

    if metadata.duration_seconds < thresholds.minimum_duration_seconds:
        _fail(
            failures,
            "recording_too_short",
            "Duration",
            "The recording is too short to provide enough continuous evidence.",
            f"{metadata.duration_seconds:.1f} seconds",
        )
    else:
        _pass(
            passed,
            "duration_passed",
            "Duration",
            "The recording meets the initial duration minimum.",
            f"{metadata.duration_seconds:.1f} seconds",
        )

    excellent = (
        orientation == "landscape"
        and short_edge >= thresholds.excellent_short_edge_pixels
        and metadata.fps >= thresholds.excellent_fps
        and metadata.duration_seconds >= thresholds.excellent_duration_seconds
    )
    return RecordingQualityAssessment(
        stage=PreflightStage.upload,
        status=_level(failures, warnings, excellent=excellent),
        passed_checks=passed,
        warnings=warnings,
        blocking_failures=failures,
        reason_codes=_reason_codes(warnings, failures),
        guidance=_guidance(warnings, failures),
        upload_signals=UploadQualitySignals(
            format=extension,
            orientation=orientation,
            width=metadata.width,
            height=metadata.height,
            fps=metadata.fps,
            duration_seconds=metadata.duration_seconds,
        ),
        assessed_at=assessed_at or datetime.now(tz=UTC),
    )


def assess_analysis_readiness(
    *,
    upload_preflight: RecordingQualityAssessment | None,
    calibration_completed: bool,
    court_detection_status: str | None,
    court_detection_confidence: float | None,
    detected_people: int,
    candidates: Sequence[PlayerCandidate],
    selected_candidate_id: str | None = None,
    assessed_at: datetime | None = None,
    thresholds: RecordingQualityThresholds = QUALITY_THRESHOLDS,
) -> RecordingQualityAssessment:
    passed: list[QualityCheck] = []
    warnings: list[QualityCheck] = []
    failures: list[QualityCheck] = []

    if upload_preflight is not None:
        if upload_preflight.status == RecordingQualityLevel.unsuitable:
            _fail(
                failures,
                "upload_preflight_blocked",
                "Upload preflight",
                "The upload preflight contains a blocking recording failure.",
            )
        elif upload_preflight.status == RecordingQualityLevel.limited:
            _warn(
                warnings,
                "upload_preflight_limited",
                "Upload preflight",
                "The source recording has limitations that carry into analysis.",
            )
        else:
            _pass(passed, "upload_preflight_passed", "Upload preflight", "Upload checks passed.")

    if calibration_completed:
        _pass(
            passed,
            "calibration_available",
            "Court calibration",
            "Court calibration is available.",
        )
    else:
        _fail(
            failures,
            "calibration_missing",
            "Court calibration",
            "A valid court calibration is required for movement measurements.",
        )

    selectable = [candidate for candidate in candidates if candidate.selection_eligible]
    selected = next(
        (candidate for candidate in selectable if candidate.candidate_id == selected_candidate_id),
        None,
    )
    evidence_candidate = selected or next(
        (candidate for candidate in selectable if candidate.quality == CandidateQuality.strong),
        None,
    )
    evidence_candidate = evidence_candidate or (selectable[0] if selectable else None)

    if detected_people == 0:
        _fail(
            failures,
            "no_person_detections",
            "Player visibility",
            "No people were detected in the recording.",
        )
    elif not selectable:
        _fail(
            failures,
            "no_selectable_player_candidate",
            "Player candidates",
            "No player candidate has enough usable court evidence for selection.",
            str(detected_people),
        )
    else:
        _pass(
            passed,
            "selectable_candidates_available",
            "Player candidates",
            f"{len(selectable)} selectable player candidate(s) are available.",
            str(len(selectable)),
        )

    duration = evidence_candidate.total_observed_duration if evidence_candidate else 0.0
    visibility = evidence_candidate.in_court_observation_ratio if evidence_candidate else None
    fragments = len(evidence_candidate.source_raw_track_ids) if evidence_candidate else 0
    span = (
        evidence_candidate.last_observed_timestamp - evidence_candidate.first_observed_timestamp
        if evidence_candidate
        else 0.0
    )
    gap_seconds = max(0.0, span - duration)
    gap_ratio = gap_seconds / span if span > 0 else 0.0

    if evidence_candidate is not None:
        if evidence_candidate.quality == CandidateQuality.strong:
            _pass(
                passed,
                "candidate_quality_strong",
                "Candidate quality",
                "The best available candidate meets the strong engineering checks.",
            )
        else:
            _warn(
                warnings,
                "candidate_quality_usable",
                "Candidate quality",
                "The best available candidate is usable but does not meet every strong check.",
                evidence_candidate.quality.value,
            )

        if visibility is not None and visibility >= thresholds.minimum_visibility_ratio:
            _pass(
                passed,
                "player_visibility_passed",
                "Player visibility",
                "The candidate is visible inside the calibrated court often enough to continue.",
                f"{visibility * 100:.0f}%",
            )
        else:
            _fail(
                failures,
                "player_visibility_too_low",
                "Player visibility",
                "The candidate is not visible inside the calibrated court often enough.",
                f"{(visibility or 0) * 100:.0f}%",
            )

        if duration < thresholds.minimum_tracked_seconds:
            _fail(
                failures,
                "tracked_duration_too_short",
                "Usable tracked time",
                "There is too little continuity-safe tracked time for movement insight.",
                f"{duration:.1f} seconds",
            )
        elif duration < thresholds.excellent_tracked_seconds:
            _warn(
                warnings,
                "tracked_duration_limited",
                "Usable tracked time",
                "Usable tracked time is limited; measurements may not represent the recording.",
                f"{duration:.1f} seconds",
            )
        else:
            _pass(
                passed,
                "tracked_duration_passed",
                "Usable tracked time",
                "Usable tracked time meets the recommended threshold.",
                f"{duration:.1f} seconds",
            )

        if gap_ratio > thresholds.blocking_gap_ratio:
            _fail(
                failures,
                "tracking_gaps_excessive",
                "Tracking gaps",
                "Unobserved gaps exceed half of the selected candidate span.",
                f"{gap_ratio * 100:.0f}%",
            )
        elif gap_ratio > thresholds.warning_gap_ratio or fragments > 1:
            _warn(
                warnings,
                "tracking_gaps_present",
                "Tracking gaps",
                "The candidate contains fragments or unobserved gaps; Court4 does not bridge them.",
                f"{gap_seconds:.1f} seconds",
            )
        else:
            _pass(passed, "tracking_continuity_passed", "Tracking gaps", "Tracking is continuous.")

        if fragments > thresholds.maximum_fragments:
            _fail(
                failures,
                "too_many_track_fragments",
                "Track fragments",
                "The candidate contains too many fragments for dependable interpretation.",
                str(fragments),
            )

    excellent = (
        upload_preflight is not None
        and upload_preflight.status == RecordingQualityLevel.excellent
        and evidence_candidate is not None
        and evidence_candidate.quality == CandidateQuality.strong
        and duration >= thresholds.excellent_tracked_seconds
        and (visibility or 0) >= thresholds.excellent_visibility_ratio
        and gap_ratio <= thresholds.warning_gap_ratio
        and fragments == 1
    )
    return RecordingQualityAssessment(
        stage=PreflightStage.analysis,
        status=_level(failures, warnings, excellent=excellent),
        passed_checks=passed,
        warnings=warnings,
        blocking_failures=failures,
        reason_codes=_reason_codes(warnings, failures),
        guidance=_guidance(warnings, failures),
        analysis_signals=AnalysisQualitySignals(
            court_detection_status=court_detection_status,
            court_detection_confidence=court_detection_confidence,
            calibration_completed=calibration_completed,
            detected_people=detected_people,
            selectable_candidate_count=len(selectable),
            candidate_quality=evidence_candidate.quality.value if evidence_candidate else None,
            player_visibility_ratio=visibility,
            tracked_duration_seconds=duration,
            unobserved_gap_seconds=gap_seconds,
            tracking_gap_ratio=min(1.0, gap_ratio),
            fragment_count=fragments,
        ),
        assessed_at=assessed_at or datetime.now(tz=UTC),
    )


def _level(
    failures: Sequence[QualityCheck],
    warnings: Sequence[QualityCheck],
    *,
    excellent: bool,
) -> RecordingQualityLevel:
    if failures:
        return RecordingQualityLevel.unsuitable
    if warnings:
        return RecordingQualityLevel.limited
    return RecordingQualityLevel.excellent if excellent else RecordingQualityLevel.good


def _pass(
    target: list[QualityCheck],
    code: str,
    label: str,
    message: str,
    value: str | None = None,
) -> None:
    target.append(
        QualityCheck(
            code=code,
            label=label,
            status=QualityCheckStatus.passed,
            message=message,
            measured_value=value,
        )
    )


def _warn(
    target: list[QualityCheck],
    code: str,
    label: str,
    message: str,
    value: str | None = None,
) -> None:
    target.append(
        QualityCheck(
            code=code,
            label=label,
            status=QualityCheckStatus.warning,
            message=message,
            measured_value=value,
        )
    )


def _fail(
    target: list[QualityCheck],
    code: str,
    label: str,
    message: str,
    value: str | None = None,
) -> None:
    target.append(
        QualityCheck(
            code=code,
            label=label,
            status=QualityCheckStatus.failed,
            message=message,
            measured_value=value,
        )
    )


def _reason_codes(
    warnings: Sequence[QualityCheck],
    failures: Sequence[QualityCheck],
) -> list[str]:
    return [check.code for check in [*failures, *warnings]]


def _guidance(
    warnings: Sequence[QualityCheck],
    failures: Sequence[QualityCheck],
) -> list[str]:
    codes = {check.code for check in [*warnings, *failures]}
    guidance: list[str] = []
    if codes & {"vertical_orientation", "upload_preflight_limited"}:
        guidance.append("Use landscape orientation with the camera behind the baseline.")
    if codes & {"resolution_too_low", "resolution_below_minimum"}:
        guidance.append("Record at 720p minimum; 1080p is recommended.")
    if codes & {"fps_too_low", "fps_below_minimum"}:
        guidance.append("Record at 24 FPS minimum; 30 FPS is recommended.")
    if codes & {"recording_too_short", "tracked_duration_too_short", "tracked_duration_limited"}:
        guidance.append("Capture a longer continuous section of gameplay.")
    if codes & {
        "calibration_missing",
        "no_person_detections",
        "no_selectable_player_candidate",
        "player_visibility_too_low",
        "tracking_gaps_excessive",
        "tracking_gaps_present",
    }:
        guidance.extend(
            [
                "Keep the full court visible and the camera stable.",
                "Place the camera behind or diagonally behind the baseline.",
            ]
        )
    return list(dict.fromkeys(guidance))
