import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.schemas.analytics import AnalyticsReport
from app.schemas.history import (
    AnalysisHistoryItem,
    AnalysisHistoryResponse,
    AnalysisHistoryStatus,
    ContributionDecision,
    ContributionStatus,
    PlayHistoryComparisonGroup,
    PlayHistoryContributingAnalysis,
    PlayHistoryPolicyVersions,
    PlayHistoryProgressSummary,
    PlayHistoryReadiness,
    PlayHistoryResponse,
    PlayHistoryTrendDirection,
    PlayHistoryTrendMetric,
    PlayHistoryZoneSummary,
    PlayStyleSummary,
    ProgressEligibilityDecision,
    ProgressEligibilityStatus,
    VerifiedMatchIQSummary,
)
from app.schemas.jobs import AnalysisJob, AnalysisStatus
from app.schemas.match_iq import MatchIQReport
from app.schemas.recording_quality import RecordingQualityLevel
from app.services.history.aggregation import (
    AGGREGATION_POLICY_VERSION,
    POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS,
    AggregateResult,
    aggregate_movement_pace,
    aggregate_zone_share,
)
from app.services.history.comparability import (
    COMPARABILITY_POLICY_VERSION,
    ComparableReport,
    evaluate_comparability,
)
from app.services.history.grouping import (
    BASELINE_MINIMUM_REPORTS,
    GROUPING_POLICY_VERSION,
    ComparisonSplit,
    deterministic_split,
)
from app.services.history.policy import (
    ANALYTICS_SCHEMA_VERSION,
    PLAY_HISTORY_POLICY_VERSION,
    evaluate_contribution,
)
from app.services.history.progress_policy import (
    INTERPRETATION_POLICY_VERSION,
    TREND_POLICY_VERSION,
    evaluate_interpretation_eligibility,
    evaluate_trend_eligibility,
)
from app.services.jobs.repository import AnalysisJobRepository

ANALYTICS_PATH = Path("analytics") / "analytics.json"
MATCH_IQ_PATH = Path("analytics") / "match_iq.json"
PROGRESS_DISCLAIMER = (
    "Court4 shows differences between similar recordings. A difference alone does not show "
    "whether your performance got better or worse."
)


