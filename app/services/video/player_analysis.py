import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import cv2
import numpy as np
from pydantic import ValidationError

from app.schemas.calibration import CourtCalibrationReport
from app.schemas.player_tracking import (
    BoundingBox,
    PlayerObservation,
    PlayerTrackingReport,
    TrackedPersonDetection,
    TrackingArtifacts,
    TrackingPerformanceSummary,
    TrackSummary,
)
from app.services.detection.interfaces import ImageArray, PersonDetectionBackend
from app.services.tracking.exceptions import (
    CalibrationReportNotFoundError,
    CalibrationReportReadError,
    TrackingConfigurationError,
    TrackingOutputExistsError,
    TrackingVideoNotFoundError,
    TrackingVideoReadError,
)
from app.sports.pickleball.calibration import court_points_to_image, image_point_to_court
from app.sports.pickleball.geometry import REGULATION_COURT, ordered_court_corner_points

logger = logging.getLogger(__name__)

PLAYER_PREVIEW_DIR_NAME = "player_previews"
PLAYER_PREVIEW_WIDTH = 320
PLAYER_PREVIEW_HEIGHT = 180
PLAYER_PREVIEW_PADDING = 10
MAX_COURT_MOVEMENT_STEP_FEET = 15.0


@dataclass(frozen=True)
class PlayerTrackingResult:
    report: PlayerTrackingReport
    tracking_dir: Path
    tracking_path: Path
    observations_path: Path
    player_selection_image_path: Path
    annotated_video_path: Path


@dataclass(frozen=True)
class EligibilityConfig:
    min_observation_count: int
    min_duration_seconds: float
    min_inside_court_ratio: float
    min_inside_extended_ratio: float
    min_court_movement_rate_feet_per_second: float
    max_selectable_tracks: int
    min_average_confidence: float


@dataclass
class _RepresentativeCrop:
    score: float
    track_id: int
    frame_index: int
    confidence: float
    crop: ImageArray


@dataclass(frozen=True)
class _PreviewCandidate:
    score: float
    track_id: int
    frame_index: int
    confidence: float
    bounding_box: BoundingBox


@dataclass
class _TrackSelectionMetrics:
    observation_count: int = 0
    confidence_sum: float = 0.0
    court_observation_count: int = 0
    extended_court_observation_count: int = 0
    court_distance_feet: float = 0.0
    last_court_position: tuple[float, float] | None = None

    def update(self, observation: PlayerObservation) -> None:
        self.observation_count += 1
        self.confidence_sum += observation.confidence
        if observation.inside_court:
            self.court_observation_count += 1
            if self.last_court_position is not None:
                step_distance = _point_distance_feet(
                    self.last_court_position,
                    observation.court_position,
                )
                if step_distance <= MAX_COURT_MOVEMENT_STEP_FEET:
                    self.court_distance_feet += step_distance
            self.last_court_position = observation.court_position
        if observation.inside_extended_court:
            self.extended_court_observation_count += 1

    @property
    def average_confidence(self) -> float:
        return self.confidence_sum / self.observation_count if self.observation_count else 0.0

    @property
    def inside_court_ratio(self) -> float:
        if not self.observation_count:
            return 0.0
        return self.court_observation_count / self.observation_count

    @property
    def inside_extended_ratio(self) -> float:
        return (
            self.extended_court_observation_count / self.observation_count
            if self.observation_count
            else 0.0
        )


