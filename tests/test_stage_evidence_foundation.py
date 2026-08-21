from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings
from app.persistence.errors import (
    InvalidStateTransitionError,
    OwnershipMismatchError,
)
from app.persistence.models import Analysis, AnalysisRun, AnalysisStageExecution
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.persistence.service import ArtifactInput, StageExecutionResult, stage_artifact_prefix
from app.schemas.ball_tracking import (
    BALL_ARTIFACT_CONTRACTS,
    BallObservation,
    BallObservationState,
)
from app.schemas.calibration import (
    CalibrationCoordinateSystem,
    CalibrationCourtDimensions,
    CalibrationVerificationRecord,
    CalibrationVerificationState,
    CourtCalibrationReport,
    CourtProjectionAvailability,
    OrderedCalibrationPoints,
    court_projection_availability,
)
from app.schemas.stage_execution import ArtifactReference
from app.services.ball_tracking import BallShadowStageService, BallTrackingDisabledError
from app.services.ball_tracking.feasibility import (
    FeasibilityDatasetError,
    validate_feasibility_dataset,
)
from app.services.jobs.exceptions import JobNotFoundError
from app.services.jobs.repository import (
    AnalysisJobRepository,
    _artifact_kind,
    _artifact_schema_version,
)
from app.services.stages.configuration import (
    effective_stage_configuration,
    stage_configuration_fingerprint,
)
from app.services.video.frame_source import OpenCVFrameSource


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _seed_completed_analysis(runtime: PersistenceRuntime, analysis_id: str) -> UUID:
    now = datetime.now(tz=UTC).isoformat()
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        idempotency_key=f"upload-{analysis_id}",
        request_fingerprint=_digest(f"request-{analysis_id}"),
        original_filename="match.mp4",
        content_type="video/mp4",
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


def _start_stage(
    runtime: PersistenceRuntime,
    analysis_id: str,
    run_id: UUID,
    *,
    stage_type: str = "synthetic_optional",
) -> StageExecutionResult:
    fingerprint = _digest("stage-config")
    return runtime.service.start_stage_execution(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        analysis_run_id=run_id,
        stage_type=stage_type,
        configuration_fingerprint=fingerprint,
        provenance_payload={
            "schema_version": 1,
            "stage_name": stage_type,
            "stage_version": "test-v1",
            "effective_configuration": {"mode": "synthetic"},
            "configuration_fingerprint": fingerprint,
            "output_schema_version": 1,
        },
        input_artifact_references=[],
    )


def test_stage_failure_is_independent_and_rerun_preserves_attempt() -> None:
    runtime = get_persistence()
    analysis_id = "optional-stage-lifecycle"
    run_id = _seed_completed_analysis(runtime, analysis_id)

    first = _start_stage(runtime, analysis_id, run_id)
    assert first.created is True
    failed = runtime.service.transition_stage_execution(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=first.stage_execution_id,
        expected_row_version=first.row_version,
        new_state="failed",
        failure_category="detector_unavailable",
    )
    second = _start_stage(runtime, analysis_id, run_id)
    completed = runtime.service.transition_stage_execution(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=second.stage_execution_id,
        expected_row_version=second.row_version,
        new_state="completed",
    )

    assert failed.state == "failed"
    assert second.attempt_number == 2
    assert completed.state == "completed"
    attempts = runtime.service.list_stage_executions(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        stage_type="synthetic_optional",
    )
    assert [(attempt.attempt_number, attempt.state) for attempt in attempts] == [
        (1, "failed"),
        (2, "completed"),
    ]
    with runtime.session_factory() as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.state == "completed"
        assert analysis.promoted_run_id == run_id
    with pytest.raises(InvalidStateTransitionError):
        runtime.service.transition_stage_execution(
            owner_user_id=runtime.owner_user_id,
            stage_execution_id=first.stage_execution_id,
            expected_row_version=failed.row_version,
            new_state="completed",
        )


def test_concurrent_duplicate_stage_start_returns_one_active_attempt() -> None:
    runtime = get_persistence()
    analysis_id = "optional-stage-concurrency"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    barrier = Barrier(6)

    def start(_: int) -> StageExecutionResult:
        barrier.wait(timeout=10)
        return _start_stage(runtime, analysis_id, run_id)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(start, range(6)))

    assert len({result.stage_execution_id for result in results}) == 1
    assert sum(result.created for result in results) == 1
    attempts = runtime.service.list_stage_executions(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        stage_type="synthetic_optional",
    )
    assert len(attempts) == 1


