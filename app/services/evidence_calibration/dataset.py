import json
from dataclasses import dataclass
from pathlib import Path

from app.schemas.evidence_calibration import (
    BalanceCategoryResult,
    CalibrationManifest,
    CalibrationQualityLabel,
    CalibrationSample,
    CandidateRole,
    CourtVisibility,
    DatasetBalanceSummary,
    DatasetSplit,
    RecordingOrientation,
    RecordingStability,
    ReviewStatus,
    ReviewValue,
    SeverityLabel,
)


@dataclass(frozen=True)
class DatasetBalancePolicy:
    recommended_minimum_samples: int = 20
    recommended_maximum_samples: int = 30
    minimum_per_category: int = 2


DATASET_BALANCE_POLICY = DatasetBalancePolicy()


def summarize_dataset_balance(
    manifest: CalibrationManifest,
    *,
    policy: DatasetBalancePolicy = DATASET_BALANCE_POLICY,
) -> DatasetBalanceSummary:
    category_values = {
        "environment": ("INDOOR", "OUTDOOR"),
        "match_format": ("SINGLES", "DOUBLES"),
        "recording_condition": ("IDEAL", "POOR"),
        "orientation": ("LANDSCAPE", "VERTICAL"),
        "camera_position": ("BASELINE", "DIAGONAL"),
        "camera_distance": ("NEAR", "DISTANT"),
        "resolution": ("720P", "1080P"),
        "recording_stability": ("STABLE", "UNSTABLE"),
        "obstruction": ("NONE", "MINOR", "MODERATE", "SEVERE"),
        "tracking": ("STRONG", "FRAGMENTED"),
        "quality": ("EXCELLENT", "GOOD", "LIMITED", "UNSUITABLE"),
        "dataset_split": ("DEVELOPMENT", "VALIDATION", "HOLDOUT"),
    }
    counts = {
        category: {value: 0 for value in values} for category, values in category_values.items()
    }
    for sample in manifest.samples:
        _increment(counts["environment"], sample.environment_type.value)
        _increment(counts["match_format"], sample.match_format.value)
        quality = _reviewed_quality(sample)
        if quality is not None:
            _increment(counts["quality"], quality.value)
            _increment(
                counts["recording_condition"],
                (
                    "IDEAL"
                    if quality in {CalibrationQualityLabel.excellent, CalibrationQualityLabel.good}
                    else "POOR"
                ),
            )
        if sample.orientation is not None:
            _increment(counts["orientation"], sample.orientation.value)
        _increment(counts["camera_position"], sample.camera_position_label.value)
        _increment(counts["camera_distance"], sample.camera_distance.value)
        resolution = _resolution_bucket(sample)
        if resolution is not None:
            _increment(counts["resolution"], resolution)
        stability = {
            RecordingStability.stable: "STABLE",
            RecordingStability.mostly_stable: "STABLE",
            RecordingStability.unstable: "UNSTABLE",
        }.get(sample.recording_stability)
        if stability is not None:
            _increment(counts["recording_stability"], stability)
        recording_review = (
            sample.human_review.recording if sample.human_review is not None else None
        )
        if recording_review is not None and recording_review.obstruction_severity in {
            SeverityLabel.none,
            SeverityLabel.minor,
            SeverityLabel.moderate,
            SeverityLabel.severe,
        }:
            _increment(counts["obstruction"], recording_review.obstruction_severity.value)
        tracking_review = sample.human_review.tracking if sample.human_review is not None else None
        if tracking_review is not None:
            if tracking_review.fragmentation_severity in {
                SeverityLabel.none,
                SeverityLabel.minor,
            }:
                tracking_bucket = "STRONG"
            elif tracking_review.fragmentation_severity in {
                SeverityLabel.moderate,
                SeverityLabel.severe,
            }:
                tracking_bucket = "FRAGMENTED"
            else:
                tracking_bucket = None
            if tracking_bucket is not None:
                _increment(counts["tracking"], tracking_bucket)
        _increment(counts["dataset_split"], sample.dataset_split.value)

    categories: list[BalanceCategoryResult] = []
    warnings: list[str] = []
    for category, values in counts.items():
        represented = [value for value, count in values.items() if count > 0]
        missing = [value for value, count in values.items() if count == 0]
        underrepresented = [
            value for value, count in values.items() if 0 < count < policy.minimum_per_category
        ]
        categories.append(
            BalanceCategoryResult(
                category=category,
                counts=values,
                represented=represented,
                missing=missing,
                underrepresented=underrepresented,
            )
        )
        if missing:
            warnings.append(f"{category}: missing {', '.join(missing)}")
        if underrepresented:
            warnings.append(
                f"{category}: underrepresented {', '.join(underrepresented)} "
                f"(<{policy.minimum_per_category} samples)"
            )
    if len(manifest.samples) < policy.recommended_minimum_samples:
        warnings.insert(
            0,
            f"Dataset has {len(manifest.samples)} samples; recommended collection size is "
            f"{policy.recommended_minimum_samples}-{policy.recommended_maximum_samples}.",
        )
    if not any(sample.dataset_split == DatasetSplit.holdout for sample in manifest.samples):
        warnings.append("No holdout samples are present; final generalization is unmeasured.")
    return DatasetBalanceSummary(
        sample_count=len(manifest.samples),
        recommended_minimum_samples=policy.recommended_minimum_samples,
        recommended_maximum_samples=policy.recommended_maximum_samples,
        minimum_per_category=policy.minimum_per_category,
        categories=categories,
        provisional_warnings=warnings,
    )


