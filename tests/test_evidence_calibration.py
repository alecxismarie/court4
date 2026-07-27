import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.evidence_calibration import (
    ArtifactEvaluationStatus,
    CalibrationManifest,
    CalibrationQualityLabel,
    CalibrationResults,
)
from app.services.active_play.policy import ACTIVE_PLAY_POLICY
from app.services.evidence_calibration import (
    CalibrationManifestError,
    evaluate_manifest,
    load_calibration_manifest,
    write_calibration_reports,
)
from app.services.recording_quality import QUALITY_THRESHOLDS

REFERENCE_TIME = "2026-07-25T00:00:00Z"


def test_manifest_validation_accepts_partial_human_labels(tmp_path: Path) -> None:
    payload = _manifest(
        [
            _sample(
                "partial-review",
                expected_quality="UNKNOWN",
                expected_gate="NOT_REVIEWED",
                human_review={
                    "recording": {
                        "full_court_visible": True,
                        "recording_quality_verdict": "UNKNOWN",
                    }
                },
            )
        ]
    )
    loaded = load_calibration_manifest(_write_manifest(tmp_path, payload))

    assert loaded.manifest.samples[0].human_review is not None
    assert loaded.manifest.samples[0].human_review.recording is not None
    assert loaded.manifest.samples[0].human_review.player_candidates is None


def test_manifest_validation_rejects_invalid_status_with_clear_location(
    tmp_path: Path,
) -> None:
    payload = _manifest([_sample("invalid-status", expected_quality="PERFECT")])
    path = _write_manifest(tmp_path, payload)

    with pytest.raises(CalibrationManifestError) as exc_info:
        load_calibration_manifest(path)

    message = str(exc_info.value)
    assert "samples.0.expected_recording_quality" in message
    assert "UNSUITABLE" in message


def test_manifest_validation_rejects_unknown_fields() -> None:
    payload = _manifest([_sample("strict")])
    samples = payload["samples"]
    assert isinstance(samples, list)
    samples[0]["invented_label"] = True

    with pytest.raises(ValidationError):
        CalibrationManifest.model_validate(payload)


def test_missing_artifacts_do_not_stop_other_samples(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "available", quality="GOOD")
    payload = _manifest(
        [
            _sample("missing", analysis_id="does-not-exist"),
            _sample(
                "available",
                analysis_id="available",
                expected_quality="GOOD",
                expected_gate="CAUTIOUS",
            ),
        ]
    )
    results = _evaluate(tmp_path, payload)

    assert results.sample_count == 2
    missing = next(sample for sample in results.samples if sample.sample_id == "missing")
    available = next(sample for sample in results.samples if sample.sample_id == "available")
    assert any(
        artifact.artifact == "inspection_metadata"
        and artifact.status == ArtifactEvaluationStatus.missing
        for artifact in missing.artifacts
    )
    assert available.system_recording_quality == CalibrationQualityLabel.good


def test_stale_candidate_schema_is_reported_but_remains_readable(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "legacy", quality="GOOD")
    _write_candidate_collection(tmp_path, "legacy", schema_version=1)
    _write_calibration(tmp_path, "legacy")
    sample = _sample(
        "legacy-candidates",
        analysis_id="legacy",
        expected_quality="LIMITED",
        expected_gate="MEASUREMENT_ONLY",
    )
    artifacts = sample["artifacts"]
    assert isinstance(artifacts, dict)
    artifacts["candidates_analysis_id"] = "legacy"
    artifacts["court_analysis_id"] = "legacy"

    results = _evaluate(tmp_path, _manifest([sample]))
    result = results.samples[0]

    candidate_artifact = next(
        artifact for artifact in result.artifacts if artifact.artifact == "player_candidates"
    )
    assert candidate_artifact.status == ArtifactEvaluationStatus.stale
    assert candidate_artifact.schema_or_engine_version == "1"
    assert result.selectable_candidate_count == 1


def test_quality_metrics_report_exact_acceptable_and_confusion_matrix(
    tmp_path: Path,
) -> None:
    samples = []
    for sample_id, quality in (
        ("excellent", "EXCELLENT"),
        ("good", "GOOD"),
        ("limited", "LIMITED"),
        ("unsuitable", "UNSUITABLE"),
    ):
        _write_metadata(tmp_path, sample_id, quality=quality)
        samples.append(
            _sample(
                sample_id,
                analysis_id=sample_id,
                expected_quality=quality,
                expected_gate=_gate_for_quality(quality),
            )
        )
    results = _evaluate(tmp_path, _manifest(samples))
    metrics = results.metrics.recording_quality

    assert metrics.exact_agreement.numerator == 4
    assert metrics.exact_agreement.denominator == 4
    assert metrics.acceptable_agreement.numerator == 4
    assert metrics.confusion_matrix["GOOD"]["GOOD"] == 1
    assert metrics.per_expected_status_count["EXCELLENT"] == 1