class HistoryProjectionService:
    def __init__(self, *, repository: AnalysisJobRepository) -> None:
        self.repository = repository

    def analysis_history(self, *, limit: int, offset: int) -> AnalysisHistoryResponse:
        all_items = self._all_items()
        return AnalysisHistoryResponse(
            items=all_items[offset : offset + limit],
            total=len(all_items),
            limit=limit,
            offset=offset,
        )

    def play_history(self, *, recent_limit: int) -> PlayHistoryResponse:
        contributions = self._all_items()
        included = self._unique_included(contributions)
        eligible = len(included)
        excluded = sum(
            item.contribution.status == ContributionStatus.excluded for item in contributions
        )
        provisional = sum(
            item.contribution.status == ContributionStatus.provisional for item in contributions
        )
        not_evaluated = sum(
            item.contribution.status == ContributionStatus.not_evaluated for item in contributions
        )
        analytics_by_id = {
            item.analysis_id: self._load_analytics(item.analysis_id) for item in included
        }
        match_iq_by_id = {
            item.analysis_id: self._load_match_iq(item.analysis_id) for item in included
        }
        qualified_analytics = {
            analysis_id: report
            for analysis_id, report in analytics_by_id.items()
            if report is not None
        }
        comparison_candidates, comparison_reports = self._comparison_data(
            included,
            analytics_by_id,
            match_iq_by_id,
        )
        split = deterministic_split(comparison_reports)
        progress = self._progress(
            included=included,
            analytics_by_id=qualified_analytics,
            comparable_reports=comparison_reports,
            split=split,
        )
        observation_values = [
            report.observed_duration_seconds for report in qualified_analytics.values()
        ]
        movement_values = [
            report.zone_occupancy.tracked_time_seconds for report in qualified_analytics.values()
        ]

        return PlayHistoryResponse(
            policy_version=PLAY_HISTORY_POLICY_VERSION,
            policy_versions=PlayHistoryPolicyVersions(
                contribution=PLAY_HISTORY_POLICY_VERSION,
                comparability=COMPARABILITY_POLICY_VERSION,
                trend=TREND_POLICY_VERSION,
                interpretation=INTERPRETATION_POLICY_VERSION,
                grouping=GROUPING_POLICY_VERSION,
                aggregation=AGGREGATION_POLICY_VERSION,
            ),
            total_analyses=len(contributions),
            eligible_count=eligible,
            comparable_count=len(comparison_reports),
            excluded_count=excluded,
            provisional_count=provisional,
            not_evaluated_count=not_evaluated,
            reliable_observation_seconds=sum(observation_values) if observation_values else None,
            qualified_movement_seconds=sum(movement_values) if movement_values else None,
            most_common_zone=self._most_common_zone(qualified_analytics),
            latest_verified_match_iq=self._verified_match_iq(
                included,
                match_iq_by_id,
            )[:recent_limit],
            recent_eligible_analyses=included[:recent_limit],
            contributions=contributions,
            comparison_candidates=comparison_candidates,
            readiness=self._readiness(progress),
            progress=progress,
        )

    def _all_items(self) -> list[AnalysisHistoryItem]:
        analysis_ids = dict.fromkeys(self.repository.list_job_ids())
        items = [self._project_analysis(analysis_id) for analysis_id in analysis_ids]
        return sorted(
            items,
            key=lambda item: (item.created_at, item.analysis_id),
            reverse=True,
        )

    def _project_analysis(self, analysis_id: str) -> AnalysisHistoryItem:
        try:
            job = self.repository.load_job_metadata(analysis_id)
        except Exception:
            return self._legacy_item(analysis_id)
        analytics = self._load_analytics(analysis_id)
        match_iq = self._load_match_iq(analysis_id)
        evaluated_at = max(
            [
                job.updated_at,
                *(item.created_at for item in [analytics, match_iq] if item is not None),
            ]
        )
        contribution = evaluate_contribution(
            job=job,
            analytics=analytics,
            match_iq=match_iq,
            evaluated_at=evaluated_at,
        )
        quality = job.analysis_readiness or job.upload_preflight
        signals = job.analysis_readiness.analysis_signals if job.analysis_readiness else None
        return AnalysisHistoryItem(
            analysis_id=analysis_id,
            title=_title(job),
            created_at=job.created_at,
            updated_at=job.updated_at,
            status=_history_status(job, quality.status if quality else None),
            processing_status=job.status.value,
            recording_quality=quality.status if quality else None,
            observation_coverage_ratio=signals.player_visibility_ratio if signals else None,
            reliable_observation_seconds=(
                analytics.observed_duration_seconds
                if analytics is not None
                else signals.tracked_duration_seconds
                if signals
                else None
            ),
            measurement_available=analytics is not None,
            match_iq_available=match_iq is not None and match_iq.status == "generated",
            contribution=contribution,
            limitation=_limitation(job, quality.status if quality else None, contribution),
            report_url=(
                f"/matches/{analysis_id}/analytics"
                if job.analytics_completed and analytics is not None
                else f"/matches/{analysis_id}"
            ),
            thumbnail_url=_thumbnail(job),
        )

    def _legacy_item(self, analysis_id: str) -> AnalysisHistoryItem:
        job_path = self.repository.job_path(analysis_id)
        timestamp = datetime.fromtimestamp(job_path.stat().st_mtime, tz=UTC)
        decision = ContributionDecision(
            status=ContributionStatus.not_evaluated,
            reason_codes=["LEGACY_METADATA_UNREADABLE"],
            explanation=(
                "This report was created before Play History tracking was added, so it does not "
                "contribute to your Play History."
            ),
            policy_version=PLAY_HISTORY_POLICY_VERSION,
            evaluated_at=timestamp,
            source_analysis_version=ANALYTICS_SCHEMA_VERSION,
            limitations=["Unreadable legacy metadata is not inferred."],
            source_versions={"analytics_schema": ANALYTICS_SCHEMA_VERSION},
        )
        return AnalysisHistoryItem(
            analysis_id=analysis_id,
            title="Legacy analysis",
            created_at=timestamp,
            updated_at=timestamp,
            status=AnalysisHistoryStatus.legacy,
            processing_status="legacy",
            recording_quality=None,
            observation_coverage_ratio=None,
            reliable_observation_seconds=None,
            measurement_available=False,
            match_iq_available=False,
            contribution=decision,
            limitation="Legacy analysis details are not available in the current format.",
            report_url=f"/matches/{analysis_id}",
            thumbnail_url=None,
        )

    def _load_analytics(self, analysis_id: str) -> AnalyticsReport | None:
        return _load_model(
            self.repository.analysis_dir(analysis_id) / ANALYTICS_PATH,
            AnalyticsReport,
        )

    def _load_match_iq(self, analysis_id: str) -> MatchIQReport | None:
        return _load_model(
            self.repository.analysis_dir(analysis_id) / MATCH_IQ_PATH,
            MatchIQReport,
        )

    def _unique_included(self, items: list[AnalysisHistoryItem]) -> list[AnalysisHistoryItem]:
        unique: dict[str, AnalysisHistoryItem] = {}
        for item in items:
            if item.contribution.status == ContributionStatus.included:
                unique.setdefault(item.analysis_id, item)
        return list(unique.values())

    def _comparison_data(
        self,
        included: list[AnalysisHistoryItem],
        analytics_by_id: dict[str, AnalyticsReport | None],
        match_iq_by_id: dict[str, MatchIQReport | None],
    ) -> tuple[list[PlayHistoryContributingAnalysis], list[ComparableReport]]:
        candidates: list[PlayHistoryContributingAnalysis] = []
        reports: list[ComparableReport] = []
        for item in included:
            analytics = analytics_by_id.get(item.analysis_id)
            match_iq = match_iq_by_id.get(item.analysis_id)
            decision = evaluate_comparability(
                item=item,
                analytics=analytics,
                match_iq=match_iq,
            )
            candidates.append(
                PlayHistoryContributingAnalysis(
                    analysis_id=item.analysis_id,
                    title=item.title,
                    created_at=item.created_at,
                    report_url=item.report_url,
                    contribution_status=item.contribution.status,
                    comparability=decision,
                    qualified_observation_seconds=(
                        analytics.observed_duration_seconds if analytics is not None else None
                    ),
                    qualified_movement_seconds=(
                        analytics.zone_occupancy.tracked_time_seconds
                        if analytics is not None
                        else None
                    ),
                )
            )
            if analytics is not None and decision.status in {
                ProgressEligibilityStatus.eligible,
                ProgressEligibilityStatus.provisional,
            }:
                reports.append(
                    ComparableReport(
                        item=item,
                        analytics=analytics,
                        match_iq=match_iq,
                        decision=decision,
                    )
                )
        return candidates, reports

    def _most_common_zone(
        self, analytics_by_id: dict[str, AnalyticsReport]
    ) -> PlayHistoryZoneSummary | None:
        totals = {"kitchen": 0.0, "transition": 0.0, "baseline": 0.0}
        contributing = 0
        for report in analytics_by_id.values():
            zones = report.zone_occupancy
            zone_total = (
                zones.kitchen.seconds + zones.transition_zone.seconds + zones.baseline_area.seconds
            )
            if zone_total <= 0:
                continue
            contributing += 1
            totals["kitchen"] += zones.kitchen.seconds
            totals["transition"] += zones.transition_zone.seconds
            totals["baseline"] += zones.baseline_area.seconds
        denominator = sum(totals.values())
        if denominator <= 0 or contributing == 0:
            return None
        zone = sorted(totals, key=lambda key: (-totals[key], key))[0]
        return PlayHistoryZoneSummary(
            zone=zone,
            label={
                "kitchen": "Kitchen",
                "transition": "Transition",
                "baseline": "Baseline",
            }[zone],
            seconds=totals[zone],
            denominator_seconds=denominator,
            percentage=(totals[zone] / denominator) * 100,
            contributing_analyses=contributing,
        )

    def _verified_match_iq(
        self,
        included: list[AnalysisHistoryItem],
        match_iq_by_id: dict[str, MatchIQReport | None],
    ) -> list[VerifiedMatchIQSummary]:
        summaries: list[VerifiedMatchIQSummary] = []
        for item in included:
            match_iq = match_iq_by_id.get(item.analysis_id)
            if (
                match_iq is None
                or match_iq.status != "generated"
                or match_iq.quality_gate not in {"NORMAL", "CAUTIOUS"}
            ):
                continue
            summaries.append(
                VerifiedMatchIQSummary(
                    analysis_id=item.analysis_id,
                    title=item.title,
                    created_at=match_iq.created_at,
                    summary=match_iq.summary,
                    report_url=item.report_url,
                )
            )
        return summaries

    def _readiness(self, progress: PlayHistoryProgressSummary) -> PlayHistoryReadiness:
        return PlayHistoryReadiness(
            status=progress.baseline_status,
            explanation=progress.explanation,
            eligible_analyses_required=BASELINE_MINIMUM_REPORTS,
            eligible_analyses_available=progress.comparable_analysis_count,
        )

    def _progress(
        self,
        *,
        included: list[AnalysisHistoryItem],
        analytics_by_id: dict[str, AnalyticsReport],
        comparable_reports: list[ComparableReport],
        split: ComparisonSplit,
    ) -> PlayHistoryProgressSummary:
        qualified_count = len(included)
        comparable_count = len(comparable_reports)
        qualified_observation_seconds = sum(
            analytics_by_id[item.analysis_id].observed_duration_seconds
            for item in included
            if item.analysis_id in analytics_by_id
        )
        trend_decision = evaluate_trend_eligibility(
            qualified_count=qualified_count,
            comparable_reports=comparable_reports,
            split=split,
        )
        earlier_group = _comparison_group("Earlier", split.earlier)
        recent_group = _comparison_group("Recent", split.recent)
        metrics: list[PlayHistoryTrendMetric] = []
        if (
            earlier_group is not None
            and recent_group is not None
            and trend_decision.status
            in {
                ProgressEligibilityStatus.eligible,
                ProgressEligibilityStatus.provisional,
            }
        ):
            metrics = _trend_metrics(
                split.earlier,
                split.recent,
                trend_decision,
            )
        interpretation = evaluate_interpretation_eligibility(
            trend_decision=trend_decision,
            has_metrics=any(metric.earlier_value is not None for metric in metrics),
        )
        baseline_status = _baseline_status(
            qualified_count=qualified_count,
            comparable_count=comparable_count,
            trend_decision=trend_decision,
        )
        answer, explanation = _progress_copy(
            baseline_status=baseline_status,
            metrics=metrics,
            comparable_count=comparable_count,
        )
        candidates = split.candidates
        period_start = min(
            (report.item.created_at for report in candidates),
            default=None,
        )
        period_end = max(
            (report.item.created_at for report in candidates),
            default=None,
        )
        contributing_ids = (
            [report.item.analysis_id for report in [*split.earlier, *split.recent]]
            if metrics
            else [report.item.analysis_id for report in candidates]
        )
        limitations = _unique(
            [
                PROGRESS_DISCLAIMER,
                *trend_decision.limitations,
                *interpretation.limitations,
                *(limitation for metric in metrics for limitation in metric.limitations),
            ]
        )
        return PlayHistoryProgressSummary(
            status=baseline_status,
            baseline_status=baseline_status,
            answer=answer,
            explanation=explanation,
            qualified_analysis_count=qualified_count,
            comparable_analysis_count=comparable_count,
            qualified_observation_seconds=qualified_observation_seconds,
            comparison_period_start=period_start,
            comparison_period_end=period_end,
            provisional=(
                baseline_status != "COMPARISON_AVAILABLE"
                or trend_decision.status == ProgressEligibilityStatus.provisional
                or interpretation.status == ProgressEligibilityStatus.provisional
                or any(metric.provisional for metric in metrics)
            ),
            limitations=limitations,
            earlier_analysis_count=len(split.earlier),
            recent_analysis_count=len(split.recent),
            earlier_group=earlier_group,
            recent_group=recent_group,
            trend_eligibility=trend_decision,
            interpretation_eligibility=interpretation,
            contributing_analysis_ids=contributing_ids,
            aggregation_methods=list(
                dict.fromkeys(metric.aggregation_method for metric in metrics)
            ),
            trend_metrics=metrics,
            play_style=_play_style_summary(metrics, interpretation),
        )


