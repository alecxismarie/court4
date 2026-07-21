import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.services.video import VideoInspectionError, inspect_video


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Inspect an uploaded pickleball match video.")
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the video file to inspect.",
    )
    parser.add_argument(
        "--output-dir",
        default=settings.output_dir,
        type=Path,
        help="Directory where analysis outputs will be written.",
    )
    parser.add_argument(
        "--sample-interval-seconds",
        default=settings.default_sample_interval_seconds,
        type=float,
        help="Number of seconds between sampled frames.",
    )
    parser.add_argument(
        "--analysis-id",
        default=None,
        help="Optional analysis ID. If omitted, a UUID-based ID is generated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.logging_level)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = inspect_video(
            input_path=args.input,
            output_dir=args.output_dir,
            sample_interval_seconds=args.sample_interval_seconds,
            supported_extensions=settings.supported_extensions,
            max_file_size_bytes=settings.max_upload_size_bytes,
            analysis_id=args.analysis_id,
        )
    except VideoInspectionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result.report.model_dump_json(indent=2))
    print(f"Metadata written to: {result.metadata_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
