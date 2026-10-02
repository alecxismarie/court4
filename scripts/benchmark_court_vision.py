"""Run an isolated, deterministic, label-based benchmark of the unchanged court detector."""

import argparse
import hashlib
import json
import platform
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pydantic

from app.config.settings import Settings
from app.services.court_detection import automatic
from scripts import court_vision_annotations, court_vision_metrics
from scripts.court_vision_annotations import BenchmarkManifest
from scripts.court_vision_metrics import POLICY, evaluate

OPTION_FIELDS = {
    "min_confidence": "court_detection_min_confidence",
    "low_confidence_threshold": "court_detection_low_confidence_threshold",
    "numeric_tolerance": "numeric_validation_tolerance",
    "min_polygon_area_pixels": "min_calibration_polygon_area_pixels",
    "transition_area_depth_feet": "transition_area_depth_feet",
    "top_down_width_pixels": "calibration_top_down_width_pixels",
}
GROUP_FIELDS = (
    "recording_id",
    "venue_id",
    "court_id",
    "camera_setup_id",
    "source_video_sha256",
    "image_sha256",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detector_options() -> dict[str, Any]:
    # Read committed defaults, not .env or deployment state. Never instantiate Settings.
    return {
        argument: Settings.model_fields[field].default for argument, field in OPTION_FIELDS.items()
    }


def leakage_report(manifest: BenchmarkManifest) -> list[dict[str, Any]]:
    warnings = []
    for field in GROUP_FIELDS:
        groups: dict[str, list[Any]] = defaultdict(list)
        for frame in manifest.frames:
            value = getattr(frame, field)
            if value is not None:
                groups[value].append(frame)
        for value, frames in sorted(groups.items()):
            splits = sorted({frame.split for frame in frames})
            if len(splits) > 1:
                warnings.append(
                    {
                        "field": field,
                        "value": value,
                        "splits": splits,
                        "frame_ids": sorted(frame.frame_id for frame in frames),
                    }
                )
    return warnings


def count_outcomes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["evaluation"]["outcome"] for row in rows)
    return {
        "frames": len(rows),
        **{name: counts[name] for name in ("accept", "abstain", "incorrect")},
    }


def run_benchmark(
    manifest: BenchmarkManifest, image_root: Path, scratch_root: Path
) -> dict[str, Any]:
    """Only scratch artifacts are written. No repository, workflow, DB or model is loaded."""
    rows: list[dict[str, Any]] = []
    root = image_root.resolve()
    options = detector_options()
    for frame in sorted(manifest.frames, key=lambda item: item.frame_id):
        path = (root / frame.image_path).resolve()
        if Path(frame.image_path).is_absolute() or not path.is_relative_to(root):
            raise ValueError(f"{frame.frame_id}: image_path must stay inside --image-root.")
        input_issue = None
        image = None
        if not path.is_file():
            input_issue = "image_missing"
        elif sha256(path) != frame.image_sha256:
            input_issue = "image_checksum_mismatch"
        else:
            image = cv2.imread(str(path))
            if image is None:
                input_issue = "image_undecodable"
            elif image.shape[:2] != (frame.height, frame.width):
                input_issue = "decoded_dimensions_mismatch"
        detector: dict[str, Any] = {"outcome": "not_run", "confidence": None, "corners": None}
        if input_issue:
            evaluation = evaluate(frame, None)
            evaluation["reasons"] = [input_issue]
        else:
            # The production function also writes timestamped calibration/overlay files.
            # Discard those scratch artifacts; include only deterministic proposal data.
            with tempfile.TemporaryDirectory(prefix="court-vision-", dir=scratch_root) as temporary:
                proposal = automatic.detect_pickleball_court(
                    frame_paths=[path],
                    output_dir=Path(temporary),
                    analysis_id="benchmark",
                    calibration_id="proposal",
                    **options,
                )
            detector = {
                "outcome": proposal.outcome.value,
                "confidence": proposal.confidence,
                "corners": proposal.image_points,
            }
            evaluation = evaluate(frame, proposal.image_points)
        rows.append(
            {
                "frame_id": frame.frame_id,
                "recording_id": frame.recording_id,
                "venue_id": frame.venue_id,
                "court_id": frame.court_id,
                "camera_setup_id": frame.camera_setup_id,
                "shot_id": frame.shot_id,
                "split": frame.split,
                "data_kind": frame.data_kind,
                "image_sha256": frame.image_sha256,
                "review_status": frame.review_status,
                "input_issue": input_issue,
                "detector": detector,
                "evaluation": evaluation,
            }
        )
    groups = {}
    for field in ("recording_id", "venue_id", "split", "data_kind"):
        groups[field] = {
            value: count_outcomes([row for row in rows if row[field] == value])
            for value in sorted({row[field] for row in rows})
        }
    canonical_manifest = manifest.model_dump(mode="json")
    canonical_manifest["frames"] = sorted(canonical_manifest["frames"], key=lambda f: f["frame_id"])
    source_files = {
        "detector": Path(automatic.__file__),
        "annotations": Path(court_vision_annotations.__file__),
        "metrics": Path(court_vision_metrics.__file__),
        "runner": Path(__file__),
    }
    repository = Path(__file__).resolve().parents[1]
    for relative in (
        "app/config/settings.py",
        "app/sports/pickleball/calibration.py",
        "app/sports/pickleball/geometry.py",
        "app/sports/pickleball/landmarks.py",
    ):
        source_files[relative] = repository / relative
    reviewed_real_examples = sum(
        row["data_kind"] == "real" and row["review_status"] == "reviewed" for row in rows
    )
    usable_reviewed_real_frames = sum(
        row["data_kind"] == "real"
        and row["review_status"] == "reviewed"
        and row["input_issue"] is None
        for row in rows
    )
    return {
        "result_version": "court-vision-benchmark-v1",
        "dataset_id": manifest.dataset_id,
        "manifest_sha256": hashlib.sha256(canonical_json(canonical_manifest).encode()).hexdigest(),
        "source_sha256": {key: sha256(value) for key, value in source_files.items()},
        "runtime": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pydantic": pydantic.__version__,
        },
        "detector_options": options,
        "evaluation_policy": POLICY,
        "summary": count_outcomes(rows),
        "groups": groups,
        "frames": rows,
        "unique_images": len({row["image_sha256"] for row in rows}),
        "reviewed_real_examples": reviewed_real_examples,
        "usable_reviewed_real_frames": usable_reviewed_real_frames,
        "real_world_assessment": {
            "accuracy_conclusion": "unavailable_no_reviewed_real_examples"
            if reviewed_real_examples == 0
            else "limited_to_reviewed_benchmark_examples",
            "accepted_geometry_correctness_gate": "not_evaluated",
            "supported_view_coverage_gate": "not_evaluated",
            "prototype_gates_claimed_met": False,
        },
        "leakage_warnings": leakage_report(manifest),
        "limitations": [
            "Annotation-conditioned offline evaluation; accept never means production verified.",
            "Per-frame replay, not production best-of-video or temporal stability validation.",
            "Line errors use independent paint labels; no learned/image line verifier.",
            "Missing evidence abstains; synthetic fixtures do not establish real-world accuracy.",
        ],
    }