def _trend_metrics(
    earlier: list[ComparableReport],
    recent: list[ComparableReport],
    trend_decision: ProgressEligibilityDecision,
) -> list[PlayHistoryTrendMetric]:
    return [
        _trend_metric(
            key="movement_pace",
            label="Observed movement pace",
            unit="m/s",
            earlier=aggregate_movement_pace(earlier),
            recent=aggregate_movement_pace(recent),
            stable_tolerance=0.05,
            context=(
                "Distance is normalized by qualified tracked time. A higher or lower value "
                "describes observed movement and is not a performance judgment."
            ),
            aggregation_method="sum distance metres ÷ sum qualified tracked seconds",
            normalization="time-normalized movement distance",
            trend_decision=trend_decision,
        ),
        _trend_metric(
            key="kitchen_share",
            label="Observed time near the kitchen",
            unit="%",
            earlier=aggregate_zone_share(earlier, "kitchen"),
            recent=aggregate_zone_share(recent, "kitchen"),
            stable_tolerance=POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS,
            context="Share of qualified tracked time observed near the kitchen.",
            aggregation_method="sum zone seconds ÷ sum qualified tracked seconds",
            normalization="duration-weighted court-zone occupancy",
            trend_decision=trend_decision,
        ),
        _trend_metric(
            key="transition_share",
            label="Observed time in transition",
            unit="%",
            earlier=aggregate_zone_share(earlier, "transition"),
            recent=aggregate_zone_share(recent, "transition"),
            stable_tolerance=POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS,
            context="Share of qualified tracked time observed in the transition zone.",
            aggregation_method="sum zone seconds ÷ sum qualified tracked seconds",
            normalization="duration-weighted court-zone occupancy",
            trend_decision=trend_decision,
        ),
        _trend_metric(
            key="baseline_share",
            label="Observed time near the baseline",
            unit="%",
            earlier=aggregate_zone_share(earlier, "baseline"),
            recent=aggregate_zone_share(recent, "baseline"),
            stable_tolerance=POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS,
            context="Share of qualified tracked time observed near the baseline.",
            aggregation_method="sum zone seconds ÷ sum qualified tracked seconds",
            normalization="duration-weighted court-zone occupancy",
            trend_decision=trend_decision,
        ),
    ]


