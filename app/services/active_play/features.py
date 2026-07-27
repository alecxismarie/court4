import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.schemas.active_play import (
    ActivePlayCoverage,
    ActivePlayLineage,
    ActivePlayReasonCode,
    ActivePlaySignals,
    CandidateContinuityQuality,
    MotionFeatureWindow,
    TrackingGapSeverity,
    VisibilityQuality,
)
from app.schemas.player_candidates import (
    CandidateQuality,
    CandidateReviewStatus,
    PlayerCandidate,
    PlayerCandidateCollection,
)
from app.schemas.player_tracking import PlayerObservation, PlayerTrackingReport
from app.services.active_play.policy import ACTIVE_PLAY_POLICY, ActivePlayPolicy
from app.sports.pickleball.geometry import REGULATION_COURT


@dataclass(frozen=True)
class SmoothedTrackPoint:
    timestamp_seconds: float
    track_id: int
    x: float
    y: float


@dataclass(frozen=True)
class VelocitySample:
    start_seconds: float
    end_seconds: float
    track_id: int
    speed_feet_per_second: float
    velocity_x: float
    velocity_y: float


@dataclass(frozen=True)
class CandidateMotionStream:
    candidate: PlayerCandidate
    observations: tuple[PlayerObservation, ...]
    observed_intervals: tuple[tuple[float, float], ...]
    velocity_samples: tuple[VelocitySample, ...]
    speed_change_samples: tuple[tuple[float, float], ...]
    direction_change_times: tuple[float, ...]


