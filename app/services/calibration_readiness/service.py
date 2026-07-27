from collections import Counter, defaultdict
from pathlib import Path

from pydantic import ValidationError

from app.schemas.active_play import ACTIVE_PLAY_POLICY_VERSION
from app.schemas.calibration_readiness import (
    ActivePlayReadinessSummary,
    ArtifactReadinessItem,
    BalanceReadinessItem,
    CalibrationReadinessGovernance,
    CalibrationReadinessIntegrity,
    CalibrationReadinessSummary,
    DashboardMetric,
    DatasetBalanceReadiness,
    DatasetOverview,
    DeterministicHashStatus,
    DisagreementReadinessItem,
    MetricAvailability,
    PolicySafetySummary,
    ReadinessDataStatus,
    ReadinessSourceStatus,
    ReviewCompletionItem,
    UnresolvedReadinessItem,
)
from app.schemas.evidence_calibration import (
    ArtifactReadiness,
    CalibrationManifest,
    CalibrationResults,
    CandidateRole,
    CountMetric,
    DatasetSplit,
    DisagreementCategory,
    DurationRateMetric,
    ExpectedActivePlayState,
    ReviewStatus,
    ReviewValue,
)
from app.services.active_play.policy import ACTIVE_PLAY_POLICY
from app.services.calibration_readiness.integrity import (
    canonical_policy_sha256,
    file_sha256,
)
from app.services.calibration_readiness.policy import (
    READINESS_POLICY,
    ReadinessFacts,
    evaluate_readiness,
)
from app.services.candidates import CANDIDATE_SCHEMA_VERSION
from app.services.evidence_calibration.dataset import summarize_dataset_balance
from app.services.evidence_calibration.manifest import (
    CalibrationManifestError,
    LoadedCalibrationManifest,
    load_calibration_manifest,
)
from app.services.recording_quality import (
    QUALITY_THRESHOLDS,
    RECORDING_QUALITY_POLICY_VERSION,
)

READINESS_CLASSES = (
    ArtifactReadiness.ready,
    ArtifactReadiness.legacy_compatible,
    ArtifactReadiness.partial,
    ArtifactReadiness.incompatible,
    ArtifactReadiness.missing,
)