def _trend_metric(
    *,
    key: str,
    label: str,
    unit: str,
    earlier: AggregateResult,
    recent: AggregateResult,
    stable_tolerance: float,
    context: str,
    aggregation_method: str,
    normalization: str,
    trend_decision: ProgressEligibilityDecision,
) -> PlayHistoryTrendMetric:
    change: float | None = None
    direction: PlayHistoryTrendDirection | None = None
    if earlier.value is not None and recent.value is not None:
        change = recent.value - earlier.value
        if abs(change) < stable_tolerance:
            direction = PlayHistoryTrendDirection.stable
        elif change > 0:
            direction = PlayHistoryTrendDirection.increased
        else:
            direction = PlayHistoryTrendDirection.decreased
    limitations = _unique([*earlier.limitations, *recent.limitations])
    return PlayHistoryTrendMetric(
        key=key,
        label=label,
        unit=unit,
        earlier_value=earlier.value,
        recent_value=recent.value,
        change_value=change,
        direction=direction,
        context=context,
        aggregation_method=aggregation_method,
        normalization=normalization,
        earlier_contributing_count=earlier.contributing_count,
        recent_contributing_count=recent.contributing_count,
        earlier_qualified_observation_seconds=earlier.qualified_observation_seconds,
        recent_qualified_observation_seconds=recent.qualified_observation_seconds,
        contributing_analysis_ids=list(
            dict.fromkeys(
                [
                    *earlier.contributing_analysis_ids,
                    *recent.contributing_analysis_ids,
                ]
            )
        ),
        provisional=(
            trend_decision.status == ProgressEligibilityStatus.provisional
            or earlier.provisional
            or recent.provisional
            or change is None
        ),
        limitations=limitations,
    )