def test_adjacent_quality_level_is_acceptable_but_not_exact(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "adjacent", quality="GOOD")
    results = _evaluate(
        tmp_path,
        _manifest(
            [
                _sample(
                    "adjacent",
                    analysis_id="adjacent",
                    expected_quality="EXCELLENT",
                    expected_gate="CAUTIOUS",
                )
            ]
        ),
    )

    assert results.metrics.recording_quality.exact_agreement.numerator == 0
    assert results.metrics.recording_quality.acceptable_agreement.numerator == 1
    assert results.samples[0].recording_quality_delta == -1


def test_false_acceptance_is_counted(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "false-accept", quality="GOOD")
    sample = _sample(
        "false-accept",
        analysis_id="false-accept",
        expected_quality="GOOD",
        expected_gate="INSUFFICIENT_EVIDENCE",
    )
    results = _evaluate(tmp_path, _manifest([sample]))

    assert results.metrics.evidence_gates.unsuitable_insights_incorrectly_allowed == 1


def test_false_suppression_is_counted(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "false-suppress", quality="UNSUITABLE")
    sample = _sample(
        "false-suppress",
        analysis_id="false-suppress",
        expected_quality="UNSUITABLE",
        expected_gate="NORMAL",
    )
    results = _evaluate(tmp_path, _manifest([sample]))

    assert results.metrics.evidence_gates.valid_insights_incorrectly_suppressed == 1


def test_small_sample_metrics_are_marked_provisional(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "small", quality="GOOD")
    results = _evaluate(
        tmp_path,
        _manifest(
            [
                _sample(
                    "small",
                    analysis_id="small",
                    expected_quality="GOOD",
                    expected_gate="CAUTIOUS",
                )
            ]
        ),
    )

    exact = results.metrics.recording_quality.exact_agreement
    assert exact.percentage == 100
    assert exact.provisional is True
    assert "recommended minimum of 5" in (exact.note or "")


def test_threshold_simulation_reports_improvement_without_mutating_policy(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "resolution-boundary", quality="CUSTOM", width=640, height=400)
    sample = _sample(
        "resolution-boundary",
        analysis_id="resolution-boundary",
        expected_quality="LIMITED",
        expected_gate="MEASUREMENT_ONLY",
    )
    payload = _manifest(
        [sample],
        threshold_simulations=[
            {
                "threshold": "blocking_short_edge_pixels",
                "proposed_value": 360,
                "rationale": "Test only.",
            }
        ],
    )

    results = _evaluate(tmp_path, payload)
    simulation = results.threshold_analysis[0]

    assert results.samples[0].system_recording_quality == CalibrationQualityLabel.unsuitable
    assert simulation.current_value == 480
    assert simulation.affected_samples == ["resolution-boundary"]
    assert simulation.improvements == ["resolution-boundary"]
    assert simulation.regressions == []
    assert QUALITY_THRESHOLDS.blocking_short_edge_pixels == 480


def test_active_play_interval_metrics_report_raw_seconds_and_counts(
    tmp_path: Path,
) -> None:
    human_review = {
        "active_play": {
            "intervals": [
                {
                    "start_time_seconds": 0,
                    "end_time_seconds": 10,
                    "expected_state": "LIKELY_ACTIVE",
                    "court4_state": "LIKELY_ACTIVE",
                    "court4_start_time_seconds": 0.2,
                    "court4_end_time_seconds": 9.7,
                    "boundary_tolerance_seconds": 0.5,
                    "reviewer_confidence": "HIGH",
                },
                {
                    "start_time_seconds": 10,
                    "end_time_seconds": 20,
                    "expected_state": "LIKELY_IDLE",
                    "court4_state": "LIKELY_ACTIVE",
                    "false_active": True,
                },
                {
                    "start_time_seconds": 20,
                    "end_time_seconds": 25,
                    "expected_state": "LIKELY_ACTIVE",
                    "court4_state": "LIKELY_IDLE",
                    "false_idle": True,
                },
                {
                    "start_time_seconds": 25,
                    "end_time_seconds": 30,
                    "expected_state": "LIKELY_IDLE",
                    "court4_state": "UNKNOWN",
                    "unknown_but_reviewable": True,
                },
            ]
        }
    }
    results = _evaluate(
        tmp_path,
        _manifest([_sample("interval-review", human_review=human_review)]),
    )

    metrics = results.metrics.active_play
    assert metrics.reviewed_duration.seconds == 30
    assert metrics.reviewed_duration.interval_count == 4
    assert metrics.likely_active_agreement.numerator_seconds == 10
    assert metrics.likely_active_agreement.denominator_seconds == 15
    assert metrics.false_active.seconds == 10
    assert metrics.false_active.interval_count == 1
    assert metrics.false_idle.seconds == 5
    assert metrics.unknown.seconds == 5
    assert metrics.abstention_rate.percentage == pytest.approx(100 / 6)
    assert metrics.coverage_rate.percentage == 100
    assert metrics.boundary_error.boundary_count == 2
    assert metrics.boundary_error.mean_absolute_seconds == pytest.approx(0.25)
    assert metrics.boundary_error.within_tolerance_count == 2