class CalibrationReadinessService:
    """Read-only projection over existing calibration manifests and reports."""

    def __init__(
        self,
        *,
        manifest_path: Path,
        results_path: Path,
        calibration_report_path: Path,
        disagreements_report_path: Path,
        integrity_path: Path,
        governance_path: Path,
    ) -> None:
        self.manifest_path = manifest_path
        self.results_path = results_path
        self.calibration_report_path = calibration_report_path
        self.disagreements_report_path = disagreements_report_path
        self.integrity_path = integrity_path
        self.governance_path = governance_path

    def get_summary(self) -> CalibrationReadinessSummary:
        loaded, manifest_status, manifest_message = self._load_manifest()
        results, report_status, report_message = self._load_results()
        governance, governance_status, governance_message = self._load_governance()
        integrity, integrity_status, integrity_message = self._load_integrity()
        messages = [
            message
            for message in (
                manifest_message,
                report_message,
                integrity_message,
                governance_message,
            )
            if message
        ]

        manifest = loaded.manifest if loaded is not None else None
        if loaded is not None and results is not None:
            if (
                results.manifest_sha256 != loaded.sha256
                or results.dataset_id != loaded.manifest.dataset_id
                or results.dataset_version != loaded.manifest.dataset_version
            ):
                report_status = ReadinessDataStatus.stale
                messages.append("The calibration report does not match the current manifest.")
            if not self._results_policy_hashes_match(results):
                report_status = ReadinessDataStatus.stale
                messages.append("The calibration report does not match current policy hashes.")

        if integrity is not None and not self._integrity_matches_files(integrity):
            integrity_status = ReadinessDataStatus.stale
            messages.append("The deterministic integrity record does not match current reports.")

        overall = _overall_status(
            manifest_status,
            report_status,
            integrity_status,
            governance_status,
        )
        source_status = ReadinessSourceStatus(
            manifest=manifest_status,
            report=report_status,
            integrity=integrity_status,
            governance=governance_status,
            overall=overall,
            messages=list(dict.fromkeys(messages)),
        )
        return self._build_summary(
            source_status=source_status,
            loaded=loaded,
            manifest=manifest,
            results=results,
            integrity=integrity,
            governance=governance,
        )

    def _load_manifest(
        self,
    ) -> tuple[LoadedCalibrationManifest | None, ReadinessDataStatus, str | None]:
        if not self.manifest_path.is_file():
            return None, ReadinessDataStatus.missing, "Calibration manifest is missing."
        try:
            return (
                load_calibration_manifest(self.manifest_path),
                ReadinessDataStatus.current,
                None,
            )
        except CalibrationManifestError:
            return None, ReadinessDataStatus.invalid, "Calibration manifest is invalid."

    def _load_results(
        self,
    ) -> tuple[CalibrationResults | None, ReadinessDataStatus, str | None]:
        if not self.results_path.is_file():
            return None, ReadinessDataStatus.missing, "Generated calibration results are missing."
        try:
            return (
                CalibrationResults.model_validate_json(
                    self.results_path.read_text(encoding="utf-8")
                ),
                ReadinessDataStatus.current,
                None,
            )
        except (OSError, ValidationError):
            return None, ReadinessDataStatus.invalid, "Generated calibration results are invalid."

    def _load_governance(
        self,
    ) -> tuple[CalibrationReadinessGovernance | None, ReadinessDataStatus, str | None]:
        if not self.governance_path.is_file():
            return None, ReadinessDataStatus.missing, "Readiness governance record is missing."
        try:
            value = CalibrationReadinessGovernance.model_validate_json(
                self.governance_path.read_text(encoding="utf-8")
            )
            if value.readiness_policy_version != READINESS_POLICY.version:
                return value, ReadinessDataStatus.stale, "Readiness governance policy is stale."
            return value, ReadinessDataStatus.current, None
        except (OSError, ValidationError):
            return None, ReadinessDataStatus.invalid, "Readiness governance record is invalid."

    def _load_integrity(
        self,
    ) -> tuple[CalibrationReadinessIntegrity | None, ReadinessDataStatus, str | None]:
        if not self.integrity_path.is_file():
            return None, ReadinessDataStatus.missing, "Deterministic integrity record is missing."
        try:
            return (
                CalibrationReadinessIntegrity.model_validate_json(
                    self.integrity_path.read_text(encoding="utf-8")
                ),
                ReadinessDataStatus.current,
                None,
            )
        except (OSError, ValidationError):
            return None, ReadinessDataStatus.invalid, "Deterministic integrity record is invalid."

    def _results_policy_hashes_match(self, results: CalibrationResults) -> bool:
        return results.recording_policy_sha256 == canonical_policy_sha256(
            QUALITY_THRESHOLDS
        ) and results.active_play_policy_sha256 == canonical_policy_sha256(ACTIVE_PLAY_POLICY)

    def _integrity_matches_files(self, integrity: CalibrationReadinessIntegrity) -> bool:
        files = (
            (self.results_path, integrity.calibration_results_sha256),
            (self.calibration_report_path, integrity.calibration_report_sha256),
            (self.disagreements_report_path, integrity.disagreements_report_sha256),
        )
        return all(path.is_file() and file_sha256(path) == expected for path, expected in files)

    def _build_summary(
        self,
        *,
        source_status: ReadinessSourceStatus,
        loaded: LoadedCalibrationManifest | None,
        manifest: CalibrationManifest | None,
        results: CalibrationResults | None,
        integrity: CalibrationReadinessIntegrity | None,
        governance: CalibrationReadinessGovernance | None,
    ) -> CalibrationReadinessSummary:
        dataset = _dataset_overview(manifest, results)
        balance = _balance_summary(manifest, results)
        artifacts = _artifact_summary(results)
        reviews = _review_completion(manifest)
        outcomes = _calibration_outcomes(results)
        active_play = _active_play_summary(results)
        disagreements, unresolved = _disagreement_summary(manifest, results)

        policy_safety = _policy_safety(
            source_status=source_status,
            loaded=loaded,
            results=results,
            integrity=integrity,
            governance=governance,
        )
        category_missing = sum(len(item.missing) for item in balance.categories)
        category_underrepresented = sum(len(item.underrepresented) for item in balance.categories)
        fully_reviewed = dataset.reviewed_samples
        active_metrics = results.metrics.active_play if results is not None else None
        active_seconds = (
            active_metrics.likely_active_agreement.denominator_seconds
            if active_metrics is not None
            else 0.0
        )
        idle_seconds = (
            active_metrics.likely_idle_agreement.denominator_seconds
            if active_metrics is not None
            else 0.0
        )
        critical_categories = {
            "artifact_compatibility",
            "player_identity",
            "tracking_continuity",
            "active_play_state",
            "active_play_boundary",
        }
        critical_disagreements = sum(
            item.count or 0 for item in disagreements if item.category in critical_categories
        )
        facts = ReadinessFacts(
            source_current=source_status.overall == ReadinessDataStatus.current,
            total_samples=dataset.total_samples,
            development_count=dataset.development_count,
            validation_count=dataset.validation_count,
            holdout_count=dataset.holdout_count,
            fully_reviewed_samples=fully_reviewed,
            current_schema_samples=active_play.current_schema_sample_count,
            active_reviewed_seconds=active_play.reviewed_duration_seconds,
            active_reviewed_intervals=active_play.reviewed_intervals,
            active_evidence_seconds=active_seconds,
            idle_evidence_seconds=idle_seconds,
            reviewed_boundaries=(
                active_metrics.boundary_error.boundary_count if active_metrics is not None else 0
            ),
            missing_balance_values=category_missing,
            underrepresented_balance_values=category_underrepresented,
            critical_disagreements=critical_disagreements,
            expensive_inference_runs=(
                results.expensive_inference_runs if results is not None else None
            ),
            production_thresholds_unchanged=(policy_safety.production_thresholds_unchanged),
            reviewer_labels_unchanged=policy_safety.reviewer_labels_unchanged,
            deterministic_report_verified=(
                policy_safety.deterministic_report_status == DeterministicHashStatus.match
            ),
            holdout_protection_enabled=policy_safety.holdout_protection_enabled,
            recording_policy_frozen=(
                governance.recording_policy_review_frozen if governance is not None else False
            ),
            active_play_policy_frozen=(
                governance.active_play_policy_review_frozen if governance is not None else False
            ),
            false_active_budget_approved=policy_safety.false_active_budget_approved,
            false_idle_budget_approved=policy_safety.false_idle_budget_approved,
        )
        return CalibrationReadinessSummary(
            source_status=source_status,
            dataset=dataset,
            balance=balance,
            artifact_readiness=artifacts,
            review_completion=reviews,
            calibration_outcomes=outcomes,
            active_play=active_play,
            disagreements=disagreements,
            unresolved_items=unresolved,
            policy_safety=policy_safety,
            readiness=evaluate_readiness(facts),
        )


