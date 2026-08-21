from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

from app.schemas.stage_execution import StageProvenance
from app.services.ball_tracking.detector import (
    OpenCVBallDetectorConfig,
    OpenCVColorMotionBallDetector,
)
from app.services.ball_tracking.pipeline import BallPipelineConfig, ExperimentalBallPipeline
from app.services.ball_tracking.tracker import TemporalBallTracker, TemporalBallTrackerConfig
from app.services.stages.configuration import stage_configuration_fingerprint


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run experimental low-level ball evidence on consent-cleared footage."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--analysis-id", default="offline-ball-review")
    parser.add_argument("--max-frames", type=int, default=18_000)
    parser.add_argument(
        "--consent-reference",
        required=True,
        help="External purpose-specific model-evaluation consent reference.",
    )
    parser.add_argument(
        "--acknowledge-experimental",
        action="store_true",
        help="Acknowledge that outputs are review evidence, not product analytics.",
    )
    args = parser.parse_args()
    if not args.acknowledge_experimental:
        parser.error("--acknowledge-experimental is required")
    if args.max_frames < 1:
        parser.error("--max-frames must be positive")

    detector_config = OpenCVBallDetectorConfig()
    tracker_config = TemporalBallTrackerConfig()
    configuration = {
        "mode": "offline_developer_review",
        "consent_reference": args.consent_reference,
        "detector": detector_config.as_dict(),
        "tracker": tracker_config.as_dict(),
        "max_processed_frames": args.max_frames,
    }
    source_checksum = _file_sha256(args.input)
    provenance = StageProvenance(
        stage_name="ball_tracking",
        stage_version="experimental-ball-evidence-v1",
        detector_name=OpenCVColorMotionBallDetector.name,
        detector_version=OpenCVColorMotionBallDetector.version,
        model_identifier=None,
        model_sha256=None,
        tracker_name=TemporalBallTracker.name,
        tracker_version=TemporalBallTracker.version,
        confidence_threshold=detector_config.acceptance_confidence,
        interpolation_policy_version=TemporalBallTracker.interpolation_policy_version,
        source_video_checksum=source_checksum,
        environment="offline_development",
        effective_configuration=configuration,
        configuration_fingerprint=stage_configuration_fingerprint(configuration),
        output_schema_version=1,
    )
    result = ExperimentalBallPipeline(
        detector=OpenCVColorMotionBallDetector(detector_config),
        tracker=TemporalBallTracker(tracker_config),
        config=BallPipelineConfig(max_processed_frames=args.max_frames),
    ).run(
        video_path=args.input,
        output_dir=args.output_dir,
        analysis_id=args.analysis_id,
        stage_attempt=1,
        storage_prefix="ball/attempt-0001/",
        provenance=provenance,
    )
    print(
        json.dumps(
            {
                "evidence_status": result.report.evidence_status,
                "observed_frames": result.report.observed_frame_count,
                "interpolated_frames": result.report.interpolated_frame_count,
                "output_dir": str(result.output_dir),
            },
            indent=2,
        )
    )
    return 0


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
