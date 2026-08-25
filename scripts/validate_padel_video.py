from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.services.video import VideoInspectionError, inspect_video


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Create a factual Padel experimental validation report."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--consent-reference", required=True)
    parser.add_argument("--acknowledge-experimental", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_experimental:
        parser.error("--acknowledge-experimental is required")

    try:
        inspection = inspect_video(
            input_path=args.input,
            output_dir=args.output_dir,
            sample_interval_seconds=settings.default_sample_interval_seconds,
            supported_extensions=settings.supported_extensions,
            max_file_size_bytes=settings.max_upload_size_bytes,
            analysis_id=args.analysis_id,
        )
    except VideoInspectionError as exc:
        parser.error(str(exc))

    metadata = inspection.report
    report = {
        "report_type": "PADEL_EXPERIMENTAL_VALIDATION",
        "schema_version": 1,
        "sport": "padel",
        "sport_config_version": "padel-experimental-v1",
        "court_definition_version": "padel-court-v1",
        "consent_reference": args.consent_reference,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "video": {
            "duration_seconds": metadata.duration_seconds,
            "resolution": {"width": metadata.width, "height": metadata.height},
            "fps": metadata.fps,
            "codec": metadata.codec,
            "rotation_degrees": metadata.rotation_degrees,
            "decoding": "READY",
            "camera_angle": "NOT_ASSESSED_AUTOMATICALLY",
        },
        "court": {
            "visibility": "REQUIRES_HUMAN_REVIEW_OF_SAMPLED_FRAMES",
            "detected": "NOT_RUN_PICKLEBALL_DETECTOR_INCOMPATIBLE",
            "calibration": "NOT_YET_VALIDATED",
            "limitations": [
                "Padel-specific court detection is not implemented.",
                "Wall, glass, and fence interactions are not modelled.",
            ],
        },
        "players": {
            "detection": "NOT_YET_VALIDATED",
            "tracking_continuity": "NOT_YET_VALIDATED",
            "occlusions": "NOT_YET_VALIDATED",
            "identity_stability": "NOT_YET_VALIDATED",
            "player_selection": "NOT_YET_VALIDATED",
        },
        "ball": {
            "status": "NOT_RUN",
            "detector_scope": "YELLOW_LIME_COLOR_MOTION_EXPERIMENT",
            "trajectory": "NOT_YET_VALIDATED",
            "glass_reflection_interference": "NOT_YET_VALIDATED",
        },
        "existing_analytics": {
            "movement_metrics": "UNAVAILABLE",
            "match_iq": "INTENTIONALLY_UNAVAILABLE",
            "play_history_contribution": "DISABLED",
        },
        "artifacts": {
            "metadata": str(inspection.metadata_path),
            "sampled_frames": [str(path) for path in inspection.frame_paths],
        },
        "runtime": {"resource_behavior": "VIDEO_INSPECTION_ONLY"},
    }
    report_path = inspection.analysis_dir / "padel_validation.v1.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "sport": "padel"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