def _dataset_overview(
    manifest: CalibrationManifest | None,
    results: CalibrationResults | None,
) -> DatasetOverview:
    samples = manifest.samples if manifest is not None else []
    statuses = Counter(sample.review_status for sample in samples)
    return DatasetOverview(
        total_samples=len(samples),
        development_count=sum(
            sample.dataset_split == DatasetSplit.development for sample in samples
        ),
        validation_count=sum(sample.dataset_split == DatasetSplit.validation for sample in samples),
        holdout_count=sum(sample.dataset_split == DatasetSplit.holdout for sample in samples),
        reviewed_samples=statuses[ReviewStatus.reviewed],
        partially_reviewed_samples=statuses[ReviewStatus.partially_reviewed],
        unreviewed_samples=statuses[ReviewStatus.not_reviewed],
        last_evaluation_timestamp=(results.generated_at if results is not None else None),
        manifest_schema_version=(manifest.schema_version if manifest is not None else None),
        manifest_version=(manifest.dataset_version if manifest is not None else None),
        report_schema_version=(results.schema_version if results is not None else None),
    )


def _balance_summary(
    manifest: CalibrationManifest | None,
    results: CalibrationResults | None,
) -> DatasetBalanceReadiness:
    if results is not None:
        source = results.dataset_balance
    elif manifest is not None:
        source = summarize_dataset_balance(manifest)
    else:
        return DatasetBalanceReadiness()
    return DatasetBalanceReadiness(
        categories=[
            BalanceReadinessItem(
                category=item.category,
                counts=item.counts,
                represented=item.represented,
                missing=item.missing,
                underrepresented=item.underrepresented,
            )
            for item in source.categories
        ],
        warnings=source.provisional_warnings,
    )


