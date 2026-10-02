"""Standalone offline tests: run with --confcutdir=tests/offline_court_vision.

No global database fixtures are needed or loaded by this isolated suite.
"""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from scripts.benchmark_court_vision import (
    canonical_json,
    detector_options,
    leakage_report,
    main,
    render_report,
    run_benchmark,
)
from scripts.court_vision_annotations import (
    CORNERS,
    KEYPOINTS,
    LINES,
    BenchmarkManifest,
    FrameAnnotation,
)
from scripts.court_vision_metrics import evaluate


def pixel(point):
    return (100.0 + point[0] * 20, 900.0 - point[1] * 18)


def frame_data(tmp_path: Path, *, background=False):
    image = np.zeros((1000, 800, 3), dtype=np.uint8)
    for a, b in LINES.values():
        cv2.line(image, tuple(map(int, pixel(a))), tuple(map(int, pixel(b))), (255, 255, 255), 2)
    if background:
        # Saturated outer rectangle is a tempting polygon, unrelated to the true white court.
        cv2.rectangle(image, (40, 50), (680, 940), (0, 255, 0), 4)
    path = tmp_path / "court.png"
    assert cv2.imwrite(str(path), image)
    return {
        "frame_id": "frame-1",
        "image_path": path.name,
        "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_reference": "generated-test-fixture",
        "usage_provenance": "synthetic-test-only",
        "recording_id": "recording-1",
        "venue_id": "venue-1",
        "court_id": "court-1",
        "camera_setup_id": "camera-1",
        "shot_id": "shot-1",
        "split": "development",
        "data_kind": "synthetic",
        "frame_number": 1,
        "timestamp_seconds": 0,
        "width": 800,
        "height": 1000,
        "coordinate_space": "original_decoded_pixels",
        "orientation": "camera_relative_near_left",
        "camera_motion": "stationary",
        "suitability": "full_geometry_supported",
        "reasons": [],
        "tags": ["synthetic"],
        "annotator": "analytic-fixture",
        "reviewer": "test-assertions",
        "review_status": "reviewed",
        "keypoints": {
            name: {"visibility": "visible", "xy": pixel(point), "uncertainty_px": 0}
            for name, point in KEYPOINTS.items()
        },
        "lines": {
            name: {
                "reference": "stripe_center"
                if "center_service" in name
                else ("away_from_net" if "nvz" in name else "outside_perimeter"),
                "visible_runs": [{"points": [pixel(a), pixel(b)]}],
                "uncertainty_px": 0,
                "paint_width_px": 2,
                "unobserved_reason": "none",
            }
            for name, (a, b) in LINES.items()
        },
    }


def manifest(frames):
    return BenchmarkManifest.model_validate(
        {
            "schema_version": "court-vision-annotations-v1",
            "template_version": "pickleball-court-v1",
            "annotation_convention": "outside-perimeter-nvz-away-service-center-v1",
            "dataset_id": "synthetic-tests-only",
            "frames": frames,
        }
    )


def corners():
    return np.array([pixel(KEYPOINTS[name]) for name in CORNERS])


@pytest.mark.parametrize("mutation", ["missing", "extra", "nan", "bounds", "edge", "reviewer"])
def test_annotation_validation(tmp_path, mutation):
    data = frame_data(tmp_path)
    if mutation == "missing":
        del data["keypoints"]["far_left"]
    elif mutation == "extra":
        data["keypoints"]["net_top"] = data["keypoints"]["near_left"]
    elif mutation == "nan":
        data["keypoints"]["near_left"]["xy"] = (float("nan"), 0)
    elif mutation == "bounds":
        data["lines"]["near_nvz"]["visible_runs"][0]["points"][0] = (800, 0)
    elif mutation == "edge":
        data["lines"]["near_nvz"]["reference"] = "stripe_center"
    else:
        data["reviewer"] = data["annotator"]
    with pytest.raises(ValidationError):
        FrameAnnotation.model_validate(data)


@pytest.mark.parametrize("visibility", ["unknown", "outside_frame", "occluded_localizable"])
def test_missing_or_occluded_points_are_not_evidence(tmp_path, visibility):
    data = frame_data(tmp_path)
    point = data["keypoints"]["far_left"]
    point["visibility"] = visibility
    if visibility != "occluded_localizable":
        point["xy"] = point["uncertainty_px"] = None
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["outcome"] == "abstain"
    assert result["corner_projection"]["count"] == 3
    assert "far_left" not in result["keypoint_errors_px"]


