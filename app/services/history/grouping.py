from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.history.comparability import ComparableReport

GROUPING_POLICY_VERSION = "play-history-grouping-v1"
BASELINE_MINIMUM_REPORTS = 3
TREND_MINIMUM_REPORTS = 4
MINIMUM_REPORTS_PER_GROUP = 2
MAXIMUM_COMPARISON_REPORTS = 8


@dataclass(frozen=True)
class ComparisonSplit:
    candidates: list[ComparableReport]
    earlier: list[ComparableReport]
    recent: list[ComparableReport]
    omitted_analysis_ids: list[str]


def deterministic_split(reports: list[ComparableReport]) -> ComparisonSplit:
    unique: dict[str, ComparableReport] = {}
    for report in reports:
        current = unique.get(report.item.analysis_id)
        if current is None or _sort_key(report) > _sort_key(current):
            unique[report.item.analysis_id] = report

    ordered = sorted(unique.values(), key=_sort_key)
    window = ordered[-MAXIMUM_COMPARISON_REPORTS:]
    omitted = [report.item.analysis_id for report in ordered[:-MAXIMUM_COMPARISON_REPORTS]]

    if len(window) < TREND_MINIMUM_REPORTS:
        return ComparisonSplit(
            candidates=window,
            earlier=[],
            recent=[],
            omitted_analysis_ids=omitted,
        )

    group_size = len(window) // 2
    earlier = window[:group_size]
    recent = window[-group_size:]
    if len(window) % 2:
        omitted.append(window[group_size].item.analysis_id)
    return ComparisonSplit(
        candidates=window,
        earlier=earlier,
        recent=recent,
        omitted_analysis_ids=omitted,
    )


def normalized_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _sort_key(report: ComparableReport) -> tuple[datetime, str]:
    return normalized_timestamp(report.item.created_at), report.item.analysis_id