def _artifact_summary(results: CalibrationResults | None) -> list[ArtifactReadinessItem]:
    by_readiness: dict[ArtifactReadiness, list[str]] = defaultdict(list)
    if results is not None:
        for sample in results.samples:
            by_readiness[sample.artifact_readiness].append(sample.sample_id)
    return [
        ArtifactReadinessItem(
            readiness=readiness.value,
            count=len(by_readiness[readiness]),
            sample_ids=sorted(by_readiness[readiness]),
        )
        for readiness in READINESS_CLASSES
    ]


def _review_completion(manifest: CalibrationManifest | None) -> list[ReviewCompletionItem]:
    samples = manifest.samples if manifest is not None else []
    total = len(samples)
    definitions: list[tuple[str, str, list[bool], int, float | None]] = []
    recording = [
        sample.human_review is not None
        and sample.human_review.recording is not None
        and sample.human_review.recording.recording_quality_verdict.value
        not in {"NOT_REVIEWED", "UNKNOWN"}
        for sample in samples
    ]
    candidates = [
        sample.human_review.player_candidates if sample.human_review is not None else None
        for sample in samples
    ]
    identity = [bool(review and review.stable_real_players) for review in candidates]
    selected = [
        review is not None and review.selected_player_identity_correct is not None
        for review in candidates
    ]
    mappings = [
        review is not None
        and bool(review.candidate_mappings)
        and all(
            mapping.mapping_correct in {ReviewValue.yes, ReviewValue.no}
            for mapping in review.candidate_mappings
        )
        for review in candidates
    ]
    duplicates = [
        review is not None
        and (
            review.duplicate_candidates is not None
            or any(mapping.role == CandidateRole.duplicate for mapping in review.candidate_mappings)
        )
        for review in candidates
    ]
    spectators = [
        review is not None
        and (
            review.spectators_incorrectly_promoted is not None
            or any(mapping.role == CandidateRole.spectator for mapping in review.candidate_mappings)
        )
        for review in candidates
    ]
    tracking_intervals = [
        interval
        for sample in samples
        if sample.human_review is not None and sample.human_review.tracking is not None
        for interval in sample.human_review.tracking.intervals
    ]
    insight_reviews = [
        sample.human_review.insight if sample.human_review is not None else None
        for sample in samples
    ]
    insights = [bool(review and review.generated_insights) for review in insight_reviews]
    active_intervals = [
        interval
        for sample in samples
        if sample.human_review is not None and sample.human_review.active_play is not None
        for interval in sample.human_review.active_play.intervals
        if interval.expected_state
        not in {ExpectedActivePlayState.not_reviewed, ExpectedActivePlayState.uncertain}
        and not interval.uncertain_human_label
    ]
    definitions.extend(
        [
            ("recording", "Recording quality", recording, sum(recording), None),
            ("identity", "Player identity", identity, sum(identity), None),
            ("selected_player", "Selected player", selected, sum(selected), None),
            ("candidate_mapping", "Candidate mapping", mappings, sum(mappings), None),
            ("duplicate", "Duplicate review", duplicates, sum(duplicates), None),
            ("spectator", "Spectator review", spectators, sum(spectators), None),
            (
                "continuity",
                "Continuity intervals",
                [
                    bool(
                        sample.human_review
                        and sample.human_review.tracking
                        and sample.human_review.tracking.intervals
                    )
                    for sample in samples
                ],
                len(tracking_intervals),
                sum(item.end_time_seconds - item.start_time_seconds for item in tracking_intervals),
            ),
            (
                "insights",
                "Per-insight review",
                insights,
                sum(len(review.generated_insights) for review in insight_reviews if review),
                None,
            ),
            (
                "active_play",
                "Active Play intervals",
                [
                    bool(
                        sample.human_review
                        and sample.human_review.active_play
                        and sample.human_review.active_play.intervals
                    )
                    for sample in samples
                ],
                len(active_intervals),
                sum(item.end_time_seconds - item.start_time_seconds for item in active_intervals),
            ),
        ]
    )
    return [
        ReviewCompletionItem(
            key=key,
            label=label,
            reviewed_samples=sum(flags),
            total_samples=total,
            reviewed_items=items,
            reviewed_seconds=seconds,
            availability=(
                MetricAvailability.not_reviewed
                if sum(flags) == 0
                else (
                    MetricAvailability.available
                    if total > 0 and sum(flags) == total
                    else MetricAvailability.provisional
                )
            ),
        )
        for key, label, flags, items, seconds in definitions
    ]


