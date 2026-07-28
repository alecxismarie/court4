from datetime import datetime

from app.schemas.analytics import AnalyticsReport
from app.schemas.history import ContributionDecision, ContributionStatus
from app.schemas.jobs import AnalysisJob, AnalysisStatus
from app.schemas.match_iq import MatchIQReport
from app.schemas.recording_quality import RecordingQualityLevel
from app.services.recording_quality.assessment import QUALITY_THRESHOLDS

PLAY_HISTORY_POLICY_VERSION = "play-history-v1"
ANALYTICS_SCHEMA_VERSION = "movement-analytics-v1"


def evaluate_contribution(
    *,
    job: AnalysisJob,
    analytics: AnalyticsReport | None,
    match_iq: MatchIQReport | None,
    evaluated_at: datetime,
) -> ContributionDecision:
    """Evaluate one persisted analysis without changing its source artifacts."""
    source_version = match_iq.engine_version if match_iq is not None else ANALYTICS_SCHEMA_VERSION
    readiness = job.analysis_readiness

    if job.status == AnalysisStatus.failed:
        return _decision(
            ContributionStatus.excluded,
            ["ANALYSIS_FAILED"],
            (
                "This analysis remains in your history but does not contribute to Play History "
                "because Court4 could not complete it."
            ),
            evaluated_at,
            source_version,
        )

    if readiness is not None and (
        readiness.status == RecordingQualityLevel.unsuitable or bool(readiness.blocking_failures)
    ):
        return _decision(
            ContributionStatus.excluded,
            ["UNSUITABLE_RECORDING", "BLOCKING_EVIDENCE_FAILURE"],
            (
                "This analysis remains in your history but does not contribute to Play History "
                "because the recording did not contain enough reliable observation."
            ),
            evaluated_at,
            source_version,
        )

    if job.status in {AnalysisStatus.pending, AnalysisStatus.processing}:
        return _decision(
            ContributionStatus.provisional,
            ["ANALYSIS_IN_PROGRESS"],
            (
                "This analysis is saved and will be evaluated for Play History after processing "
                "is complete."
            ),
            evaluated_at,
            source_version,
        )

    if not job.analytics_completed:
        return _decision(
            ContributionStatus.provisional,
            ["ANALYSIS_INCOMPLETE"],
            (
                "This analysis is saved but does not yet have complete movement measurements for "
                "Play History."
            ),
            evaluated_at,
            source_version,
        )

    if analytics is None:
        return _decision(
            ContributionStatus.not_evaluated,
            ["LEGACY_ANALYTICS_UNAVAILABLE"],
            (
                "This report was created before Play History tracking was added, so it does not "
                "contribute to your Play History."
            ),
            evaluated_at,
            source_version,
        )

    if readiness is None or readiness.analysis_signals is None:
        return _decision(
            ContributionStatus.not_evaluated,
            ["LEGACY_EVIDENCE_UNAVAILABLE"],
            (
                "This report was created before Play History tracking was added, so it does not "
                "contribute to your Play History."
            ),
            evaluated_at,
            source_version,
        )

    signals = readiness.analysis_signals
    exclusion_reasons: list[str] = []
    if signals.player_visibility_ratio is None:
        exclusion_reasons.append("MISSING_OBSERVATION_COVERAGE")
    elif signals.player_visibility_ratio < QUALITY_THRESHOLDS.minimum_visibility_ratio:
        exclusion_reasons.append("INSUFFICIENT_OBSERVATION_COVERAGE")
    if signals.tracked_duration_seconds < QUALITY_THRESHOLDS.minimum_tracked_seconds:
        exclusion_reasons.append("INSUFFICIENT_USABLE_DURATION")
    if signals.tracking_gap_ratio > QUALITY_THRESHOLDS.blocking_gap_ratio:
        exclusion_reasons.append("FRAGMENTED_PLAYER_TRACKING")
    if signals.fragment_count > QUALITY_THRESHOLDS.maximum_fragments:
        exclusion_reasons.append("TOO_MANY_TRACK_FRAGMENTS")
    if analytics.observed_duration_seconds <= 0:
        exclusion_reasons.append("MISSING_RELIABLE_OBSERVATION")
    if analytics.zone_occupancy.tracked_time_seconds <= 0:
        exclusion_reasons.append("MISSING_MOVEMENT_MEASUREMENTS")

    measurement_confidence = (
        match_iq.confidence.measurement.level
        if (match_iq is not None and match_iq.confidence is not None)
        else None
    )
    if measurement_confidence in {"LOW", "NOT_AVAILABLE"}:
        exclusion_reasons.append("WEAK_MEASUREMENT_CONFIDENCE")

    if exclusion_reasons:
        return _decision(
            ContributionStatus.excluded,
            exclusion_reasons,
            (
                "This analysis remains in your history but does not contribute to Play History "
                "because its observation or movement measurements did not meet the current "
                "evidence standard."
            ),
            evaluated_at,
            source_version,
        )

    explanation = (
        "Included because recording quality, observation coverage, and movement measurement "
        "evidence met the current standard."
    )
    if readiness.status == RecordingQualityLevel.limited:
        explanation = (
            "Included because the movement measurements met the current evidence standard; "
            "recording limitations remain visible in the full analysis."
        )
    return _decision(
        ContributionStatus.included,
        ["EVIDENCE_STANDARD_MET"],
        explanation,
        evaluated_at,
        source_version,
    )


def _decision(
    status: ContributionStatus,
    reason_codes: list[str],
    explanation: str,
    evaluated_at: datetime,
    source_analysis_version: str,
) -> ContributionDecision:
    return ContributionDecision(
        status=status,
        reason_codes=reason_codes,
        explanation=explanation,
        policy_version=PLAY_HISTORY_POLICY_VERSION,
        evaluated_at=evaluated_at,
        source_analysis_version=source_analysis_version,
        limitations=[],
        source_versions={
            "analytics_schema": ANALYTICS_SCHEMA_VERSION,
            "analysis_source": source_analysis_version,
        },
    )