@dataclass
class _TrackAccumulator:
    track_id: int
    first_frame: int
    last_frame: int
    first_timestamp_seconds: float
    last_timestamp_seconds: float
    observation_count: int = 0
    confidence_sum: float = 0.0
    court_observation_count: int = 0
    extended_court_observation_count: int = 0
    court_distance_feet: float = 0.0
    last_court_position: tuple[float, float] | None = None
    representative_crop: _RepresentativeCrop | None = None
    rejection_reasons: list[str] = field(default_factory=list)

    def update(self, observation: PlayerObservation, frame: ImageArray) -> None:
        self.last_frame = observation.frame_index
        self.last_timestamp_seconds = observation.timestamp_seconds
        self.observation_count += 1
        self.confidence_sum += observation.confidence
        if observation.inside_court:
            self.court_observation_count += 1
            if self.last_court_position is not None:
                step_distance = _point_distance_feet(
                    self.last_court_position,
                    observation.court_position,
                )
                if step_distance <= MAX_COURT_MOVEMENT_STEP_FEET:
                    self.court_distance_feet += step_distance
            self.last_court_position = observation.court_position
        if observation.inside_extended_court:
            self.extended_court_observation_count += 1
        self._update_representative_crop(observation, frame)

    def to_summary(self, eligibility: EligibilityConfig) -> TrackSummary:
        duration_seconds = max(0.0, self.last_timestamp_seconds - self.first_timestamp_seconds)
        average_confidence = (
            self.confidence_sum / self.observation_count if self.observation_count else 0.0
        )
        inside_extended_ratio = (
            self.extended_court_observation_count / self.observation_count
            if self.observation_count
            else 0.0
        )
        inside_court_ratio = (
            self.court_observation_count / self.observation_count if self.observation_count else 0.0
        )
        court_movement_rate = (
            self.court_distance_feet / duration_seconds if duration_seconds > 0 else 0.0
        )
        rejection_reasons = _eligibility_rejection_reasons(
            observation_count=self.observation_count,
            duration_seconds=duration_seconds,
            inside_court_ratio=inside_court_ratio,
            inside_extended_ratio=inside_extended_ratio,
            court_movement_rate_feet_per_second=court_movement_rate,
            average_confidence=average_confidence,
            eligibility=eligibility,
        )
        return TrackSummary(
            track_id=self.track_id,
            first_frame=self.first_frame,
            last_frame=self.last_frame,
            observation_count=self.observation_count,
            first_timestamp_seconds=self.first_timestamp_seconds,
            last_timestamp_seconds=self.last_timestamp_seconds,
            duration_seconds=duration_seconds,
            average_confidence=average_confidence,
            court_distance_feet=self.court_distance_feet,
            court_movement_rate_feet_per_second=court_movement_rate,
            court_observation_count=self.court_observation_count,
            extended_court_observation_count=self.extended_court_observation_count,
            inside_extended_court_ratio=inside_extended_ratio,
            eligible_for_selection=not rejection_reasons,
            rejection_reasons=rejection_reasons,
        )

    def _update_representative_crop(
        self,
        observation: PlayerObservation,
        frame: ImageArray,
    ) -> None:
        if observation.excluded_from_player_tracks:
            return
        height, width = frame.shape[:2]
        if not observation.bounding_box.is_inside_image(width, height):
            return
        if observation.bounding_box.area < 100:
            return

        crop = _crop_detection(frame, observation.bounding_box)
        if crop.size == 0:
            return

        score = observation.confidence * math.sqrt(observation.bounding_box.area)
        if self.representative_crop is not None and score <= self.representative_crop.score:
            return

        self.representative_crop = _RepresentativeCrop(
            score=score,
            track_id=observation.track_id,
            frame_index=observation.frame_index,
            confidence=observation.confidence,
            crop=crop,
        )


def load_calibration_report(calibration_path: Path) -> CourtCalibrationReport:
    if not calibration_path.exists():
        raise CalibrationReportNotFoundError(
            f"Calibration report does not exist: {calibration_path}"
        )
    if not calibration_path.is_file():
        raise CalibrationReportReadError(f"Calibration path is not a file: {calibration_path}")

    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
        return CourtCalibrationReport.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CalibrationReportReadError(
            f"Calibration report could not be parsed: {calibration_path}"
        ) from exc


