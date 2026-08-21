from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import select

from app.config import Settings
from app.persistence.models import Analysis, AnalysisRun
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.schemas.ball_tracking import (
    BALL_ARTIFACT_CONTRACTS,
    BallBoundingBox,
    BallCandidateDisposition,
    BallDetectionCandidate,
    BallEvidenceStatus,
    BallFrameDetection,
    BallFrameDetectionState,
    BallObservationState,
    CalibrationEvidenceState,
)
from app.schemas.calibration import (
    CalibrationCoordinateSystem,
    CalibrationCourtDimensions,
    CalibrationVerificationRecord,
    CalibrationVerificationState,
    CourtCalibrationReport,
    OrderedCalibrationPoints,
)
from app.schemas.stage_execution import ArtifactReference, StageProvenance
from app.services.ball_tracking import BallShadowStageService
from app.services.ball_tracking.detector import OpenCVColorMotionBallDetector
from app.services.ball_tracking.pipeline import (
    BallPipelineConfig,
    ExperimentalBallPipeline,
)
from app.services.ball_tracking.projection import project_ball_observations
from app.services.ball_tracking.tracker import (
    TemporalBallTracker,
    TemporalBallTrackerConfig,
)
from app.services.video.frame_source import VideoFrame, VideoSourceMetadata


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _seed_completed_analysis(runtime: PersistenceRuntime, analysis_id: str) -> UUID:
    now = datetime.now(tz=UTC).isoformat()
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        idempotency_key=f"upload-{analysis_id}",
        request_fingerprint=_digest(f"request-{analysis_id}"),
        original_filename="match.avi",
        content_type="video/x-msvideo",
        size_bytes=100,
        source_checksum=_digest(f"source-{analysis_id}"),
        job_payload={
            "analysis_id": analysis_id,
            "status": "processing",
            "current_stage": "uploaded",
            "created_at": now,
            "updated_at": now,
        },
    )
    with runtime.session_factory() as session:
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.analysis_id == analysis_id))
        assert run is not None
        run_id = run.id
        row_version = run.row_version
    runtime.service.transition_run(
        owner_user_id=runtime.owner_user_id,
        run_id=run_id,
        expected_row_version=row_version,
        new_state="completed",
    )
    return run_id


def _frame(index: int, image: np.ndarray, *, fps: float = 10.0) -> VideoFrame:
    height, width = image.shape[:2]
    return VideoFrame(
        frame_index=index,
        timestamp_seconds=index / fps,
        image=image,
        source=VideoSourceMetadata(
            path=Path("synthetic.avi"),
            width=width,
            height=height,
            fps=fps,
            frame_count=10,
        ),
    )


def _candidate(frame_index: int, x: float, y: float) -> BallFrameDetection:
    candidate = BallDetectionCandidate(
        candidate_id=f"candidate-{frame_index}",
        image_x=x,
        image_y=y,
        bounding_box=BallBoundingBox(x1=x - 3, y1=y - 3, x2=x + 3, y2=y + 3),
        confidence=0.8,
        radius_pixels=3,
        circularity=0.9,
        color_fill_ratio=0.8,
        motion_fill_ratio=0.8,
        disposition=BallCandidateDisposition.accepted,
    )
    return BallFrameDetection(
        frame_index=frame_index,
        timestamp_seconds=frame_index / 10,
        state=BallFrameDetectionState.observed,
        candidates=(candidate,),
        accepted_candidate_id=candidate.candidate_id,
    )


def _missing(frame_index: int) -> BallFrameDetection:
    return BallFrameDetection(
        frame_index=frame_index,
        timestamp_seconds=frame_index / 10,
        state=BallFrameDetectionState.missing,
    )


def _provenance() -> StageProvenance:
    configuration = {"mode": "synthetic-test"}
    return StageProvenance(
        stage_name="ball_tracking",
        stage_version="experimental-ball-evidence-v1",
        detector_name=OpenCVColorMotionBallDetector.name,
        detector_version=OpenCVColorMotionBallDetector.version,
        tracker_name=TemporalBallTracker.name,
        tracker_version=TemporalBallTracker.version,
        confidence_threshold=0.48,
        interpolation_policy_version=TemporalBallTracker.interpolation_policy_version,
        effective_configuration=configuration,
        configuration_fingerprint=_digest("synthetic-test-configuration"),
        output_schema_version=1,
    )