def _comparison_group(
    name: str,
    reports: list[ComparableReport],
) -> PlayHistoryComparisonGroup | None:
    if not reports:
        return None
    return PlayHistoryComparisonGroup(
        name=name,
        period_start=min(report.item.created_at for report in reports),
        period_end=max(report.item.created_at for report in reports),
        analysis_count=len(reports),
        qualified_observation_seconds=sum(
            report.analytics.observed_duration_seconds for report in reports
        ),
        qualified_movement_seconds=sum(
            report.analytics.zone_occupancy.tracked_time_seconds for report in reports
        ),
        analyses=[
            PlayHistoryContributingAnalysis(
                analysis_id=report.item.analysis_id,
                title=report.item.title,
                created_at=report.item.created_at,
                report_url=report.item.report_url,
                contribution_status=report.item.contribution.status,
                comparability=report.decision,
                qualified_observation_seconds=report.analytics.observed_duration_seconds,
                qualified_movement_seconds=(report.analytics.zone_occupancy.tracked_time_seconds),
            )
            for report in reports
        ],
    )


def _baseline_status(
    *,
    qualified_count: int,
    comparable_count: int,
    trend_decision: ProgressEligibilityDecision,
) -> str:
    if qualified_count == 0:
        return "NO_QUALIFIED_REPORTS"
    if comparable_count < BASELINE_MINIMUM_REPORTS:
        return (
            "MIXED_OR_INCOMPATIBLE_REPORTS"
            if qualified_count >= BASELINE_MINIMUM_REPORTS
            else "BUILDING_BASELINE"
        )
    if comparable_count == BASELINE_MINIMUM_REPORTS:
        return "BASELINE_ESTABLISHED"
    if trend_decision.status == ProgressEligibilityStatus.ineligible:
        return "MIXED_OR_INCOMPATIBLE_REPORTS"
    return "COMPARISON_AVAILABLE"


