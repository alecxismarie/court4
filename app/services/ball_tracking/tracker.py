from __future__ import annotations

import math
from dataclasses import dataclass

from app.schemas.ball_tracking import (
    BallCandidateDisposition,
    BallFrameDetection,
    BallObservation,
    BallObservationState,
    BallTrackEvent,
    BallTrackEventType,
)


@dataclass(frozen=True)
class TemporalBallTrackerConfig:
    base_association_distance_pixels: float = 42.0
    per_gap_distance_pixels: float = 24.0
    velocity_tolerance_multiplier: float = 2.5
    max_interpolation_gap_frames: int = 4
    restart_after_gap_frames: int = 8

    def __post_init__(self) -> None:
        if self.base_association_distance_pixels <= 0:
            raise ValueError("Tracker association distance must be positive.")
        if self.per_gap_distance_pixels < 0 or self.velocity_tolerance_multiplier < 0:
            raise ValueError("Tracker gap and velocity tolerances cannot be negative.")
        if self.max_interpolation_gap_frames < 0:
            raise ValueError("Tracker interpolation gap cannot be negative.")
        if self.restart_after_gap_frames < self.max_interpolation_gap_frames:
            raise ValueError("Tracker restart gap cannot be shorter than interpolation policy.")

    def as_dict(self) -> dict[str, float | int]:
        return {
            "base_association_distance_pixels": self.base_association_distance_pixels,
            "per_gap_distance_pixels": self.per_gap_distance_pixels,
            "velocity_tolerance_multiplier": self.velocity_tolerance_multiplier,
            "max_interpolation_gap_frames": self.max_interpolation_gap_frames,
            "restart_after_gap_frames": self.restart_after_gap_frames,
        }


@dataclass(frozen=True)
class TemporalBallTrackResult:
    observations: tuple[BallObservation, ...]
    events: tuple[BallTrackEvent, ...]
    gap_lengths: tuple[int, ...]
    reacquisition_count: int
    segment_count: int
    impossible_motion_count: int