def smooth_track_positions(
    observations: Sequence[PlayerObservation],
    *,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> tuple[SmoothedTrackPoint, ...]:
    """Smooth court positions without crossing raw-track or observation-gap boundaries."""

    valid = sorted(
        (item for item in observations if item.inside_court),
        key=lambda item: (item.track_id, item.timestamp_seconds, item.frame_index),
    )
    segments: list[list[PlayerObservation]] = []
    for observation in valid:
        if (
            not segments
            or observation.track_id != segments[-1][-1].track_id
            or observation.timestamp_seconds - segments[-1][-1].timestamp_seconds
            > policy.maximum_observed_gap_seconds
        ):
            segments.append([observation])
        else:
            segments[-1].append(observation)

    half_window = policy.smoothing_seconds / 2.0
    smoothed: list[SmoothedTrackPoint] = []
    for segment in segments:
        for center in segment:
            neighbors = [
                item
                for item in segment
                if abs(item.timestamp_seconds - center.timestamp_seconds) <= half_window
            ]
            smoothed.append(
                SmoothedTrackPoint(
                    timestamp_seconds=center.timestamp_seconds,
                    track_id=center.track_id,
                    x=sum(item.court_position[0] for item in neighbors) / len(neighbors),
                    y=sum(item.court_position[1] for item in neighbors) / len(neighbors),
                )
            )
    return tuple(sorted(smoothed, key=lambda item: (item.timestamp_seconds, item.track_id)))


def calculate_velocity_samples(
    points: Sequence[SmoothedTrackPoint],
    *,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> tuple[VelocitySample, ...]:
    samples: list[VelocitySample] = []
    ordered = sorted(points, key=lambda item: (item.track_id, item.timestamp_seconds))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        delta = current.timestamp_seconds - previous.timestamp_seconds
        if current.track_id != previous.track_id:
            continue
        if (
            delta < policy.minimum_velocity_delta_seconds
            or delta > policy.maximum_observed_gap_seconds
        ):
            continue
        velocity_x = (current.x - previous.x) / delta
        velocity_y = (current.y - previous.y) / delta
        samples.append(
            VelocitySample(
                start_seconds=previous.timestamp_seconds,
                end_seconds=current.timestamp_seconds,
                track_id=current.track_id,
                speed_feet_per_second=math.hypot(velocity_x, velocity_y),
                velocity_x=velocity_x,
                velocity_y=velocity_y,
            )
        )
    return tuple(sorted(samples, key=lambda item: (item.end_seconds, item.track_id)))


def calculate_speed_change_samples(
    samples: Sequence[VelocitySample],
    *,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> tuple[tuple[float, float], ...]:
    changes: list[tuple[float, float]] = []
    ordered = sorted(samples, key=lambda item: (item.track_id, item.end_seconds))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        delta = current.end_seconds - previous.end_seconds
        if current.track_id != previous.track_id:
            continue
        if (
            delta < policy.minimum_velocity_delta_seconds
            or delta > policy.maximum_observed_gap_seconds
        ):
            continue
        changes.append(
            (
                current.end_seconds,
                abs(current.speed_feet_per_second - previous.speed_feet_per_second) / delta,
            )
        )
    return tuple(sorted(changes))


def calculate_direction_change_times(
    samples: Sequence[VelocitySample],
    *,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> tuple[float, ...]:
    changes: list[float] = []
    ordered = sorted(samples, key=lambda item: (item.track_id, item.end_seconds))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current.track_id != previous.track_id:
            continue
        if (
            previous.speed_feet_per_second < policy.minimum_direction_speed_feet_per_second
            or current.speed_feet_per_second < policy.minimum_direction_speed_feet_per_second
        ):
            continue
        denominator = previous.speed_feet_per_second * current.speed_feet_per_second
        cosine = (
            previous.velocity_x * current.velocity_x + previous.velocity_y * current.velocity_y
        ) / denominator
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
        if angle >= policy.direction_change_degrees:
            changes.append(current.end_seconds)
    return tuple(sorted(changes))


def build_motion_feature_windows(
    *,
    tracking_report: PlayerTrackingReport,
    candidates: PlayerCandidateCollection,
    observations: Sequence[PlayerObservation],
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> list[MotionFeatureWindow]:
    streams = _candidate_streams(candidates, observations, policy=policy)
    source_duration = tracking_report.performance.source_duration_seconds
    if source_duration <= 0:
        return []

    windows: list[MotionFeatureWindow] = []
    start = 0.0
    while start < source_duration - 1e-9:
        end = min(source_duration, start + policy.window_seconds)
        windows.append(_window_features(start, end, streams, policy=policy))
        start = end
    return windows


def _candidate_streams(
    collection: PlayerCandidateCollection,
    observations: Sequence[PlayerObservation],
    *,
    policy: ActivePlayPolicy,
) -> list[CandidateMotionStream]:
    all_candidates = [
        candidate
        for candidate in [*collection.candidates, *collection.excluded_candidates]
        if candidate.review_status != CandidateReviewStatus.rejected
        and candidate.quality != CandidateQuality.rejected
    ]
    observations_by_track: dict[int, list[PlayerObservation]] = {}
    for observation in observations:
        observations_by_track.setdefault(observation.track_id, []).append(observation)

    streams: list[CandidateMotionStream] = []
    for candidate in sorted(all_candidates, key=lambda item: item.candidate_id):
        candidate_observations = _deduplicate_observations(
            observation
            for track_id in candidate.source_raw_track_ids
            for observation in observations_by_track.get(track_id, [])
        )
        points = smooth_track_positions(candidate_observations, policy=policy)
        velocities = calculate_velocity_samples(points, policy=policy)
        streams.append(
            CandidateMotionStream(
                candidate=candidate,
                observations=tuple(candidate_observations),
                observed_intervals=_observed_intervals(candidate_observations, policy=policy),
                velocity_samples=velocities,
                speed_change_samples=calculate_speed_change_samples(velocities, policy=policy),
                direction_change_times=calculate_direction_change_times(
                    velocities,
                    policy=policy,
                ),
            )
        )
    return streams


def _window_features(
    start: float,
    end: float,
    streams: Sequence[CandidateMotionStream],
    *,
    policy: ActivePlayPolicy,
) -> MotionFeatureWindow:
    duration = end - start
    visible = [
        stream
        for stream in streams
        if any(start <= item.timestamp_seconds < end for item in stream.observations)
    ]
    clipped_intervals = {
        stream.candidate.candidate_id: _clip_intervals(
            stream.observed_intervals,
            start,
            end,
        )
        for stream in visible
    }
    reliable = [
        stream
        for stream in visible
        if _base_candidate_reliable(stream.candidate, policy=policy)
        and _interval_duration(clipped_intervals[stream.candidate.candidate_id]) / duration
        >= policy.minimum_player_window_coverage_ratio
    ]
    reliable_ids = {stream.candidate.candidate_id for stream in reliable}
    reliable_intervals = {
        candidate_id: intervals
        for candidate_id, intervals in clipped_intervals.items()
        if candidate_id in reliable_ids
    }
    observed_seconds = _duration_with_minimum_streams(
        reliable_intervals,
        required=policy.minimum_reliable_players,
    )
    observed_ratio = observed_seconds / duration if duration > 0 else 0.0

    weighted_speeds: list[tuple[float, float]] = []
    weighted_changes: list[float] = []
    direction_changes = 0
    moving_intervals: dict[str, tuple[tuple[float, float], ...]] = {}
    stationary_by_player: list[float] = []
    low_movement_kitchen_player_count = 0
    for stream in reliable:
        clipped_velocity = [
            (sample, overlap)
            for sample in stream.velocity_samples
            if (
                overlap := _overlap_duration(
                    sample.start_seconds,
                    sample.end_seconds,
                    start,
                    end,
                )
            )
            > 0
        ]
        weighted_speeds.extend(
            (sample.speed_feet_per_second, overlap) for sample, overlap in clipped_velocity
        )
        weighted_changes.extend(
            value for timestamp, value in stream.speed_change_samples if start <= timestamp < end
        )
        direction_changes += sum(
            start <= timestamp < end for timestamp in stream.direction_change_times
        )
        moving_intervals[stream.candidate.candidate_id] = tuple(
            (max(start, sample.start_seconds), min(end, sample.end_seconds))
            for sample, overlap in clipped_velocity
            if sample.speed_feet_per_second >= policy.moving_speed_feet_per_second and overlap > 0
        )
        stationary_seconds = sum(
            overlap
            for sample, overlap in clipped_velocity
            if sample.speed_feet_per_second <= policy.stationary_speed_feet_per_second
        )
        stationary_by_player.append(stationary_seconds)
        window_observations = [
            observation
            for observation in stream.observations
            if observation.inside_court and start <= observation.timestamp_seconds < end
        ]
        kitchen_observations = sum(
            REGULATION_COURT.near_kitchen_y_feet
            <= observation.court_position[1]
            <= REGULATION_COURT.far_kitchen_y_feet
            for observation in window_observations
        )
        if (
            stationary_seconds >= duration * policy.minimum_player_window_coverage_ratio
            and window_observations
            and kitchen_observations / len(window_observations) >= 0.5
        ):
            low_movement_kitchen_player_count += 1

    speed_duration = sum(weight for _, weight in weighted_speeds)
    smoothed_speed = (
        sum(speed * weight for speed, weight in weighted_speeds) / speed_duration
        if speed_duration > 0
        else 0.0
    )
    speed_change = sum(weighted_changes) / len(weighted_changes) if weighted_changes else 0.0
    movement_intensity = min(
        1.0,
        smoothed_speed / policy.active_reference_speed_feet_per_second,
    )
    reliable_observed_total = sum(
        _interval_duration(intervals) for intervals in reliable_intervals.values()
    )
    direction_frequency = (
        direction_changes / reliable_observed_total if reliable_observed_total > 0 else 0.0
    )
    moving_player_count = sum(
        _interval_duration(intervals) >= policy.minimum_moving_seconds
        for intervals in moving_intervals.values()
    )
    simultaneous_seconds = _duration_with_minimum_streams(moving_intervals, required=2)
    gap_ratio = 1.0 - observed_ratio
    gap_severity = _gap_severity(gap_ratio, policy=policy)
    continuity = _continuity_quality(reliable, gap_severity)
    visibility = _visibility_quality(
        reliable_player_count=len(reliable),
        observed_ratio=observed_ratio,
        policy=policy,
    )
    evidence_reasons = _feature_reason_codes(
        visible_count=len(visible),
        reliable_count=len(reliable),
        observed_ratio=observed_ratio,
        gap_severity=gap_severity,
        continuity=continuity,
        policy=policy,
    )
    lineage_streams = reliable or visible
    return MotionFeatureWindow(
        start_seconds=start,
        end_seconds=end,
        coverage=ActivePlayCoverage(
            observed_seconds=observed_seconds,
            window_seconds=duration,
            observed_ratio=observed_ratio,
            visible_player_count=len(visible),
            reliable_player_count=len(reliable),
        ),
        signals=ActivePlaySignals(
            smoothed_speed_feet_per_second=smoothed_speed,
            speed_change_feet_per_second_squared=speed_change,
            movement_intensity=movement_intensity,
            direction_changes_per_second=direction_frequency,
            mean_stationary_seconds_per_player=(
                sum(stationary_by_player) / len(stationary_by_player)
                if stationary_by_player
                else 0.0
            ),
            low_movement_kitchen_player_count=low_movement_kitchen_player_count,
            moving_player_count=moving_player_count,
            simultaneous_movement=(
                simultaneous_seconds >= policy.minimum_simultaneous_movement_seconds
            ),
            simultaneous_movement_seconds=simultaneous_seconds,
            visibility_quality=visibility,
            tracking_gap_severity=gap_severity,
            candidate_continuity=continuity,
        ),
        evidence_reason_codes=evidence_reasons,
        lineage=ActivePlayLineage(
            candidate_ids=sorted(stream.candidate.candidate_id for stream in lineage_streams),
            source_raw_track_ids=sorted(
                {
                    track_id
                    for stream in lineage_streams
                    for track_id in stream.candidate.source_raw_track_ids
                }
            ),
        ),
        policy_version=policy.version,
    )


def _base_candidate_reliable(
    candidate: PlayerCandidate,
    *,
    policy: ActivePlayPolicy,
) -> bool:
    return (
        candidate.quality in {CandidateQuality.strong, CandidateQuality.usable}
        and candidate.in_court_observation_ratio >= policy.minimum_candidate_in_court_ratio
        and candidate.total_observed_duration >= policy.minimum_candidate_duration_seconds
        and len(candidate.source_raw_track_ids) <= policy.maximum_reliable_candidate_fragments
    )


def _deduplicate_observations(
    observations: Iterable[PlayerObservation],
) -> list[PlayerObservation]:
    by_frame: dict[int, PlayerObservation] = {}
    for observation in observations:
        current = by_frame.get(observation.frame_index)
        if current is None or (observation.confidence, -observation.track_id) > (
            current.confidence,
            -current.track_id,
        ):
            by_frame[observation.frame_index] = observation
    return sorted(
        by_frame.values(),
        key=lambda item: (item.timestamp_seconds, item.frame_index, item.track_id),
    )


def _observed_intervals(
    observations: Sequence[PlayerObservation],
    *,
    policy: ActivePlayPolicy,
) -> tuple[tuple[float, float], ...]:
    inside = sorted(
        (item for item in observations if item.inside_court),
        key=lambda item: (item.timestamp_seconds, item.frame_index),
    )
    intervals: list[tuple[float, float]] = []
    for previous, current in zip(inside, inside[1:], strict=False):
        gap = current.timestamp_seconds - previous.timestamp_seconds
        if previous.track_id != current.track_id:
            continue
        if 0 < gap <= policy.maximum_observed_gap_seconds:
            intervals.append((previous.timestamp_seconds, current.timestamp_seconds))
    return _merge_numeric_intervals(intervals)


def _clip_intervals(
    intervals: Sequence[tuple[float, float]],
    start: float,
    end: float,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (max(start, first), min(end, last))
        for first, last in intervals
        if min(end, last) > max(start, first)
    )


def _merge_numeric_intervals(
    intervals: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return tuple(merged)


def _interval_duration(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def _duration_with_minimum_streams(
    intervals_by_stream: Mapping[str, Sequence[tuple[float, float]]],
    *,
    required: int,
) -> float:
    events: list[tuple[float, int]] = []
    for intervals in intervals_by_stream.values():
        for start, end in intervals:
            events.append((start, 1))
            events.append((end, -1))
    if not events:
        return 0.0
    total = 0.0
    count = 0
    previous = events[0][0]
    for timestamp, delta in sorted(events, key=lambda item: (item[0], item[1])):
        if count >= required:
            total += timestamp - previous
        count += delta
        previous = timestamp
    return total


def _overlap_duration(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> float:
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


def _gap_severity(gap_ratio: float, *, policy: ActivePlayPolicy) -> TrackingGapSeverity:
    if gap_ratio >= policy.severe_gap_ratio:
        return TrackingGapSeverity.severe
    if gap_ratio >= policy.minor_gap_ratio:
        return TrackingGapSeverity.minor
    return TrackingGapSeverity.none


def _continuity_quality(
    reliable: Sequence[CandidateMotionStream],
    gap_severity: TrackingGapSeverity,
) -> CandidateContinuityQuality:
    if not reliable:
        return CandidateContinuityQuality.not_available
    if gap_severity == TrackingGapSeverity.severe:
        return CandidateContinuityQuality.poor
    if gap_severity == TrackingGapSeverity.none and all(
        len(stream.candidate.source_raw_track_ids) == 1 for stream in reliable
    ):
        return CandidateContinuityQuality.strong
    return CandidateContinuityQuality.limited


def _visibility_quality(
    *,
    reliable_player_count: int,
    observed_ratio: float,
    policy: ActivePlayPolicy,
) -> VisibilityQuality:
    if reliable_player_count < policy.minimum_reliable_players:
        return VisibilityQuality.not_available
    if observed_ratio >= policy.strong_window_coverage_ratio:
        return VisibilityQuality.high
    if observed_ratio >= policy.minimum_window_coverage_ratio:
        return VisibilityQuality.moderate
    return VisibilityQuality.low


def _feature_reason_codes(
    *,
    visible_count: int,
    reliable_count: int,
    observed_ratio: float,
    gap_severity: TrackingGapSeverity,
    continuity: CandidateContinuityQuality,
    policy: ActivePlayPolicy,
) -> list[ActivePlayReasonCode]:
    reasons: list[ActivePlayReasonCode] = []
    if visible_count == 0:
        reasons.append(ActivePlayReasonCode.no_observations)
    if reliable_count < policy.minimum_reliable_players:
        reasons.append(ActivePlayReasonCode.insufficient_reliable_players)
        if reliable_count == 1:
            reasons.append(ActivePlayReasonCode.one_player_only)
    if observed_ratio >= policy.minimum_window_coverage_ratio:
        reasons.append(ActivePlayReasonCode.sufficient_tracked_coverage)
    else:
        reasons.append(ActivePlayReasonCode.insufficient_tracked_coverage)
    if gap_severity != TrackingGapSeverity.none:
        reasons.append(ActivePlayReasonCode.tracking_gap)
    if gap_severity == TrackingGapSeverity.severe:
        reasons.append(ActivePlayReasonCode.severe_tracking_gaps)
    if continuity in {CandidateContinuityQuality.limited, CandidateContinuityQuality.poor}:
        reasons.append(ActivePlayReasonCode.fragmented_candidates)
    return sorted(set(reasons), key=lambda item: item.value)
