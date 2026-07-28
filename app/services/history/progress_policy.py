from app.schemas.history import (
    ProgressEligibilityDecision,
    ProgressEligibilityStatus,
    ProgressSourceVersions,
)
from app.services.history.aggregation import AGGREGATION_POLICY_VERSION
from app.services.history.comparability import (
    COMPARABILITY_POLICY_VERSION,
    ComparableReport,
    compatible_source_versions,
    source_versions,
    unique_source_versions,
)
from app.services.history.grouping import (
    BASELINE_MINIMUM_REPORTS,
    GROUPING_POLICY_VERSION,
    MINIMUM_REPORTS_PER_GROUP,
    ComparisonSplit,
)

TREND_POLICY_VERSION = "play-history-trend-v1"
INTERPRETATION_POLICY_VERSION = "play-history-interpretation-v1"


def evaluate_trend_eligibility(
    *,
    qualified_count: int,
    comparable_reports: list[ComparableReport],
    split: ComparisonSplit,
) -> ProgressEligibilityDecision:
    versions = unique_source_versions(comparable_reports) or [source_versions(None)]
    comparable_count = len(comparable_reports)
    if comparable_count == 0:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["No reports currently meet the comparison requirements."],
            [
                "Court4 needs reports with enough reliable information before it can compare them.",
                "Court4 will not guess when information is missing or cannot be compared.",
            ],
            versions,
            TREND_POLICY_VERSION,
        )
    if not compatible_source_versions(comparable_reports):
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["The available reports use incompatible progress source versions."],
            ["Mixed source versions are never combined into a trend."],
            versions,
            TREND_POLICY_VERSION,
        )
    if comparable_count < BASELINE_MINIMUM_REPORTS:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["More comparable reports are required to establish a baseline."],
            [f"{comparable_count} of {BASELINE_MINIMUM_REPORTS} comparable reports are available."],
            versions,
            TREND_POLICY_VERSION,
        )
    if comparable_count == BASELINE_MINIMUM_REPORTS:
        return _decision(
            ProgressEligibilityStatus.provisional,
            ["Three comparable reports establish an initial baseline only."],
            [
                "A trend is not displayed until both earlier and recent groups contain at "
                "least two reports."
            ],
            versions,
            TREND_POLICY_VERSION,
        )
    if (
        len(split.earlier) < MINIMUM_REPORTS_PER_GROUP
        or len(split.recent) < MINIMUM_REPORTS_PER_GROUP
    ):
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["The deterministic groups do not have enough reports for comparison."],
            ["Each non-overlapping group requires at least two reports."],
            versions,
            TREND_POLICY_VERSION,
        )

    limitations = [
        limitation for report in comparable_reports for limitation in report.decision.limitations
    ]
    if qualified_count > comparable_count:
        limitations.append(
            f"{qualified_count - comparable_count} contributing report(s) were not suitable "
            "for this comparison."
        )
    if split.omitted_analysis_ids:
        limitations.append(
            f"{len(split.omitted_analysis_ids)} report(s) were omitted by the deterministic "
            "bounded-window or middle-report grouping rule."
        )
    status = (
        ProgressEligibilityStatus.provisional
        if any(
            report.decision.status == ProgressEligibilityStatus.provisional
            for report in comparable_reports
        )
        else ProgressEligibilityStatus.eligible
    )
    return _decision(
        status,
        ["Both earlier and recent groups meet the minimum report-count requirement."],
        _unique(limitations),
        versions,
        TREND_POLICY_VERSION,
    )


def evaluate_interpretation_eligibility(
    *,
    trend_decision: ProgressEligibilityDecision,
    has_metrics: bool,
) -> ProgressEligibilityDecision:
    if trend_decision.status in {
        ProgressEligibilityStatus.ineligible,
        ProgressEligibilityStatus.not_evaluated,
    }:
        return _decision(
            ProgressEligibilityStatus.not_evaluated,
            ["There is no eligible trend to interpret."],
            trend_decision.limitations,
            trend_decision.source_versions,
            INTERPRETATION_POLICY_VERSION,
        )
    if not has_metrics:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["No comparable metric has values in both groups."],
            [
                "Missing measurements are excluded and are never interpreted as zero.",
            ],
            trend_decision.source_versions,
            INTERPRETATION_POLICY_VERSION,
        )
    return _decision(
        ProgressEligibilityStatus.provisional,
        ["Court4 may describe measured changes using neutral observation language."],
        _unique(
            [
                *trend_decision.limitations,
                (
                    "No validated match-outcome metric links these movement changes to better "
                    "or worse performance."
                ),
                "Tactical intent, opponent response, and match format are not inferred.",
            ]
        ),
        trend_decision.source_versions,
        INTERPRETATION_POLICY_VERSION,
    )


def active_policy_versions() -> dict[str, str]:
    return {
        "comparability": COMPARABILITY_POLICY_VERSION,
        "trend": TREND_POLICY_VERSION,
        "interpretation": INTERPRETATION_POLICY_VERSION,
        "grouping": GROUPING_POLICY_VERSION,
        "aggregation": AGGREGATION_POLICY_VERSION,
    }


def _decision(
    status: ProgressEligibilityStatus,
    reasons: list[str],
    limitations: list[str],
    versions: list[ProgressSourceVersions],
    policy_version: str,
) -> ProgressEligibilityDecision:
    return ProgressEligibilityDecision(
        status=status,
        reasons=reasons,
        limitations=limitations,
        source_versions=versions,
        policy_version=policy_version,
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