def _calibration_outcomes(results: CalibrationResults | None) -> list[DashboardMetric]:
    if results is None:
        return [_unavailable_metric(key, label) for key, label in _outcome_labels()]
    metrics = results.metrics
    insight_numerator = sum(item.numerator for item in metrics.insight_integrity.fields.values())
    insight_denominator = sum(
        item.denominator for item in metrics.insight_integrity.fields.values()
    )
    return [
        _count_dashboard_metric(
            "quality_exact", "Recording exact agreement", metrics.recording_quality.exact_agreement
        ),
        _count_dashboard_metric(
            "quality_acceptable",
            "Recording acceptable agreement",
            metrics.recording_quality.acceptable_agreement,
        ),
        _error_metric(
            "false_acceptance",
            "False acceptance",
            metrics.evidence_gates.unsuitable_insights_incorrectly_allowed,
            metrics.evidence_gates.unsuitable_insights_correctly_suppressed.denominator,
        ),
        _error_metric(
            "false_suppression",
            "False suppression",
            metrics.evidence_gates.valid_insights_incorrectly_suppressed,
            metrics.evidence_gates.valid_insights_correctly_allowed.denominator,
        ),
        _count_dashboard_metric(
            "player_recall",
            "Expected-player recall",
            metrics.candidate_reliability.expected_player_recall,
        ),
        _count_dashboard_metric(
            "candidate_precision",
            "Candidate precision",
            metrics.candidate_reliability.candidate_precision,
        ),
        _count_dashboard_metric(
            "selected_identity",
            "Selected-player identity",
            metrics.candidate_reliability.selected_player_identity_accuracy,
        ),
        _raw_metric(
            "duplicate_count",
            "Duplicate count",
            metrics.candidate_reliability.duplicate_candidate_count,
        ),
        _raw_metric(
            "spectator_promotions",
            "Spectator promotions",
            metrics.candidate_reliability.spectator_promotion_count,
        ),
        _count_dashboard_metric(
            "continuity_agreement",
            "Continuity agreement",
            metrics.tracking_continuity.correctly_maintained_identity_intervals,
        ),
        _error_metric(
            "insight_review", "Insight-review agreement", insight_numerator, insight_denominator
        ),
    ]


def _outcome_labels() -> list[tuple[str, str]]:
    return [
        ("quality_exact", "Recording exact agreement"),
        ("quality_acceptable", "Recording acceptable agreement"),
        ("false_acceptance", "False acceptance"),
        ("false_suppression", "False suppression"),
        ("player_recall", "Expected-player recall"),
        ("candidate_precision", "Candidate precision"),
        ("selected_identity", "Selected-player identity"),
        ("duplicate_count", "Duplicate count"),
        ("spectator_promotions", "Spectator promotions"),
        ("continuity_agreement", "Continuity agreement"),
        ("insight_review", "Insight-review agreement"),
    ]


