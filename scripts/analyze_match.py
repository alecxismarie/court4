import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.config import get_settings
from app.core.logging import configure_logging
from app.schemas.analytics import AnalyticsReport, TimelineReport
from app.services.analytics import (
    AnalyticsError,
    AnalyticsOutputExistsError,
    generate_match_analytics,
)
from app.services.match_iq import (
    MATCH_IQ_FILENAME,
    MatchIQPersistenceError,
    generate_and_write_match_iq,
    load_match_iq_report,
)


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
        match_iq = generate_and_write_match_iq(
            analytics=result.report,
            timeline=result.timeline,
            analytics_dir=result.analytics_dir,
        )
        analytics_report = result.report
        analytics_path = result.analytics_path
        movement_summary_path = result.movement_summary_path
        timeline_path = result.timeline_path
        trajectory_path = result.trajectory_path
        heatmap_path = result.heatmap_path
        match_iq_path = result.analytics_dir / MATCH_IQ_FILENAME
    except AnalyticsOutputExistsError:
        try:
            existing = _load_existing_outputs(args.output_dir, args.analysis_id)
        except (OSError, ValueError, ValidationError, MatchIQPersistenceError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        analytics_report = existing.analytics
        analytics_path = existing.analytics_path
        movement_summary_path = existing.movement_summary_path
        timeline_path = existing.timeline_path
        trajectory_path = existing.trajectory_path
        heatmap_path = existing.heatmap_path
        match_iq_path = existing.match_iq_path
        match_iq = (
            load_match_iq_report(match_iq_path)
            if match_iq_path.is_file()
            else generate_and_write_match_iq(
                analytics=existing.analytics,
                timeline=existing.timeline,
                analytics_dir=existing.analytics_dir,
            )
        )
    except AnalyticsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(analytics_report.model_dump_json(indent=2))
    print(f"Analytics written to: {analytics_path}", file=sys.stderr)
    print(f"Movement summary written to: {movement_summary_path}", file=sys.stderr)
    print(f"Timeline written to: {timeline_path}", file=sys.stderr)
    print(f"Trajectory image written to: {trajectory_path}", file=sys.stderr)
    print(f"Heatmap image written to: {heatmap_path}", file=sys.stderr)
    print(f"Match IQ written to: {match_iq_path}", file=sys.stderr)
    print(f"Match IQ status: {match_iq.status}", file=sys.stderr)
    return 0


class ExistingAnalyticsOutputs:
    def __init__(
        self,
        *,
        analytics_dir: Path,
        analytics_path: Path,
        movement_summary_path: Path,
        timeline_path: Path,
        trajectory_path: Path,
        heatmap_path: Path,
        match_iq_path: Path,
        analytics: AnalyticsReport,
        timeline: TimelineReport,
    ) -> None:
        self.analytics_dir = analytics_dir
        self.analytics_path = analytics_path
        self.movement_summary_path = movement_summary_path
        self.timeline_path = timeline_path
        self.trajectory_path = trajectory_path
        self.heatmap_path = heatmap_path
        self.match_iq_path = match_iq_path
        self.analytics = analytics
        self.timeline = timeline


def _load_existing_outputs(output_dir: Path, analysis_id: str) -> ExistingAnalyticsOutputs:
    analytics_dir = output_dir.expanduser() / analysis_id / "analytics"
    analytics_path = analytics_dir / "analytics.json"
    movement_summary_path = analytics_dir / "movement_summary.json"
    timeline_path = analytics_dir / "timeline.json"
    trajectory_path = analytics_dir / "trajectory.png"
    heatmap_path = analytics_dir / "heatmap.png"
    match_iq_path = analytics_dir / MATCH_IQ_FILENAME

    if not analytics_path.is_file():
        raise ValueError(f"Analytics report does not exist: {analytics_path}")
    if not timeline_path.is_file():
        raise ValueError(f"Timeline report does not exist: {timeline_path}")

    analytics = AnalyticsReport.model_validate(
        json.loads(analytics_path.read_text(encoding="utf-8"))
    )
    timeline = TimelineReport.model_validate(json.loads(timeline_path.read_text(encoding="utf-8")))
    return ExistingAnalyticsOutputs(
        analytics_dir=analytics_dir,
        analytics_path=analytics_path,
        movement_summary_path=movement_summary_path,
        timeline_path=timeline_path,
        trajectory_path=trajectory_path,
        heatmap_path=heatmap_path,
        match_iq_path=match_iq_path,
        analytics=analytics,
        timeline=timeline,
    )


if __name__ == "__main__":
    raise SystemExit(main())