def test_stage_artifacts_are_versioned_promoted_and_historical() -> None:
    runtime = get_persistence()
    analysis_id = "optional-stage-artifacts"
    run_id = _seed_completed_analysis(runtime, analysis_id)

    first = _start_stage(runtime, analysis_id, run_id, stage_type="ball_tracking")
    first_key = stage_artifact_prefix("ball_tracking", 1) + "tracking-report.v1.json"
    first_artifacts = runtime.service.register_stage_artifacts(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=first.stage_execution_id,
        artifacts=[
            ArtifactInput(
                storage_key=first_key,
                content_type="application/json",
                size_bytes=10,
                checksum_sha256=_digest("report-one"),
                artifact_kind="ball_tracking_report",
                schema_version=1,
            )
        ],
    )
    runtime.service.transition_stage_execution(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=first.stage_execution_id,
        expected_row_version=first.row_version,
        new_state="completed",
    )

    second = _start_stage(runtime, analysis_id, run_id, stage_type="ball_tracking")
    second_key = stage_artifact_prefix("ball_tracking", 2) + "tracking-report.v1.json"
    runtime.service.register_stage_artifacts(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=second.stage_execution_id,
        artifacts=[
            ArtifactInput(
                storage_key=second_key,
                content_type="application/json",
                size_bytes=11,
                checksum_sha256=_digest("report-two"),
                artifact_kind="ball_tracking_report",
                schema_version=1,
            )
        ],
    )
    runtime.service.transition_stage_execution(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=second.stage_execution_id,
        expected_row_version=second.row_version,
        new_state="completed",
    )

    current = runtime.service.list_artifacts(
        owner_user_id=runtime.owner_user_id, analysis_id=analysis_id
    )
    history = runtime.service.list_artifact_history(
        owner_user_id=runtime.owner_user_id, analysis_id=analysis_id
    )
    assert [artifact.storage_key for artifact in current] == [second_key]
    assert [artifact.storage_key for artifact in history] == [first_key, second_key]
    assert first_artifacts[0].schema_version == 1
    assert first_artifacts[0].stage_execution_id == first.stage_execution_id
    assert history[0].is_current is False
    assert history[1].is_current is True


def test_missing_artifact_bytes_fail_safely(tmp_path: Path) -> None:
    runtime = get_persistence()
    analysis_id = "missing-stage-bytes"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    stage = _start_stage(runtime, analysis_id, run_id, stage_type="ball_tracking")
    key = stage_artifact_prefix("ball_tracking", 1) + "tracking-report.v1.json"
    runtime.service.register_stage_artifacts(
        owner_user_id=runtime.owner_user_id,
        stage_execution_id=stage.stage_execution_id,
        artifacts=[
            ArtifactInput(
                storage_key=key,
                content_type="application/json",
                size_bytes=12,
                checksum_sha256=_digest("missing"),
                artifact_kind="ball_tracking_report",
                schema_version=1,
            )
        ],
    )
    repository = AnalysisJobRepository(
        output_dir=tmp_path,
        api_base_path="/api/v1",
        owner_user_id=runtime.owner_user_id,
        persistence=runtime,
    )
    with pytest.raises(JobNotFoundError, match="bytes are unavailable"):
        repository.resolve_artifact(analysis_id, key)


def test_stage_owner_isolation_is_enforced() -> None:
    runtime = get_persistence()
    analysis_id = "stage-owner-isolation"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    _start_stage(runtime, analysis_id, run_id)
    with pytest.raises(OwnershipMismatchError):
        runtime.service.list_stage_executions(owner_user_id=uuid4(), analysis_id=analysis_id)


def test_effective_configuration_is_deterministic_includes_overrides_and_omits_secrets() -> None:
    first = effective_stage_configuration(
        {
            "detector": {"confidence": 0.25, "image_size": 640},
            "api_key": "must-not-survive",
            "tiles": {3, 1, 2},
        },
        {
            "detector": {"confidence": 0.42},
            "auth_token": "also-secret",
        },
    )
    second = effective_stage_configuration(
        {"tiles": {2, 3, 1}, "detector": {"image_size": 640, "confidence": 0.25}},
        {"detector": {"confidence": 0.42}},
    )
    assert first == second
    assert first["detector"]["confidence"] == 0.42
    assert first["tiles"] == [1, 2, 3]
    assert "api_key" not in first
    assert "auth_token" not in first
    assert stage_configuration_fingerprint(first) == stage_configuration_fingerprint(second)