def _active_play_summary(results: CalibrationResults | None) -> ActivePlayReadinessSummary:
    if results is None:
        unavailable = _unavailable_metric("unavailable", "Not available")
        return ActivePlayReadinessSummary(
            generated_intervals=0,
            reviewed_intervals=0,
            reviewed_duration_seconds=0,
            likely_active_seconds=0,
            likely_idle_seconds=0,
            unknown_seconds=0,
            false_active=unavailable.model_copy(
                update={"key": "false_active", "label": "False active"}
            ),
            false_idle=unavailable.model_copy(update={"key": "false_idle", "label": "False idle"}),
            boundary_error=unavailable.model_copy(
                update={"key": "boundary_error", "label": "Boundary error"}
            ),
            abstention_rate=unavailable.model_copy(
                update={"key": "abstention", "label": "Abstention rate"}
            ),
            coverage_rate=unavailable.model_copy(
                update={"key": "coverage", "label": "Coverage rate"}
            ),
            current_schema_sample_count=0,
            stale_artifact_sample_count=0,
        )
    active = results.metrics.active_play
    versions = {
        item.active_play_policy_version
        for item in results.samples
        if item.active_play_policy_version is not None
    }
    return ActivePlayReadinessSummary(
        policy_version=(next(iter(versions)) if len(versions) == 1 else None),
        generated_intervals=sum(item.active_play_interval_count for item in results.samples),
        reviewed_intervals=active.reviewed_duration.interval_count,
        reviewed_duration_seconds=active.reviewed_duration.seconds,
        likely_active_seconds=sum(
            item.active_play_state_seconds.get("LIKELY_ACTIVE", 0) for item in results.samples
        ),
        likely_idle_seconds=sum(
            item.active_play_state_seconds.get("LIKELY_IDLE", 0) for item in results.samples
        ),
        unknown_seconds=sum(
            item.active_play_state_seconds.get("UNKNOWN", 0) for item in results.samples
        ),
        false_active=_duration_error_metric(
            "false_active",
            "False active",
            active.false_active.seconds,
            active.likely_idle_agreement.denominator_seconds,
            active.false_active.interval_count,
        ),
        false_idle=_duration_error_metric(
            "false_idle",
            "False idle",
            active.false_idle.seconds,
            active.likely_active_agreement.denominator_seconds,
            active.false_idle.interval_count,
        ),
        boundary_error=DashboardMetric(
            key="boundary_error",
            label="Boundary error",
            numerator=active.boundary_error.mean_absolute_seconds,
            denominator=float(active.boundary_error.boundary_count),
            raw_count=active.boundary_error.boundary_count,
            availability=(
                MetricAvailability.not_reviewed
                if active.boundary_error.boundary_count == 0
                else MetricAvailability.provisional
            ),
            note="Mean absolute boundary error in seconds.",
        ),
        abstention_rate=_duration_rate_metric(
            "abstention", "Abstention rate", active.abstention_rate
        ),
        coverage_rate=_duration_rate_metric("coverage", "Coverage rate", active.coverage_rate),
        current_schema_sample_count=sum(
            item.active_play_candidate_schema_version == CANDIDATE_SCHEMA_VERSION
            for item in results.samples
            if item.active_play_generated
        ),
        stale_artifact_sample_count=sum(
            item.active_play_generated
            and item.active_play_candidate_schema_version != CANDIDATE_SCHEMA_VERSION
            for item in results.samples
        ),
    )


