import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.evidence_calibration import (
    ArtifactReadiness,
    CalibrationManifest,
    CandidateRole,
)
from app.services.evidence_calibration import (
    LoadedCalibrationManifest,
    evaluate_manifest,
    load_calibration_manifest,
    write_calibration_reports,
)
from app.services.evidence_calibration.dataset import (
    incomplete_review_fields,
    sample_template,
    summarize_dataset_balance,
    unresolved_candidate_mappings,
    write_sample_template,
)
from app.services.recording_quality import QUALITY_THRESHOLDS

REFERENCE_TIME = "2026-07-25T00:00:00Z"


def test_v2_schema_accepts_detailed_partial_review() -> None:
    manifest = CalibrationManifest.model_validate(
        _manifest(
            [
                _sample(
                    "detailed",
                    human_review=_detailed_review(),
                )
            ]
        )
    )

    review = manifest.samples[0].human_review
    assert manifest.schema_version == 2
    assert review is not None
    assert review.player_candidates is not None
    assert len(review.player_candidates.candidate_mappings) == 3
    assert review.tracking is not None
    assert len(review.tracking.intervals) == 1


def test_phase_15_manifest_remains_readable() -> None:
    loaded = load_calibration_manifest(Path("calibration/manifest.v1.json"))

    assert loaded.manifest.schema_version == 1
    assert [sample.sample_id for sample in loaded.manifest.samples] == [
        "landscape-indoor-doubles-01",
        "vertical-indoor-drill-01",
    ]


def test_unknown_and_not_reviewed_labels_remain_distinct() -> None:
    payload = _manifest([_sample("unknown")])
    samples = payload["samples"]
    assert isinstance(samples, list)
    sample = samples[0]
    assert isinstance(sample, dict)
    sample["environment_type"] = "UNKNOWN"
    sample["camera_distance"] = "NOT_REVIEWED"

    manifest = CalibrationManifest.model_validate(payload)

    assert manifest.samples[0].environment_type.value == "UNKNOWN"
    assert manifest.samples[0].camera_distance.value == "NOT_REVIEWED"


def test_one_real_player_can_map_to_multiple_candidate_fragments() -> None:
    manifest = CalibrationManifest.model_validate(
        _manifest([_sample("fragments", human_review=_detailed_review())])
    )
    review = manifest.samples[0].human_review
    assert review is not None and review.player_candidates is not None

    mappings = review.player_candidates.candidate_mappings
    player_ids = [
        mapping.player_id
        for mapping in mappings
        if mapping.role in {CandidateRole.court_player, CandidateRole.duplicate}
    ]
    assert player_ids == ["player-a", "player-a"]


def test_duplicate_spectator_and_mapping_metrics_use_only_reviewed_labels(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "mapped", width=1280, height=720)
    loaded = _load(
        tmp_path,
        _manifest(
            [
                _sample(
                    "mapped",
                    expected_quality="GOOD",
                    human_review=_detailed_review(),
                )
            ]
        ),
    )

    results = evaluate_manifest(loaded, repository_root=tmp_path)
    metrics = results.metrics.candidate_reliability

    assert metrics.candidate_precision.numerator == 1
    assert metrics.candidate_precision.denominator == 3
    assert metrics.candidate_to_player_mapping_accuracy.numerator == 2
    assert metrics.candidate_to_player_mapping_accuracy.denominator == 3
    assert metrics.duplicate_candidate_count == 1
    assert metrics.spectator_promotion_count == 1


def test_interval_metrics_report_identity_continuity_and_gap_labels(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "intervals", width=1280, height=720)
    loaded = _load(
        tmp_path,
        _manifest([_sample("intervals", human_review=_detailed_review())]),
    )

    metrics = evaluate_manifest(
        loaded,
        repository_root=tmp_path,
    ).metrics.tracking_continuity

    assert metrics.reviewed_interval_count == 1
    assert metrics.correctly_maintained_identity_intervals.numerator == 1
    assert metrics.identity_switch_intervals == 0
    assert metrics.fragmented_intervals == 0
    assert metrics.valid_observed_time_agreement.numerator == 1
    assert metrics.gap_label_agreement.numerator == 1


def test_tracking_interval_rejects_invalid_time_range() -> None:
    review = _detailed_review()
    tracking = review["tracking"]
    assert isinstance(tracking, dict)
    intervals = tracking["intervals"]
    assert isinstance(intervals, list)
    intervals[0]["start_time_seconds"] = 5
    intervals[0]["end_time_seconds"] = 4

    with pytest.raises(ValidationError, match="end time must be after start time"):
        CalibrationManifest.model_validate(
            _manifest([_sample("invalid-time", human_review=review)])
        )


def test_tracking_review_rejects_overlapping_intervals_for_same_player() -> None:
    review = _detailed_review()
    tracking = review["tracking"]
    assert isinstance(tracking, dict)
    intervals = tracking["intervals"]
    assert isinstance(intervals, list)
    intervals.append(
        {
            **intervals[0],
            "start_time_seconds": 4,
            "end_time_seconds": 8,
        }
    )

    with pytest.raises(ValidationError, match="overlap"):
        CalibrationManifest.model_validate(_manifest([_sample("overlap", human_review=review)]))


