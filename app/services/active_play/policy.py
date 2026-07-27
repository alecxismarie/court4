from dataclasses import dataclass

from app.schemas.active_play import ACTIVE_PLAY_POLICY_VERSION


@dataclass(frozen=True)
class ActivePlayPolicy:
    """Provisional engineering thresholds; not calibrated gameplay probabilities."""

    version: str = ACTIVE_PLAY_POLICY_VERSION
    window_seconds: float = 3.0
    smoothing_seconds: float = 0.5
    minimum_velocity_delta_seconds: float = 0.08
    maximum_observed_gap_seconds: float = 0.75
    minimum_context_seconds: float = 6.0
    minimum_candidate_in_court_ratio: float = 0.30
    minimum_candidate_duration_seconds: float = 1.0
    maximum_reliable_candidate_fragments: int = 3
    minimum_player_window_coverage_ratio: float = 0.55
    minimum_window_coverage_ratio: float = 0.65
    strong_window_coverage_ratio: float = 0.85
    minimum_reliable_players: int = 2
    moving_speed_feet_per_second: float = 0.80
    stationary_speed_feet_per_second: float = 0.30
    active_reference_speed_feet_per_second: float = 4.0
    active_intensity_threshold: float = 0.25
    idle_intensity_threshold: float = 0.12
    minimum_moving_seconds: float = 0.50
    minimum_simultaneous_movement_seconds: float = 0.35
    direction_change_degrees: float = 50.0
    minimum_direction_speed_feet_per_second: float = 0.50
    meaningful_direction_changes_per_second: float = 0.08
    minor_gap_ratio: float = 0.15
    severe_gap_ratio: float = 0.35
    maximum_interval_discontinuity_seconds: float = 0.05


ACTIVE_PLAY_POLICY = ActivePlayPolicy()
