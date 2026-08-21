from __future__ import annotations

import json
import shutil
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from pydantic import BaseModel

from app.schemas.ball_tracking import (
    BALL_ARTIFACT_CONTRACTS,
    BallArtifactKind,
    BallEvidenceStatus,
    BallFrameDetection,
    BallFrameDetectionState,
    BallObservation,
    BallObservationState,
    BallReviewSidecar,
    BallTrackingReport,
    BallTrackSegmentEvidence,
    BallTrackSegmentStatus,
    ConfidencePercentiles,
    ProcessingTimings,
)
from app.schemas.calibration import (
    CalibrationVerificationRecord,
    CourtCalibrationReport,
)
from app.schemas.stage_execution import StageProvenance
from app.services.ball_tracking.detector import BallDetector
from app.services.ball_tracking.projection import project_ball_observations
from app.services.ball_tracking.tracker import TemporalBallTracker
from app.services.ball_tracking.visualization import (
    write_overlay_video,
    write_trajectory_image,
)
from app.services.video.frame_source import OpenCVFrameSource


@dataclass(frozen=True)
class BallPipelineConfig:
    max_processed_frames: int = 18_000
    minimum_observations: int = 3


@dataclass(frozen=True)
class BallPipelineArtifact:
    kind: BallArtifactKind
    path: Path
    content_type: str
    schema_version: int | None


@dataclass(frozen=True)
class BallPipelineResult:
    output_dir: Path
    report: BallTrackingReport
    artifacts: tuple[BallPipelineArtifact, ...]