def test_incomplete_review_reporting_lists_identity_interval_and_insight_work() -> None:
    manifest = CalibrationManifest.model_validate(_manifest([_sample("incomplete")]))

    missing = incomplete_review_fields(manifest.samples[0])

    assert "human_review" in missing
    assert "camera_distance" in missing
    assert "recording_stability" in missing


def test_unresolved_mapping_reporting_excludes_completed_mappings() -> None:
    review = _detailed_review()
    candidates = review["player_candidates"]
    assert isinstance(candidates, dict)
    mappings = candidates["candidate_mappings"]
    assert isinstance(mappings, list)
    mappings[2]["role"] = "UNCERTAIN"
    mappings[2]["mapping_correct"] = "NOT_REVIEWED"
    manifest = CalibrationManifest.model_validate(
        _manifest([_sample("mapping-review", human_review=review)])
    )

    assert unresolved_candidate_mappings(manifest.samples[0]) == ["candidate-3"]


def test_dataset_balance_reports_missing_and_underrepresented_categories() -> None:
    payload = _manifest(
        [
            _sample(
                "balanced-one",
                expected_quality="GOOD",
                environment_type="INDOOR",
                match_format="DOUBLES",
                orientation="LANDSCAPE",
                camera_position_label="BASELINE",
            )
        ]
    )
    summary = summarize_dataset_balance(CalibrationManifest.model_validate(payload))
    environment = next(
        category for category in summary.categories if category.category == "environment"
    )

    assert environment.counts == {"INDOOR": 1, "OUTDOOR": 0}
    assert environment.missing == ["OUTDOOR"]
    assert environment.underrepresented == ["INDOOR"]
    assert summary.provisional_warnings


def test_artifact_compatibility_distinguishes_legacy_and_missing(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "legacy", width=1280, height=720)
    _write_candidate_collection(tmp_path, "legacy", schema_version=1)
    sample = _sample("legacy", expected_quality="GOOD")
    artifacts = sample["artifacts"]
    assert isinstance(artifacts, dict)
    artifacts["candidates_analysis_id"] = "legacy"
    artifacts["analytics_analysis_id"] = "missing"
    results = evaluate_manifest(
        _load(tmp_path, _manifest([sample])),
        repository_root=tmp_path,
    )
    by_name = {artifact.artifact: artifact for artifact in results.samples[0].artifacts}

    assert by_name["inspection_metadata"].compatibility == ArtifactReadiness.ready
    assert by_name["player_candidates"].compatibility == ArtifactReadiness.legacy_compatible
    assert by_name["analytics"].compatibility == ArtifactReadiness.missing
    assert results.samples[0].artifact_readiness == ArtifactReadiness.partial


def test_disagreement_generation_covers_output_and_incomplete_annotation(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "disagree", width=1280, height=720)
    results = evaluate_manifest(
        _load(
            tmp_path,
            _manifest(
                [
                    _sample(
                        "disagree",
                        expected_quality="UNSUITABLE",
                        expected_gate="INSUFFICIENT_EVIDENCE",
                    )
                ]
            ),
        ),
        repository_root=tmp_path,
    )

    categories = {item.category.value for item in results.disagreements}
    assert "RECORDING_ASSESSMENT" in categories
    assert "INSIGHT_GATING" in categories
    assert "INCOMPLETE_ANNOTATION" in categories


def test_holdout_and_validation_are_excluded_from_threshold_simulation(
    tmp_path: Path,
) -> None:
    for analysis_id in ("development", "validation", "holdout"):
        _write_metadata(tmp_path, analysis_id, width=640, height=400)
    payload = _manifest(
        [
            _sample(
                "development",
                dataset_split="DEVELOPMENT",
                expected_quality="LIMITED",
            ),
            _sample(
                "validation",
                dataset_split="VALIDATION",
                expected_quality="LIMITED",
            ),
            _sample(
                "holdout",
                dataset_split="HOLDOUT",
                expected_quality="LIMITED",
            ),
        ],
        threshold_simulations=[
            {
                "threshold": "blocking_short_edge_pixels",
                "proposed_value": 360,
                "rationale": "Exploratory test.",
            }
        ],
    )

    result = evaluate_manifest(_load(tmp_path, payload), repository_root=tmp_path)
    simulation = result.threshold_analysis[0]

    assert simulation.affected_samples == ["development"]
    assert simulation.improvements == ["development"]
    assert simulation.excluded_samples == ["holdout", "validation"]
    assert QUALITY_THRESHOLDS.blocking_short_edge_pixels == 480