def analyze_players(
    *,
    video_path: Path,
    calibration: CourtCalibrationReport,
    output_dir: Path,
    tracking_backend: PersonDetectionBackend,
    analysis_id: str | None,
    frame_interval: int,
    court_inclusion_margin_feet: float,
    min_eligible_track_duration_seconds: float,
    min_eligible_observation_count: int,
    min_eligible_inside_extended_ratio: float,
    min_eligible_average_confidence: float,
    annotated_video_codec: str,
    annotated_video_fps: float,
    min_eligible_inside_court_ratio: float = 0.6,
    min_eligible_court_movement_rate_feet_per_second: float = 1.2,
    max_selectable_player_tracks: int = 4,
) -> PlayerTrackingResult:
    _validate_tracking_options(
        frame_interval=frame_interval,
        court_inclusion_margin_feet=court_inclusion_margin_feet,
        min_eligible_track_duration_seconds=min_eligible_track_duration_seconds,
        min_eligible_observation_count=min_eligible_observation_count,
        min_eligible_inside_court_ratio=min_eligible_inside_court_ratio,
        min_eligible_inside_extended_ratio=min_eligible_inside_extended_ratio,
        min_eligible_court_movement_rate_feet_per_second=(
            min_eligible_court_movement_rate_feet_per_second
        ),
        max_selectable_player_tracks=max_selectable_player_tracks,
        min_eligible_average_confidence=min_eligible_average_confidence,
        annotated_video_codec=annotated_video_codec,
        annotated_video_fps=annotated_video_fps,
    )

    resolved_video_path = video_path.expanduser()
    if not resolved_video_path.exists():
        raise TrackingVideoNotFoundError(f"Source video does not exist: {resolved_video_path}")
    if not resolved_video_path.is_file():
        raise TrackingVideoReadError(f"Source video input is not a file: {resolved_video_path}")

    resolved_analysis_id = _validate_output_id(analysis_id or uuid4().hex, "analysis ID")
    tracking_dir = output_dir.expanduser() / resolved_analysis_id / "tracking"
    if tracking_dir.exists():
        raise TrackingOutputExistsError(f"Tracking output directory already exists: {tracking_dir}")
    tracking_dir.mkdir(parents=True, exist_ok=False)

    tracking_path = tracking_dir / "tracking.json"
    observations_path = tracking_dir / "observations.jsonl"
    player_selection_image_path = tracking_dir / "player_selection.jpg"
    annotated_video_path = tracking_dir / "tracked_players.mp4"

    capture = cv2.VideoCapture(str(resolved_video_path))
    video_writer: cv2.VideoWriter | None = None
    start_time = time.monotonic()
    detector_time_seconds = 0.0
    processed_frame_count = 0
    skipped_frame_count = 0
    frame_index = 0
    track_accumulators: dict[int, _TrackAccumulator] = {}

    try:
        if not capture.isOpened():
            raise TrackingVideoReadError(f"OpenCV could not open video: {resolved_video_path}")

        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if source_width <= 0 or source_height <= 0:
            raise TrackingVideoReadError("OpenCV could not determine source video dimensions.")
        if source_fps <= 0:
            raise TrackingVideoReadError("OpenCV could not determine source video FPS.")
        _validate_calibration_matches_video(calibration, source_width, source_height)

        video_writer = _create_video_writer(
            output_path=annotated_video_path,
            codec=annotated_video_codec,
            fps=annotated_video_fps,
            width=source_width,
            height=source_height,
        )

        court_polygon_image_points = court_points_to_image(
            ordered_court_corner_points(),
            calibration,
        )
        eligibility = EligibilityConfig(
            min_observation_count=min_eligible_observation_count,
            min_duration_seconds=min_eligible_track_duration_seconds,
            min_inside_court_ratio=min_eligible_inside_court_ratio,
            min_inside_extended_ratio=min_eligible_inside_extended_ratio,
            min_court_movement_rate_feet_per_second=(
                min_eligible_court_movement_rate_feet_per_second
            ),
            max_selectable_tracks=max_selectable_player_tracks,
            min_average_confidence=min_eligible_average_confidence,
        )

        with observations_path.open("w", encoding="utf-8") as observations_file:
            while True:
                success, frame = capture.read()
                if not success:
                    break

                if frame_index % frame_interval != 0:
                    skipped_frame_count += 1
                    frame_index += 1
                    continue

                timestamp_seconds = frame_index / source_fps
                detector_start = time.monotonic()
                detections = tracking_backend.track_frame(
                    cast(ImageArray, frame),
                    frame_index=frame_index,
                    timestamp_seconds=timestamp_seconds,
                )
                detector_time_seconds += time.monotonic() - detector_start

                observations = tuple(
                    _build_observation(
                        detection=detection,
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        calibration=calibration,
                        court_inclusion_margin_feet=court_inclusion_margin_feet,
                    )
                    for detection in detections
                )
                for observation in observations:
                    observations_file.write(
                        json.dumps(observation.model_dump(mode="json"), separators=(",", ":"))
                        + "\n"
                    )
                    accumulator = track_accumulators.setdefault(
                        observation.track_id,
                        _TrackAccumulator(
                            track_id=observation.track_id,
                            first_frame=observation.frame_index,
                            last_frame=observation.frame_index,
                            first_timestamp_seconds=observation.timestamp_seconds,
                            last_timestamp_seconds=observation.timestamp_seconds,
                        ),
                    )
                    accumulator.update(observation, cast(ImageArray, frame))

                annotated_frame = _draw_annotated_frame(
                    frame=cast(ImageArray, frame),
                    observations=observations,
                    court_polygon_image_points=court_polygon_image_points,
                )
                video_writer.write(annotated_frame)
                processed_frame_count += 1
                frame_index += 1

        if processed_frame_count == 0:
            raise TrackingVideoReadError("No frames were processed from the source video.")

        track_summaries = [
            accumulator.to_summary(eligibility)
            for accumulator in sorted(track_accumulators.values(), key=lambda item: item.track_id)
        ]
        track_summaries = _apply_selectable_track_limit(track_summaries, eligibility)
        preview_paths = _write_player_preview_images_from_accumulators(
            summaries=track_summaries,
            accumulators=track_accumulators,
            tracking_dir=tracking_dir,
        )
        track_summaries = _apply_preview_paths(track_summaries, preview_paths)
        eligible_track_ids = [
            summary.track_id for summary in track_summaries if summary.eligible_for_selection
        ]
        _write_player_selection_contact_sheet(
            summaries=track_summaries,
            accumulators=track_accumulators,
            output_path=player_selection_image_path,
        )

        processing_time_seconds = time.monotonic() - start_time
        average_processing_fps = (
            processed_frame_count / processing_time_seconds if processing_time_seconds > 0 else 0.0
        )
        report = PlayerTrackingReport(
            analysis_id=resolved_analysis_id,
            source_video=resolved_video_path.name,
            calibration_id=calibration.calibration_id,
            model_name=tracking_backend.model_name,
            processed_frame_count=processed_frame_count,
            source_frame_count=max(0, source_frame_count),
            frame_interval=frame_interval,
            track_count=len(track_summaries),
            eligible_player_track_ids=eligible_track_ids,
            selected_player_track_id=None,
            court_inclusion_margin_feet=court_inclusion_margin_feet,
            track_summaries=track_summaries,
            artifacts=TrackingArtifacts(
                tracking_json=tracking_path.name,
                observations_jsonl=observations_path.name,
                player_selection_image=player_selection_image_path.name,
                annotated_video=annotated_video_path.name,
            ),
            performance=TrackingPerformanceSummary(
                source_duration_seconds=source_frame_count / source_fps
                if source_frame_count > 0
                else 0.0,
                source_frame_count=max(0, source_frame_count),
                processed_frame_count=processed_frame_count,
                skipped_frame_count=skipped_frame_count,
                processing_time_seconds=processing_time_seconds,
                average_processing_fps=average_processing_fps,
                detector_time_seconds=detector_time_seconds,
            ),
            created_at=datetime.now(tz=UTC),
        )
        _write_tracking_report(report, tracking_path)

        logger.info(
            "player_tracking_completed",
            extra={
                "analysis_id": resolved_analysis_id,
                "source_video": str(resolved_video_path),
                "tracking_path": str(tracking_path),
                "processed_frame_count": processed_frame_count,
                "track_count": len(track_summaries),
                "eligible_track_ids": eligible_track_ids,
            },
        )
        return PlayerTrackingResult(
            report=report,
            tracking_dir=tracking_dir,
            tracking_path=tracking_path,
            observations_path=observations_path,
            player_selection_image_path=player_selection_image_path,
            annotated_video_path=annotated_video_path,
        )
    finally:
        capture.release()
        if video_writer is not None:
            video_writer.release()
        tracking_backend.close()