def test_ball_observation_contract_separates_observed_and_interpolated() -> None:
    observed = BallObservation(
        frame_index=1,
        timestamp_seconds=0.1,
        image_x=10,
        image_y=20,
        confidence=0.9,
        observation_state=BallObservationState.observed,
        track_segment_id="segment-1",
        gap_length_frames=0,
        detector_version=None,
        model_digest=None,
    )
    assert observed.court_projection_method is None
    with pytest.raises(ValidationError, match="non-zero frame gap"):
        BallObservation(
            frame_index=2,
            timestamp_seconds=0.2,
            image_x=11,
            image_y=21,
            confidence=0.5,
            observation_state=BallObservationState.interpolated,
            track_segment_id="segment-1",
            gap_length_frames=0,
        )
    with pytest.raises(ValidationError):
        BallObservation.model_validate({**observed.model_dump(), "hitter": "player-1"})


def test_ball_artifact_contracts_are_versioned_and_classified() -> None:
    assert {contract.filename for contract in BALL_ARTIFACT_CONTRACTS} == {
        "detections.v1.jsonl",
        "track.v1.jsonl",
        "tracking-report.v1.json",
        "trajectory.v1.png",
        "overlay.v1.mp4",
        "review-sidecar.v1.json",
    }
    assert all(contract.schema_version == 1 for contract in BALL_ARTIFACT_CONTRACTS)
    assert _artifact_kind("ball/attempt-0001/tracking-report.v1.json") == "ball_tracking"
    assert _artifact_schema_version("ball/attempt-0001/tracking-report.v1.json") == 1


def test_calibration_generation_is_not_verification_and_projection_is_bounded() -> None:
    calibration = _calibration_report()
    checksum = _digest("calibration")
    assert (
        court_projection_availability(calibration, None, calibration_checksum_sha256=checksum)
        == CourtProjectionAvailability.unavailable
    )
    verification = CalibrationVerificationRecord(
        calibration_id=calibration.calibration_id,
        calibration_checksum_sha256=checksum,
        verification_state=CalibrationVerificationState.verified,
        verified_at=datetime.now(tz=UTC),
        verification_method="human_corner_review",
    )
    assert (
        court_projection_availability(
            calibration, verification, calibration_checksum_sha256=checksum
        )
        == CourtProjectionAvailability.approximate_court_plane_projection
    )
    assert (
        court_projection_availability(
            calibration,
            verification,
            calibration_checksum_sha256=_digest("changed-calibration"),
        )
        == CourtProjectionAvailability.unavailable
    )


def test_calibration_review_record_is_owner_scoped_and_immutable() -> None:
    runtime = get_persistence()
    analysis_id = "calibration-review"
    _seed_completed_analysis(runtime, analysis_id)
    checksum = _digest("reviewed-calibration")
    first = runtime.service.record_calibration_verification(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        calibration_id="court-1",
        calibration_checksum_sha256=checksum,
        verification_state="verified",
        verification_method="human_corner_review",
        reviewer_context="internal-reviewer",
    )
    repeated = runtime.service.record_calibration_verification(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        calibration_id="court-1",
        calibration_checksum_sha256=checksum,
        verification_state="rejected",
        verification_method="different-review",
    )
    assert repeated.id == first.id
    assert repeated.verification_state == "verified"


def test_ball_flag_defaults_off_and_disabled_boundary_changes_nothing() -> None:
    settings = Settings.model_validate({})
    assert settings.ball_tracking_enabled is False
    runtime = get_persistence()
    analysis_id = "ball-disabled-isolation"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    service = BallShadowStageService(persistence=runtime.service, settings=settings)
    with pytest.raises(BallTrackingDisabledError):
        service.start_for_analysis(
            owner_user_id=runtime.owner_user_id,
            analysis_id=analysis_id,
            analysis_run_id=run_id,
            source_video_checksum=_digest("source-ball-disabled-isolation"),
            input_artifacts=[],
        )
    assert (
        runtime.service.list_stage_executions(
            owner_user_id=runtime.owner_user_id, analysis_id=analysis_id
        )
        == []
    )
    with runtime.session_factory() as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.state == "completed"
        assert analysis.current_stage == "uploaded"