def _write_ball_video(path: Path, *, frame_count: int = 12, stationary: bool = False) -> Path:
    width, height = 160, 120
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),  # type: ignore[attr-defined]
        10.0,
        (width, height),
    )
    assert writer.isOpened()
    try:
        for index in range(frame_count):
            image = np.zeros((height, width, 3), dtype=np.uint8)
            x = 30 if stationary else 30 + index * 4
            cv2.circle(image, (x, 62), 5, (0, 255, 180), -1)
            writer.write(image)
    finally:
        writer.release()
    return path


def test_detector_preserves_candidates_but_accepts_only_gated_motion() -> None:
    detector = OpenCVColorMotionBallDetector()
    first = np.zeros((120, 160, 3), dtype=np.uint8)
    second = first.copy()
    cv2.circle(first, (30, 60), 5, (0, 255, 180), -1)
    cv2.circle(second, (35, 60), 5, (0, 255, 180), -1)

    warmup = detector.detect(_frame(0, first))
    moving = detector.detect(_frame(1, second))

    assert warmup.state == BallFrameDetectionState.missing
    assert warmup.candidates
    assert "motion_warmup" in warmup.candidates[0].rejection_reasons
    assert moving.state == BallFrameDetectionState.observed
    assert moving.accepted_candidate_id is not None
    assert (
        sum(
            candidate.disposition == BallCandidateDisposition.accepted
            for candidate in moving.candidates
        )
        == 1
    )


def test_detector_does_not_promote_a_static_color_blob() -> None:
    detector = OpenCVColorMotionBallDetector()
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.circle(image, (40, 60), 5, (0, 255, 180), -1)
    detector.detect(_frame(0, image))
    result = detector.detect(_frame(1, image.copy()))

    assert result.state == BallFrameDetectionState.missing
    assert result.candidates[0].disposition == BallCandidateDisposition.rejected
    assert "insufficient_motion" in result.candidates[0].rejection_reasons


def test_tracker_marks_short_gap_interpolation_and_reacquisition() -> None:
    tracker = TemporalBallTracker()
    result = tracker.reconstruct(
        (_candidate(0, 20, 40), _missing(1), _missing(2), _candidate(3, 32, 40)),
        detector_version="test-detector",
        model_digest=None,
    )

    assert [item.observation_state for item in result.observations] == [
        BallObservationState.observed,
        BallObservationState.interpolated,
        BallObservationState.interpolated,
        BallObservationState.observed,
    ]
    assert result.observations[1].inferred_from_frame_indices == (0, 3)
    assert result.reacquisition_count == 1
    assert result.gap_lengths == (2,)
    assert any(event.event_type == "reacquired" for event in result.events)


def test_observation_serialization_retains_detector_and_source_provenance() -> None:
    source_checksum = _digest("observation-source")
    fingerprint = _digest("observation-configuration")
    observation = (
        TemporalBallTracker()
        .reconstruct(
            (_candidate(0, 20, 40),),
            detector_name="detector-name",
            detector_version="detector-version",
            model_identifier=None,
            model_digest=None,
            source_video_checksum=source_checksum,
            configuration_fingerprint=fingerprint,
        )
        .observations[0]
    )
    serialized = json.loads(observation.model_dump_json())

    assert serialized["detector_name"] == "detector-name"
    assert serialized["detector_version"] == "detector-version"
    assert serialized["source_video_checksum"] == source_checksum
    assert serialized["configuration_fingerprint"] == fingerprint
    assert serialized["observation_state"] == "observed"


def test_tracker_rejects_impossible_motion_instead_of_fabricating_continuity() -> None:
    tracker = TemporalBallTracker(
        TemporalBallTrackerConfig(
            base_association_distance_pixels=10,
            per_gap_distance_pixels=0,
            max_interpolation_gap_frames=2,
            restart_after_gap_frames=2,
        )
    )
    result = tracker.reconstruct(
        (_candidate(0, 10, 10), _candidate(1, 140, 100), _missing(2)),
        detector_version="test-detector",
        model_digest=None,
    )

    assert result.impossible_motion_count == 1
    assert [item.frame_index for item in result.observations] == [0]


