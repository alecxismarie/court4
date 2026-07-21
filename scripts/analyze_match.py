import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.services.analytics import AnalyticsError, generate_match_analytics


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Generate movement analytics for a selected player."
    )
    parser.add_argument("--analysis-id", required=True, help="Analysis ID to analyze.")
    parser.add_argument(
        "--output-dir",
        default=settings.analytics_output_dir,
        type=Path,
        help="Base data output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.logging_level)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = generate_match_analytics(
            analysis_id=args.analysis_id,
            output_dir=args.output_dir,
            transition_area_depth_feet=settings.transition_area_depth_feet,
            image_width_pixels=settings.analytics_image_width_pixels,
        )
    except AnalyticsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.report.model_dump_json(indent=2))
    print(f"Analytics written to: {result.analytics_path}", file=sys.stderr)
    print(f"Movement summary written to: {result.movement_summary_path}", file=sys.stderr)
    print(f"Timeline written to: {result.timeline_path}", file=sys.stderr)
    print(f"Trajectory image written to: {result.trajectory_path}", file=sys.stderr)
    print(f"Heatmap image written to: {result.heatmap_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
