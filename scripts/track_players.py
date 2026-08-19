import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.services.tracking import (
    JsonTrackingBackend,
    TrackingError,
    UltralyticsByteTrackBackend,
)
from app.services.video.player_analysis import analyze_players, load_calibration_report


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Track pickleball players in a calibrated video.")
    parser.add_argument("--input", required=True, type=Path, help="Path to the source match video.")
    parser.add_argument(
        "--calibration",
        required=True,
        type=Path,
        help="Path to a Phase 0.2 calibration.json file.",
    )
    parser.add_argument("--analysis-id", default=None, help="Optional analysis ID.")
    parser.add_argument(
        "--output-dir",
        default=settings.tracking_output_dir,
        type=Path,
        help="Base directory where tracking outputs will be written.",
    )
    parser.add_argument(
        "--detections-jsonl",
        default=None,
        type=Path,
        help="Controlled pre-tracked detections JSONL for offline validation.",
    )
    parser.add_argument(
        "--model-path",
        default=settings.detector_model_path,
        type=Path,
        help="Local Ultralytics YOLO model path. Required unless --detections-jsonl is used.",
    )
    parser.add_argument(
        "--confidence-threshold",
        default=settings.detector_confidence_threshold,
        type=float,
        help="Detector confidence threshold.",
    )
    parser.add_argument(
        "--frame-interval",
        default=settings.frame_processing_interval,
        type=int,
        help="Process every Nth frame.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.logging_level)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        calibration = load_calibration_report(args.calibration)
        backend = (
            JsonTrackingBackend(args.detections_jsonl)
            if args.detections_jsonl is not None
            else UltralyticsByteTrackBackend(
                model_path=args.model_path,
                expected_model_sha256=settings.detector_model_sha256,
                confidence_threshold=args.confidence_threshold,
                image_size=settings.detector_image_size,
            )
        )
        result = analyze_players(
            video_path=args.input,
            calibration=calibration,
            output_dir=args.output_dir,
            tracking_backend=backend,
            analysis_id=args.analysis_id,
            frame_interval=args.frame_interval,
            court_inclusion_margin_feet=settings.court_inclusion_margin_feet,
            min_eligible_track_duration_seconds=settings.min_eligible_track_duration_seconds,
            min_eligible_observation_count=settings.min_eligible_observation_count,
            min_eligible_inside_extended_ratio=settings.min_eligible_inside_extended_ratio,
            min_eligible_inside_court_ratio=settings.min_eligible_inside_court_ratio,
            min_eligible_court_movement_rate_feet_per_second=(
                settings.min_eligible_court_movement_rate_feet_per_second
            ),
            max_selectable_player_tracks=settings.max_selectable_player_tracks,
            min_eligible_average_confidence=settings.min_eligible_average_confidence,
            annotated_video_codec=settings.annotated_video_codec,
            annotated_video_fps=settings.annotated_video_fps,
        )
    except TrackingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.report.model_dump_json(indent=2))
    print(f"Tracking report written to: {result.tracking_path}", file=sys.stderr)
    print(f"Observations written to: {result.observations_path}", file=sys.stderr)
    print(
        f"Player selection image written to: {result.player_selection_image_path}",
        file=sys.stderr,
    )
    print(f"Annotated video written to: {result.annotated_video_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