def test_active_play_threshold_simulation_excludes_holdout_and_preserves_policy(
    tmp_path: Path,
) -> None:
    development = _sample("development")
    holdout = _sample("holdout")
    holdout["dataset_split"] = "HOLDOUT"
    payload = _manifest(
        [development, holdout],
        active_play_threshold_simulations=[
            {
                "threshold": "minimum_window_coverage_ratio",
                "proposed_value": 0.7,
                "rationale": "Exploratory shadow-only test.",
            }
        ],
    )

    results = _evaluate(tmp_path, payload)
    simulation = results.active_play_threshold_analysis[0]

    assert simulation.current_value == 0.65
    assert simulation.excluded_samples == ["holdout"]
    assert simulation.unchanged_samples == 1
    assert ACTIVE_PLAY_POLICY.minimum_window_coverage_ratio == 0.65


def test_report_generation_is_deterministic_and_has_no_absolute_paths(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "deterministic", quality="GOOD")
    manifest_path = _write_manifest(
        tmp_path,
        _manifest(
            [
                _sample(
                    "deterministic",
                    analysis_id="deterministic",
                    expected_quality="GOOD",
                    expected_gate="CAUTIOUS",
                )
            ]
        ),
    )
    loaded = load_calibration_manifest(manifest_path)
    first = evaluate_manifest(loaded, repository_root=tmp_path)
    second = evaluate_manifest(loaded, repository_root=tmp_path)
    first_json = tmp_path / "first.json"
    first_markdown = tmp_path / "first.md"
    second_json = tmp_path / "second.json"
    second_markdown = tmp_path / "second.md"

    write_calibration_reports(
        first,
        json_path=first_json,
        markdown_path=first_markdown,
        manifest_path=manifest_path,
    )
    write_calibration_reports(
        second,
        json_path=second_json,
        markdown_path=second_markdown,
        manifest_path=manifest_path,
    )

    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_markdown.read_bytes() == second_markdown.read_bytes()
    assert str(tmp_path) not in first_markdown.read_text(encoding="utf-8")


def test_reports_cannot_overwrite_reviewer_manifest(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "protected", quality="GOOD")
    manifest_path = _write_manifest(
        tmp_path,
        _manifest([_sample("protected", analysis_id="protected")]),
    )
    original = manifest_path.read_bytes()
    loaded = load_calibration_manifest(manifest_path)
    results = evaluate_manifest(loaded, repository_root=tmp_path)

    with pytest.raises(ValueError, match="cannot overwrite"):
        write_calibration_reports(
            results,
            json_path=manifest_path,
            markdown_path=tmp_path / "report.md",
            manifest_path=manifest_path,
        )

    assert manifest_path.read_bytes() == original


def test_expensive_inference_is_disabled_by_default(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "no-inference", quality="GOOD")
    results = _evaluate(
        tmp_path,
        _manifest([_sample("no-inference", analysis_id="no-inference")]),
    )

    assert results.expensive_recomputation_enabled is False
    assert results.expensive_inference_runs == 0
    assert all(sample.inference_recomputed is False for sample in results.samples)


def test_unlabeled_candidate_counts_are_not_reported_as_zero(tmp_path: Path) -> None:
    _write_metadata(tmp_path, "unlabeled", quality="GOOD")
    results = _evaluate(
        tmp_path,
        _manifest([_sample("unlabeled", analysis_id="unlabeled")]),
    )
    candidate_metrics = results.metrics.candidate_reliability

    assert candidate_metrics.duplicate_candidate_count is None
    assert candidate_metrics.spectator_promotion_count is None


