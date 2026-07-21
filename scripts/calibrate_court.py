import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.sports.pickleball import CourtCalibrationError, calibrate_court
from app.sports.pickleball.geometry import Point2D


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Calibrate a pickleball court from one frame.")
    parser.add_argument("--input", required=True, type=Path, help="Path to a sampled frame image.")
    parser.add_argument(
        "--output-dir",
        default=settings.calibration_output_dir,
        type=Path,
        help="Directory where calibration outputs will be written.",
    )
    parser.add_argument("--analysis-id", default=None, help="Optional existing analysis ID.")
    parser.add_argument(
        "--calibration-id",
        default=None,
        help="Optional calibration ID. If omitted, a UUID-based ID is generated.",
    )
    parser.add_argument("--near-left", required=True, type=_parse_point)
    parser.add_argument("--near-right", required=True, type=_parse_point)
    parser.add_argument("--far-right", required=True, type=_parse_point)
    parser.add_argument("--far-left", required=True, type=_parse_point)
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.logging_level)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = calibrate_court(
            image_path=args.input,
            output_dir=args.output_dir,
            image_points=(args.near_left, args.near_right, args.far_right, args.far_left),
            calibration_id=args.calibration_id,
            analysis_id=args.analysis_id,
            numeric_tolerance=settings.numeric_validation_tolerance,
            min_polygon_area_pixels=settings.min_calibration_polygon_area_pixels,
            transition_area_depth_feet=settings.transition_area_depth_feet,
            top_down_width_pixels=settings.calibration_top_down_width_pixels,
        )
    except CourtCalibrationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.report.model_dump_json(indent=2))
    print(f"Calibration written to: {result.calibration_path}", file=sys.stderr)
    print(f"Verification image written to: {result.verification_image_path}", file=sys.stderr)
    if result.top_down_image_path is not None:
        print(f"Top-down image written to: {result.top_down_image_path}", file=sys.stderr)
    return 0


def _parse_point(value: str) -> Point2D:
    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("Point must use x,y format.")
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Point values must be numeric.") from exc


if __name__ == "__main__":
    raise SystemExit(main())
