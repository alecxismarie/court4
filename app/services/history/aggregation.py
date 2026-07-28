from dataclasses import dataclass
from statistics import median
from typing import Literal

from app.services.history.comparability import ComparableReport

AGGREGATION_POLICY_VERSION = "play-history-aggregation-v1"
DURATION_DOMINANCE_SHARE = 0.60
MOVEMENT_PACE_OUTLIER_MULTIPLIER = 3.0
POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS = 5.0

ZoneKey = Literal["kitchen", "transition", "baseline"]


@dataclass(frozen=True)
class AggregateResult:
    value: float | None
    contributing_analysis_ids: list[str]
    contributing_count: int
    qualified_observation_seconds: float
    qualified_movement_seconds: float
    provisional: bool
    limitations: list[str]


def aggregate_movement_pace(reports: list[ComparableReport]) -> AggregateResult:
    usable = [
        report for report in reports if report.analytics.zone_occupancy.tracked_time_seconds > 0
    ]
    if not usable:
        return _missing_result(
            "Movement pace is unavailable because no report has a qualified time denominator."
        )
    distances = [report.analytics.distance.total_distance_meters for report in usable]
    durations = [report.analytics.zone_occupancy.tracked_time_seconds for report in usable]
    value = sum(distances) / sum(durations)
    individual = [
        distance / duration for distance, duration in zip(distances, durations, strict=True)
    ]
    limitations = _shared_limitations(usable, durations)
    center = median(individual)
    if center > 0 and any(
        pace > center * MOVEMENT_PACE_OUTLIER_MULTIPLIER
        or pace < center / MOVEMENT_PACE_OUTLIER_MULTIPLIER
        for pace in individual
    ):
        limitations.append(
            "A movement-pace observation differs by more than the deterministic 3× "
            "outlier check. It is retained, and this comparison is provisional."
        )
    return _result(value, usable, limitations)


def aggregate_zone_share(
    reports: list[ComparableReport],
    zone: ZoneKey,
) -> AggregateResult:
    usable = [
        report for report in reports if report.analytics.zone_occupancy.tracked_time_seconds > 0
    ]
    if not usable:
        return _missing_result(
            "Court-position share is unavailable because no report has a qualified denominator."
        )
    zone_seconds = [_zone_seconds(report, zone) for report in usable]
    durations = [report.analytics.zone_occupancy.tracked_time_seconds for report in usable]
    value = (sum(zone_seconds) / sum(durations)) * 100
    return _result(value, usable, _shared_limitations(usable, durations))


def _zone_seconds(report: ComparableReport, zone: ZoneKey) -> float:
    occupancy = report.analytics.zone_occupancy
    if zone == "kitchen":
        return occupancy.kitchen.seconds
    if zone == "transition":
        return occupancy.transition_zone.seconds
    return occupancy.baseline_area.seconds


def _shared_limitations(
    reports: list[ComparableReport],
    durations: list[float],
) -> list[str]:
    limitations = [
        "All eligible observations are retained; no outlier is silently removed.",
    ]
    total = sum(durations)
    if len(reports) > 1 and total > 0 and max(durations) / total > DURATION_DOMINANCE_SHARE:
        limitations.append(
            "One report supplies more than 60% of the qualified duration. The weighted "
            "result is retained and marked provisional."
        )
    return limitations


def _result(
    value: float,
    reports: list[ComparableReport],
    limitations: list[str],
) -> AggregateResult:
    return AggregateResult(
        value=value,
        contributing_analysis_ids=[report.item.analysis_id for report in reports],
        contributing_count=len(reports),
        qualified_observation_seconds=sum(
            report.analytics.observed_duration_seconds for report in reports
        ),
        qualified_movement_seconds=sum(
            report.analytics.zone_occupancy.tracked_time_seconds for report in reports
        ),
        provisional=len(limitations) > 1,
        limitations=limitations,
    )


def _missing_result(limitation: str) -> AggregateResult:
    return AggregateResult(
        value=None,
        contributing_analysis_ids=[],
        contributing_count=0,
        qualified_observation_seconds=0,
        qualified_movement_seconds=0,
        provisional=True,
        limitations=[limitation, "Missing values are excluded and are never treated as zero."],
    )