def _progress_copy(
    *,
    baseline_status: str,
    metrics: list[PlayHistoryTrendMetric],
    comparable_count: int,
) -> tuple[str, str]:
    if baseline_status == "NO_QUALIFIED_REPORTS":
        return (
            "Your progress history hasn't started yet",
            (
                "Court4 needs completed analyses with enough clear, reliable video before it "
                "can compare how your play changes over time."
            ),
        )
    if baseline_status == "BUILDING_BASELINE":
        return (
            "Building your baseline",
            (
                f"Court4 has {comparable_count} comparable "
                f"{'report' if comparable_count == 1 else 'reports'}. More are needed before "
                "showing changes over time."
            ),
        )
    if baseline_status == "BASELINE_ESTABLISHED":
        return (
            "Initial baseline established",
            (
                "Three comparable reports establish a baseline. Court4 requires at least two "
                "reports in both the earlier and recent groups before showing a comparison."
            ),
        )
    if baseline_status == "MIXED_OR_INCOMPATIBLE_REPORTS":
        return (
            "Reports are not comparable yet",
            (
                "Court4 has qualified reports, but their available evidence is not compatible "
                "enough for a reliable comparison."
            ),
        )
    changed = any(
        metric.direction
        in {
            PlayHistoryTrendDirection.increased,
            PlayHistoryTrendDirection.decreased,
        }
        for metric in metrics
    )
    return (
        "Observed changes are ready to review" if changed else "No clear change yet",
        (
            "Court4 compared your earlier and recent qualified observations using the same "
            "versioned grouping and aggregation rules."
        ),
    )