def incomplete_review_fields(sample: CalibrationSample) -> list[str]:
    missing: list[str] = []
    if sample.review_status != ReviewStatus.reviewed:
        missing.append("review_status")
    metadata = {
        "environment_type": sample.environment_type.value,
        "match_format": sample.match_format.value,
        "camera_position_label": sample.camera_position_label.value,
        "camera_distance": sample.camera_distance.value,
        "lighting_condition": sample.lighting_condition.value,
        "recording_stability": sample.recording_stability.value,
    }
    for field_name, value in metadata.items():
        if value in {"UNKNOWN", "NOT_REVIEWED"}:
            missing.append(field_name)
    if sample.orientation in {None, RecordingOrientation.unknown}:
        missing.append("orientation")
    if sample.resolution is None:
        missing.append("resolution")
    if sample.fps is None:
        missing.append("fps")
    if sample.court_visibility in {None, CourtVisibility.unknown}:
        missing.append("court_visibility")

    review = sample.human_review
    if review is None:
        return [*missing, "human_review"]
    if review.player_candidates is None:
        missing.append("human_review.player_candidates")
    else:
        candidates = review.player_candidates
        if not candidates.stable_real_players:
            missing.append("human_review.player_candidates.stable_real_players")
        if not candidates.candidate_mappings:
            missing.append("human_review.player_candidates.candidate_mappings")
        if candidates.selected_player_identity_correct is None:
            missing.append("human_review.player_candidates.selected_player_identity_correct")
        if any(
            mapping.role in {CandidateRole.uncertain, CandidateRole.not_reviewed}
            or mapping.mapping_correct in {ReviewValue.unknown, ReviewValue.not_reviewed}
            for mapping in candidates.candidate_mappings
        ):
            missing.append("human_review.player_candidates.unresolved_mappings")
    if review.tracking is None or not review.tracking.intervals:
        missing.append("human_review.tracking.intervals")
    if review.insight is None or not review.insight.generated_insights:
        missing.append("human_review.insight.generated_insights")
    return list(dict.fromkeys(missing))


def unresolved_candidate_mappings(sample: CalibrationSample) -> list[str]:
    review = sample.human_review.player_candidates if sample.human_review is not None else None
    if review is None:
        return ["candidate review missing"]
    if not review.candidate_mappings:
        return ["no candidate mappings reviewed"]
    return [
        mapping.candidate_id
        for mapping in review.candidate_mappings
        if mapping.role in {CandidateRole.uncertain, CandidateRole.not_reviewed}
        or mapping.mapping_correct in {ReviewValue.unknown, ReviewValue.not_reviewed}
    ]


