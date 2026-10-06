"""Shared evidence boundary for existing Pickleball court observations.

Short same-ID intervals are continuity-supported, not proof of personal identity.
Callers must pair the original ordered stream: filtering first can bridge exclusions.
"""

from app.schemas.player_tracking import PlayerObservation

MAX_OBSERVED_GAP_SECONDS = 1.0


def is_observed_court_position(observation: PlayerObservation) -> bool:
    return (
        observation.inside_court
        and not observation.excluded_from_player_tracks
        and not observation.interpolated
    )


def supports_observed_interval(
    first: PlayerObservation,
    second: PlayerObservation,
    *,
    max_gap_seconds: float = MAX_OBSERVED_GAP_SECONDS,
) -> bool:
    return (
        first.track_id == second.track_id
        and second.frame_index > first.frame_index
        and 0 < second.timestamp_seconds - first.timestamp_seconds <= max_gap_seconds
        and is_observed_court_position(first)
        and is_observed_court_position(second)
    )
