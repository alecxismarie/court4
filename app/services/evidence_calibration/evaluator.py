import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from app.schemas.active_play import (
    ACTIVE_PLAY_POLICY_VERSION,
    ActivePlayReport,
    ActivePlayState,
    MotionFeatureWindow,
)
from app.schemas.analytics import AnalyticsReport, TimelineReport
from app.schemas.calibration import CourtCalibrationReport
from app.schemas.evidence_calibration import (
    ActivePlayCalibrationMetrics,
    ArtifactEvaluation,
    ArtifactEvaluationStatus,
    ArtifactReadiness,
    BoundaryErrorMetric,
    CalibrationDisagreement,
    CalibrationManifest,
    CalibrationMetrics,
    CalibrationQualityLabel,
    CalibrationResults,
    CalibrationSample,
    CandidateReliabilityMetrics,
    CandidateRole,
    ContinuityLabel,
    CountMetric,
    DatasetSplit,
    DisagreementCategory,
    DurationMetric,
    DurationRateMetric,
    EvidenceGateMetrics,
    ExpectedActivePlayState,
    ExpectedInsightEligibility,
    InsightIntegrityMetrics,
    PlayerCandidateReview,
    RecordingQualityMetrics,
    ReviewStatus,
    ReviewValue,
    SampleCalibrationResult,
    SampleEvaluationStatus,
    ThresholdSimulationResult,
    TrackingContinuityMetrics,
)
from app.schemas.jobs import AnalysisJob
from app.schemas.match_iq import MatchIQReport
from app.schemas.player_candidates import (
    CandidateQuality,
    PlayerCandidate,
    PlayerCandidateCollection,
)
from app.schemas.player_tracking import PlayerTrackingReport
from app.schemas.recording_quality import RecordingQualityAssessment
from app.schemas.video import VideoMetadataReport
from app.services.active_play.engine import classify_motion_windows
from app.services.active_play.policy import ACTIVE_PLAY_POLICY
from app.services.calibration_readiness.integrity import canonical_policy_sha256
from app.services.candidates.service import CANDIDATE_SCHEMA_VERSION, THRESHOLDS
from app.services.evidence_calibration.dataset import (
    incomplete_review_fields,
    summarize_dataset_balance,
)
from app.services.evidence_calibration.manifest import LoadedCalibrationManifest
from app.services.match_iq.engine import MATCH_IQ_ENGINE_VERSION, generate_match_iq
from app.services.recording_quality import (
    QUALITY_THRESHOLDS,
    RECORDING_QUALITY_POLICY_VERSION,
    RecordingQualityThresholds,
    assess_analysis_readiness,
    assess_upload_preflight,
)

QUALITY_ORDER = {
    CalibrationQualityLabel.unsuitable: 0,
    CalibrationQualityLabel.limited: 1,
    CalibrationQualityLabel.good: 2,
    CalibrationQualityLabel.excellent: 3,
}
REVIEWED_QUALITY_LEVELS = tuple(QUALITY_ORDER)
REVIEWED_GATES = {
    ExpectedInsightEligibility.normal,
    ExpectedInsightEligibility.cautious,
    ExpectedInsightEligibility.measurement_only,
    ExpectedInsightEligibility.insufficient_evidence,
}
INSIGHT_REVIEW_FIELDS = (
    "recording_quality_verdict_correct",
    "confidence_levels_justified",
    "measurement_only_decision_correct",
    "suppression_decision_correct",
    "interpretation_justified",
    "limitations_accurate",
    "wording_understandable",
    "action_appropriately_conservative",
    "recording_guidance_accurate",
)


