from dataclasses import dataclass

from app.sports.types import SportType


@dataclass(frozen=True)
class SportAnalysisPolicy:
    automatic_court_detection: bool
    manual_calibration: bool
    movement_analytics: bool
    match_iq: bool
    play_history_contribution: bool


@dataclass(frozen=True)
class SportConfig:
    sport: SportType
    config_version: str
    court_definition_version: str
    capability_status: str
    policy: SportAnalysisPolicy


SPORT_CONFIGS: dict[SportType, SportConfig] = {
    SportType.PICKLEBALL: SportConfig(
        sport=SportType.PICKLEBALL,
        config_version="pickleball-analysis-v1",
        court_definition_version="pickleball-court-v1",
        capability_status="supported",
        policy=SportAnalysisPolicy(
            automatic_court_detection=True,
            manual_calibration=True,
            movement_analytics=True,
            match_iq=True,
            play_history_contribution=True,
        ),
    ),
    SportType.PADEL: SportConfig(
        sport=SportType.PADEL,
        config_version="padel-experimental-v1",
        court_definition_version="padel-court-v1",
        capability_status="experimental",
        policy=SportAnalysisPolicy(
            automatic_court_detection=False,
            manual_calibration=False,
            movement_analytics=False,
            match_iq=False,
            play_history_contribution=False,
        ),
    ),
}


def get_sport_config(sport: SportType) -> SportConfig:
    return SPORT_CONFIGS[sport]