def ground_contact_point(bounding_box: BoundingBox) -> tuple[float, float]:
    return bounding_box.bottom_center()


def is_inside_court(point: tuple[float, float]) -> bool:
    x, y = point
    court = REGULATION_COURT
    return 0.0 <= x <= court.width_feet and 0.0 <= y <= court.length_feet


def is_inside_extended_court(point: tuple[float, float], margin_feet: float) -> bool:
    x, y = point
    court = REGULATION_COURT
    return (
        -margin_feet <= x <= court.width_feet + margin_feet
        and -margin_feet <= y <= court.length_feet + margin_feet
    )


def _build_observation(
    *,
    detection: TrackedPersonDetection,
    frame_index: int,
    timestamp_seconds: float,
    calibration: CourtCalibrationReport,
    court_inclusion_margin_feet: float,
) -> PlayerObservation:
    image_ground_point = ground_contact_point(detection.bounding_box)
    court_position = image_point_to_court(image_ground_point, calibration)
    inside = is_inside_court(court_position)
    inside_extended = is_inside_extended_court(court_position, court_inclusion_margin_feet)
    return PlayerObservation(
        frame_index=frame_index,
        timestamp_seconds=timestamp_seconds,
        track_id=detection.track_id,
        bounding_box=detection.bounding_box,
        confidence=detection.confidence,
        image_ground_point=image_ground_point,
        court_position=court_position,
        inside_court=inside,
        inside_extended_court=inside_extended,
        excluded_from_player_tracks=not inside,
    )


