from collections import Counter
from collections.abc import Sequence

from app.schemas.active_play import (
    ActivePlayConfidence,
    ActivePlayCoverage,
    ActivePlayInterval,
    ActivePlayLineage,
    ActivePlayReasonCode,
    ActivePlaySignals,
    ActivePlayState,
    ActivePlayWindow,
    CandidateContinuityQuality,
    MotionFeatureWindow,
    TrackingGapSeverity,
    VisibilityQuality,
)
from app.schemas.recording_quality import RecordingQualityAssessment, RecordingQualityLevel
from app.services.active_play.policy import ACTIVE_PLAY_POLICY, ActivePlayPolicy

BASE_LIMITATIONS = [
    "Ball movement was not observed.",
    "Warm-up and ball retrieval may resemble likely active play.",
    "Slow live play may be misclassified.",
    "States are unvalidated shadow-mode estimates, not rally or point detection.",
]

UNKNOWN_LIMITATION = "Weak or incomplete tracking evidence prevented a classification."


def classify_motion_windows(
    features: Sequence[MotionFeatureWindow],
    *,
    source_duration_seconds: float,
    recording_quality: RecordingQualityAssessment | None,
    source_artifacts_current: bool = True,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> list[ActivePlayWindow]:
    return [
        _classify_window(
            feature,
            source_duration_seconds=source_duration_seconds,
            recording_quality=recording_quality,
            source_artifacts_current=source_artifacts_current,
            policy=policy,
        )
        for feature in features
    ]


def merge_active_play_windows(
    windows: Sequence[ActivePlayWindow],
    *,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> list[ActivePlayInterval]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda item: (item.start_seconds, item.end_seconds))
    intervals: list[ActivePlayInterval] = [_interval_from_window(ordered[0])]
    for window in ordered[1:]:
        current = intervals[-1]
        discontinuity = window.start_seconds - current.end_seconds
        if (
            window.state == current.state
            and abs(discontinuity) <= policy.maximum_interval_discontinuity_seconds
        ):
            intervals[-1] = _merge_interval_and_window(current, window)
        else:
            intervals.append(_interval_from_window(window))
    return intervals


def confidence_distribution(
    windows: Sequence[ActivePlayWindow],
) -> dict[ActivePlayConfidence, int]:
    counts = Counter(window.confidence for window in windows)
    return {level: counts[level] for level in ActivePlayConfidence}


def reason_distribution(
    windows: Sequence[ActivePlayWindow],
) -> dict[ActivePlayReasonCode, int]:
    counts = Counter(reason for window in windows for reason in window.reason_codes)
    return {reason: counts[reason] for reason in ActivePlayReasonCode if counts[reason]}


def _classify_window(
    feature: MotionFeatureWindow,
    *,
    source_duration_seconds: float,
    recording_quality: RecordingQualityAssessment | None,
    source_artifacts_current: bool,
    policy: ActivePlayPolicy,
) -> ActivePlayWindow:
    reasons = list(feature.evidence_reason_codes)
    state = ActivePlayState.unknown
    confidence = ActivePlayConfidence.not_available

    unsuitable = (
        recording_quality is not None
        and recording_quality.status == RecordingQualityLevel.unsuitable
    )
    short_context = (
        source_duration_seconds < policy.minimum_context_seconds
        or feature.coverage.window_seconds < policy.window_seconds - 1e-6
    )
    inadequate_players = feature.coverage.reliable_player_count < policy.minimum_reliable_players
    inadequate_coverage = feature.coverage.observed_ratio < policy.minimum_window_coverage_ratio
    severe_gaps = feature.signals.tracking_gap_severity == TrackingGapSeverity.severe
    stale_source = not source_artifacts_current

    if unsuitable:
        reasons.append(ActivePlayReasonCode.unsuitable_recording)
    if short_context:
        reasons.append(ActivePlayReasonCode.short_context)
    if stale_source:
        reasons.append(ActivePlayReasonCode.stale_source_artifact)

    if not any(
        [
            unsuitable,
            short_context,
            inadequate_players,
            inadequate_coverage,
            severe_gaps,
            stale_source,
        ]
    ):
        active_evidence = (
            feature.signals.moving_player_count >= policy.minimum_reliable_players
            and feature.signals.simultaneous_movement
            and feature.signals.movement_intensity >= policy.active_intensity_threshold
        )
        idle_evidence = (
            feature.signals.moving_player_count == 0
            and feature.signals.low_movement_kitchen_player_count == 0
            and feature.signals.movement_intensity <= policy.idle_intensity_threshold
            and feature.signals.mean_stationary_seconds_per_player
            >= feature.coverage.window_seconds * policy.minimum_player_window_coverage_ratio
        )
        if active_evidence:
            state = ActivePlayState.likely_active
            reasons.extend(
                [
                    ActivePlayReasonCode.sustained_multi_player_movement,
                    ActivePlayReasonCode.simultaneous_movement,
                ]
            )
            if (
                feature.signals.direction_changes_per_second
                >= policy.meaningful_direction_changes_per_second
            ):
                reasons.append(ActivePlayReasonCode.meaningful_direction_changes)
            if feature.signals.moving_player_count < feature.coverage.reliable_player_count:
                reasons.append(ActivePlayReasonCode.stationary_player_with_active_peers)
            confidence = _supported_confidence(feature, policy=policy)
        elif idle_evidence:
            state = ActivePlayState.likely_idle
            reasons.extend(
                [
                    ActivePlayReasonCode.sustained_low_movement,
                    ActivePlayReasonCode.stable_low_activity,
                ]
            )
            confidence = _supported_confidence(feature, policy=policy)
        else:
            if feature.signals.low_movement_kitchen_player_count > 0:
                reasons.append(ActivePlayReasonCode.kitchen_low_movement_safeguard)
            reasons.append(ActivePlayReasonCode.conflicting_evidence)
            confidence = ActivePlayConfidence.low

    limitations = list(BASE_LIMITATIONS)
    if state == ActivePlayState.unknown:
        limitations.append(UNKNOWN_LIMITATION)
    return ActivePlayWindow(
        start_seconds=feature.start_seconds,
        end_seconds=feature.end_seconds,
        state=state,
        confidence=confidence,
        coverage=feature.coverage,
        signals=feature.signals,
        reason_codes=sorted(set(reasons), key=lambda item: item.value),
        limitations=limitations,
        lineage=feature.lineage,
        policy_version=policy.version,
    )


def _supported_confidence(
    feature: MotionFeatureWindow,
    *,
    policy: ActivePlayPolicy,
) -> ActivePlayConfidence:
    if (
        feature.coverage.observed_ratio >= policy.strong_window_coverage_ratio
        and feature.signals.candidate_continuity == CandidateContinuityQuality.strong
        and feature.signals.visibility_quality == VisibilityQuality.high
    ):
        # Shadow v1 is deliberately capped at MODERATE until validation exists.
        return ActivePlayConfidence.moderate
    return ActivePlayConfidence.low


def _interval_from_window(window: ActivePlayWindow) -> ActivePlayInterval:
    return ActivePlayInterval(
        **window.model_dump(),
        source_window_count=1,
    )


def _merge_interval_and_window(
    interval: ActivePlayInterval,
    window: ActivePlayWindow,
) -> ActivePlayInterval:
    first_duration = interval.coverage.window_seconds
    second_duration = window.coverage.window_seconds
    total_duration = first_duration + second_duration
    observed_seconds = interval.coverage.observed_seconds + window.coverage.observed_seconds
    return ActivePlayInterval(
        start_seconds=interval.start_seconds,
        end_seconds=window.end_seconds,
        state=interval.state,
        confidence=_weaker_confidence(interval.confidence, window.confidence),
        coverage=ActivePlayCoverage(
            observed_seconds=observed_seconds,
            window_seconds=total_duration,
            observed_ratio=observed_seconds / total_duration,
            visible_player_count=min(
                interval.coverage.visible_player_count,
                window.coverage.visible_player_count,
            ),
            reliable_player_count=min(
                interval.coverage.reliable_player_count,
                window.coverage.reliable_player_count,
            ),
        ),
        signals=ActivePlaySignals(
            smoothed_speed_feet_per_second=_weighted_average(
                interval.signals.smoothed_speed_feet_per_second,
                first_duration,
                window.signals.smoothed_speed_feet_per_second,
                second_duration,
            ),
            speed_change_feet_per_second_squared=_weighted_average(
                interval.signals.speed_change_feet_per_second_squared,
                first_duration,
                window.signals.speed_change_feet_per_second_squared,
                second_duration,
            ),
            movement_intensity=_weighted_average(
                interval.signals.movement_intensity,
                first_duration,
                window.signals.movement_intensity,
                second_duration,
            ),
            direction_changes_per_second=_weighted_average(
                interval.signals.direction_changes_per_second,
                first_duration,
                window.signals.direction_changes_per_second,
                second_duration,
            ),
            mean_stationary_seconds_per_player=(
                interval.signals.mean_stationary_seconds_per_player
                + window.signals.mean_stationary_seconds_per_player
            ),
            low_movement_kitchen_player_count=max(
                interval.signals.low_movement_kitchen_player_count,
                window.signals.low_movement_kitchen_player_count,
            ),
            moving_player_count=min(
                interval.signals.moving_player_count,
                window.signals.moving_player_count,
            ),
            simultaneous_movement=(
                interval.signals.simultaneous_movement and window.signals.simultaneous_movement
            ),
            simultaneous_movement_seconds=(
                interval.signals.simultaneous_movement_seconds
                + window.signals.simultaneous_movement_seconds
            ),
            visibility_quality=_weaker_visibility(
                interval.signals.visibility_quality,
                window.signals.visibility_quality,
            ),
            tracking_gap_severity=_worse_gap(
                interval.signals.tracking_gap_severity,
                window.signals.tracking_gap_severity,
            ),
            candidate_continuity=_weaker_continuity(
                interval.signals.candidate_continuity,
                window.signals.candidate_continuity,
            ),
        ),
        reason_codes=sorted(
            {*interval.reason_codes, *window.reason_codes},
            key=lambda item: item.value,
        ),
        limitations=sorted({*interval.limitations, *window.limitations}),
        lineage=ActivePlayLineage(
            candidate_ids=sorted({*interval.lineage.candidate_ids, *window.lineage.candidate_ids}),
            source_raw_track_ids=sorted(
                {
                    *interval.lineage.source_raw_track_ids,
                    *window.lineage.source_raw_track_ids,
                }
            ),
        ),
        policy_version=interval.policy_version,
        source_window_count=interval.source_window_count + 1,
    )


def _weighted_average(
    first: float,
    first_weight: float,
    second: float,
    second_weight: float,
) -> float:
    return (first * first_weight + second * second_weight) / (first_weight + second_weight)


def _weaker_confidence(
    first: ActivePlayConfidence,
    second: ActivePlayConfidence,
) -> ActivePlayConfidence:
    rank = {
        ActivePlayConfidence.not_available: 0,
        ActivePlayConfidence.low: 1,
        ActivePlayConfidence.moderate: 2,
        ActivePlayConfidence.high: 3,
    }
    return min((first, second), key=lambda item: rank[item])


def _weaker_visibility(
    first: VisibilityQuality,
    second: VisibilityQuality,
) -> VisibilityQuality:
    rank = {
        VisibilityQuality.not_available: 0,
        VisibilityQuality.low: 1,
        VisibilityQuality.moderate: 2,
        VisibilityQuality.high: 3,
    }
    return min((first, second), key=lambda item: rank[item])


def _worse_gap(
    first: TrackingGapSeverity,
    second: TrackingGapSeverity,
) -> TrackingGapSeverity:
    rank = {
        TrackingGapSeverity.none: 0,
        TrackingGapSeverity.minor: 1,
        TrackingGapSeverity.severe: 2,
    }
    return max((first, second), key=lambda item: rank[item])


def _weaker_continuity(
    first: CandidateContinuityQuality,
    second: CandidateContinuityQuality,
) -> CandidateContinuityQuality:
    rank = {
        CandidateContinuityQuality.not_available: 0,
        CandidateContinuityQuality.poor: 1,
        CandidateContinuityQuality.limited: 2,
        CandidateContinuityQuality.strong: 3,
    }
    return min((first, second), key=lambda item: rank[item])
