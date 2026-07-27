from dataclasses import dataclass

from app.schemas.calibration_readiness import ReadinessDecision, ReadinessVerdict

READINESS_POLICY_VERSION = "calibration-readiness-v1"


@dataclass(frozen=True)
class CalibrationReadinessPolicy:
    """Engineering governance gates; these are not scientific accuracy thresholds."""

    version: str = READINESS_POLICY_VERSION
    minimum_total_samples: int = 20
    minimum_fully_reviewed_samples: int = 5
    minimum_current_schema_samples: int = 5
    minimum_active_play_reviewed_seconds: float = 300.0
    minimum_active_play_reviewed_intervals: int = 10
    minimum_reviewed_boundaries: int = 10
    preferred_samples_per_balance_value: int = 2


READINESS_POLICY = CalibrationReadinessPolicy()


@dataclass(frozen=True)
class ReadinessFacts:
    source_current: bool
    total_samples: int
    development_count: int
    validation_count: int
    holdout_count: int
    fully_reviewed_samples: int
    current_schema_samples: int
    active_reviewed_seconds: float
    active_reviewed_intervals: int
    active_evidence_seconds: float
    idle_evidence_seconds: float
    reviewed_boundaries: int
    missing_balance_values: int
    underrepresented_balance_values: int
    critical_disagreements: int
    expensive_inference_runs: int | None
    production_thresholds_unchanged: bool | None
    reviewer_labels_unchanged: bool | None
    deterministic_report_verified: bool
    holdout_protection_enabled: bool
    recording_policy_frozen: bool
    active_play_policy_frozen: bool
    false_active_budget_approved: bool
    false_idle_budget_approved: bool