def _evaluate(tmp_path: Path, payload: dict[str, object]) -> CalibrationResults:
    loaded = load_calibration_manifest(_write_manifest(tmp_path, payload))
    return evaluate_manifest(loaded, repository_root=tmp_path)


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _manifest(
    samples: list[dict[str, object]],
    *,
    threshold_simulations: list[dict[str, object]] | None = None,
    active_play_threshold_simulations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "dataset_id": "test-calibration",
        "dataset_version": "1.0.0",
        "reference_time": REFERENCE_TIME,
        "minimum_recommended_sample_size": 5,
        "threshold_simulations": threshold_simulations or [],
        "active_play_threshold_simulations": active_play_threshold_simulations or [],
        "samples": samples,
    }


def _sample(
    sample_id: str,
    *,
    analysis_id: str | None = None,
    expected_quality: str = "NOT_REVIEWED",
    expected_gate: str = "NOT_REVIEWED",
    human_review: dict[str, object] | None = None,
) -> dict[str, object]:
    resolved_analysis_id = analysis_id or sample_id
    sample: dict[str, object] = {
        "sample_id": sample_id,
        "expected_recording_quality": expected_quality,
        "expected_insight_eligibility": expected_gate,
        "review_status": "NOT_REVIEWED",
        "artifacts": {
            "artifact_root": "artifacts",
            "inspection_analysis_id": resolved_analysis_id,
        },
    }
    if human_review is not None:
        sample["human_review"] = human_review
    return sample


def _write_metadata(
    tmp_path: Path,
    analysis_id: str,
    *,
    quality: str,
    width: int | None = None,
    height: int | None = None,
) -> None:
    settings = {
        "EXCELLENT": (1920, 1080, 30.0, 60.0),
        "GOOD": (1280, 720, 24.0, 20.0),
        "LIMITED": (720, 1280, 30.0, 20.0),
        "UNSUITABLE": (320, 240, 30.0, 20.0),
        "CUSTOM": (640, 400, 30.0, 20.0),
    }
    default_width, default_height, fps, duration = settings[quality]
    payload = {
        "analysis_id": analysis_id,
        "filename": "source.mp4",
        "file_size_bytes": 1000,
        "width": width or default_width,
        "height": height or default_height,
        "fps": fps,
        "frame_count": int(fps * duration),
        "duration_seconds": duration,
        "codec": "mp4v",
        "sample_interval_seconds": 5,
        "sampled_frames": 4,
        "rotation_degrees": 0,
        "created_at": REFERENCE_TIME,
    }
    path = tmp_path / "artifacts" / analysis_id / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_candidate_collection(
    tmp_path: Path,
    analysis_id: str,
    *,
    schema_version: int,
) -> None:
    candidate = {
        "candidate_id": "candidate-1",
        "source_raw_track_ids": [1],
        "first_observed_timestamp": 0,
        "last_observed_timestamp": 10,
        "total_observed_duration": 10,
        "total_observed_frames": 100,
        "court_distance_feet": 20,
        "court_movement_rate_feet_per_second": 2,
        "in_court_observation_ratio": 0.9,
        "representative_frame": 50,
        "representative_crop_artifact": None,
        "representative_full_frame_artifact": None,
        "preview_frames": [],
        "average_bounding_box": {
            "width_pixels": 30,
            "height_pixels": 80,
            "area_ratio": 0.01,
        },
        "court_side_estimate": "NEAR",
        "quality": "STRONG",
        "quality_reasons": [],
        "warnings": [],
        "automatic_merge_evidence": [],
        "review_status": "PENDING",
        "rejection_reason": None,
        "manual_merge_id": None,
    }
    payload = {
        "schema_version": schema_version,
        "analysis_id": analysis_id,
        "candidates": [candidate],
        "excluded_candidates": [],
        "selected_candidate_id": None,
        "manual_merge_decisions": [],
        "recording_suitability": {
            "status": "SUITABLE",
            "reasons": [],
            "guidance": [],
            "orientation": "landscape",
            "detected_people": 1,
            "usable_candidate_count": 1,
        },
        "performance": {
            "candidate_build_seconds": 0,
            "preview_generation_seconds": 0,
        },
        "generated_at": REFERENCE_TIME,
        "updated_at": REFERENCE_TIME,
    }
    path = tmp_path / "artifacts" / analysis_id / "tracking" / "player_candidates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_calibration(tmp_path: Path, analysis_id: str) -> None:
    path = (
        tmp_path
        / "artifacts"
        / analysis_id
        / "calibrations"
        / "auto-court-detection"
        / "calibration.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")


def _gate_for_quality(quality: str) -> str:
    return {
        "EXCELLENT": "NORMAL",
        "GOOD": "CAUTIOUS",
        "LIMITED": "MEASUREMENT_ONLY",
        "UNSUITABLE": "INSUFFICIENT_EVIDENCE",
    }[quality]