def test_unknown_with_guessed_coordinate_rejected(tmp_path):
    data = frame_data(tmp_path)
    data["keypoints"]["near_left"]["visibility"] = "unknown"
    with pytest.raises(ValidationError):
        FrameAnnotation.model_validate(data)


def test_known_projection_and_line_errors(tmp_path):
    frame = FrameAnnotation.model_validate(frame_data(tmp_path))
    result = evaluate(frame, corners() + (3, 4))
    assert result["corner_projection"]["mean_px"] == pytest.approx(5)
    assert result["interior_projection"]["mean_px"] == pytest.approx(5)
    # Interior samples avoid finite-segment endpoint effects for the maximum statistic.
    assert result["lines"]["left_sideline"]["p95_px"] == pytest.approx(3)
    assert result["lines"]["near_nvz"]["p95_px"] == pytest.approx(4)
    assert result["court_error_p95_feet"] == pytest.approx(np.hypot(3 / 20, 4 / 18))


def test_correct_geometry_and_missing_line(tmp_path):
    data = frame_data(tmp_path)
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["outcome"] == "accept"
    assert result["corner_projection"]["max_px"] == pytest.approx(0)
    assert all(m["mean_px"] == pytest.approx(0) for m in result["lines"].values())
    data["lines"]["far_nvz"].update(visible_runs=[], unobserved_reason="occluded")
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["outcome"] == "abstain"
    assert result["lines"]["far_nvz"] is None


def test_interior_lines_can_contradict_perfect_corners(tmp_path):
    data = frame_data(tmp_path)
    data["lines"]["near_nvz"]["visible_runs"][0]["points"] = [(100, 550), (500, 550)]
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["corner_projection"]["max_px"] == pytest.approx(0)
    assert result["outcome"] == "incorrect"
    assert "line_misaligned:near_nvz" in result["reasons"]


def test_sparse_and_duplicate_visible_runs_do_not_manufacture_coverage(tmp_path):
    data = frame_data(tmp_path)
    run = {"points": [(100, 630), (120, 630)]}
    data["lines"]["near_nvz"]["visible_runs"] = [run, run]
    data["lines"]["near_nvz"]["unobserved_reason"] = "occluded"
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["lines"]["near_nvz"]["projected_coverage"] == pytest.approx(0.05)
    assert result["outcome"] == "abstain"


@pytest.mark.parametrize("kind", ["draft", "uncertainty", "no_proposal", "singular"])
def test_unsupported_inputs_do_not_accept(tmp_path, kind):
    data = frame_data(tmp_path)
    proposal = corners()
    if kind == "draft":
        data["review_status"] = "draft"
    elif kind == "uncertainty":
        data["keypoints"]["near_left"]["uncertainty_px"] = 100
    elif kind == "no_proposal":
        proposal = None
    else:
        proposal = np.zeros((4, 2))
    assert evaluate(FrameAnnotation.model_validate(data), proposal)["outcome"] != "accept"


def test_no_target_is_not_correct_geometry(tmp_path):
    data = frame_data(tmp_path)
    data["suitability"] = "no_target_court"
    data["keypoints"] = {name: {"visibility": "unknown"} for name in KEYPOINTS}
    for line in data["lines"].values():
        line.update(visible_runs=[], unobserved_reason="unknown")
    frame = FrameAnnotation.model_validate(data)
    assert evaluate(frame, corners())["outcome"] == "incorrect"
    assert evaluate(frame, None)["outcome"] == "abstain"


@pytest.mark.parametrize("background", [False, True])
def test_existing_detector_replay(tmp_path, background):
    data = frame_data(tmp_path, background=background)
    result = run_benchmark(manifest([data]), tmp_path, tmp_path)
    row = result["frames"][0]
    assert row["detector"]["outcome"] == "detected"
    assert row["detector"]["confidence"] > 0.9
    assert row["evaluation"]["outcome"] == ("incorrect" if background else "accept")
    assert result["usable_reviewed_real_frames"] == 0
    assert not list(tmp_path.glob("court-vision-*"))