def _validate_tracking_options(
    *,
    frame_interval: int,
    court_inclusion_margin_feet: float,
    min_eligible_track_duration_seconds: float,
    min_eligible_observation_count: int,
    min_eligible_inside_court_ratio: float,
    min_eligible_inside_extended_ratio: float,
    min_eligible_court_movement_rate_feet_per_second: float,
    max_selectable_player_tracks: int,
    min_eligible_average_confidence: float,
    annotated_video_codec: str,
    annotated_video_fps: float,
) -> None:
    if frame_interval <= 0:
        raise TrackingConfigurationError("Frame processing interval must be at least 1.")
    if court_inclusion_margin_feet < 0:
        raise TrackingConfigurationError("Court inclusion margin must be non-negative.")
    if min_eligible_track_duration_seconds < 0:
        raise TrackingConfigurationError("Minimum eligible duration must be non-negative.")
    if min_eligible_observation_count <= 0:
        raise TrackingConfigurationError("Minimum eligible observation count must be positive.")
    if not 0 <= min_eligible_inside_court_ratio <= 1:
        raise TrackingConfigurationError("Minimum inside-court ratio must be between 0 and 1.")
    if not 0 <= min_eligible_inside_extended_ratio <= 1:
        raise TrackingConfigurationError("Minimum inside-extended ratio must be between 0 and 1.")
    if min_eligible_court_movement_rate_feet_per_second < 0:
        raise TrackingConfigurationError("Minimum court movement rate must be non-negative.")
    if max_selectable_player_tracks <= 0:
        raise TrackingConfigurationError("Maximum selectable player tracks must be positive.")
    if not 0 <= min_eligible_average_confidence <= 1:
        raise TrackingConfigurationError("Minimum average confidence must be between 0 and 1.")
    if len(annotated_video_codec) != 4:
        raise TrackingConfigurationError("Annotated video codec must be exactly four characters.")
    if annotated_video_fps <= 0:
        raise TrackingConfigurationError("Annotated video FPS must be positive.")


def _validate_output_id(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise TrackingConfigurationError(f"{label} cannot be empty.")
    if cleaned in {".", ".."} or "/" in cleaned or "\\" in cleaned:
        raise TrackingConfigurationError(f"{label} must not contain path separators.")
    return cleaned


def _validate_calibration_matches_video(
    calibration: CourtCalibrationReport,
    source_width: int,
    source_height: int,
) -> None:
    if calibration.image_width != source_width or calibration.image_height != source_height:
        raise CalibrationReportReadError(
            "Calibration image dimensions do not match source video dimensions "
            f"({calibration.image_width}x{calibration.image_height} != "
            f"{source_width}x{source_height})."
        )
    image_point_to_court(calibration.image_points.near_left, calibration)


def _create_video_writer(
    *,
    output_path: Path,
    codec: str,
    fps: float,
    width: int,
    height: int,
) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*codec)  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise TrackingVideoReadError(f"OpenCV could not create annotated video: {output_path}")
    return writer


def _draw_annotated_frame(
    *,
    frame: ImageArray,
    observations: tuple[PlayerObservation, ...],
    court_polygon_image_points: tuple[tuple[float, float], ...],
) -> ImageArray:
    annotated = frame.copy()
    polygon = np.array([_int_point(point) for point in court_polygon_image_points], dtype=np.int32)
    cv2.polylines(annotated, [polygon], isClosed=True, color=(0, 255, 255), thickness=2)

    for observation in observations:
        color = (0, 180, 0) if not observation.excluded_from_player_tracks else (0, 0, 255)
        box = observation.bounding_box
        top_left = _int_point((box.x1, box.y1))
        bottom_right = _int_point((box.x2, box.y2))
        cv2.rectangle(annotated, top_left, bottom_right, color, thickness=2)
        cv2.circle(annotated, _int_point(observation.image_ground_point), 4, (255, 255, 0), -1)
        label = f"ID {observation.track_id}"
        if observation.excluded_from_player_tracks:
            label = f"{label} excluded"
        _draw_text(annotated, label, (top_left[0], max(18, top_left[1] - 6)), color)
    return cast(ImageArray, annotated)


