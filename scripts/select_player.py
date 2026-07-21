import argparse
import sys
from pathlib import Path

from app.config import get_settings
from app.core.logging import configure_logging
from app.services.tracking import PlayerSelectionError, TrackingError
from app.services.video.player_selection import select_player_track


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select the user's tracked player ID.")
    parser.add_argument(
        "--tracking-report",
        required=True,
        type=Path,
        help="Path to data/output/<analysis_id>/tracking/tracking.json.",
    )
    parser.add_argument("--track-id", required=True, type=int, help="Eligible track ID to select.")
    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.logging_level)
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        report = select_player_track(
            tracking_report_path=args.tracking_report,
            track_id=args.track_id,
        )
    except (PlayerSelectionError, TrackingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(report.model_dump_json(indent=2))
    print(f"Selected track ID {args.track_id} in: {args.tracking_report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