def test_deterministic_output_and_groups(tmp_path, monkeypatch):
    first = frame_data(tmp_path)
    second = {**first, "frame_id": "frame-2", "split": "test"}
    dataset = manifest([second, first])
    monkeypatch.setenv("PICKLEBALL_AI_COURT_DETECTION_MIN_CONFIDENCE", "0.01")
    assert detector_options()["min_confidence"] == 0.72
    a = run_benchmark(dataset, tmp_path, tmp_path)
    b = run_benchmark(manifest([first, second]), tmp_path, tmp_path)
    assert canonical_json(a) == canonical_json(b)
    assert render_report(a) == render_report(b)
    assert a["groups"]["recording_id"]["recording-1"]["frames"] == 2
    assert {item["field"] for item in leakage_report(dataset)} >= {
        "recording_id",
        "venue_id",
        "image_sha256",
    }


@pytest.mark.parametrize("problem", ["checksum", "missing", "dimensions", "escape"])
def test_input_integrity(tmp_path, problem):
    data = frame_data(tmp_path)
    if problem == "checksum":
        data["image_sha256"] = "0" * 64
    elif problem == "missing":
        data["image_path"] = "missing.png"
    elif problem == "dimensions":
        data["width"] = 900
    else:
        data["image_path"] = "../escape.png"
        with pytest.raises(ValueError, match="inside"):
            run_benchmark(manifest([data]), tmp_path, tmp_path)
        return
    result = run_benchmark(manifest([data]), tmp_path, tmp_path)
    assert result["frames"][0]["input_issue"] is not None
    assert result["frames"][0]["detector"]["outcome"] == "not_run"
    assert result["summary"]["abstain"] == 1


def test_cli_reports_empty_dataset_and_refuses_overwrite(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(manifest([]).model_dump_json(), encoding="utf-8")
    args = [
        "--manifest",
        str(path),
        "--image-root",
        str(tmp_path),
        "--output-dir",
        str(tmp_path / "results"),
    ]
    assert main(args) == 0
    result = json.loads((tmp_path / "results/results.json").read_text())
    assert result["reviewed_real_examples"] == 0
    assert result["real_world_assessment"] == {
        "accepted_geometry_correctness_gate": "not_evaluated",
        "accuracy_conclusion": "unavailable_no_reviewed_real_examples",
        "prototype_gates_claimed_met": False,
        "supported_view_coverage_gate": "not_evaluated",
    }
    report = (tmp_path / "results/REPORT.md").read_text()
    assert "Reviewed real examples: 0" in report
    assert "no real-world accuracy conclusion is available" in report
    assert report.count("not evaluated; not claimed met") == 2
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_projective_geometry_and_swapped_corners(tmp_path):
    data = frame_data(tmp_path)

    def perspective(point):
        x, y = point
        return ((100 + 20 * x + y) / (1 + 0.015 * y), (900 - 16 * y) / (1 + 0.015 * y))

    for name, point in KEYPOINTS.items():
        data["keypoints"][name]["xy"] = perspective(point)
    for name, endpoints in LINES.items():
        data["lines"][name]["visible_runs"] = [{"points": list(map(perspective, endpoints))}]
    frame = FrameAnnotation.model_validate(data)
    proposal = np.array([perspective(KEYPOINTS[name]) for name in CORNERS])
    result = evaluate(frame, proposal)
    assert result["outcome"] == "accept"
    assert result["corner_projection"]["max_px"] < 0.001
    assert evaluate(frame, proposal[[3, 2, 1, 0]])["outcome"] == "incorrect"


def test_unresolved_orientation_abstains_even_for_plausible_shape(tmp_path):
    data = frame_data(tmp_path)
    data["orientation"] = "unresolved"
    result = evaluate(FrameAnnotation.model_validate(data), corners())
    assert result["outcome"] == "abstain"
    assert result["reasons"] == ["unresolved_orientation"]


def test_schema_and_template_match_executable_contract():
    directory = Path(__file__).resolve().parents[2] / "calibration/court_vision"
    schema = json.loads((directory / "annotation.schema.json").read_text())
    assert schema == BenchmarkManifest.model_json_schema()
    template = FrameAnnotation.model_validate_json(
        (directory / "frame-template.v1.json").read_text()
    )
    assert template.review_status == "draft"
    assert all(point.visibility == "unknown" for point in template.keypoints.values())
    assert set(schema["$defs"]["FrameAnnotation"]["properties"]["keypoints"]["required"]) == set(
        KEYPOINTS
    )