class ExperimentalBallPipeline:
    """Bounded offline evidence pipeline. It emits no rally, bounce, or coaching semantics."""

    def __init__(
        self,
        *,
        detector: BallDetector,
        tracker: TemporalBallTracker,
        config: BallPipelineConfig | None = None,
    ) -> None:
        self.detector = detector
        self.tracker = tracker
        self.config = config or BallPipelineConfig()
        if self.config.max_processed_frames < 1:
            raise ValueError("Ball pipeline frame limit must be positive.")
        if self.config.minimum_observations < 1:
            raise ValueError("Ball pipeline observation minimum must be positive.")

    def run(
        self,
        *,
        video_path: Path,
        output_dir: Path,
        analysis_id: str,
        stage_attempt: int,
        storage_prefix: str,
        provenance: StageProvenance,
        calibration: CourtCalibrationReport | None = None,
        calibration_verification: CalibrationVerificationRecord | None = None,
        calibration_checksum_sha256: str | None = None,
    ) -> BallPipelineResult:
        if output_dir.exists():
            raise FileExistsError(f"Ball attempt output already exists: {output_dir}")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_dir.parent / f".{output_dir.name}.partial-{uuid4().hex}"
        temporary.mkdir(parents=False, exist_ok=False)
        started = time.perf_counter()
        try:
            with OpenCVFrameSource(video_path) as source:
                metadata = source.metadata
                detections: list[BallFrameDetection] = []
                truncated = False
                decode_seconds = 0.0
                detection_seconds = 0.0
                frames = iter(source)
                while True:
                    decode_started = time.perf_counter()
                    try:
                        frame = next(frames)
                    except StopIteration:
                        decode_seconds += time.perf_counter() - decode_started
                        break
                    decode_seconds += time.perf_counter() - decode_started
                    if frame.frame_index >= self.config.max_processed_frames:
                        truncated = True
                        break
                    detection_started = time.perf_counter()
                    try:
                        detections.append(self.detector.detect(frame))
                    except Exception:
                        detections.append(
                            BallFrameDetection(
                                frame_index=frame.frame_index,
                                timestamp_seconds=frame.timestamp_seconds,
                                state=BallFrameDetectionState.frame_failed,
                                error_category="detector_frame_error",
                            )
                        )
                    detection_seconds += time.perf_counter() - detection_started

            reconstruction_started = time.perf_counter()
            track = self.tracker.reconstruct(
                tuple(detections),
                detector_name=self.detector.name,
                detector_version=self.detector.version,
                model_identifier=self.detector.model_identifier,
                model_digest=self.detector.model_sha256,
                source_video_checksum=provenance.source_video_checksum,
                configuration_fingerprint=provenance.configuration_fingerprint,
            )
            projection = project_ball_observations(
                track.observations,
                calibration=calibration,
                verification=calibration_verification,
                calibration_checksum_sha256=calibration_checksum_sha256,
            )
            reconstruction_seconds = time.perf_counter() - reconstruction_started

            self._write_jsonl(temporary / "detections.v1.jsonl", detections)
            self._write_jsonl(temporary / "track.v1.jsonl", projection.observations)
            observed_count = sum(
                item.observation_state == BallObservationState.observed
                for item in projection.observations
            )
            status, quality_reasons = self._status(
                detections=tuple(detections),
                observed_count=observed_count,
                segment_count=track.segment_count,
                truncated=truncated,
            )
            if projection.calibration_state == "absent":
                quality_reasons = (*quality_reasons, "calibration_unavailable")
            elif projection.calibration_state == "generated_unverified":
                quality_reasons = (*quality_reasons, "calibration_unverified")
            write_trajectory_image(
                output_path=temporary / "trajectory.v1.png",
                width=metadata.width,
                height=metadata.height,
                observations=projection.observations,
                evidence_label=status.value.replace("_", " "),
            )
            write_overlay_video(
                video_path=video_path,
                output_path=temporary / "overlay.v1.mp4",
                observations=projection.observations,
                events=track.events,
                max_frames=len(detections),
            )

            processed_frames = len(detections)
            frame_failure_count = sum(
                item.state == BallFrameDetectionState.frame_failed for item in detections
            )
            eligible_frames = max(0, processed_frames - frame_failure_count)
            raw_observed = sum(
                item.state == BallFrameDetectionState.observed for item in detections
            )
            observed = tuple(
                item
                for item in projection.observations
                if item.observation_state == BallObservationState.observed
            )
            interpolated_count = sum(
                item.observation_state == BallObservationState.interpolated
                for item in projection.observations
            )
            reconstructed_frames = len({item.frame_index for item in projection.observations})
            rejected_count = sum(
                candidate.disposition == "rejected"
                for detection in detections
                for candidate in detection.candidates
            )
            mapped_count = sum(item.court_x is not None for item in projection.observations)
            total_seconds = time.perf_counter() - started
            report = BallTrackingReport(
                evidence_status=status,
                quality_reasons=quality_reasons,
                eligible_frames=eligible_frames,
                processed_frames=processed_frames,
                frame_failure_count=frame_failure_count,
                processing_truncated=truncated,
                raw_detection_coverage=(raw_observed / eligible_frames if eligible_frames else 0.0),
                reconstructed_track_coverage=(
                    reconstructed_frames / processed_frames if processed_frames else 0.0
                ),
                observed_frame_count=len(observed),
                interpolated_frame_count=interpolated_count,
                observed_interpolated_ratio=(
                    len(observed) / interpolated_count if interpolated_count else None
                ),
                confidence_percentiles=self._percentiles(
                    tuple(item.confidence for item in observed)
                ),
                longest_gap_frames=max(track.gap_lengths, default=0),
                average_gap_frames=(
                    sum(track.gap_lengths) / len(track.gap_lengths) if track.gap_lengths else 0.0
                ),
                reacquisition_count=track.reacquisition_count,
                track_segment_count=track.segment_count,
                fragmentation_rate=(max(0, track.segment_count - 1) / max(1, len(observed))),
                rejected_detection_count=rejected_count,
                impossible_motion_count=track.impossible_motion_count,
                track_events=track.events,
                track_segments=self._segments(projection.observations),
                court_mapped_coverage=(
                    mapped_count / len(projection.observations) if projection.observations else 0.0
                ),
                calibration_state=projection.calibration_state,
                processing_timings=ProcessingTimings(
                    decode_seconds=decode_seconds,
                    detection_seconds=detection_seconds,
                    reconstruction_seconds=reconstruction_seconds,
                    total_seconds=total_seconds,
                ),
                provenance=provenance,
            )
            self._write_json(temporary / "tracking-report.v1.json", report)
            sidecar = BallReviewSidecar(
                analysis_id=analysis_id,
                stage_attempt=stage_attempt,
                overlay_storage_key=f"{storage_prefix}overlay.v1.mp4",
                trajectory_storage_key=f"{storage_prefix}trajectory.v1.png",
                report_storage_key=f"{storage_prefix}tracking-report.v1.json",
                notes=(
                    "Experimental low-level evidence only; no match or player-history contribution."
                ),
            )
            self._write_json(temporary / "review-sidecar.v1.json", sidecar)
            temporary.rename(output_dir)
            return BallPipelineResult(
                output_dir=output_dir,
                report=report,
                artifacts=tuple(
                    BallPipelineArtifact(
                        kind=contract.kind,
                        path=output_dir / contract.filename,
                        content_type=contract.content_type,
                        schema_version=contract.schema_version,
                    )
                    for contract in BALL_ARTIFACT_CONTRACTS
                ),
            )
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def _status(
        self,
        *,
        detections: tuple[BallFrameDetection, ...],
        observed_count: int,
        segment_count: int,
        truncated: bool,
    ) -> tuple[BallEvidenceStatus, tuple[str, ...]]:
        if truncated:
            return BallEvidenceStatus.truncated, ("processing_frame_limit_reached",)
        if detections and all(
            item.state == BallFrameDetectionState.frame_failed for item in detections
        ):
            return BallEvidenceStatus.analysis_failed, ("all_frames_failed_detection",)
        if observed_count == 0:
            return BallEvidenceStatus.no_ball_detected, ("no_candidate_passed_acceptance_gates",)
        if observed_count < self.config.minimum_observations:
            return BallEvidenceStatus.insufficient_observations, (
                "accepted_observations_below_minimum",
            )
        if segment_count >= 3 and segment_count == observed_count:
            return BallEvidenceStatus.excessive_track_fragmentation, (
                "every_observation_is_an_isolated_fragment",
            )
        return BallEvidenceStatus.available, ()

    @staticmethod
    def _segments(
        observations: tuple[BallObservation, ...],
    ) -> tuple[BallTrackSegmentEvidence, ...]:
        grouped: dict[str, list[BallObservation]] = {}
        for observation in observations:
            grouped.setdefault(observation.track_segment_id, []).append(observation)
        result: list[BallTrackSegmentEvidence] = []
        for segment_id, segment in grouped.items():
            observed_count = sum(
                item.observation_state == BallObservationState.observed for item in segment
            )
            interpolated_count = len(segment) - observed_count
            is_fragment = observed_count < 3
            result.append(
                BallTrackSegmentEvidence(
                    track_segment_id=segment_id,
                    start_frame=segment[0].frame_index,
                    end_frame=segment[-1].frame_index,
                    observation_count=len(segment),
                    observed_count=observed_count,
                    interpolated_count=interpolated_count,
                    mean_confidence=sum(item.confidence for item in segment) / len(segment),
                    status=(
                        BallTrackSegmentStatus.fragment
                        if is_fragment
                        else BallTrackSegmentStatus.candidate_trajectory
                    ),
                    quality_reasons=("fewer_than_three_direct_observations",)
                    if is_fragment
                    else (),
                )
            )
        return tuple(result)

    @staticmethod
    def _percentiles(confidences: tuple[float, ...]) -> ConfidencePercentiles:
        if not confidences:
            return ConfidencePercentiles()
        p10, p50, p90 = np.percentile(np.asarray(confidences), (10, 50, 90))
        return ConfidencePercentiles(p10=float(p10), p50=float(p50), p90=float(p90))

    @staticmethod
    def _write_jsonl(path: Path, models: Sequence[BaseModel]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for model in models:
                handle.write(model.model_dump_json())
                handle.write("\n")

    @staticmethod
    def _write_json(path: Path, model: BaseModel) -> None:
        path.write_text(
            json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
