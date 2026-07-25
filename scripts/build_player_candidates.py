"""Build deterministic player candidates from persisted raw tracking artifacts."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.schemas.player_tracking import PlayerTrackingReport
from app.services.candidates import CandidateError, build_player_candidates
from app.services.tracking import TrackingConfigurationError
from app.services.video.player_selection import load_tracking_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build reviewable player candidates from raw Court4 tracks."
    )
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--tracking-report", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--tracking-dir", type=Path, required=True)
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print candidate IDs, membership, quality, and timing instead of the full payload.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tracking: PlayerTrackingReport = load_tracking_report(args.tracking_report)
        collection = build_player_candidates(
            analysis_id=args.analysis_id,
            tracking_report=tracking,
            observations_path=args.observations,
            source_video_path=args.video,
            metadata_path=args.metadata,
            tracking_dir=args.tracking_dir,
            preserve_review=True,
        )
    except (CandidateError, TrackingConfigurationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    payload = (
        {
            "analysis_id": collection.analysis_id,
            "candidate_count": len(collection.candidates),
            "excluded_candidate_count": len(collection.excluded_candidates),
            "suitability": collection.recording_suitability.model_dump(mode="json"),
            "performance": collection.performance.model_dump(mode="json"),
            "candidates": [
                {
                    "candidate_id": candidate.candidate_id,
                    "source_raw_track_ids": candidate.source_raw_track_ids,
                    "quality": candidate.quality,
                    "duration_seconds": candidate.total_observed_duration,
                    "observed_frames": candidate.total_observed_frames,
                    "in_court_ratio": candidate.in_court_observation_ratio,
                    "court_side": candidate.court_side_estimate,
                    "warnings": candidate.warnings,
                }
                for candidate in collection.candidates
            ],
        }
        if args.summary
        else collection.model_dump(mode="json")
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