def _disagreement_summary(
    manifest: CalibrationManifest | None,
    results: CalibrationResults | None,
) -> tuple[list[DisagreementReadinessItem], list[UnresolvedReadinessItem]]:
    samples = manifest.samples if manifest is not None else []
    existing: dict[DisagreementCategory, list[str]] = defaultdict(list)
    unresolved: list[UnresolvedReadinessItem] = []
    if results is not None:
        for item in results.disagreements:
            existing[item.category].append(item.sample_id)
            unresolved.append(
                UnresolvedReadinessItem(
                    sample_id=item.sample_id,
                    category=item.category.value,
                    reason=item.reason,
                )
            )
    artifact_samples = sorted(
        sample.sample_id
        for sample in (results.samples if results is not None else [])
        if sample.artifact_readiness != ArtifactReadiness.ready
    )
    identity_samples = sorted(
        sample.sample_id
        for sample in samples
        if sample.human_review is None
        or sample.human_review.player_candidates is None
        or sample.human_review.player_candidates.selected_player_identity_correct is None
    )
    tracking_samples = sorted(
        sample.sample_id
        for sample in samples
        if sample.human_review is None
        or sample.human_review.tracking is None
        or not sample.human_review.tracking.intervals
    )
    active_intervals = [
        interval
        for sample in samples
        if sample.human_review is not None and sample.human_review.active_play is not None
        for interval in sample.human_review.active_play.intervals
    ]
    active_state_samples = sorted(
        sample.sample_id
        for sample in samples
        if sample.human_review is None
        or sample.human_review.active_play is None
        or not sample.human_review.active_play.intervals
    )
    boundary_samples = sorted(
        {
            sample.sample_id
            for sample in samples
            if sample.human_review is not None and sample.human_review.active_play is not None
            for interval in sample.human_review.active_play.intervals
            if interval.court4_start_time_seconds is None
        }
    )
    categories = [
        (
            "incomplete_annotation",
            "Incomplete annotation",
            existing[DisagreementCategory.incomplete_annotation],
            True,
        ),
        (
            "recording_assessment",
            "Recording assessment",
            existing[DisagreementCategory.recording_assessment],
            True,
        ),
        ("artifact_compatibility", "Artifact compatibility", artifact_samples, results is not None),
        ("player_identity", "Player identity", identity_samples, manifest is not None),
        (
            "candidate_association",
            "Candidate association",
            existing[DisagreementCategory.candidate_association],
            True,
        ),
        ("tracking_continuity", "Tracking continuity", tracking_samples, manifest is not None),
        ("measurement", "Measurement", existing[DisagreementCategory.measurement], True),
        ("insight_gating", "Insight gating", existing[DisagreementCategory.insight_gating], True),
        ("confidence", "Confidence", [], False),
        ("wording", "Wording", existing[DisagreementCategory.wording], True),
        ("active_play_state", "Active Play state", active_state_samples, bool(active_intervals)),
        ("active_play_boundary", "Active Play boundary", boundary_samples, bool(active_intervals)),
    ]
    return (
        [
            DisagreementReadinessItem(
                category=key,
                label=label,
                count=(len(set(ids)) if available else None),
                sample_ids=sorted(set(ids)),
                availability=(
                    MetricAvailability.available if available else MetricAvailability.not_reviewed
                ),
            )
            for key, label, ids, available in categories
        ],
        unresolved[:10],
    )


def _policy_safety(
    *,
    source_status: ReadinessSourceStatus,
    loaded: LoadedCalibrationManifest | None,
    results: CalibrationResults | None,
    integrity: CalibrationReadinessIntegrity | None,
    governance: CalibrationReadinessGovernance | None,
) -> PolicySafetySummary:
    policies_unchanged = (
        results is not None
        and results.recording_policy_sha256 == canonical_policy_sha256(QUALITY_THRESHOLDS)
        and results.active_play_policy_sha256 == canonical_policy_sha256(ACTIVE_PLAY_POLICY)
    )
    labels_unchanged = (
        results is not None and loaded is not None and results.manifest_sha256 == loaded.sha256
    )
    simulations = (
        [*results.threshold_analysis, *results.active_play_threshold_analysis]
        if results is not None
        else []
    )
    nondevelopment_ids = (
        {
            sample.sample_id
            for sample in loaded.manifest.samples
            if sample.dataset_split != DatasetSplit.development
        }
        if loaded is not None
        else set()
    )
    holdout_protected = all(
        nondevelopment_ids.issubset(set(simulation.excluded_samples)) for simulation in simulations
    )
    return PolicySafetySummary(
        recording_policy_version=RECORDING_QUALITY_POLICY_VERSION,
        active_play_policy_version=ACTIVE_PLAY_POLICY_VERSION,
        readiness_policy_version=READINESS_POLICY.version,
        recording_policy_immutable=True,
        active_play_policy_immutable=True,
        policies_frozen_for_review=(
            governance is not None
            and governance.recording_policy_review_frozen
            and governance.active_play_policy_review_frozen
        ),
        threshold_simulations_exist=bool(simulations),
        holdout_protection_enabled=(
            holdout_protected and source_status.report == ReadinessDataStatus.current
        ),
        production_thresholds_unchanged=(policies_unchanged if results else None),
        reviewer_labels_unchanged=(labels_unchanged if results and loaded else None),
        deterministic_report_status=(
            integrity.deterministic_report_status
            if integrity is not None
            else DeterministicHashStatus.not_verified
        ),
        calibration_report_sha256=(
            integrity.calibration_report_sha256 if integrity is not None else None
        ),
        false_active_budget_approved=(
            governance.false_active_budget_approved if governance is not None else False
        ),
        false_idle_budget_approved=(
            governance.false_idle_budget_approved if governance is not None else False
        ),
    )