@dataclass(frozen=True)
class _ArtifactContext:
    sample: CalibrationSample
    artifact_root: Path
    metadata: VideoMetadataReport | None
    job: AnalysisJob | None
    tracking: PlayerTrackingReport | None
    candidates: PlayerCandidateCollection | None
    normalized_candidates: tuple[PlayerCandidate, ...]
    analytics: AnalyticsReport | None
    timeline: TimelineReport | None
    persisted_match_iq: MatchIQReport | None
    active_play: ActivePlayReport | None
    calibration_available: bool
    artifacts: tuple[ArtifactEvaluation, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _EvaluatedSample:
    sample: CalibrationSample
    context: _ArtifactContext
    assessment: RecordingQualityAssessment | None
    current_match_iq: MatchIQReport | None
    result: SampleCalibrationResult


def evaluate_manifest(
    loaded: LoadedCalibrationManifest,
    *,
    repository_root: Path,
    allow_expensive_recomputation: bool = False,
) -> CalibrationResults:
    """Evaluate reusable artifacts without mutating artifacts or reviewer labels."""

    root = repository_root.expanduser().resolve()
    evaluated: list[_EvaluatedSample] = []
    for sample in loaded.manifest.samples:
        try:
            evaluated.append(
                _evaluate_sample(
                    sample,
                    manifest=loaded.manifest,
                    repository_root=root,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one malformed sample must not stop the set.
            result = SampleCalibrationResult(
                sample_id=sample.sample_id,
                status=SampleEvaluationStatus.failed,
                review_status=sample.review_status,
                expected_recording_quality=_expected_quality(sample),
                expected_insight_eligibility=sample.expected_insight_eligibility,
                errors=[f"Unexpected sample evaluation failure: {type(exc).__name__}: {exc}"],
                inference_recomputed=False,
            )
            empty_context = _ArtifactContext(
                sample=sample,
                artifact_root=root,
                metadata=None,
                job=None,
                tracking=None,
                candidates=None,
                normalized_candidates=(),
                analytics=None,
                timeline=None,
                persisted_match_iq=None,
                active_play=None,
                calibration_available=False,
                artifacts=(),
                warnings=(),
                errors=tuple(result.errors),
            )
            evaluated.append(
                _EvaluatedSample(
                    sample=sample,
                    context=empty_context,
                    assessment=None,
                    current_match_iq=None,
                    result=result,
                )
            )

    metrics = _aggregate_metrics(evaluated, loaded.manifest.minimum_recommended_sample_size)
    common_failures = _common_failure_reasons(evaluated)
    policy_errors = _policy_error_reasons(evaluated)
    balance = summarize_dataset_balance(loaded.manifest)
    disagreements = _build_disagreements(evaluated)
    threshold_analysis = _threshold_analysis(
        evaluated,
        loaded.manifest,
    )
    active_play_threshold_analysis = _active_play_threshold_analysis(
        evaluated,
        loaded.manifest,
    )
    manual_review = sorted(
        item.sample.sample_id for item in evaluated if _requires_manual_review(item)
    )
    reviewed = sum(item.sample.review_status != ReviewStatus.not_reviewed for item in evaluated)
    return CalibrationResults(
        dataset_id=loaded.manifest.dataset_id,
        dataset_version=loaded.manifest.dataset_version,
        manifest_sha256=loaded.sha256,
        recording_policy_version=RECORDING_QUALITY_POLICY_VERSION,
        recording_policy_sha256=canonical_policy_sha256(QUALITY_THRESHOLDS),
        active_play_policy_version=ACTIVE_PLAY_POLICY.version,
        active_play_policy_sha256=canonical_policy_sha256(ACTIVE_PLAY_POLICY),
        generated_at=loaded.manifest.reference_time,
        expensive_recomputation_enabled=allow_expensive_recomputation,
        expensive_inference_runs=0,
        sample_count=len(evaluated),
        reviewed_sample_count=reviewed,
        unreviewed_sample_count=len(evaluated) - reviewed,
        samples=[item.result for item in evaluated],
        metrics=metrics,
        common_failure_reasons=common_failures,
        policy_error_reasons=policy_errors,
        dataset_balance=balance,
        disagreements=disagreements,
        threshold_analysis=threshold_analysis,
        active_play_threshold_analysis=active_play_threshold_analysis,
        samples_requiring_manual_review=manual_review,
        dataset_limitations=_dataset_limitations(evaluated, loaded.manifest),
    )


def _evaluate_sample(
    sample: CalibrationSample,
    *,
    manifest: CalibrationManifest,
    repository_root: Path,
) -> _EvaluatedSample:
    context = _load_artifacts(sample, repository_root)
    assessment = _assessment_for(
        context,
        assessed_at=manifest.reference_time,
        thresholds=QUALITY_THRESHOLDS,
    )
    current_match_iq = (
        generate_match_iq(
            analytics=context.analytics,
            timeline=context.timeline,
            recording_quality=assessment,
            created_at=manifest.reference_time,
        )
        if context.analytics is not None
        else None
    )
    system_quality = (
        CalibrationQualityLabel(assessment.status.value) if assessment is not None else None
    )
    system_gate = _system_gate(system_quality, current_match_iq)
    expected_quality = _expected_quality(sample)
    quality_delta = (
        QUALITY_ORDER[system_quality] - QUALITY_ORDER[expected_quality]
        if system_quality in QUALITY_ORDER and expected_quality in QUALITY_ORDER
        else None
    )
    exact = quality_delta == 0 if quality_delta is not None else None
    acceptable = abs(quality_delta) <= 1 if quality_delta is not None else None
    gate_agreement = (
        system_gate == sample.expected_insight_eligibility
        if system_gate is not None and sample.expected_insight_eligibility in REVIEWED_GATES
        else None
    )
    warnings = list(context.warnings)
    errors = list(context.errors)
    if assessment is not None:
        warnings.extend(f"quality_policy:{code}" for code in assessment.reason_codes)
    status = (
        SampleEvaluationStatus.evaluated
        if not warnings and not errors
        else SampleEvaluationStatus.partial
    )
    if assessment is None and system_gate is None:
        status = SampleEvaluationStatus.failed
    normalized = context.normalized_candidates
    result = SampleCalibrationResult(
        sample_id=sample.sample_id,
        status=status,
        review_status=sample.review_status,
        system_recording_quality=system_quality,
        expected_recording_quality=expected_quality,
        recording_quality_delta=quality_delta,
        exact_quality_agreement=exact,
        acceptable_quality_agreement=acceptable,
        system_insight_eligibility=system_gate,
        expected_insight_eligibility=sample.expected_insight_eligibility,
        insight_eligibility_agreement=gate_agreement,
        candidate_count=(
            len(context.candidates.candidates) + len(context.candidates.excluded_candidates)
            if context.candidates is not None
            else None
        ),
        selectable_candidate_count=(
            sum(candidate.selection_eligible for candidate in normalized)
            if context.candidates is not None
            else None
        ),
        selected_candidate_id=(
            context.candidates.selected_candidate_id if context.candidates is not None else None
        ),
        active_play_generated=context.active_play is not None,
        active_play_policy_version=(
            context.active_play.policy_version if context.active_play is not None else None
        ),
        active_play_interval_count=(
            len(context.active_play.intervals) if context.active_play is not None else 0
        ),
        active_play_candidate_schema_version=(
            context.active_play.source_artifacts.candidate_schema_version
            if context.active_play is not None
            else None
        ),
        active_play_state_seconds=(
            {
                ActivePlayState.likely_active.value: (
                    context.active_play.summary.likely_active_seconds
                ),
                ActivePlayState.likely_idle.value: (
                    context.active_play.summary.likely_idle_seconds
                ),
                ActivePlayState.unknown.value: context.active_play.summary.unknown_seconds,
            }
            if context.active_play is not None
            else {}
        ),
        active_play_unknown_coverage=(
            (
                context.active_play.summary.unknown_seconds
                / context.active_play.summary.source_duration_seconds
            )
            if context.active_play is not None
            and context.active_play.summary.source_duration_seconds > 0
            else None
        ),
        artifacts=list(context.artifacts),
        warnings=list(dict.fromkeys(warnings)),
        errors=errors,
        inference_recomputed=False,
        artifact_readiness=_artifact_readiness(context.artifacts),
    )
    return _EvaluatedSample(
        sample=sample,
        context=context,
        assessment=assessment,
        current_match_iq=current_match_iq,
        result=result,
    )


def _load_artifacts(sample: CalibrationSample, repository_root: Path) -> _ArtifactContext:
    reuse = sample.artifacts
    artifact_root = (repository_root / reuse.artifact_root).resolve()
    try:
        artifact_root.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError("Artifact root resolves outside the repository.") from exc

    artifacts: list[ArtifactEvaluation] = []
    warnings: list[str] = []
    errors: list[str] = []

    metadata = _load_standard_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.inspection_analysis_id,
        relative_path="metadata.json",
        label="inspection_metadata",
        model=VideoMetadataReport,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
    job = _load_standard_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.inspection_analysis_id,
        relative_path="job.json",
        label="analysis_job",
        model=AnalysisJob,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        required=False,
    )
    tracking = _load_standard_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.tracking_analysis_id,
        relative_path="tracking/tracking.json",
        label="tracking",
        model=PlayerTrackingReport,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
    candidates, candidate_payload = _load_versioned_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.candidates_analysis_id,
        relative_path="tracking/player_candidates.json",
        label="player_candidates",
        model=PlayerCandidateCollection,
        expected_version=str(CANDIDATE_SCHEMA_VERSION),
        version_key="schema_version",
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
    analytics = _load_standard_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.analytics_analysis_id,
        relative_path="analytics/analytics.json",
        label="analytics",
        model=AnalyticsReport,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
    timeline = _load_standard_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.analytics_analysis_id,
        relative_path="analytics/timeline.json",
        label="timeline",
        model=TimelineReport,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        required=False,
    )
    persisted_match_iq, _ = _load_versioned_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.match_iq_analysis_id,
        relative_path="analytics/match_iq.json",
        label="match_iq",
        model=MatchIQReport,
        expected_version=MATCH_IQ_ENGINE_VERSION,
        version_key="engine_version",
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        required=False,
    )
    active_play, _ = _load_versioned_artifact(
        artifact_root=artifact_root,
        analysis_id=reuse.active_play_analysis_id,
        relative_path="active_play/active_play.json",
        label="active_play",
        model=ActivePlayReport,
        expected_version=ACTIVE_PLAY_POLICY_VERSION,
        version_key="policy_version",
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        required=False,
    )

    court_reference, court_readiness = _find_calibration(
        artifact_root,
        reuse.court_analysis_id,
    )
    calibration_available = court_readiness == ArtifactReadiness.ready
    if reuse.court_analysis_id is None:
        artifacts.append(_not_referenced("court_calibration"))
    elif court_readiness == ArtifactReadiness.ready:
        artifacts.append(
            ArtifactEvaluation(
                artifact="court_calibration",
                reference=court_reference,
                status=ArtifactEvaluationStatus.available,
                schema_or_engine_version="UNVERSIONED",
                expected_version="UNVERSIONED",
                compatibility=ArtifactReadiness.ready,
                message="A persisted court calibration is available.",
            )
        )
    elif court_readiness == ArtifactReadiness.missing:
        reference = (
            f"{reuse.artifact_root}/{reuse.court_analysis_id}/calibrations/*/calibration.json"
        )
        artifacts.append(
            ArtifactEvaluation(
                artifact="court_calibration",
                reference=reference,
                status=ArtifactEvaluationStatus.missing,
                schema_or_engine_version=None,
                expected_version="UNVERSIONED",
                compatibility=ArtifactReadiness.missing,
                message="No persisted court calibration was found.",
            )
        )
        warnings.append("missing_artifact:court_calibration")
    else:
        artifacts.append(
            ArtifactEvaluation(
                artifact="court_calibration",
                reference=court_reference,
                status=ArtifactEvaluationStatus.invalid,
                schema_or_engine_version="UNVERSIONED",
                expected_version="UNVERSIONED",
                compatibility=ArtifactReadiness.incompatible,
                message="The persisted court calibration could not be validated.",
            )
        )
        errors.append("invalid_artifact:court_calibration")

    normalized_candidates = (
        tuple(_normalize_candidate_eligibility(candidates)) if candidates is not None else ()
    )
    if candidate_payload is not None and candidate_payload.get("schema_version") != (
        CANDIDATE_SCHEMA_VERSION
    ):
        warnings.append("stale_artifact:player_candidates")

    return _ArtifactContext(
        sample=sample,
        artifact_root=artifact_root,
        metadata=metadata,
        job=job,
        tracking=tracking,
        candidates=candidates,
        normalized_candidates=normalized_candidates,
        analytics=analytics,
        timeline=timeline,
        persisted_match_iq=persisted_match_iq,
        active_play=active_play,
        calibration_available=calibration_available,
        artifacts=tuple(artifacts),
        warnings=tuple(dict.fromkeys(warnings)),
        errors=tuple(errors),
    )