def test_enabled_shadow_boundary_records_real_component_provenance_without_model_claims() -> None:
    settings = Settings.model_validate({"ball_tracking_enabled": True})
    runtime = get_persistence()
    analysis_id = "ball-shadow-boundary"
    run_id = _seed_completed_analysis(runtime, analysis_id)
    service = BallShadowStageService(persistence=runtime.service, settings=settings)
    result = service.start_for_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        analysis_run_id=run_id,
        source_video_checksum=_digest("source-ball-shadow-boundary"),
        input_artifacts=[
            ArtifactReference(
                storage_key="uploads/match.mp4",
                checksum_sha256=_digest("source-ball-shadow-boundary"),
            )
        ],
        request_overrides={"detector": {"acceptance_confidence": 0.4}},
    )
    with runtime.session_factory() as session:
        execution = session.get(AnalysisStageExecution, result.stage_execution_id)
        assert execution is not None
        provenance = execution.provenance_payload
        assert provenance["effective_configuration"]["detector"]["acceptance_confidence"] == 0.4
        assert provenance["detector_name"] == "opencv_color_motion_ball_detector"
        assert provenance["tracker_name"] == "bounded_nearest_trajectory_tracker"
        assert provenance["confidence_threshold"] == 0.4
        assert provenance["model_identifier"] is None
        assert provenance["model_sha256"] is None
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.state == "completed"


def test_streaming_frame_source_exposes_consistent_metadata(
    tmp_path: Path, synthetic_video_factory: Callable[..., Path]
) -> None:
    video_path = synthetic_video_factory(tmp_path / "frames.avi", frame_count=3, fps=10)
    with OpenCVFrameSource(video_path) as source:
        frames = list(source)
        assert source.metadata.width == 64
        assert source.metadata.height == 48
        assert source.metadata.frame_count == 3
    assert [frame.frame_index for frame in frames] == [0, 1, 2]
    assert [frame.timestamp_seconds for frame in frames] == pytest.approx([0.0, 0.1, 0.2])
    assert all(frame.source == frames[0].source for frame in frames)


def test_offline_feasibility_harness_requires_consent_and_verifies_bytes(
    tmp_path: Path,
) -> None:
    clips = []
    accepted_at = datetime.now(tz=UTC).isoformat()
    for index, environment in enumerate(("indoor", "outdoor"), start=1):
        video_path = tmp_path / f"clip-{index}.mp4"
        video_path.write_bytes(f"manual-clip-{index}".encode())
        labels_path = tmp_path / f"clip-{index}.jsonl"
        labels_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "frame_index": 0,
                    "timestamp_seconds": 0,
                    "visibility": "visible",
                    "center_x": 100,
                    "center_y": 50,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        clips.append(
            {
                "clip_id": f"clip-{index}",
                "video_path": video_path.name,
                "labels_path": labels_path.name,
                "video_sha256": sha256(video_path.read_bytes()).hexdigest(),
                "duration_seconds": 12,
                "width": 1920,
                "height": 1080,
                "fixed_camera": True,
                "capture_environment": environment,
                "consent": {
                    "purpose": "model_evaluation",
                    "agreement_version": "evaluation-v1",
                    "acceptance_id": f"acceptance-{index}",
                    "accepted_at": accepted_at,
                    "withdrawn_at": None,
                },
            }
        )
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema_version": 1,
        "dataset_id": "ball-visibility-small-1",
        "purpose": "offline_ball_visibility_feasibility",
        "clips": clips,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    summary = validate_feasibility_dataset(manifest_path)
    assert summary.clip_count == 2
    assert summary.labeled_frame_count == 2

    del clips[0]["consent"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FeasibilityDatasetError, match="manifest is missing or invalid"):
        validate_feasibility_dataset(manifest_path)


def _calibration_report() -> CourtCalibrationReport:
    points = OrderedCalibrationPoints(
        near_left=(0.0, 100.0),
        near_right=(100.0, 100.0),
        far_right=(80.0, 0.0),
        far_left=(20.0, 0.0),
    )
    court_points = OrderedCalibrationPoints(
        near_left=(0.0, 0.0),
        near_right=(20.0, 0.0),
        far_right=(20.0, 44.0),
        far_left=(0.0, 44.0),
    )
    return CourtCalibrationReport(
        calibration_id="court-1",
        source_image="frames/frame_000001.jpg",
        image_width=100,
        image_height=100,
        coordinate_system=CalibrationCoordinateSystem(
            unit="feet", origin="near_left", x_axis="right", y_axis="far"
        ),
        court_dimensions=CalibrationCourtDimensions(width=20, length=44, non_volley_zone_depth=7),
        image_points=points,
        court_points=court_points,
        image_to_court_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        court_to_image_matrix=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        reprojection_error=0,
        round_trip_error=0,
        created_at=datetime.now(tz=UTC),
    )