def _play_style_summary(
    metrics: list[PlayHistoryTrendMetric],
    interpretation: ProgressEligibilityDecision,
) -> PlayStyleSummary | None:
    zone_metrics = [
        metric
        for metric in metrics
        if metric.key in {"kitchen_share", "transition_share", "baseline_share"}
        and metric.earlier_value is not None
        and metric.recent_value is not None
        and metric.change_value is not None
    ]
    if not zone_metrics:
        return None
    strongest = max(
        zone_metrics,
        key=lambda metric: abs(metric.change_value or 0),
    )
    change = strongest.change_value or 0
    if abs(change) < POSITION_CHANGE_MINIMUM_PERCENTAGE_POINTS:
        status = "NO_CLEAR_CHANGE"
        summary = (
            "No clear court-positioning change yet. The largest observed zone difference was "
            f"{abs(change):.1f} percentage points."
        )
    else:
        status = "PROVISIONAL_CHANGE"
        amount = "more" if change > 0 else "less"
        summary = (
            f"Court4 observed {amount} of your reliably tracked positioning for "
            f"{strongest.label.lower()} in recent qualified analyses "
            f"({strongest.earlier_value:.1f}% to {strongest.recent_value:.1f}%)."
        )
    return PlayStyleSummary(
        status=status,
        metric_key=strongest.key,
        metric_label=strongest.label,
        earlier_value=strongest.earlier_value,
        recent_value=strongest.recent_value,
        unit=strongest.unit,
        summary=summary,
        qualified_analysis_count=len(strongest.contributing_analysis_ids),
        qualified_observation_seconds=(
            strongest.earlier_qualified_observation_seconds
            + strongest.recent_qualified_observation_seconds
        ),
        provisional=True,
        limitations=_unique(
            [
                *strongest.limitations,
                *interpretation.limitations,
                PROGRESS_DISCLAIMER,
            ]
        ),
    )


def _load_model[ModelT](
    path: Path,
    model_type: type[ModelT],
) -> ModelT | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return model_type.model_validate(payload)  # type: ignore[attr-defined, no-any-return]
    except (OSError, json.JSONDecodeError, ValidationError):
        return None


def _title(job: AnalysisJob) -> str:
    if not job.source_video:
        return f"Analysis {job.analysis_id[:8]}"
    source_name = Path(job.source_video).stem.replace("_", " ").replace("-", " ").strip()
    return source_name or f"Analysis {job.analysis_id[:8]}"


def _history_status(
    job: AnalysisJob,
    quality: RecordingQualityLevel | None,
) -> AnalysisHistoryStatus:
    if job.status == AnalysisStatus.failed:
        return AnalysisHistoryStatus.failed
    if quality == RecordingQualityLevel.unsuitable:
        return AnalysisHistoryStatus.unsuitable
    if job.status in {AnalysisStatus.pending, AnalysisStatus.processing}:
        return AnalysisHistoryStatus.processing
    if quality == RecordingQualityLevel.limited:
        return AnalysisHistoryStatus.limited
    if job.status == AnalysisStatus.completed and job.analytics_completed:
        return AnalysisHistoryStatus.ready
    return AnalysisHistoryStatus.legacy


def _limitation(
    job: AnalysisJob,
    quality: RecordingQualityLevel | None,
    contribution: ContributionDecision,
) -> str | None:
    if job.status == AnalysisStatus.failed:
        return "Court4 could not complete this analysis. The recording remains saved."
    if quality == RecordingQualityLevel.unsuitable:
        return "The recording did not contain enough reliable evidence for movement summaries."
    if quality == RecordingQualityLevel.limited:
        return "Some recording or tracking limitations apply; review the full report for context."
    return None


def _thumbnail(job: AnalysisJob) -> str | None:
    for artifact in job.available_artifacts:
        if artifact.content_type.startswith("image/") and artifact.path.startswith("frames/"):
            return artifact.url
    return None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