def test_projection_requires_checksum_bound_verified_calibration() -> None:
    observation = (
        TemporalBallTracker()
        .reconstruct(
            (_candidate(0, 10, 20),),
            detector_version="test-detector",
            model_digest=None,
        )
        .observations
    )
    checksum = _digest("calibration")
    calibration = CourtCalibrationReport(
        calibration_id="calibration-1",
        source_image="frame.jpg",
        image_width=160,
        image_height=120,
        coordinate_system=CalibrationCoordinateSystem(
            unit="feet", origin="near-left", x_axis="right", y_axis="far"
        ),
        court_dimensions=CalibrationCourtDimensions(width=20, length=44, non_volley_zone_depth=7),
        image_points=OrderedCalibrationPoints(
            near_left=(0, 0), near_right=(1, 0), far_right=(1, 1), far_left=(0, 1)
        ),
        court_points=OrderedCalibrationPoints(
            near_left=(0, 0), near_right=(1, 0), far_right=(1, 1), far_left=(0, 1)
        ),
        image_to_court_matrix=[[2, 0, 0], [0, 3, 0], [0, 0, 1]],
        court_to_image_matrix=[[0.5, 0, 0], [0, 1 / 3, 0], [0, 0, 1]],
        reprojection_error=0,
        round_trip_error=0,
        created_at=datetime.now(tz=UTC),
    )
    unverified = project_ball_observations(
        observation,
        calibration=calibration,
        verification=None,
        calibration_checksum_sha256=checksum,
    )
    verification = CalibrationVerificationRecord(
        calibration_id=calibration.calibration_id,
        calibration_checksum_sha256=checksum,
        verification_state=CalibrationVerificationState.verified,
        verified_at=datetime.now(tz=UTC),
        verification_method="human_corner_review",
    )
    verified = project_ball_observations(
        observation,
        calibration=calibration,
        verification=verification,
        calibration_checksum_sha256=checksum,
    )

    assert unverified.calibration_state == CalibrationEvidenceState.generated_unverified
    assert unverified.observations[0].court_x is None
    assert verified.calibration_state == CalibrationEvidenceState.verified
    assert verified.observations[0].court_x == 20
    assert verified.observations[0].court_y == 60


def test_pipeline_writes_versioned_review_artifacts_and_explicit_evidence(
    tmp_path: Path,
) -> None:
    video = _write_ball_video(tmp_path / "ball.avi")
    output = tmp_path / "analysis" / "ball" / "attempt-0001"
    pipeline = ExperimentalBallPipeline(
        detector=OpenCVColorMotionBallDetector(),
        tracker=TemporalBallTracker(),
        config=BallPipelineConfig(max_processed_frames=100),
    )
    result = pipeline.run(
        video_path=video,
        output_dir=output,
        analysis_id="synthetic-ball",
        stage_attempt=1,
        storage_prefix="ball/attempt-0001/",
        provenance=_provenance(),
    )

    assert result.report.evidence_status == BallEvidenceStatus.available
    assert result.report.observed_frame_count >= 3
    assert result.report.provenance.model_identifier is None
    assert {artifact.path.name for artifact in result.artifacts} == {
        contract.filename for contract in BALL_ARTIFACT_CONTRACTS
    }
    assert all(artifact.path.stat().st_size > 0 for artifact in result.artifacts)
    assert not any(output.rglob("match_iq.json"))
    assert not any(output.rglob("player_history*"))


def test_pipeline_reports_no_ball_and_enforces_frame_cap(tmp_path: Path) -> None:
    video = _write_ball_video(tmp_path / "stationary.avi", frame_count=8, stationary=True)
    result = ExperimentalBallPipeline(
        detector=OpenCVColorMotionBallDetector(),
        tracker=TemporalBallTracker(),
        config=BallPipelineConfig(max_processed_frames=4),
    ).run(
        video_path=video,
        output_dir=tmp_path / "limited",
        analysis_id="limited-ball",
        stage_attempt=1,
        storage_prefix="ball/attempt-0001/",
        provenance=_provenance(),
    )

    assert result.report.evidence_status == BallEvidenceStatus.truncated
    assert result.report.processing_truncated is True
    assert result.report.processed_frames == 4
    assert result.report.observed_frame_count == 0
    assert "processing_frame_limit_reached" in result.report.quality_reasons