def _load_standard_artifact[ModelT: BaseModel](
    *,
    artifact_root: Path,
    analysis_id: str | None,
    relative_path: str,
    label: str,
    model: type[ModelT],
    artifacts: list[ArtifactEvaluation],
    warnings: list[str],
    errors: list[str],
    required: bool = True,
) -> ModelT | None:
    if analysis_id is None:
        artifacts.append(_not_referenced(label))
        return None
    path = artifact_root / analysis_id / relative_path
    reference = _display_reference(artifact_root, analysis_id, relative_path)
    if not path.is_file():
        artifacts.append(
            ArtifactEvaluation(
                artifact=label,
                reference=reference,
                status=ArtifactEvaluationStatus.missing,
                expected_version="UNVERSIONED",
                compatibility=ArtifactReadiness.missing,
                message="The referenced artifact is missing.",
            )
        )
        if required:
            warnings.append(f"missing_artifact:{label}")
        return None
    try:
        value, _ = _read_model(path, model)
    except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        artifacts.append(
            ArtifactEvaluation(
                artifact=label,
                reference=reference,
                status=ArtifactEvaluationStatus.invalid,
                expected_version="UNVERSIONED",
                compatibility=ArtifactReadiness.incompatible,
                message=f"The artifact could not be validated: {type(exc).__name__}.",
            )
        )
        errors.append(f"invalid_artifact:{label}")
        return None
    artifacts.append(
        ArtifactEvaluation(
            artifact=label,
            reference=reference,
            status=ArtifactEvaluationStatus.available,
            schema_or_engine_version="UNVERSIONED",
            expected_version="UNVERSIONED",
            compatibility=ArtifactReadiness.ready,
            message="The persisted artifact was reused.",
        )
    )
    return value


def _load_versioned_artifact[ModelT: BaseModel](
    *,
    artifact_root: Path,
    analysis_id: str | None,
    relative_path: str,
    label: str,
    model: type[ModelT],
    expected_version: str,
    version_key: str,
    artifacts: list[ArtifactEvaluation],
    warnings: list[str],
    errors: list[str],
    required: bool = True,
) -> tuple[ModelT | None, dict[str, object] | None]:
    if analysis_id is None:
        artifacts.append(_not_referenced(label))
        return None, None
    path = artifact_root / analysis_id / relative_path
    reference = _display_reference(artifact_root, analysis_id, relative_path)
    if not path.is_file():
        artifacts.append(
            ArtifactEvaluation(
                artifact=label,
                reference=reference,
                status=ArtifactEvaluationStatus.missing,
                expected_version=expected_version,
                compatibility=ArtifactReadiness.missing,
                message="The referenced artifact is missing.",
            )
        )
        if required:
            warnings.append(f"missing_artifact:{label}")
        return None, None
    try:
        value, payload = _read_model(path, model)
    except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        artifacts.append(
            ArtifactEvaluation(
                artifact=label,
                reference=reference,
                status=ArtifactEvaluationStatus.invalid,
                expected_version=expected_version,
                compatibility=ArtifactReadiness.incompatible,
                message=f"The artifact could not be validated: {type(exc).__name__}.",
            )
        )
        errors.append(f"invalid_artifact:{label}")
        return None, None
    actual = str(payload.get(version_key, "missing"))
    stale = actual != expected_version
    artifacts.append(
        ArtifactEvaluation(
            artifact=label,
            reference=reference,
            status=(
                ArtifactEvaluationStatus.stale if stale else ArtifactEvaluationStatus.available
            ),
            schema_or_engine_version=actual,
            expected_version=expected_version,
            compatibility=(
                ArtifactReadiness.legacy_compatible if stale else ArtifactReadiness.ready
            ),
            message=(
                "The artifact is readable but uses a stale schema or engine version."
                if stale
                else "The persisted artifact was reused."
            ),
        )
    )
    if stale:
        warnings.append(f"stale_artifact:{label}")
    return value, payload