def test_report_generation_preserves_labels_and_is_deterministic(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path, "stable", width=1280, height=720)
    manifest_path = _write_manifest(
        tmp_path,
        _manifest([_sample("stable", human_review=_detailed_review())]),
    )
    original = manifest_path.read_bytes()
    results = evaluate_manifest(
        load_calibration_manifest(manifest_path),
        repository_root=tmp_path,
    )
    outputs: list[bytes] = []
    for prefix in ("first", "second"):
        json_path = tmp_path / f"{prefix}.json"
        markdown_path = tmp_path / f"{prefix}.md"
        disagreement_path = tmp_path / f"{prefix}-disagreements.md"
        write_calibration_reports(
            results,
            json_path=json_path,
            markdown_path=markdown_path,
            disagreements_path=disagreement_path,
            manifest_path=manifest_path,
        )
        outputs.extend(
            [
                json_path.read_bytes(),
                markdown_path.read_bytes(),
                disagreement_path.read_bytes(),
            ]
        )

    assert outputs[:3] == outputs[3:]
    assert manifest_path.read_bytes() == original


def test_sample_template_is_valid_and_requires_explicit_overwrite(
    tmp_path: Path,
) -> None:
    template = sample_template("new-recording")
    CalibrationManifest.model_validate(_manifest([template]))
    output = tmp_path / "sample.json"

    write_sample_template(output, "new-recording")
    with pytest.raises(FileExistsError, match="--force"):
        write_sample_template(output, "new-recording")
    write_sample_template(output, "new-recording", overwrite=True)


def _manifest(
    samples: list[dict[str, object]],
    *,
    threshold_simulations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "dataset_id": "phase15a-test",
        "dataset_version": "2.0.0",
        "reference_time": REFERENCE_TIME,
        "minimum_recommended_sample_size": 5,
        "threshold_simulations": threshold_simulations or [],
        "samples": samples,
    }


def _sample(
    sample_id: str,
    *,
    expected_quality: str = "NOT_REVIEWED",
    expected_gate: str = "NOT_REVIEWED",
    human_review: dict[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    sample: dict[str, object] = {
        "sample_id": sample_id,
        "dataset_split": "DEVELOPMENT",
        "environment_type": "NOT_REVIEWED",
        "match_format": "NOT_REVIEWED",
        "orientation": "UNKNOWN",
        "camera_position_label": "NOT_REVIEWED",
        "camera_distance": "NOT_REVIEWED",
        "lighting_condition": "NOT_REVIEWED",
        "recording_stability": "NOT_REVIEWED",
        "court_visibility": "UNKNOWN",
        "expected_recording_quality": expected_quality,
        "expected_insight_eligibility": expected_gate,
        "review_status": "PARTIALLY_REVIEWED" if human_review else "NOT_REVIEWED",
        "artifacts": {
            "artifact_root": "artifacts",
            "inspection_analysis_id": sample_id,
        },
    }
    if human_review is not None:
        sample["human_review"] = human_review
    sample.update(overrides)
    return sample


def _detailed_review() -> dict[str, object]:
    return {
        "recording": {
            "recording_quality_verdict": "GOOD",
            "obstruction_severity": "NONE",
        },
        "player_candidates": {
            "expected_court_player_count": 1,
            "expected_players_represented": 1,
            "missed_players": 0,
            "stable_real_players": [{"player_id": "player-a"}],
            "candidate_mappings": [
                {
                    "candidate_id": "candidate-1",
                    "player_id": "player-a",
                    "role": "COURT_PLAYER",
                    "mapping_correct": "YES",
                },
                {
                    "candidate_id": "candidate-2",
                    "player_id": "player-a",
                    "role": "DUPLICATE",
                    "mapping_correct": "YES",
                },
                {
                    "candidate_id": "candidate-3",
                    "role": "SPECTATOR",
                    "mapping_correct": "NO",
                },
            ],
        },
        "tracking": {
            "fragmentation_severity": "NONE",
            "intervals": [
                {
                    "start_time_seconds": 0,
                    "end_time_seconds": 5,
                    "expected_player_id": "player-a",
                    "candidate_id": "candidate-1",
                    "identity_correct": "YES",
                    "continuity": "ACCEPTABLE",
                    "occlusion": "NO",
                    "player_outside_frame": "NO",
                    "tracking_gap": "NO",
                    "observed_time_agreement": "YES",
                    "gap_label_agreement": "YES",
                }
            ],
        },
        "insight": {
            "generated_insights": [
                {
                    "insight_id": "movement-summary",
                    "measurement_correct": "YES",
                    "interpretation_justified": "YES",
                    "confidence_appropriate": "YES",
                    "limitation_accurate": "YES",
                    "action_conservative": "YES",
                    "wording_understandable": "YES",
                    "expected_gate_result": "CAUTIOUS",
                }
            ]
        },
    }


def _load(
    tmp_path: Path,
    payload: dict[str, object],
) -> LoadedCalibrationManifest:
    return load_calibration_manifest(_write_manifest(tmp_path, payload))


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_metadata(
    tmp_path: Path,
    analysis_id: str,
    *,
    width: int,
    height: int,
) -> None:
    payload = {
        "analysis_id": analysis_id,
        "filename": "source.mp4",
        "file_size_bytes": 1000,
        "width": width,
        "height": height,
        "fps": 30,
        "frame_count": 900,
        "duration_seconds": 30,
        "codec": "mp4v",
        "sample_interval_seconds": 5,
        "sampled_frames": 6,
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
        "selection_eligible": True,
        "selection_exclusion_reasons": [],
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