def _draw_text(
    image: ImageArray,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    cv2.putText(
        image,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        thickness=3,
        lineType=cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        thickness=1,
        lineType=cv2.LINE_AA,
    )


def _crop_detection(frame: ImageArray, bounding_box: BoundingBox) -> ImageArray:
    height, width = frame.shape[:2]
    x1 = max(0, int(math.floor(bounding_box.x1)))
    y1 = max(0, int(math.floor(bounding_box.y1)))
    x2 = min(width, int(math.ceil(bounding_box.x2)))
    y2 = min(height, int(math.ceil(bounding_box.y2)))
    crop = frame[y1:y2, x1:x2].copy()
    if crop.size:
        cv2.rectangle(
            crop,
            (0, 0),
            (max(0, crop.shape[1] - 1), max(0, crop.shape[0] - 1)),
            (0, 255, 0),
            2,
        )
    return cast(ImageArray, crop)


def ensure_player_preview_images(
    *,
    tracking_report_path: Path,
    source_video_path: Path,
) -> PlayerTrackingReport:
    """Backfill per-track preview images for persisted tracking reports."""
    report = _read_tracking_report(tracking_report_path)
    tracking_dir = tracking_report_path.parent
    expected_paths = {
        summary.track_id: _player_preview_artifact_path(summary.track_id)
        for summary in report.track_summaries
        if summary.eligible_for_selection
    }
    preview_paths = {
        track_id: artifact_path
        for track_id, artifact_path in expected_paths.items()
        if _artifact_path_exists(tracking_dir, artifact_path)
    }
    missing_track_ids = set(expected_paths) - set(preview_paths)

    if missing_track_ids:
        preview_paths.update(
            _write_player_preview_images_from_observations(
                observations_path=tracking_dir / report.artifacts.observations_jsonl,
                source_video_path=source_video_path,
                tracking_dir=tracking_dir,
                track_ids=missing_track_ids,
            )
        )

    updated_summaries = _apply_preview_paths(report.track_summaries, preview_paths)
    if updated_summaries == report.track_summaries:
        return report

    updated_report = report.model_copy(update={"track_summaries": updated_summaries})
    _write_tracking_report(updated_report, tracking_report_path)
    return updated_report


def refresh_player_selection_metrics(
    *,
    tracking_report_path: Path,
    eligibility: EligibilityConfig,
) -> PlayerTrackingReport:
    report = _read_tracking_report(tracking_report_path)
    observations_path = tracking_report_path.parent / report.artifacts.observations_jsonl
    if not observations_path.is_file():
        return report

    metrics_by_track = _collect_track_selection_metrics(observations_path)
    updated_summaries: list[TrackSummary] = []
    for summary in report.track_summaries:
        metrics = metrics_by_track.get(summary.track_id)
        if metrics is None:
            updated_summaries.append(summary)
            continue

        court_movement_rate = (
            metrics.court_distance_feet / summary.duration_seconds
            if summary.duration_seconds > 0
            else 0.0
        )
        rejection_reasons = _eligibility_rejection_reasons(
            observation_count=summary.observation_count,
            duration_seconds=summary.duration_seconds,
            inside_court_ratio=metrics.inside_court_ratio,
            inside_extended_ratio=metrics.inside_extended_ratio,
            court_movement_rate_feet_per_second=court_movement_rate,
            average_confidence=metrics.average_confidence,
            eligibility=eligibility,
        )
        eligible = not rejection_reasons
        updated_summaries.append(
            summary.model_copy(
                update={
                    "average_confidence": metrics.average_confidence,
                    "court_distance_feet": metrics.court_distance_feet,
                    "court_movement_rate_feet_per_second": court_movement_rate,
                    "court_observation_count": metrics.court_observation_count,
                    "extended_court_observation_count": (metrics.extended_court_observation_count),
                    "inside_extended_court_ratio": metrics.inside_extended_ratio,
                    "eligible_for_selection": eligible,
                    "rejection_reasons": rejection_reasons,
                    "preview_image": summary.preview_image if eligible else None,
                }
            )
        )

    updated_summaries = _apply_selectable_track_limit(updated_summaries, eligibility)
    eligible_track_ids = [
        summary.track_id for summary in updated_summaries if summary.eligible_for_selection
    ]
    updated_report = report.model_copy(
        update={
            "track_summaries": updated_summaries,
            "eligible_player_track_ids": eligible_track_ids,
        }
    )
    if updated_report == report:
        return report

    _write_tracking_report(updated_report, tracking_report_path)
    return updated_report


def _collect_track_selection_metrics(
    observations_path: Path,
) -> dict[int, _TrackSelectionMetrics]:
    metrics_by_track: dict[int, _TrackSelectionMetrics] = {}
    with observations_path.open("r", encoding="utf-8") as observations_file:
        for line in observations_file:
            if not line.strip():
                continue
            try:
                observation = PlayerObservation.model_validate_json(line)
            except ValidationError:
                continue
            metrics = metrics_by_track.setdefault(
                observation.track_id,
                _TrackSelectionMetrics(),
            )
            metrics.update(observation)
    return metrics_by_track


def _write_player_preview_images_from_accumulators(
    *,
    summaries: list[TrackSummary],
    accumulators: dict[int, _TrackAccumulator],
    tracking_dir: Path,
) -> dict[int, str]:
    preview_paths: dict[int, str] = {}
    preview_dir = tracking_dir / PLAYER_PREVIEW_DIR_NAME
    for summary in summaries:
        if not summary.eligible_for_selection:
            continue
        crop = accumulators[summary.track_id].representative_crop
        if crop is None:
            continue
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = _player_preview_file_path(tracking_dir, summary.track_id)
        preview = _format_player_preview(crop.crop)
        if not cv2.imwrite(str(preview_path), preview):
            raise TrackingVideoReadError(f"OpenCV could not write player preview: {preview_path}")
        preview_paths[summary.track_id] = _player_preview_artifact_path(summary.track_id)
    return preview_paths


def _write_player_preview_images_from_observations(
    *,
    observations_path: Path,
    source_video_path: Path,
    tracking_dir: Path,
    track_ids: set[int],
) -> dict[int, str]:
    if not observations_path.is_file() or not source_video_path.is_file():
        return {}

    capture = cv2.VideoCapture(str(source_video_path))
    try:
        if not capture.isOpened():
            return {}
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if source_width <= 0 or source_height <= 0:
            return {}

        candidates = _collect_player_preview_candidates(
            observations_path=observations_path,
            track_ids=track_ids,
            image_width=source_width,
            image_height=source_height,
        )
        if not candidates:
            return {}

        preview_dir = tracking_dir / PLAYER_PREVIEW_DIR_NAME
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_paths: dict[int, str] = {}
        for candidate in sorted(candidates.values(), key=lambda item: item.frame_index):
            capture.set(cv2.CAP_PROP_POS_FRAMES, candidate.frame_index)
            success, frame = capture.read()
            if not success:
                continue
            crop = _crop_detection(cast(ImageArray, frame), candidate.bounding_box)
            if crop.size == 0:
                continue
            preview_path = _player_preview_file_path(tracking_dir, candidate.track_id)
            preview = _format_player_preview(crop)
            if not cv2.imwrite(str(preview_path), preview):
                continue
            preview_paths[candidate.track_id] = _player_preview_artifact_path(candidate.track_id)
        return preview_paths
    finally:
        capture.release()


def _collect_player_preview_candidates(
    *,
    observations_path: Path,
    track_ids: set[int],
    image_width: int,
    image_height: int,
) -> dict[int, _PreviewCandidate]:
    candidates: dict[int, _PreviewCandidate] = {}
    with observations_path.open("r", encoding="utf-8") as observations_file:
        for line in observations_file:
            if not line.strip():
                continue
            try:
                observation = PlayerObservation.model_validate_json(line)
            except ValidationError:
                continue
            if observation.track_id not in track_ids or observation.excluded_from_player_tracks:
                continue
            if not observation.bounding_box.is_inside_image(image_width, image_height):
                continue
            if observation.bounding_box.area < 100:
                continue

            score = observation.confidence * math.sqrt(observation.bounding_box.area)
            current = candidates.get(observation.track_id)
            if current is not None and score <= current.score:
                continue
            candidates[observation.track_id] = _PreviewCandidate(
                score=score,
                track_id=observation.track_id,
                frame_index=observation.frame_index,
                confidence=observation.confidence,
                bounding_box=observation.bounding_box,
            )
    return candidates


def _format_player_preview(crop: ImageArray) -> ImageArray:
    preview = np.full(
        (PLAYER_PREVIEW_HEIGHT, PLAYER_PREVIEW_WIDTH, 3),
        255,
        dtype=np.uint8,
    )
    height, width = crop.shape[:2]
    if height <= 0 or width <= 0:
        return cast(ImageArray, preview)

    max_width = PLAYER_PREVIEW_WIDTH - PLAYER_PREVIEW_PADDING * 2
    max_height = PLAYER_PREVIEW_HEIGHT - PLAYER_PREVIEW_PADDING * 2
    scale = min(max_width / width, max_height / height)
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    resized = cv2.resize(crop, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    x = (PLAYER_PREVIEW_WIDTH - resized_width) // 2
    y = (PLAYER_PREVIEW_HEIGHT - resized_height) // 2
    preview[y : y + resized_height, x : x + resized_width] = resized
    return cast(ImageArray, preview)


def _apply_preview_paths(
    summaries: list[TrackSummary],
    preview_paths: dict[int, str],
) -> list[TrackSummary]:
    updated_summaries: list[TrackSummary] = []
    for summary in summaries:
        preview_path = preview_paths.get(summary.track_id)
        if preview_path is not None and summary.preview_image != preview_path:
            updated_summaries.append(summary.model_copy(update={"preview_image": preview_path}))
        else:
            updated_summaries.append(summary)
    return updated_summaries


def _apply_selectable_track_limit(
    summaries: list[TrackSummary],
    eligibility: EligibilityConfig,
) -> list[TrackSummary]:
    eligible_summaries = [summary for summary in summaries if summary.eligible_for_selection]
    if len(eligible_summaries) <= eligibility.max_selectable_tracks:
        return summaries

    kept_track_ids = {
        summary.track_id
        for summary in sorted(eligible_summaries, key=_selectable_track_rank_key)[
            : eligibility.max_selectable_tracks
        ]
    }
    limited_summaries: list[TrackSummary] = []
    for summary in summaries:
        if not summary.eligible_for_selection or summary.track_id in kept_track_ids:
            limited_summaries.append(summary)
            continue
        limited_summaries.append(
            summary.model_copy(
                update={
                    "eligible_for_selection": False,
                    "rejection_reasons": [
                        *summary.rejection_reasons,
                        "outside_top_player_candidates",
                    ],
                    "preview_image": None,
                }
            )
        )
    return limited_summaries


def _selectable_track_rank_key(summary: TrackSummary) -> tuple[float, float, float, float, int]:
    return (
        -summary.court_distance_feet,
        -summary.court_movement_rate_feet_per_second,
        -summary.duration_seconds,
        -summary.average_confidence,
        summary.track_id,
    )


def _player_preview_artifact_path(track_id: int) -> str:
    return f"tracking/{PLAYER_PREVIEW_DIR_NAME}/track_{track_id}.jpg"


def _player_preview_file_path(tracking_dir: Path, track_id: int) -> Path:
    return tracking_dir / PLAYER_PREVIEW_DIR_NAME / f"track_{track_id}.jpg"


def _artifact_path_exists(tracking_dir: Path, artifact_path: str) -> bool:
    analysis_dir = tracking_dir.parent.resolve()
    path = (analysis_dir / artifact_path).resolve()
    return path.is_relative_to(analysis_dir) and path.is_file()


def _read_tracking_report(tracking_path: Path) -> PlayerTrackingReport:
    try:
        payload = json.loads(tracking_path.read_text(encoding="utf-8"))
        return PlayerTrackingReport.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise TrackingConfigurationError(
            f"Tracking report could not be parsed: {tracking_path}"
        ) from exc


def _write_player_selection_contact_sheet(
    *,
    summaries: list[TrackSummary],
    accumulators: dict[int, _TrackAccumulator],
    output_path: Path,
) -> None:
    eligible_summaries = [summary for summary in summaries if summary.eligible_for_selection]
    cell_width = 260
    cell_height = 220
    rows = max(1, len(eligible_summaries))
    sheet = np.full((rows * cell_height, cell_width, 3), 245, dtype=np.uint8)

    if not eligible_summaries:
        _draw_text(cast(ImageArray, sheet), "No eligible player tracks", (20, 60), (0, 0, 255))
    for row, summary in enumerate(eligible_summaries):
        y_offset = row * cell_height
        crop = accumulators[summary.track_id].representative_crop
        label = (
            f"Track {summary.track_id} | obs {summary.observation_count} | "
            f"conf {summary.average_confidence:.2f}"
        )
        _draw_text(cast(ImageArray, sheet), label, (12, y_offset + 24), (0, 0, 0))
        if crop is None:
            _draw_text(
                cast(ImageArray, sheet),
                "No representative crop",
                (20, y_offset + 90),
                (0, 0, 255),
            )
            continue

        resized = _resize_for_contact_sheet(crop.crop, max_width=220, max_height=160)
        x = 20
        y = y_offset + 45
        sheet[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
        _draw_text(
            cast(ImageArray, sheet),
            f"frame {crop.frame_index}",
            (20, y_offset + 205),
            (0, 0, 0),
        )

    if not cv2.imwrite(str(output_path), sheet):
        raise TrackingVideoReadError(
            f"OpenCV could not write player selection image: {output_path}"
        )


def _resize_for_contact_sheet(
    crop: ImageArray,
    *,
    max_width: int,
    max_height: int,
) -> ImageArray:
    height, width = crop.shape[:2]
    scale = min(max_width / width, max_height / height)
    new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    resized = cv2.resize(crop, new_size, interpolation=cv2.INTER_AREA)
    return cast(ImageArray, resized)


def _eligibility_rejection_reasons(
    *,
    observation_count: int,
    duration_seconds: float,
    inside_court_ratio: float,
    inside_extended_ratio: float,
    court_movement_rate_feet_per_second: float,
    average_confidence: float,
    eligibility: EligibilityConfig,
) -> list[str]:
    reasons: list[str] = []
    if observation_count < eligibility.min_observation_count:
        reasons.append("insufficient_observations")
    if duration_seconds < eligibility.min_duration_seconds:
        reasons.append("insufficient_duration")
    if inside_court_ratio < eligibility.min_inside_court_ratio:
        reasons.append("mostly_outside_detected_court")
    if inside_extended_ratio < eligibility.min_inside_extended_ratio:
        reasons.append("mostly_outside_court")
    if (
        duration_seconds >= eligibility.min_duration_seconds
        and court_movement_rate_feet_per_second
        < eligibility.min_court_movement_rate_feet_per_second
    ):
        reasons.append("limited_court_movement")
    if average_confidence < eligibility.min_average_confidence:
        reasons.append("low_average_confidence")
    return reasons


def _write_tracking_report(report: PlayerTrackingReport, tracking_path: Path) -> None:
    tracking_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _int_point(point: tuple[float, float]) -> tuple[int, int]:
    return (int(round(point[0])), int(round(point[1])))


def _point_distance_feet(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])