def test_pipeline_reports_detector_frame_failure_honestly(tmp_path: Path) -> None:
    class FailingDetector:
        name: str = "failing_test_detector"
        version: str = "1.0.0"
        model_identifier: str | None = None
        model_sha256: str | None = None

        def detect(self, frame: VideoFrame) -> BallFrameDetection:
            del frame
            raise RuntimeError("synthetic detector failure")

    video = _write_ball_video(tmp_path / "detector-failure.avi", frame_count=3)
    result = ExperimentalBallPipeline(
        detector=FailingDetector(),
        tracker=TemporalBallTracker(),
    ).run(
        video_path=video,
        output_dir=tmp_path / "failed-detection",
        analysis_id="failed-detection",
        stage_attempt=1,
        storage_prefix="ball/attempt-0001/",
        provenance=_provenance(),
    )

    assert result.report.evidence_status == BallEvidenceStatus.analysis_failed
    assert result.report.frame_failure_count == 3
    assert result.report.observed_frame_count == 0
    assert "all_frames_failed_detection" in result.report.quality_reasons


def test_pipeline_keeps_reconstructed_coverage_bounded_across_failed_frame(
    tmp_path: Path,
) -> None:
    class IntermittentDetector:
        name: str = "intermittent_test_detector"
        version: str = "1.0.0"
        model_identifier: str | None = None
        model_sha256: str | None = None

        def detect(self, frame: VideoFrame) -> BallFrameDetection:
            if frame.frame_index == 1:
                raise RuntimeError("synthetic middle-frame failure")
            return _candidate(frame.frame_index, 20 + frame.frame_index * 4, 40)

    video = _write_ball_video(tmp_path / "intermittent.avi", frame_count=3)
    result = ExperimentalBallPipeline(
        detector=IntermittentDetector(),
        tracker=TemporalBallTracker(),
    ).run(
        video_path=video,
        output_dir=tmp_path / "intermittent-output",
        analysis_id="intermittent-detection",
        stage_attempt=1,
        storage_prefix="ball/attempt-0001/",
        provenance=_provenance(),
    )

    assert result.report.frame_failure_count == 1
    assert result.report.interpolated_frame_count == 1
    assert result.report.reconstructed_track_coverage == 1.0


def test_optional_stage_registers_attempt_artifacts_without_mutating_parent_outputs(
    tmp_path: Path,
) -> None:
    runtime = get_persistence()
    analysis_id = "experimental-ball-stage"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    video = _write_ball_video(tmp_path / "stage-ball.avi")
    checksum = _digest("stage-ball-source")
    service = BallShadowStageService(
        persistence=runtime.service,
        settings=Settings.model_validate({"ball_tracking_enabled": True}),
    )

    result = service.run_for_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        analysis_run_id=run_id,
        video_path=video,
        analysis_output_dir=tmp_path / analysis_id,
        source_video_checksum=checksum,
        input_artifacts=[
            ArtifactReference(storage_key="uploads/source.avi", checksum_sha256=checksum)
        ],
    )

    assert result.stage.state == "completed"
    assert result.pipeline is not None
    artifacts = runtime.service.list_artifacts(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
    )
    assert len(artifacts) == len(BALL_ARTIFACT_CONTRACTS)
    assert all(item.storage_key.startswith("ball/attempt-0001/") for item in artifacts)
    assert not any("analytics/" in item.storage_key for item in artifacts)
    assert not any("history" in item.storage_key for item in artifacts)
    with runtime.session_factory() as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.state == "completed"
        assert analysis.current_stage == "uploaded"
        assert analysis.promoted_run_id == run_id


def test_ball_evidence_has_no_workflow_match_iq_history_or_api_consumer() -> None:
    guarded_paths = [
        Path("app/services/jobs/workflow.py"),
        *Path("app/services/match_iq").glob("*.py"),
        *Path("app/services/history").glob("*.py"),
        *Path("app/api/v1").glob("*.py"),
    ]
    forbidden_references = (
        "BallObservation",
        "BallTrackingReport",
        "ball/attempt",
        "ball_tracking",
    )

    for path in guarded_paths:
        source = path.read_text(encoding="utf-8")
        assert not any(reference in source for reference in forbidden_references), path