def _count_dashboard_metric(key: str, label: str, metric: CountMetric) -> DashboardMetric:
    availability = (
        MetricAvailability.not_reviewed
        if metric.denominator == 0
        else (
            MetricAvailability.provisional if metric.provisional else MetricAvailability.available
        )
    )
    return DashboardMetric(
        key=key,
        label=label,
        numerator=float(metric.numerator),
        denominator=float(metric.denominator),
        percentage=(metric.percentage if availability == MetricAvailability.available else None),
        availability=availability,
        note=metric.note,
    )


def _error_metric(
    key: str,
    label: str,
    numerator: int,
    denominator: int,
) -> DashboardMetric:
    return DashboardMetric(
        key=key,
        label=label,
        numerator=float(numerator),
        denominator=float(denominator),
        percentage=None,
        raw_count=numerator,
        availability=(
            MetricAvailability.not_reviewed if denominator == 0 else MetricAvailability.provisional
        ),
        note="Percentage withheld until the denominator is no longer provisional.",
    )


def _raw_metric(key: str, label: str, value: int | None) -> DashboardMetric:
    return DashboardMetric(
        key=key,
        label=label,
        raw_count=value,
        availability=(
            MetricAvailability.not_reviewed if value is None else MetricAvailability.provisional
        ),
    )


def _duration_error_metric(
    key: str,
    label: str,
    numerator: float,
    denominator: float,
    count: int,
) -> DashboardMetric:
    return DashboardMetric(
        key=key,
        label=label,
        numerator=numerator,
        denominator=denominator,
        percentage=None,
        raw_count=count,
        availability=(
            MetricAvailability.not_reviewed if denominator == 0 else MetricAvailability.provisional
        ),
        note="Raw seconds; no error-rate claim is made.",
    )


def _duration_rate_metric(
    key: str,
    label: str,
    metric: DurationRateMetric,
) -> DashboardMetric:
    numerator = float(metric.numerator_seconds)
    denominator = float(metric.denominator_seconds)
    percentage = metric.percentage
    return DashboardMetric(
        key=key,
        label=label,
        numerator=numerator,
        denominator=denominator,
        percentage=(
            float(percentage)
            if percentage is not None and denominator > 0 and not metric.provisional
            else None
        ),
        raw_count=int(metric.interval_count),
        availability=(
            MetricAvailability.not_reviewed
            if denominator == 0
            else (
                MetricAvailability.provisional
                if metric.provisional
                else MetricAvailability.available
            )
        ),
        note=metric.note,
    )


def _unavailable_metric(key: str, label: str) -> DashboardMetric:
    return DashboardMetric(
        key=key,
        label=label,
        availability=MetricAvailability.not_available,
    )


def _overall_status(*statuses: ReadinessDataStatus) -> ReadinessDataStatus:
    if ReadinessDataStatus.invalid in statuses:
        return ReadinessDataStatus.invalid
    if ReadinessDataStatus.missing in statuses:
        return ReadinessDataStatus.missing
    if ReadinessDataStatus.stale in statuses:
        return ReadinessDataStatus.stale
    return ReadinessDataStatus.current
