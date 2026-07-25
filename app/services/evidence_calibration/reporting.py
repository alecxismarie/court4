import json
from pathlib import Path

from app.schemas.evidence_calibration import CalibrationResults, CountMetric


def write_calibration_reports(
    results: CalibrationResults,
    *,
    json_path: Path,
    markdown_path: Path,
    disagreements_path: Path | None = None,
    manifest_path: Path | None = None,
) -> None:
    resolved_manifest = manifest_path.expanduser().resolve() if manifest_path is not None else None
    output_paths = [json_path, markdown_path]
    if disagreements_path is not None:
        output_paths.append(disagreements_path)
    for output_path in output_paths:
        resolved_output = output_path.expanduser().resolve()
        if resolved_manifest is not None and resolved_output == resolved_manifest:
            raise ValueError("Calibration reports cannot overwrite the reviewer manifest.")
        resolved_output.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(results.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(results), encoding="utf-8")
    if disagreements_path is not None:
        disagreements_path.write_text(
            _render_disagreements(results),
            encoding="utf-8",
        )


def _render_markdown(results: CalibrationResults) -> str:
    quality = results.metrics.recording_quality
    gates = results.metrics.evidence_gates
    candidates = results.metrics.candidate_reliability
    lines = [
        "# Court4 Calibration Report",
        "",
        f"Dataset: `{results.dataset_id}` version `{results.dataset_version}`",
        f"Manifest SHA256: `{results.manifest_sha256}`",
        f"Reference time: `{results.generated_at.isoformat()}`",
        "",
        "## Dataset summary",
        "",
        f"- Samples: {results.sample_count}",
        f"- Reviewed or partially reviewed: {results.reviewed_sample_count}",
        f"- Not reviewed: {results.unreviewed_sample_count}",
        (
            "- Expensive inference rerun: "
            f"{'enabled' if results.expensive_recomputation_enabled else 'disabled'}; "
            f"{results.expensive_inference_runs} inference runs performed"
        ),
        "- Validation status: provisional; this dataset is not representative.",
        "",
        "## Sample results",
        "",
        (
            "| Sample | Evaluation | Readiness | Human quality | Court4 quality | "
            "Expected gate | Court4 gate | Exact | Artifacts |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for sample in results.samples:
        artifact_summary = ", ".join(
            f"{artifact.artifact}:{artifact.status.value}" for artifact in sample.artifacts
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    sample.sample_id,
                    sample.status.value,
                    sample.artifact_readiness.value,
                    sample.expected_recording_quality.value,
                    (
                        sample.system_recording_quality.value
                        if sample.system_recording_quality is not None
                        else "unavailable"
                    ),
                    sample.expected_insight_eligibility.value,
                    (
                        sample.system_insight_eligibility.value
                        if sample.system_insight_eligibility is not None
                        else "unavailable"
                    ),
                    _boolean_label(sample.exact_quality_agreement),
                    artifact_summary,
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Recording-quality classification",
            "",
            f"- Exact agreement: {_metric_text(quality.exact_agreement)}",
            (
                "- Acceptable agreement (exact or one adjacent level): "
                f"{_metric_text(quality.acceptable_agreement)}"
            ),
            f"- Quality overestimation count: {quality.overestimation_count}",
            f"- Quality underestimation count: {quality.underestimation_count}",
            "",
            "Per expected status:",
            "",
        ]
    )
    for label, count in quality.per_expected_status_count.items():
        lines.append(f"- `{label}`: {count}")
    lines.extend(["", "Confusion matrix (rows expected, columns Court4):", ""])
    labels = list(quality.confusion_matrix)
    lines.append("| Expected | " + " | ".join(labels) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in labels) + " |")
    for expected in labels:
        row = quality.confusion_matrix[expected]
        lines.append(f"| {expected} | " + " | ".join(str(row[actual]) for actual in labels) + " |")

    lines.extend(
        [
            "",
            "## Evidence-gate outcomes",
            "",
            (
                "- Valid insights correctly allowed: "
                f"{_metric_text(gates.valid_insights_correctly_allowed)}"
            ),
            (
                "- Weak insights correctly reduced to measurement-only: "
                f"{_metric_text(gates.weak_insights_correctly_measurement_only)}"
            ),
            (
                "- Unsuitable insights correctly suppressed: "
                f"{_metric_text(gates.unsuitable_insights_correctly_suppressed)}"
            ),
            (
                "- Valid insights incorrectly suppressed: "
                f"{gates.valid_insights_incorrectly_suppressed}"
            ),
            f"- Weak insights incorrectly allowed: {gates.weak_insights_incorrectly_allowed}",
            (
                "- Unsuitable insights incorrectly allowed: "
                f"{gates.unsuitable_insights_incorrectly_allowed}"
            ),
            "",
            "## Candidate reliability",
            "",
            f"- Expected player recall: {_metric_text(candidates.expected_player_recall)}",
            (
                "- Duplicate candidates: "
                f"{_optional_count_text(candidates.duplicate_candidate_count)}"
            ),
            f"- Missed players: {_optional_count_text(candidates.missed_player_count)}",
            (
                "- Spectator promotions: "
                f"{_optional_count_text(candidates.spectator_promotion_count)}"
            ),
            (
                "- Selected-player identity accuracy: "
                f"{_metric_text(candidates.selected_player_identity_accuracy)}"
            ),
            f"- Candidate precision: {_metric_text(candidates.candidate_precision)}",
            (
                "- Candidate-to-player mapping accuracy: "
                f"{_metric_text(candidates.candidate_to_player_mapping_accuracy)}"
            ),
            (
                "- Duplicate candidates per labeled sample: "
                f"{_metric_text(candidates.duplicate_candidates_per_sample)}"
            ),
            (
                "- Missed players per labeled sample: "
                f"{_metric_text(candidates.missed_players_per_sample)}"
            ),
            "- Counts are included only where a reviewer supplied the corresponding label.",
            "",
            "## Tracking-continuity review",
            "",
            (
                "- Reviewed intervals: "
                f"{results.metrics.tracking_continuity.reviewed_interval_count}"
            ),
            (
                "- Correctly maintained identity intervals: "
                f"{_metric_text(results.metrics.tracking_continuity.correctly_maintained_identity_intervals)}"
            ),
            (
                "- Identity-switch intervals: "
                f"{results.metrics.tracking_continuity.identity_switch_intervals}"
            ),
            (f"- Fragmented intervals: {results.metrics.tracking_continuity.fragmented_intervals}"),
            (
                "- Valid observed-time agreement: "
                f"{_metric_text(results.metrics.tracking_continuity.valid_observed_time_agreement)}"
            ),
            (
                "- Gap-label agreement: "
                f"{_metric_text(results.metrics.tracking_continuity.gap_label_agreement)}"
            ),
            "",
            "## Insight-integrity findings",
            "",
        ]
    )
    for field_name, metric in results.metrics.insight_integrity.fields.items():
        lines.append(f"- {field_name.replace('_', ' ').title()}: {_metric_text(metric)}")

    lines.extend(["", "## Dataset balance", ""])
    balance = results.dataset_balance
    lines.extend(
        [
            (
                f"- Collection size: {balance.sample_count}/"
                f"{balance.recommended_minimum_samples}-{balance.recommended_maximum_samples}"
            ),
            f"- Minimum target per category value: {balance.minimum_per_category}",
            "",
            "| Category | Counts | Missing | Underrepresented |",
            "| --- | --- | --- | --- |",
        ]
    )
    for balance_category in balance.categories:
        counts = ", ".join(f"{key}={value}" for key, value in balance_category.counts.items())
        lines.append(
            "| "
            + " | ".join(
                (
                    balance_category.category,
                    counts,
                    ", ".join(balance_category.missing) or "none",
                    ", ".join(balance_category.underrepresented) or "none",
                )
            )
            + " |"
        )
    lines.extend(["", "Provisional balance warnings:", ""])
    lines.extend(f"- {warning}" for warning in balance.provisional_warnings)

    lines.extend(["", "## Artifact compatibility", ""])
    lines.extend(
        [
            "| Sample | Stage | Actual version | Expected version | Compatibility |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for sample in results.samples:
        for artifact in sample.artifacts:
            lines.append(
                "| "
                + " | ".join(
                    (
                        sample.sample_id,
                        artifact.artifact,
                        artifact.schema_or_engine_version or "unavailable",
                        artifact.expected_version or "unavailable",
                        artifact.compatibility.value,
                    )
                )
                + " |"
            )

    lines.extend(["", "## Common failure reasons", ""])
    if results.common_failure_reasons:
        for reason, count in results.common_failure_reasons.items():
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- No quality or artifact failure reason was recorded.")

    lines.extend(["", "## Policy error reasons", ""])
    for policy_category, reasons in results.policy_error_reasons.items():
        if reasons:
            rendered = ", ".join(f"`{reason}` ({count})" for reason, count in reasons.items())
            lines.append(f"- {policy_category.replace('_', ' ').title()}: {rendered}")
        else:
            lines.append(f"- {policy_category.replace('_', ' ').title()}: none observed")

    lines.extend(["", "## Threshold-analysis findings", ""])
    if results.threshold_analysis:
        for simulation in results.threshold_analysis:
            lines.extend(
                [
                    f"### `{simulation.threshold}`",
                    "",
                    f"- Current value: {simulation.current_value:g}",
                    f"- Proposed value: {simulation.proposed_value:g}",
                    ("- Affected samples: " + (", ".join(simulation.affected_samples) or "none")),
                    "- Improvements: " + (", ".join(simulation.improvements) or "none"),
                    "- Regressions: " + (", ".join(simulation.regressions) or "none"),
                    "- Excluded validation/holdout samples: "
                    + (", ".join(simulation.excluded_samples) or "none"),
                    f"- Unchanged samples: {simulation.unchanged_samples}",
                    f"- Exploratory: {'yes' if simulation.exploratory else 'no'}",
                    f"- Remaining uncertainty: {simulation.remaining_uncertainty}",
                    "",
                ]
            )
    else:
        lines.append("- No alternative thresholds were requested.")

    lines.extend(["## Samples requiring manual review", ""])
    if results.samples_requiring_manual_review:
        lines.extend(f"- `{sample_id}`" for sample_id in results.samples_requiring_manual_review)
    else:
        lines.append("- None.")

    lines.extend(["", "## Dataset limitations", ""])
    lines.extend(f"- {limitation}" for limitation in results.dataset_limitations)
    lines.extend(
        [
            "",
            "## Recommended next actions",
            "",
            "1. Complete independent review for samples listed as requiring manual review.",
            (
                f"2. Collect toward the documented {balance.recommended_minimum_samples}-"
                f"{balance.recommended_maximum_samples} sample target and address balance gaps."
            ),
            (
                "3. Collect landscape and vertical recordings across lighting, camera "
                "distance, obstruction, and spectator conditions."
            ),
            (
                "4. Add frame-level player identity and continuity labels before claiming "
                "candidate precision or tracking accuracy."
            ),
            (
                "5. Keep all threshold changes manual; rerun this report and inspect "
                "regressions before any production edit."
            ),
            "",
            "## Verdict",
            "",
            (
                "The calibration framework is operational, but current coverage and "
                "review completeness remain insufficient for broad validation. "
                "Production thresholds remain unchanged."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _render_disagreements(results: CalibrationResults) -> str:
    lines = [
        "# Court4 Calibration Disagreements",
        "",
        f"Dataset: `{results.dataset_id}` version `{results.dataset_version}`",
        f"Manifest SHA256: `{results.manifest_sha256}`",
        "",
        (
            "This report identifies disagreements and incomplete annotations. It does "
            "not resolve labels or change policy."
        ),
        "",
        f"Total findings: {len(results.disagreements)}",
        "",
    ]
    if not results.disagreements:
        lines.extend(["No disagreements or incomplete annotations were found.", ""])
        return "\n".join(lines)
    for index, disagreement in enumerate(results.disagreements, start=1):
        lines.extend(
            [
                f"## {index}. `{disagreement.sample_id}` — {disagreement.category.value}",
                "",
                f"- Court4 output: {disagreement.court4_output}",
                f"- Human expectation: {disagreement.human_expectation}",
                f"- Reason: {disagreement.reason}",
                (
                    "- Affected threshold or rule: "
                    f"{disagreement.affected_threshold_or_rule or 'not identified'}"
                ),
                "- Artifact evidence: " + (", ".join(disagreement.artifact_evidence) or "none"),
                "",
            ]
        )
    return "\n".join(lines)


def _metric_text(metric: CountMetric) -> str:
    percentage = f"{metric.percentage:.1f}%" if metric.percentage is not None else "not available"
    suffix = " — provisional" if metric.provisional else ""
    return f"{metric.numerator}/{metric.denominator} ({percentage}){suffix}"


def _boolean_label(value: bool | None) -> str:
    if value is None:
        return "not reviewed"
    return "yes" if value else "no"


def _optional_count_text(value: int | None) -> str:
    return str(value) if value is not None else "not reviewed"