def samples_requiring_insight_review(manifest: CalibrationManifest) -> list[str]:
    return [
        sample.sample_id
        for sample in manifest.samples
        if sample.human_review is None
        or sample.human_review.insight is None
        or not sample.human_review.insight.generated_insights
        or any(
            insight.measurement_correct in {ReviewValue.unknown, ReviewValue.not_reviewed}
            or insight.interpretation_justified in {ReviewValue.unknown, ReviewValue.not_reviewed}
            or insight.confidence_appropriate in {ReviewValue.unknown, ReviewValue.not_reviewed}
            or insight.limitation_accurate in {ReviewValue.unknown, ReviewValue.not_reviewed}
            or insight.action_conservative in {ReviewValue.unknown, ReviewValue.not_reviewed}
            or insight.wording_understandable in {ReviewValue.unknown, ReviewValue.not_reviewed}
            for insight in sample.human_review.insight.generated_insights
        )
    ]


def sample_template(sample_id: str) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "dataset_split": "DEVELOPMENT",
        "video_reference": None,
        "external_video_reference": None,
        "local_video_reference": None,
        "recording_environment": None,
        "environment_type": "NOT_REVIEWED",
        "match_format": "NOT_REVIEWED",
        "orientation": "UNKNOWN",
        "resolution": None,
        "fps": None,
        "camera_position": None,
        "camera_position_label": "NOT_REVIEWED",
        "camera_distance": "NOT_REVIEWED",
        "lighting_condition": "NOT_REVIEWED",
        "recording_stability": "NOT_REVIEWED",
        "court_visibility": "UNKNOWN",
        "expected_players_on_court": None,
        "known_spectators_or_irrelevant_detections": [],
        "expected_recording_quality": "NOT_REVIEWED",
        "expected_insight_eligibility": "NOT_REVIEWED",
        "reviewer_notes": None,
        "review_status": "NOT_REVIEWED",
        "reviewer_confidence": None,
        "artifacts": {
            "artifact_root": "data/output",
            "inspection_analysis_id": "replace-me",
            "court_analysis_id": None,
            "tracking_analysis_id": None,
            "candidates_analysis_id": None,
            "analytics_analysis_id": None,
            "match_iq_analysis_id": None,
            "inference_run_id": None,
            "reuse_notes": (
                "Replace the placeholder analysis ID. Keep video files external or ignored."
            ),
        },
        "human_review": {
            "recording": {
                "recording_quality_verdict": "NOT_REVIEWED",
                "reviewer_confidence": None,
            },
            "player_candidates": {
                "stable_real_players": [],
                "candidate_mappings": [],
                "reviewer_confidence": None,
            },
            "tracking": {"intervals": [], "reviewer_confidence": None},
            "insight": {"generated_insights": [], "reviewer_confidence": None},
        },
    }


def write_sample_template(path: Path, sample_id: str, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Template output already exists: {path}. Use --force to overwrite explicitly."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sample_template(sample_id), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_balance_summary(summary: DatasetBalanceSummary) -> str:
    lines = [
        f"Dataset samples: {summary.sample_count}",
        (
            "Recommended size: "
            f"{summary.recommended_minimum_samples}-{summary.recommended_maximum_samples}"
        ),
        f"Minimum per balance value: {summary.minimum_per_category}",
    ]
    for category in summary.categories:
        counts = ", ".join(f"{key}={value}" for key, value in category.counts.items())
        lines.append(f"{category.category}: {counts}")
    lines.append("Warnings:")
    lines.extend(f"- {warning}" for warning in summary.provisional_warnings)
    return "\n".join(lines)


def _increment(counts: dict[str, int], value: str) -> None:
    if value in counts:
        counts[value] += 1


def _reviewed_quality(sample: CalibrationSample) -> CalibrationQualityLabel | None:
    review = sample.human_review.recording if sample.human_review is not None else None
    quality = (
        review.recording_quality_verdict
        if review is not None
        else sample.expected_recording_quality
    )
    if quality in {
        CalibrationQualityLabel.excellent,
        CalibrationQualityLabel.good,
        CalibrationQualityLabel.limited,
        CalibrationQualityLabel.unsuitable,
    }:
        return quality
    return None


def _resolution_bucket(sample: CalibrationSample) -> str | None:
    if sample.resolution is None:
        return None
    short_edge = min(sample.resolution.width, sample.resolution.height)
    if short_edge >= 1080:
        return "1080P"
    if short_edge >= 720:
        return "720P"
    return None
