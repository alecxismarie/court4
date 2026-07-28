from dataclasses import dataclass

from app.schemas.analytics import AnalyticsReport
from app.schemas.history import (
    AnalysisHistoryItem,
    ContributionStatus,
    ProgressEligibilityDecision,
    ProgressEligibilityStatus,
    ProgressSourceVersions,
)
from app.schemas.match_iq import MatchIQReport
from app.schemas.recording_quality import RecordingQualityLevel
from app.services.history.policy import (
    ANALYTICS_SCHEMA_VERSION,
    PLAY_HISTORY_POLICY_VERSION,
)

COMPARABILITY_POLICY_VERSION = "play-history-comparability-v1"
ZONE_DEFINITION_VERSION = "court-zones-v1"
COURT_GEOMETRY_VERSION = "normalized-court-coordinate-v1"
UNITS_VERSION = "metric-seconds-percent-v1"


@dataclass(frozen=True)
class ComparableReport:
    item: AnalysisHistoryItem
    analytics: AnalyticsReport
    match_iq: MatchIQReport | None
    decision: ProgressEligibilityDecision


def source_versions(match_iq: MatchIQReport | None) -> ProgressSourceVersions:
    return ProgressSourceVersions(
        analytics_schema=ANALYTICS_SCHEMA_VERSION,
        zone_definition=ZONE_DEFINITION_VERSION,
        court_geometry=COURT_GEOMETRY_VERSION,
        units=UNITS_VERSION,
        contribution_policy=PLAY_HISTORY_POLICY_VERSION,
        match_iq_engine=match_iq.engine_version if match_iq is not None else None,
    )


def evaluate_comparability(
    *,
    item: AnalysisHistoryItem,
    analytics: AnalyticsReport | None,
    match_iq: MatchIQReport | None,
) -> ProgressEligibilityDecision:
    versions = [source_versions(match_iq)]
    if item.contribution.status == ContributionStatus.provisional:
        return _decision(
            ProgressEligibilityStatus.provisional,
            ["This report is still awaiting a final contribution decision."],
            ["Provisional reports are never promoted into a completed comparison."],
            versions,
        )
    if item.contribution.status == ContributionStatus.not_evaluated:
        return _decision(
            ProgressEligibilityStatus.not_evaluated,
            ["This report does not have the current evidence needed for comparison."],
            ["Legacy or unreadable evidence is not inferred."],
            versions,
        )
    if item.contribution.status == ContributionStatus.excluded:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["This report did not meet the Play History contribution standard."],
            ["Excluded reports never affect progress calculations."],
            versions,
        )
    if analytics is None:
        return _decision(
            ProgressEligibilityStatus.not_evaluated,
            ["Comparable movement measurements are unavailable."],
            ["Missing measurements are excluded and are never treated as zero."],
            versions,
        )
    if (
        analytics.observed_duration_seconds <= 0
        or analytics.zone_occupancy.tracked_time_seconds <= 0
    ):
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["The report has no usable observation denominator for comparison."],
            ["Raw values are not compared without qualified observed time."],
            versions,
        )

    confidence = match_iq.confidence if match_iq is not None else None
    if confidence is not None and confidence.tracking.level in {"LOW", "NOT_AVAILABLE"}:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["Tracking confidence is too weak for an across-report comparison."],
            ["The report remains available in Analysis History."],
            versions,
        )
    if confidence is not None and confidence.measurement.level in {"LOW", "NOT_AVAILABLE"}:
        return _decision(
            ProgressEligibilityStatus.ineligible,
            ["Measurement confidence is too weak for an across-report comparison."],
            ["The report remains available in Analysis History."],
            versions,
        )

    limitations = [
        "Match format is not recorded, so singles-versus-doubles compatibility is unknown.",
        "Camera placement is not recorded, so camera compatibility is unknown.",
    ]
    reasons = [
        "The report has qualified, time-normalized movement and court-position measurements.",
        "Court geometry, zone definitions, and measurement units use current Court4 versions.",
    ]
    if item.recording_quality == RecordingQualityLevel.limited:
        limitations.append("The source recording has documented quality limitations.")
    if confidence is None:
        limitations.append(
            "Tracking and measurement confidence are not available as comparable fields."
        )

    # Current persisted reports do not record match format or camera placement. They may
    # support a provisional descriptive comparison, but never full compatibility.
    return _decision(
        ProgressEligibilityStatus.provisional,
        reasons,
        limitations,
        versions,
    )


def compatible_source_versions(reports: list[ComparableReport]) -> bool:
    fingerprints = {
        (
            report.decision.source_versions[0].analytics_schema,
            report.decision.source_versions[0].zone_definition,
            report.decision.source_versions[0].court_geometry,
            report.decision.source_versions[0].units,
            report.decision.source_versions[0].contribution_policy,
        )
        for report in reports
    }
    return len(fingerprints) <= 1


def unique_source_versions(
    reports: list[ComparableReport],
) -> list[ProgressSourceVersions]:
    versions: dict[tuple[str, str, str, str, str, str | None], ProgressSourceVersions] = {}
    for report in reports:
        source = report.decision.source_versions[0]
        key = (
            source.analytics_schema,
            source.zone_definition,
            source.court_geometry,
            source.units,
            source.contribution_policy,
            source.match_iq_engine,
        )
        versions.setdefault(key, source)
    return list(versions.values())


def _decision(
    status: ProgressEligibilityStatus,
    reasons: list[str],
    limitations: list[str],
    versions: list[ProgressSourceVersions],
) -> ProgressEligibilityDecision:
    return ProgressEligibilityDecision(
        status=status,
        reasons=reasons,
        limitations=limitations,
        source_versions=versions,
        policy_version=COMPARABILITY_POLICY_VERSION,
    )