def render_report(result: dict[str, Any]) -> str:
    counts = result["summary"]
    lines = [
        f"# Court vision benchmark: {result['dataset_id']}",
        "",
        f"Frames: {counts['frames']}; unique images: {result['unique_images']}.",
        f"Reviewed real examples: {result['reviewed_real_examples']}; "
        f"usable reviewed real frames: {result['usable_reviewed_real_frames']}.",
        "",
        f"Accept: {counts['accept']}; abstain: {counts['abstain']}; "
        f"incorrect: {counts['incorrect']}.",
        "",
        "Outcomes assess proposals against labels, independently of detector confidence.",
        "An accept is an offline annotation-supported result, never human verification.",
        "",
        f"Cross-split leakage warnings: {len(result['leakage_warnings'])}.",
    ]
    if not counts["frames"]:
        lines.extend(
            [
                "",
                "EMPTY DATASET: no real-world accuracy conclusion is available.",
                "Prototype accepted-geometry correctness gate: not evaluated; not claimed met.",
                "Prototype supported-view coverage gate: not evaluated; not claimed met.",
            ]
        )
    for field in ("recording_id", "venue_id"):
        lines.extend(
            [
                "",
                f"## By {field}",
                "",
                "| Group | Frames | Accept | Abstain | Incorrect |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for group, values in result["groups"][field].items():
            lines.append(
                f"| {group} | {values['frames']} | {values['accept']} | "
                f"{values['abstain']} | {values['incorrect']} |"
            )
    lines.extend(
        [
            "",
            "## Frames",
            "",
            "| Frame | Detector | Evaluation | Corner p95 px | Worst line p95 px | Reasons |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for row in result["frames"]:
        evaluation = row["evaluation"]
        corner = evaluation["corner_projection"]
        corner_text = f"{corner['p95_px']:.3f}" if corner else "n/a"
        line_errors = [m["p95_px"] for m in evaluation["lines"].values() if m]
        line_text = f"{max(line_errors):.3f}" if line_errors else "n/a"
        lines.append(
            f"| {row['frame_id']} | {row['detector']['outcome']} | "
            f"{evaluation['outcome']} | {corner_text} | {line_text} | "
            f"{', '.join(evaluation['reasons'])} |"
        )
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in result["limitations"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--image-root", required=True, type=Path)
    parser.add_argument(
        "--output-dir", required=True, type=Path, help="New offline directory only."
    )
    args = parser.parse_args(argv)
    try:
        manifest = BenchmarkManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
        args.output_dir.mkdir(parents=True, exist_ok=False)
        result = run_benchmark(manifest, args.image_root, args.output_dir)
        (args.output_dir / "results.json").write_text(canonical_json(result), encoding="utf-8")
        (args.output_dir / "REPORT.md").write_text(render_report(result), encoding="utf-8")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Benchmark failed: {exc}\n")
    print(f"Offline results: {args.output_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