class TemporalBallTracker:
    """Small, auditable image-space tracker with explicitly bounded interpolation."""

    name = "bounded_nearest_trajectory_tracker"
    version = "1.0.0"
    interpolation_policy_version = "linear-short-gap-v1"

    def __init__(self, config: TemporalBallTrackerConfig | None = None) -> None:
        self.config = config or TemporalBallTrackerConfig()

    def reconstruct(
        self,
        detections: tuple[BallFrameDetection, ...],
        *,
        detector_name: str | None = None,
        detector_version: str,
        model_identifier: str | None = None,
        model_digest: str | None,
        source_video_checksum: str | None = None,
        configuration_fingerprint: str | None = None,
    ) -> TemporalBallTrackResult:
        observations: list[BallObservation] = []
        events: list[BallTrackEvent] = []
        gaps: list[int] = []
        last_observed: BallObservation | None = None
        prior_observed: BallObservation | None = None
        pending_gap = 0
        segment_number = 0
        impossible_motion_count = 0
        reacquisition_count = 0

        for detection in detections:
            candidate = next(
                (
                    item
                    for item in detection.candidates
                    if item.disposition == BallCandidateDisposition.accepted
                ),
                None,
            )
            if candidate is None:
                if last_observed is not None:
                    pending_gap += 1
                    if pending_gap == 1:
                        events.append(
                            BallTrackEvent(
                                event_type=BallTrackEventType.gap_started,
                                frame_index=detection.frame_index,
                                track_segment_id=last_observed.track_segment_id,
                            )
                        )
                continue

            if last_observed is None or pending_gap > self.config.restart_after_gap_frames:
                if last_observed is not None:
                    gaps.append(pending_gap)
                    events.append(
                        BallTrackEvent(
                            event_type=BallTrackEventType.segment_ended,
                            frame_index=last_observed.frame_index,
                            track_segment_id=last_observed.track_segment_id,
                            gap_length_frames=pending_gap,
                            detail="association_gap_exceeded",
                        )
                    )
                segment_number += 1
                segment_id = f"ball-segment-{segment_number:04d}"
                current = self._observed(
                    detection=detection,
                    segment_id=segment_id,
                    detector_name=detector_name,
                    detector_version=detector_version,
                    model_identifier=model_identifier,
                    model_digest=model_digest,
                    source_video_checksum=source_video_checksum,
                    configuration_fingerprint=configuration_fingerprint,
                    association_distance=None,
                )
                events.append(
                    BallTrackEvent(
                        event_type=BallTrackEventType.segment_started,
                        frame_index=detection.frame_index,
                        track_segment_id=segment_id,
                    )
                )
                observations.append(current)
                prior_observed = None
                last_observed = current
                pending_gap = 0
                continue

            distance = math.hypot(
                candidate.image_x - last_observed.image_x,
                candidate.image_y - last_observed.image_y,
            )
            maximum_distance = self._association_limit(
                last_observed=last_observed,
                prior_observed=prior_observed,
                gap_frames=pending_gap,
            )
            if distance > maximum_distance:
                impossible_motion_count += 1
                pending_gap += 1
                continue

            current = self._observed(
                detection=detection,
                segment_id=last_observed.track_segment_id,
                detector_name=detector_name,
                detector_version=detector_version,
                model_identifier=model_identifier,
                model_digest=model_digest,
                source_video_checksum=source_video_checksum,
                configuration_fingerprint=configuration_fingerprint,
                association_distance=distance,
            )
            if pending_gap:
                gaps.append(pending_gap)
                reacquisition_count += 1
                if pending_gap <= self.config.max_interpolation_gap_frames:
                    observations.extend(
                        self._interpolate(
                            previous=last_observed,
                            current=current,
                            gap_frames=pending_gap,
                            detector_name=detector_name,
                            detector_version=detector_version,
                            model_identifier=model_identifier,
                            model_digest=model_digest,
                            source_video_checksum=source_video_checksum,
                            configuration_fingerprint=configuration_fingerprint,
                        )
                    )
                events.append(
                    BallTrackEvent(
                        event_type=BallTrackEventType.reacquired,
                        frame_index=detection.frame_index,
                        track_segment_id=current.track_segment_id,
                        gap_length_frames=pending_gap,
                        detail=(
                            "short_gap_interpolated"
                            if pending_gap <= self.config.max_interpolation_gap_frames
                            else "long_gap_not_interpolated"
                        ),
                    )
                )
            observations.append(current)
            prior_observed = last_observed
            last_observed = current
            pending_gap = 0

        if last_observed is not None:
            if pending_gap:
                gaps.append(pending_gap)
            events.append(
                BallTrackEvent(
                    event_type=BallTrackEventType.segment_ended,
                    frame_index=last_observed.frame_index,
                    track_segment_id=last_observed.track_segment_id,
                    gap_length_frames=pending_gap,
                    detail="stream_ended",
                )
            )
        return TemporalBallTrackResult(
            observations=tuple(sorted(observations, key=lambda item: item.frame_index)),
            events=tuple(events),
            gap_lengths=tuple(gaps),
            reacquisition_count=reacquisition_count,
            segment_count=segment_number,
            impossible_motion_count=impossible_motion_count,
        )

    def _association_limit(
        self,
        *,
        last_observed: BallObservation,
        prior_observed: BallObservation | None,
        gap_frames: int,
    ) -> float:
        limit = self.config.base_association_distance_pixels + (
            gap_frames * self.config.per_gap_distance_pixels
        )
        if prior_observed is not None:
            velocity = math.hypot(
                last_observed.image_x - prior_observed.image_x,
                last_observed.image_y - prior_observed.image_y,
            )
            limit = max(
                limit,
                velocity * (gap_frames + 1) * self.config.velocity_tolerance_multiplier,
            )
        return limit

    @staticmethod
    def _observed(
        *,
        detection: BallFrameDetection,
        segment_id: str,
        detector_name: str | None,
        detector_version: str,
        model_identifier: str | None,
        model_digest: str | None,
        source_video_checksum: str | None,
        configuration_fingerprint: str | None,
        association_distance: float | None,
    ) -> BallObservation:
        candidate = next(
            item
            for item in detection.candidates
            if item.disposition == BallCandidateDisposition.accepted
        )
        return BallObservation(
            frame_index=detection.frame_index,
            timestamp_seconds=detection.timestamp_seconds,
            image_x=candidate.image_x,
            image_y=candidate.image_y,
            bounding_box=candidate.bounding_box,
            confidence=candidate.confidence,
            observation_state=BallObservationState.observed,
            track_segment_id=segment_id,
            gap_length_frames=0,
            detector_name=detector_name,
            detector_version=detector_version,
            model_identifier=model_identifier,
            model_digest=model_digest,
            source_video_checksum=source_video_checksum,
            configuration_fingerprint=configuration_fingerprint,
            association_distance_pixels=association_distance,
        )

    @staticmethod
    def _interpolate(
        *,
        previous: BallObservation,
        current: BallObservation,
        gap_frames: int,
        detector_name: str | None,
        detector_version: str,
        model_identifier: str | None,
        model_digest: str | None,
        source_video_checksum: str | None,
        configuration_fingerprint: str | None,
    ) -> tuple[BallObservation, ...]:
        result: list[BallObservation] = []
        for offset in range(1, gap_frames + 1):
            fraction = offset / (gap_frames + 1)
            frame_index = previous.frame_index + offset
            result.append(
                BallObservation(
                    frame_index=frame_index,
                    timestamp_seconds=(
                        previous.timestamp_seconds
                        + fraction * (current.timestamp_seconds - previous.timestamp_seconds)
                    ),
                    image_x=previous.image_x + fraction * (current.image_x - previous.image_x),
                    image_y=previous.image_y + fraction * (current.image_y - previous.image_y),
                    confidence=min(previous.confidence, current.confidence) * 0.6,
                    observation_state=BallObservationState.interpolated,
                    track_segment_id=previous.track_segment_id,
                    gap_length_frames=gap_frames,
                    detector_name=detector_name,
                    detector_version=detector_version,
                    model_identifier=model_identifier,
                    model_digest=model_digest,
                    source_video_checksum=source_video_checksum,
                    configuration_fingerprint=configuration_fingerprint,
                    inferred_from_frame_indices=(previous.frame_index, current.frame_index),
                )
            )
        return tuple(result)