def evaluate_readiness(
    facts: ReadinessFacts,
    *,
    policy: CalibrationReadinessPolicy = READINESS_POLICY,
) -> ReadinessDecision:
    blockers: list[str] = []
    warnings: list[str] = []
    satisfied: list[str] = []

    def criterion(condition: bool, success: str, failure: str) -> None:
        (satisfied if condition else blockers).append(success if condition else failure)

    criterion(facts.source_current, "Sources are current.", "Calibration sources are not current.")
    criterion(
        facts.expensive_inference_runs == 0,
        "Calibration evaluation ran without inference.",
        "No-inference execution is not verified.",
    )
    criterion(
        facts.production_thresholds_unchanged is True,
        "Production policy hashes match the evaluated report.",
        "Production threshold integrity is not verified.",
    )
    criterion(
        facts.reviewer_labels_unchanged is True,
        "Reviewer-label hash matches the evaluated report.",
        "Reviewer-label integrity is not verified.",
    )
    criterion(
        facts.deterministic_report_verified,
        "Repeat report hashes match.",
        "Deterministic repeat-report hashes are not verified.",
    )
    criterion(
        facts.holdout_protection_enabled,
        "Threshold simulations protect validation and holdout samples.",
        "Holdout exclusion is not verified.",
    )

    integrity_blocked = any(
        [
            not facts.source_current,
            facts.expensive_inference_runs != 0,
            facts.production_thresholds_unchanged is not True,
            facts.reviewer_labels_unchanged is not True,
            not facts.deterministic_report_verified,
            not facts.holdout_protection_enabled,
        ]
    )
    integrity_blocker_count = len(blockers)

    criterion(
        facts.total_samples >= policy.minimum_total_samples,
        f"Dataset has at least {policy.minimum_total_samples} samples.",
        f"Dataset has fewer than {policy.minimum_total_samples} samples.",
    )
    criterion(
        facts.development_count > 0,
        "Development split is represented.",
        "No development samples.",
    )
    criterion(
        facts.validation_count > 0,
        "Validation split is represented.",
        "No validation samples.",
    )
    criterion(
        facts.holdout_count > 0,
        "Holdout split is represented.",
        "No holdout samples.",
    )
    criterion(
        facts.fully_reviewed_samples >= policy.minimum_fully_reviewed_samples,
        (
            "Fully reviewed sample count meets the "
            f"{policy.minimum_fully_reviewed_samples}-sample governance target."
        ),
        (f"Fewer than {policy.minimum_fully_reviewed_samples} samples are fully reviewed."),
    )
    criterion(
        facts.current_schema_samples >= policy.minimum_current_schema_samples,
        "Current-schema artifact coverage meets the governance target.",
        "Current-schema artifact coverage is insufficient.",
    )
    criterion(
        facts.active_reviewed_seconds >= policy.minimum_active_play_reviewed_seconds,
        "Active Play reviewed-duration target is met.",
        (
            "Active Play reviewed duration is below "
            f"{policy.minimum_active_play_reviewed_seconds:g} seconds."
        ),
    )
    criterion(
        facts.active_reviewed_intervals >= policy.minimum_active_play_reviewed_intervals,
        "Active Play reviewed-interval target is met.",
        (
            "Active Play has fewer than "
            f"{policy.minimum_active_play_reviewed_intervals} reviewed intervals."
        ),
    )
    criterion(
        facts.active_evidence_seconds > 0,
        "Likely-active human-reviewed evidence exists.",
        "No likely-active reviewed evidence.",
    )
    criterion(
        facts.idle_evidence_seconds > 0,
        "Likely-idle human-reviewed evidence exists.",
        "No likely-idle reviewed evidence.",
    )
    criterion(
        facts.reviewed_boundaries >= policy.minimum_reviewed_boundaries,
        "Active Play boundary-review target is met.",
        f"Fewer than {policy.minimum_reviewed_boundaries} boundaries are reviewed.",
    )
    criterion(
        facts.missing_balance_values == 0,
        "Every required balance value is represented.",
        "Dataset balance still has missing categories.",
    )
    criterion(
        facts.critical_disagreements == 0,
        "No critical readiness disagreements remain.",
        "Critical readiness disagreements remain unresolved.",
    )
    if facts.underrepresented_balance_values > 0:
        warnings.append(
            f"{facts.underrepresented_balance_values} represented balance values remain "
            "under the preferred engineering count."
        )

    evidence_blocked = len(blockers) > integrity_blocker_count
    policy_approved = facts.recording_policy_frozen and facts.active_play_policy_frozen
    budgets_approved = facts.false_active_budget_approved and facts.false_idle_budget_approved
    if integrity_blocked:
        verdict = ReadinessVerdict.not_ready
        explanation = "Readiness cannot be assessed until source and integrity checks pass."
    elif evidence_blocked:
        verdict = ReadinessVerdict.collecting_evidence
        explanation = "The framework is current, but evidence collection and review are incomplete."
    elif not policy_approved or not budgets_approved:
        verdict = ReadinessVerdict.ready_for_policy_review
        explanation = "Evidence targets are met; explicit policy and error-budget review remains."
        if not policy_approved:
            blockers.append("Recording and Active Play policies are not frozen for review.")
        if not budgets_approved:
            blockers.append("False-active and false-idle budgets are not approved.")
    else:
        verdict = ReadinessVerdict.ready_for_phase_1_6b
        explanation = "All engineering governance gates are satisfied."

    actions: list[str] = []
    if facts.holdout_count == 0:
        actions.append("Add the first independently reviewed holdout sample.")
    if facts.active_reviewed_seconds < policy.minimum_active_play_reviewed_seconds:
        actions.append("Review bounded Active Play intervals with confident human labels.")
    if facts.current_schema_samples < policy.minimum_current_schema_samples:
        actions.append("Replace legacy candidate artifacts with current-schema tracking runs.")
    if facts.fully_reviewed_samples < policy.minimum_fully_reviewed_samples:
        actions.append("Complete selected-player, identity, continuity, and insight labels.")
    if facts.missing_balance_values:
        actions.append("Collect missing balance cases, prioritizing outdoor singles footage.")
    if facts.critical_disagreements:
        actions.append("Resolve critical artifact, identity, continuity, and Active Play findings.")
    if not policy_approved:
        actions.append("Schedule policy review only after evidence gates are satisfied.")
    if not budgets_approved:
        actions.append("Establish false-active and false-idle governance budgets.")

    return ReadinessDecision(
        verdict=verdict,
        explanation=explanation,
        reasons=[explanation],
        blockers=list(dict.fromkeys(blockers)),
        warnings=warnings,
        satisfied_criteria=list(dict.fromkeys(satisfied)),
        recommended_actions=list(dict.fromkeys(actions)),
        policy_version=policy.version,
    )