def _read_model[ModelT: BaseModel](
    path: Path,
    model: type[ModelT],
) -> tuple[ModelT, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Artifact root must be a JSON object.")
    return model.model_validate(payload), payload


def _find_calibration(
    artifact_root: Path,
    analysis_id: str | None,
) -> tuple[str | None, ArtifactReadiness]:
    if analysis_id is None:
        return None, ArtifactReadiness.missing
    analysis_root = artifact_root / analysis_id
    matches = sorted(analysis_root.glob("calibrations/*/calibration.json"))
    if not matches:
        return None, ArtifactReadiness.missing
    relative = matches[0].relative_to(artifact_root).as_posix()
    reference = f"{_display_root(artifact_root)}/{relative}"
    try:
        _read_model(matches[0], CourtCalibrationReport)
    except (OSError, ValueError, json.JSONDecodeError, ValidationError):
        return reference, ArtifactReadiness.incompatible
    return reference, ArtifactReadiness.ready


def _display_reference(artifact_root: Path, analysis_id: str, relative_path: str) -> str:
    return f"{_display_root(artifact_root)}/{analysis_id}/{relative_path}"


def _display_root(artifact_root: Path) -> str:
    return "/".join(artifact_root.parts[-2:])


def _not_referenced(label: str) -> ArtifactEvaluation:
    return ArtifactEvaluation(
        artifact=label,
        reference=None,
        status=ArtifactEvaluationStatus.not_referenced,
        compatibility=ArtifactReadiness.missing,
        message="No artifact reference was supplied for this stage.",
    )


def _artifact_readiness(artifacts: Sequence[ArtifactEvaluation]) -> ArtifactReadiness:
    if not artifacts or all(
        artifact.compatibility == ArtifactReadiness.missing for artifact in artifacts
    ):
        return ArtifactReadiness.missing
    if any(artifact.compatibility == ArtifactReadiness.incompatible for artifact in artifacts):
        return ArtifactReadiness.incompatible
    if any(artifact.compatibility == ArtifactReadiness.missing for artifact in artifacts):
        return ArtifactReadiness.partial
    if any(artifact.compatibility == ArtifactReadiness.legacy_compatible for artifact in artifacts):
        return ArtifactReadiness.legacy_compatible
    return ArtifactReadiness.ready


def _normalize_candidate_eligibility(
    collection: PlayerCandidateCollection,
) -> list[PlayerCandidate]:
    candidates = [*collection.candidates, *collection.excluded_candidates]
    normalized: list[PlayerCandidate] = []
    for candidate in candidates:
        reasons: list[str] = []
        if candidate.quality not in {CandidateQuality.strong, CandidateQuality.usable}:
            reasons.append("uncertain_player_candidate")
        if candidate.in_court_observation_ratio < THRESHOLDS.selectable_min_in_court_ratio:
            reasons.append("mostly_outside_detected_court")
        if (
            candidate.court_movement_rate_feet_per_second
            < THRESHOLDS.selectable_min_court_movement_rate_feet_per_second
        ):
            reasons.append("limited_court_movement")
        if len(candidate.source_raw_track_ids) > THRESHOLDS.selectable_max_fragment_count:
            reasons.append("excessive_track_fragmentation")
        normalized.append(
            candidate.model_copy(
                update={
                    "selection_eligible": not reasons,
                    "selection_exclusion_reasons": reasons,
                }
            )
        )

    eligible = [candidate for candidate in normalized if candidate.selection_eligible]
    kept = {
        candidate.candidate_id for candidate in eligible[: THRESHOLDS.max_selectable_candidates]
    }
    return [
        (
            candidate
            if not candidate.selection_eligible or candidate.candidate_id in kept
            else candidate.model_copy(
                update={
                    "selection_eligible": False,
                    "selection_exclusion_reasons": [
                        *candidate.selection_exclusion_reasons,
                        "outside_top_four_court_players",
                    ],
                }
            )
        )
        for candidate in normalized
    ]


def _assessment_for(
    context: _ArtifactContext,
    *,
    assessed_at: datetime,
    thresholds: RecordingQualityThresholds,
) -> RecordingQualityAssessment | None:
    if context.metadata is None:
        return None
    upload = assess_upload_preflight(
        context.metadata,
        assessed_at=assessed_at,
        thresholds=thresholds,
    )
    if context.candidates is None:
        return upload
    detected_people = (
        context.tracking.track_count
        if context.tracking is not None
        else context.candidates.recording_suitability.detected_people
    )
    selected_id = context.candidates.selected_candidate_id
    return assess_analysis_readiness(
        upload_preflight=upload,
        calibration_completed=context.calibration_available,
        court_detection_status=(
            context.job.court_detection_status.value
            if context.job is not None and context.job.court_detection_status is not None
            else None
        ),
        court_detection_confidence=(
            context.job.court_detection_confidence if context.job is not None else None
        ),
        detected_people=detected_people,
        candidates=context.normalized_candidates,
        selected_candidate_id=selected_id,
        assessed_at=assessed_at,
        thresholds=thresholds,
    )


def _system_gate(
    quality: CalibrationQualityLabel | None,
    current_match_iq: MatchIQReport | None,
) -> ExpectedInsightEligibility | None:
    if current_match_iq is not None:
        return ExpectedInsightEligibility(current_match_iq.quality_gate)
    if quality is None:
        return None
    return {
        CalibrationQualityLabel.excellent: ExpectedInsightEligibility.normal,
        CalibrationQualityLabel.good: ExpectedInsightEligibility.cautious,
        CalibrationQualityLabel.limited: ExpectedInsightEligibility.measurement_only,
        CalibrationQualityLabel.unsuitable: ExpectedInsightEligibility.insufficient_evidence,
    }.get(quality)


def _expected_quality(sample: CalibrationSample) -> CalibrationQualityLabel:
    review = sample.human_review.recording if sample.human_review is not None else None
    if review is not None and review.recording_quality_verdict in REVIEWED_QUALITY_LEVELS:
        return review.recording_quality_verdict
    return sample.expected_recording_quality


def _aggregate_metrics(
    evaluated: list[_EvaluatedSample],
    minimum_sample_size: int,
) -> CalibrationMetrics:
    quality_pairs = [
        (
            item.result.expected_recording_quality,
            item.result.system_recording_quality,
            item.result.recording_quality_delta,
        )
        for item in evaluated
        if item.result.expected_recording_quality in QUALITY_ORDER
        and item.result.system_recording_quality in QUALITY_ORDER
        and item.result.recording_quality_delta is not None
    ]
    exact_count = sum(delta == 0 for _, _, delta in quality_pairs)
    acceptable_count = sum(abs(delta) <= 1 for _, _, delta in quality_pairs)
    labels = [level.value for level in REVIEWED_QUALITY_LEVELS]
    matrix = {expected: {actual: 0 for actual in labels} for expected in labels}
    expected_counts = {label: 0 for label in labels}
    for expected, actual, _ in quality_pairs:
        matrix[expected.value][actual.value] += 1
        expected_counts[expected.value] += 1
    quality_metrics = RecordingQualityMetrics(
        exact_agreement=_count_metric(exact_count, len(quality_pairs), minimum_sample_size),
        acceptable_agreement=_count_metric(
            acceptable_count,
            len(quality_pairs),
            minimum_sample_size,
        ),
        overestimation_count=sum(delta > 0 for _, _, delta in quality_pairs),
        underestimation_count=sum(delta < 0 for _, _, delta in quality_pairs),
        confusion_matrix=matrix,
        per_expected_status_count=expected_counts,
    )

    gate_pairs = [
        (item.result.expected_insight_eligibility, item.result.system_insight_eligibility)
        for item in evaluated
        if item.result.expected_insight_eligibility in REVIEWED_GATES
        and item.result.system_insight_eligibility in REVIEWED_GATES
    ]
    valid_pairs = [
        pair
        for pair in gate_pairs
        if pair[0] in {ExpectedInsightEligibility.normal, ExpectedInsightEligibility.cautious}
    ]
    weak_pairs = [
        pair for pair in gate_pairs if pair[0] == ExpectedInsightEligibility.measurement_only
    ]
    unsuitable_pairs = [
        pair for pair in gate_pairs if pair[0] == ExpectedInsightEligibility.insufficient_evidence
    ]
    evidence_metrics = EvidenceGateMetrics(
        valid_insights_correctly_allowed=_count_metric(
            sum(
                actual in {ExpectedInsightEligibility.normal, ExpectedInsightEligibility.cautious}
                for _, actual in valid_pairs
            ),
            len(valid_pairs),
            minimum_sample_size,
        ),
        weak_insights_correctly_measurement_only=_count_metric(
            sum(actual == ExpectedInsightEligibility.measurement_only for _, actual in weak_pairs),
            len(weak_pairs),
            minimum_sample_size,
        ),
        unsuitable_insights_correctly_suppressed=_count_metric(
            sum(
                actual == ExpectedInsightEligibility.insufficient_evidence
                for _, actual in unsuitable_pairs
            ),
            len(unsuitable_pairs),
            minimum_sample_size,
        ),
        valid_insights_incorrectly_suppressed=sum(
            actual == ExpectedInsightEligibility.insufficient_evidence for _, actual in valid_pairs
        ),
        weak_insights_incorrectly_allowed=sum(
            actual in {ExpectedInsightEligibility.normal, ExpectedInsightEligibility.cautious}
            for _, actual in weak_pairs
        ),
        unsuitable_insights_incorrectly_allowed=sum(
            actual != ExpectedInsightEligibility.insufficient_evidence
            for _, actual in unsuitable_pairs
        ),
    )

    candidate_reviews = [
        item.sample.human_review.player_candidates
        for item in evaluated
        if item.sample.human_review is not None
        and item.sample.human_review.player_candidates is not None
    ]
    recall_reviews = [
        review
        for review in candidate_reviews
        if review.expected_court_player_count is not None
        and review.expected_players_represented is not None
    ]
    expected_players = sum(review.expected_court_player_count or 0 for review in recall_reviews)
    represented_players = sum(review.expected_players_represented or 0 for review in recall_reviews)
    selected_labels = [
        review.selected_player_identity_correct
        for review in candidate_reviews
        if review.selected_player_identity_correct is not None
    ]
    mappings = [mapping for review in candidate_reviews for mapping in review.candidate_mappings]
    precision_mappings = [
        mapping
        for mapping in mappings
        if mapping.role
        in {
            CandidateRole.court_player,
            CandidateRole.duplicate,
            CandidateRole.spectator,
            CandidateRole.false_detection,
        }
    ]
    mapping_labels = [
        mapping.mapping_correct
        for mapping in mappings
        if mapping.mapping_correct in {ReviewValue.yes, ReviewValue.no}
    ]
    duplicate_labeled_reviews = [
        review
        for review in candidate_reviews
        if review.duplicate_candidates is not None or review.candidate_mappings
    ]
    missed_labeled_reviews = [
        review for review in candidate_reviews if review.missed_players is not None
    ]
    duplicate_total = sum(
        (
            review.duplicate_candidates
            if review.duplicate_candidates is not None
            else sum(
                mapping.role == CandidateRole.duplicate for mapping in review.candidate_mappings
            )
        )
        for review in duplicate_labeled_reviews
    )
    missed_total = sum(review.missed_players or 0 for review in missed_labeled_reviews)
    candidate_metrics = CandidateReliabilityMetrics(
        expected_player_recall=_count_metric_with_sample_count(
            represented_players,
            expected_players,
            minimum_sample_size,
            sample_count=len(recall_reviews),
        ),
        duplicate_candidate_count=_review_count_with_mapping_fallback(
            candidate_reviews,
            "duplicate_candidates",
            CandidateRole.duplicate,
        ),
        missed_player_count=_optional_review_count(candidate_reviews, "missed_players"),
        spectator_promotion_count=_review_count_with_mapping_fallback(
            candidate_reviews,
            "spectators_incorrectly_promoted",
            CandidateRole.spectator,
        ),
        selected_player_identity_accuracy=_count_metric(
            sum(value is True for value in selected_labels),
            len(selected_labels),
            minimum_sample_size,
        ),
        candidate_precision=_count_metric_with_sample_count(
            sum(mapping.role == CandidateRole.court_player for mapping in precision_mappings),
            len(precision_mappings),
            minimum_sample_size,
            sample_count=len(
                {
                    item.sample.sample_id
                    for item in evaluated
                    if item.sample.human_review is not None
                    and item.sample.human_review.player_candidates is not None
                    and item.sample.human_review.player_candidates.candidate_mappings
                }
            ),
        ),
        candidate_to_player_mapping_accuracy=_count_metric(
            sum(value == ReviewValue.yes for value in mapping_labels),
            len(mapping_labels),
            minimum_sample_size,
        ),
        duplicate_candidates_per_sample=_raw_per_sample_metric(
            duplicate_total,
            len(duplicate_labeled_reviews),
            minimum_sample_size,
        ),
        missed_players_per_sample=_raw_per_sample_metric(
            missed_total,
            len(missed_labeled_reviews),
            minimum_sample_size,
        ),
        labeled_sample_counts={
            "player_recall": len(recall_reviews),
            "duplicate_candidates": sum(
                review.duplicate_candidates is not None or bool(review.candidate_mappings)
                for review in candidate_reviews
            ),
            "missed_players": sum(
                review.missed_players is not None for review in candidate_reviews
            ),
            "spectator_promotions": sum(
                review.spectators_incorrectly_promoted is not None
                or bool(review.candidate_mappings)
                for review in candidate_reviews
            ),
            "selected_identity": len(selected_labels),
            "candidate_precision": sum(
                bool(review.candidate_mappings) for review in candidate_reviews
            ),
            "candidate_mapping_accuracy": sum(
                any(
                    mapping.mapping_correct in {ReviewValue.yes, ReviewValue.no}
                    for mapping in review.candidate_mappings
                )
                for review in candidate_reviews
            ),
        },
    )

    tracking_reviews = [
        item.sample.human_review.tracking
        for item in evaluated
        if item.sample.human_review is not None and item.sample.human_review.tracking is not None
    ]
    intervals = [interval for review in tracking_reviews for interval in review.intervals]
    maintained_labels = [
        interval
        for interval in intervals
        if interval.identity_correct in {ReviewValue.yes, ReviewValue.no}
        and interval.continuity in {ContinuityLabel.acceptable, ContinuityLabel.broken}
    ]
    observed_labels = [
        interval.observed_time_agreement
        for interval in intervals
        if interval.observed_time_agreement in {ReviewValue.yes, ReviewValue.no}
    ]
    gap_labels = [
        interval.gap_label_agreement
        for interval in intervals
        if interval.gap_label_agreement in {ReviewValue.yes, ReviewValue.no}
    ]
    tracking_metrics = TrackingContinuityMetrics(
        reviewed_interval_count=len(intervals),
        correctly_maintained_identity_intervals=_count_metric(
            sum(
                interval.identity_correct == ReviewValue.yes
                and interval.continuity == ContinuityLabel.acceptable
                for interval in maintained_labels
            ),
            len(maintained_labels),
            minimum_sample_size,
        ),
        identity_switch_intervals=sum(
            interval.identity_correct == ReviewValue.no for interval in intervals
        ),
        fragmented_intervals=sum(
            interval.continuity == ContinuityLabel.broken for interval in intervals
        ),
        valid_observed_time_agreement=_count_metric(
            sum(value == ReviewValue.yes for value in observed_labels),
            len(observed_labels),
            minimum_sample_size,
        ),
        gap_label_agreement=_count_metric(
            sum(value == ReviewValue.yes for value in gap_labels),
            len(gap_labels),
            minimum_sample_size,
        ),
    )

    insight_reviews = [
        item.sample.human_review.insight
        for item in evaluated
        if item.sample.human_review is not None and item.sample.human_review.insight is not None
    ]
    insight_fields: dict[str, CountMetric] = {}
    for field_name in INSIGHT_REVIEW_FIELDS:
        labels_for_field = [
            value
            for review in insight_reviews
            if (value := getattr(review, field_name)) is not None
        ]
        insight_fields[field_name] = _count_metric(
            sum(value is True for value in labels_for_field),
            len(labels_for_field),
            minimum_sample_size,
        )
    generated_insights = [
        insight for review in insight_reviews for insight in review.generated_insights
    ]
    generated_fields = {
        "generated_measurement_correctness": "measurement_correct",
        "generated_interpretation_justification": "interpretation_justified",
        "generated_confidence_appropriateness": "confidence_appropriate",
        "generated_limitation_accuracy": "limitation_accurate",
        "generated_conservative_action_agreement": "action_conservative",
        "generated_wording_understandability": "wording_understandable",
    }
    for metric_name, field_name in generated_fields.items():
        labels_for_field = [
            value
            for insight in generated_insights
            if (value := getattr(insight, field_name)) in {ReviewValue.yes, ReviewValue.no}
        ]
        insight_fields[metric_name] = _count_metric(
            sum(value == ReviewValue.yes for value in labels_for_field),
            len(labels_for_field),
            minimum_sample_size,
        )
    active_play_metrics = _active_play_metrics(evaluated, minimum_sample_size)
    return CalibrationMetrics(
        recording_quality=quality_metrics,
        evidence_gates=evidence_metrics,
        candidate_reliability=candidate_metrics,
        tracking_continuity=tracking_metrics,
        active_play=active_play_metrics,
        insight_integrity=InsightIntegrityMetrics(fields=insight_fields),
    )


def _active_play_metrics(
    evaluated: Sequence[_EvaluatedSample],
    minimum_sample_size: int,
) -> ActivePlayCalibrationMetrics:
    intervals = [
        interval
        for item in evaluated
        if item.sample.human_review is not None and item.sample.human_review.active_play is not None
        for interval in item.sample.human_review.active_play.intervals
    ]
    reviewed = [
        interval
        for interval in intervals
        if interval.expected_state
        in {
            ExpectedActivePlayState.likely_active,
            ExpectedActivePlayState.likely_idle,
        }
        and not interval.uncertain_human_label
    ]
    active = [
        interval
        for interval in reviewed
        if interval.expected_state == ExpectedActivePlayState.likely_active
    ]
    idle = [
        interval
        for interval in reviewed
        if interval.expected_state == ExpectedActivePlayState.likely_idle
    ]

    def duration(interval: Any) -> float:
        return float(interval.end_time_seconds - interval.start_time_seconds)

    reviewed_seconds = sum(duration(interval) for interval in reviewed)
    active_seconds = sum(duration(interval) for interval in active)
    idle_seconds = sum(duration(interval) for interval in idle)
    active_agreement_seconds = sum(
        duration(interval)
        for interval in active
        if interval.court4_state == ActivePlayState.likely_active
    )
    idle_agreement_seconds = sum(
        duration(interval)
        for interval in idle
        if interval.court4_state == ActivePlayState.likely_idle
    )
    false_active = [
        interval
        for interval in reviewed
        if interval.false_active is True
        or (
            interval.expected_state == ExpectedActivePlayState.likely_idle
            and interval.court4_state == ActivePlayState.likely_active
        )
    ]
    false_idle = [
        interval
        for interval in reviewed
        if interval.false_idle is True
        or (
            interval.expected_state == ExpectedActivePlayState.likely_active
            and interval.court4_state == ActivePlayState.likely_idle
        )
    ]
    unknown = [
        interval
        for interval in reviewed
        if interval.court4_state == ActivePlayState.unknown
        or (interval.court4_state is None and interval.unknown_but_reviewable is True)
    ]
    covered = [interval for interval in reviewed if interval.court4_state is not None]
    boundary_errors: list[tuple[float, float]] = []
    for interval in reviewed:
        if (
            interval.court4_start_time_seconds is not None
            and interval.court4_end_time_seconds is not None
        ):
            boundary_errors.extend(
                [
                    (
                        abs(interval.court4_start_time_seconds - interval.start_time_seconds),
                        interval.boundary_tolerance_seconds,
                    ),
                    (
                        abs(interval.court4_end_time_seconds - interval.end_time_seconds),
                        interval.boundary_tolerance_seconds,
                    ),
                ]
            )
    provisional = len(reviewed) < minimum_sample_size
    note = (
        "Raw reviewed duration only; this dataset is too small for broad accuracy claims."
        if provisional
        else None
    )
    return ActivePlayCalibrationMetrics(
        reviewed_duration=DurationMetric(
            seconds=reviewed_seconds,
            interval_count=len(reviewed),
        ),
        likely_active_agreement=_duration_rate(
            active_agreement_seconds,
            active_seconds,
            len(active),
            provisional,
            note,
        ),
        likely_idle_agreement=_duration_rate(
            idle_agreement_seconds,
            idle_seconds,
            len(idle),
            provisional,
            note,
        ),
        false_active=DurationMetric(
            seconds=sum(duration(interval) for interval in false_active),
            interval_count=len(false_active),
        ),
        false_idle=DurationMetric(
            seconds=sum(duration(interval) for interval in false_idle),
            interval_count=len(false_idle),
        ),
        unknown=DurationMetric(
            seconds=sum(duration(interval) for interval in unknown),
            interval_count=len(unknown),
        ),
        boundary_error=BoundaryErrorMetric(
            boundary_count=len(boundary_errors),
            mean_absolute_seconds=(
                sum(error for error, _ in boundary_errors) / len(boundary_errors)
                if boundary_errors
                else None
            ),
            maximum_absolute_seconds=(
                max(error for error, _ in boundary_errors) if boundary_errors else None
            ),
            within_tolerance_count=sum(error <= tolerance for error, tolerance in boundary_errors),
        ),
        abstention_rate=_duration_rate(
            sum(duration(interval) for interval in unknown),
            reviewed_seconds,
            len(unknown),
            provisional,
            note,
        ),
        coverage_rate=_duration_rate(
            sum(duration(interval) for interval in covered),
            reviewed_seconds,
            len(covered),
            provisional,
            note,
        ),
    )


def _duration_rate(
    numerator_seconds: float,
    denominator_seconds: float,
    interval_count: int,
    provisional: bool,
    note: str | None,
) -> DurationRateMetric:
    return DurationRateMetric(
        numerator_seconds=numerator_seconds,
        denominator_seconds=denominator_seconds,
        percentage=(
            numerator_seconds / denominator_seconds * 100 if denominator_seconds > 0 else None
        ),
        interval_count=interval_count,
        provisional=provisional,
        note=note,
    )


def _count_metric(numerator: int, denominator: int, minimum_sample_size: int) -> CountMetric:
    return _count_metric_with_sample_count(
        numerator,
        denominator,
        minimum_sample_size,
        sample_count=denominator,
    )


def _count_metric_with_sample_count(
    numerator: int,
    denominator: int,
    minimum_sample_size: int,
    *,
    sample_count: int,
) -> CountMetric:
    percentage = round(numerator / denominator * 100, 1) if denominator else None
    provisional = sample_count < minimum_sample_size
    note = (
        f"Provisional: reviewed sample count {sample_count} is below the recommended "
        f"minimum of {minimum_sample_size}."
        if provisional
        else None
    )
    return CountMetric(
        numerator=numerator,
        denominator=denominator,
        percentage=percentage,
        provisional=provisional,
        note=note,
    )


def _raw_per_sample_metric(
    total_count: int,
    labeled_sample_count: int,
    minimum_sample_size: int,
) -> CountMetric:
    provisional = labeled_sample_count < minimum_sample_size
    note = (
        f"Raw total across {labeled_sample_count} labeled samples; a percentage is not meaningful."
    )
    if provisional:
        note += f" Coverage is provisional below {minimum_sample_size} reviewed samples."
    return CountMetric(
        numerator=total_count,
        denominator=labeled_sample_count,
        percentage=None,
        provisional=provisional,
        note=note,
    )


def _optional_review_count(
    reviews: Sequence[PlayerCandidateReview],
    field_name: str,
) -> int | None:
    values: list[int] = []
    for review in reviews:
        value = getattr(review, field_name)
        if isinstance(value, int):
            values.append(value)
    return sum(values) if values else None


def _review_count_with_mapping_fallback(
    reviews: Sequence[PlayerCandidateReview],
    field_name: str,
    role: CandidateRole,
) -> int | None:
    values: list[int] = []
    for review in reviews:
        explicit = getattr(review, field_name)
        mappings = review.candidate_mappings
        if isinstance(explicit, int):
            values.append(explicit)
        elif mappings:
            values.append(sum(mapping.role == role for mapping in mappings))
    return sum(values) if values else None


def _threshold_analysis(
    evaluated: list[_EvaluatedSample],
    manifest: CalibrationManifest,
) -> list[ThresholdSimulationResult]:
    supported = {field.name for field in fields(RecordingQualityThresholds)}
    eligible = [item for item in evaluated if item.sample.dataset_split == DatasetSplit.development]
    excluded = sorted(
        item.sample.sample_id
        for item in evaluated
        if item.sample.dataset_split != DatasetSplit.development
    )
    results: list[ThresholdSimulationResult] = []
    for simulation in manifest.threshold_simulations:
        if simulation.threshold not in supported:
            results.append(
                ThresholdSimulationResult(
                    threshold=simulation.threshold,
                    current_value=0,
                    proposed_value=simulation.proposed_value,
                    affected_samples=[],
                    improvements=[],
                    regressions=[],
                    unchanged_samples=len(eligible),
                    excluded_samples=excluded,
                    exploratory=True,
                    remaining_uncertainty=(
                        "Unsupported threshold name; no production or simulated policy was changed."
                    ),
                )
            )
            continue
        current_value = float(getattr(QUALITY_THRESHOLDS, simulation.threshold))
        proposed = replace(
            QUALITY_THRESHOLDS,
            **cast(Any, {simulation.threshold: simulation.proposed_value}),
        )
        affected: list[str] = []
        improvements: list[str] = []
        regressions: list[str] = []
        unchanged = 0
        for item in eligible:
            simulated = _assessment_for(
                item.context,
                assessed_at=manifest.reference_time,
                thresholds=proposed,
            )
            simulated_quality = (
                CalibrationQualityLabel(simulated.status.value) if simulated is not None else None
            )
            current_quality = item.result.system_recording_quality
            expected = item.result.expected_recording_quality
            if simulated_quality == current_quality:
                unchanged += 1
                continue
            affected.append(item.sample.sample_id)
            current_exact = current_quality == expected
            simulated_exact = simulated_quality == expected
            if not current_exact and simulated_exact:
                improvements.append(item.sample.sample_id)
            elif current_exact and not simulated_exact:
                regressions.append(item.sample.sample_id)
        results.append(
            ThresholdSimulationResult(
                threshold=simulation.threshold,
                current_value=current_value,
                proposed_value=simulation.proposed_value,
                affected_samples=affected,
                improvements=improvements,
                regressions=regressions,
                unchanged_samples=unchanged,
                excluded_samples=excluded,
                exploratory=True,
                remaining_uncertainty=(
                    "Exploratory development-split simulation only. Validation and holdout "
                    "samples are excluded. The dataset is too small for a production "
                    "recommendation, and production policy is not mutated."
                ),
            )
        )
    return results


def _active_play_threshold_analysis(
    evaluated: list[_EvaluatedSample],
    manifest: CalibrationManifest,
) -> list[ThresholdSimulationResult]:
    supported = {
        field.name
        for field in fields(type(ACTIVE_PLAY_POLICY))
        if field.name != "policy_version"
        and isinstance(getattr(ACTIVE_PLAY_POLICY, field.name), (int, float))
    }
    eligible = [item for item in evaluated if item.sample.dataset_split == DatasetSplit.development]
    excluded = sorted(
        item.sample.sample_id
        for item in evaluated
        if item.sample.dataset_split != DatasetSplit.development
    )
    results: list[ThresholdSimulationResult] = []
    for simulation in manifest.active_play_threshold_simulations:
        if simulation.threshold not in supported:
            results.append(
                ThresholdSimulationResult(
                    threshold=simulation.threshold,
                    current_value=0,
                    proposed_value=simulation.proposed_value,
                    affected_samples=[],
                    improvements=[],
                    regressions=[],
                    unchanged_samples=len(eligible),
                    excluded_samples=excluded,
                    exploratory=True,
                    remaining_uncertainty=(
                        "Unsupported Active Play threshold; production policy was unchanged."
                    ),
                )
            )
            continue

        current_value = float(getattr(ACTIVE_PLAY_POLICY, simulation.threshold))
        proposed = replace(
            ACTIVE_PLAY_POLICY,
            **cast(Any, {simulation.threshold: simulation.proposed_value}),
        )
        affected: list[str] = []
        improvements: list[str] = []
        regressions: list[str] = []
        unchanged = 0
        for item in eligible:
            review = (
                item.sample.human_review.active_play
                if item.sample.human_review is not None
                else None
            )
            report = item.context.active_play
            analysis_id = item.sample.artifacts.active_play_analysis_id
            if review is None or not review.intervals or report is None or analysis_id is None:
                unchanged += 1
                continue
            feature_path = (
                item.context.artifact_root / analysis_id / "active_play" / "features.jsonl"
            )
            try:
                features = [
                    MotionFeatureWindow.model_validate_json(line)
                    for line in feature_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except (OSError, ValidationError, ValueError):
                unchanged += 1
                continue
            simulated_windows = classify_motion_windows(
                features,
                source_duration_seconds=report.summary.source_duration_seconds,
                recording_quality=(
                    item.context.candidates.analysis_readiness
                    if item.context.candidates is not None
                    else None
                ),
                source_artifacts_current=(
                    report.source_artifacts.candidate_schema_version == CANDIDATE_SCHEMA_VERSION
                ),
                policy=proposed,
            )
            current_states = [
                _state_for_review_interval(
                    report.windows,
                    interval.start_time_seconds,
                    interval.end_time_seconds,
                )
                for interval in review.intervals
            ]
            simulated_states = [
                _state_for_review_interval(
                    simulated_windows,
                    interval.start_time_seconds,
                    interval.end_time_seconds,
                )
                for interval in review.intervals
            ]
            if current_states == simulated_states:
                unchanged += 1
                continue
            affected.append(item.sample.sample_id)
            current_matches = _active_play_review_match_count(review.intervals, current_states)
            simulated_matches = _active_play_review_match_count(review.intervals, simulated_states)
            if simulated_matches > current_matches:
                improvements.append(item.sample.sample_id)
            elif simulated_matches < current_matches:
                regressions.append(item.sample.sample_id)
        results.append(
            ThresholdSimulationResult(
                threshold=simulation.threshold,
                current_value=current_value,
                proposed_value=simulation.proposed_value,
                affected_samples=affected,
                improvements=improvements,
                regressions=regressions,
                unchanged_samples=unchanged,
                excluded_samples=excluded,
                exploratory=True,
                remaining_uncertainty=(
                    "Exploratory development-split shadow simulation only. Validation and "
                    "holdout samples are excluded; reviewer labels and active-play-v1 are "
                    "never mutated."
                ),
            )
        )
    return results


def _state_for_review_interval(
    windows: Sequence[Any],
    start_seconds: float,
    end_seconds: float,
) -> ActivePlayState:
    overlap_by_state = {state: 0.0 for state in ActivePlayState}
    for window in windows:
        overlap = max(
            0.0,
            min(end_seconds, window.end_seconds) - max(start_seconds, window.start_seconds),
        )
        overlap_by_state[window.state] += overlap
    if overlap_by_state[ActivePlayState.unknown] > 0:
        return ActivePlayState.unknown
    maximum = max(overlap_by_state.values(), default=0)
    leaders = [state for state, overlap in overlap_by_state.items() if overlap == maximum]
    if maximum <= 0 or len(leaders) != 1:
        return ActivePlayState.unknown
    return leaders[0]


def _active_play_review_match_count(
    intervals: Sequence[Any],
    states: Sequence[ActivePlayState],
) -> int:
    return sum(
        (
            interval.expected_state == ExpectedActivePlayState.likely_active
            and state == ActivePlayState.likely_active
        )
        or (
            interval.expected_state == ExpectedActivePlayState.likely_idle
            and state == ActivePlayState.likely_idle
        )
        for interval, state in zip(intervals, states, strict=True)
        if not interval.uncertain_human_label
    )


def _common_failure_reasons(evaluated: list[_EvaluatedSample]) -> dict[str, int]:
    reasons: Counter[str] = Counter()
    for item in evaluated:
        if item.assessment is not None:
            reasons.update(item.assessment.reason_codes)
        reasons.update(item.context.errors)
    return dict(sorted(reasons.items(), key=lambda entry: (-entry[1], entry[0])))


def _build_disagreements(
    evaluated: list[_EvaluatedSample],
) -> list[CalibrationDisagreement]:
    disagreements: list[CalibrationDisagreement] = []
    for item in evaluated:
        evidence = [
            f"{artifact.artifact}:{artifact.compatibility.value}"
            for artifact in item.result.artifacts
        ]
        if item.result.exact_quality_agreement is False:
            disagreements.append(
                CalibrationDisagreement(
                    sample_id=item.sample.sample_id,
                    category=DisagreementCategory.recording_assessment,
                    court4_output=_enum_text(item.result.system_recording_quality),
                    human_expectation=item.result.expected_recording_quality.value,
                    artifact_evidence=evidence,
                    reason="Court4 recording quality differs from the reviewed verdict.",
                    affected_threshold_or_rule="RecordingQualityThresholds",
                )
            )
        if item.result.insight_eligibility_agreement is False:
            disagreements.append(
                CalibrationDisagreement(
                    sample_id=item.sample.sample_id,
                    category=DisagreementCategory.insight_gating,
                    court4_output=_enum_text(item.result.system_insight_eligibility),
                    human_expectation=item.result.expected_insight_eligibility.value,
                    artifact_evidence=evidence,
                    reason="Court4 evidence gate differs from the reviewed gate.",
                    affected_threshold_or_rule="Match IQ quality gate",
                )
            )
        candidate_review = (
            item.sample.human_review.player_candidates
            if item.sample.human_review is not None
            else None
        )
        if candidate_review is not None:
            for mapping in candidate_review.candidate_mappings:
                if mapping.mapping_correct == ReviewValue.no:
                    disagreements.append(
                        CalibrationDisagreement(
                            sample_id=item.sample.sample_id,
                            category=DisagreementCategory.candidate_association,
                            court4_output=mapping.candidate_id,
                            human_expectation=(
                                f"{mapping.role.value}:{mapping.player_id or 'no-player'}"
                            ),
                            artifact_evidence=evidence,
                            reason="Reviewer marked the candidate-to-player mapping incorrect.",
                            affected_threshold_or_rule="candidate association",
                        )
                    )
        tracking_review = (
            item.sample.human_review.tracking if item.sample.human_review is not None else None
        )
        if tracking_review is not None:
            for interval in tracking_review.intervals:
                if (
                    interval.identity_correct == ReviewValue.no
                    or interval.continuity == ContinuityLabel.broken
                ):
                    disagreements.append(
                        CalibrationDisagreement(
                            sample_id=item.sample.sample_id,
                            category=DisagreementCategory.tracking_continuity,
                            court4_output=interval.candidate_id or "no candidate",
                            human_expectation=(
                                f"{interval.expected_player_id} from "
                                f"{interval.start_time_seconds:g}-"
                                f"{interval.end_time_seconds:g}s"
                            ),
                            artifact_evidence=evidence,
                            reason=(
                                "Reviewed interval contains an identity error or broken continuity."
                            ),
                            affected_threshold_or_rule="tracking continuity",
                        )
                    )
        insight_review = (
            item.sample.human_review.insight if item.sample.human_review is not None else None
        )
        if insight_review is not None:
            insight_fields = (
                ("measurement_correct", DisagreementCategory.measurement),
                ("interpretation_justified", DisagreementCategory.insight_gating),
                ("confidence_appropriate", DisagreementCategory.insight_gating),
                ("limitation_accurate", DisagreementCategory.insight_gating),
                ("action_conservative", DisagreementCategory.insight_gating),
                ("wording_understandable", DisagreementCategory.wording),
            )
            for insight in insight_review.generated_insights:
                for field_name, category in insight_fields:
                    if getattr(insight, field_name) == ReviewValue.no:
                        disagreements.append(
                            CalibrationDisagreement(
                                sample_id=item.sample.sample_id,
                                category=category,
                                court4_output=f"{insight.insight_id}:{field_name}",
                                human_expectation="YES",
                                artifact_evidence=evidence,
                                reason=f"Reviewer marked {field_name} incorrect.",
                                affected_threshold_or_rule=insight.expected_gate_result.value,
                            )
                        )
        incomplete = incomplete_review_fields(item.sample)
        if incomplete:
            disagreements.append(
                CalibrationDisagreement(
                    sample_id=item.sample.sample_id,
                    category=DisagreementCategory.incomplete_annotation,
                    court4_output=item.result.status.value,
                    human_expectation="Complete independent review",
                    artifact_evidence=evidence,
                    reason="Unreviewed fields: " + ", ".join(incomplete),
                    affected_threshold_or_rule=None,
                )
            )
    return sorted(
        disagreements,
        key=lambda item: (item.sample_id, item.category.value, item.court4_output),
    )


def _enum_text(value: object | None) -> str:
    if value is None:
        return "unavailable"
    return str(getattr(value, "value", value))


def _policy_error_reasons(evaluated: list[_EvaluatedSample]) -> dict[str, dict[str, int]]:
    categories: dict[str, Counter[str]] = {
        "false_acceptance": Counter(),
        "false_suppression": Counter(),
        "quality_overestimation": Counter(),
        "quality_underestimation": Counter(),
    }
    for item in evaluated:
        reasons = (
            item.assessment.reason_codes if item.assessment is not None else ["missing_assessment"]
        )
        delta = item.result.recording_quality_delta
        if delta is not None and delta > 0:
            categories["quality_overestimation"].update(reasons)
        elif delta is not None and delta < 0:
            categories["quality_underestimation"].update(reasons)
        expected_gate = item.result.expected_insight_eligibility
        actual_gate = item.result.system_insight_eligibility
        if (
            expected_gate == ExpectedInsightEligibility.insufficient_evidence
            and actual_gate is not None
            and actual_gate != ExpectedInsightEligibility.insufficient_evidence
        ):
            categories["false_acceptance"].update(reasons)
        if (
            expected_gate
            in {ExpectedInsightEligibility.normal, ExpectedInsightEligibility.cautious}
            and actual_gate == ExpectedInsightEligibility.insufficient_evidence
        ):
            categories["false_suppression"].update(reasons)
    return {
        category: dict(sorted(counter.items(), key=lambda entry: (-entry[1], entry[0])))
        for category, counter in categories.items()
    }


def _requires_manual_review(item: _EvaluatedSample) -> bool:
    return (
        item.sample.review_status != ReviewStatus.reviewed
        or item.result.status != SampleEvaluationStatus.evaluated
        or item.result.exact_quality_agreement is False
        or item.result.insight_eligibility_agreement is False
        or any(
            artifact.status
            in {
                ArtifactEvaluationStatus.missing,
                ArtifactEvaluationStatus.stale,
                ArtifactEvaluationStatus.invalid,
            }
            for artifact in item.result.artifacts
        )
    )


def _dataset_limitations(
    evaluated: list[_EvaluatedSample],
    manifest: CalibrationManifest,
) -> list[str]:
    limitations = [
        (
            f"The dataset contains {len(evaluated)} samples; balance and review coverage "
            "must be assessed before interpreting aggregate metrics."
        ),
        "Unreviewed and unknown labels are excluded; incomplete coverage remains provisional.",
        "This report is a deterministic framework evaluation, not scientific validation.",
    ]
    if len(evaluated) < manifest.minimum_recommended_sample_size:
        limitations.insert(
            1,
            (
                f"Sample count is below the manifest minimum of "
                f"{manifest.minimum_recommended_sample_size}."
            ),
        )
    if any(
        artifact.compatibility == ArtifactReadiness.legacy_compatible
        for item in evaluated
        for artifact in item.result.artifacts
    ):
        limitations.append("Some reusable artifacts are legacy-compatible rather than current.")
    if any(item.result.artifact_readiness == ArtifactReadiness.partial for item in evaluated):
        limitations.append("At least one sample has a partial artifact chain.")
    if not any(item.sample.dataset_split == DatasetSplit.holdout for item in evaluated):
        limitations.append("No holdout sample exists; generalization remains unmeasured.")
    if not any(
        item.sample.human_review is not None
        and item.sample.human_review.tracking is not None
        and item.sample.human_review.tracking.intervals
        for item in evaluated
    ):
        limitations.append("No interval-level tracking ground truth is currently reviewed.")
    return limitations
