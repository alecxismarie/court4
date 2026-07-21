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
    min_inside_extended_ratio: float
    min_average_confidence: float


@dataclass
class _RepresentativeCrop:
    score: float
    track_id: int
    frame_index: int
    confidence: float
    crop: ImageArray


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
    representative_crop: _RepresentativeCrop | None = None
    rejection_reasons: list[str] = field(default_factory=list)

    def update(self, observation: PlayerObservation, frame: ImageArray) -> None:
        self.last_frame = observation.frame_index
        self.last_timestamp_seconds = observation.timestamp_seconds
        self.observation_count += 1
        self.confidence_sum += observation.confidence
        if observation.inside_court:
            self.court_observation_count += 1
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
        rejection_reasons = _eligibility_rejection_reasons(
            observation_count=self.observation_count,
            duration_seconds=duration_seconds,
            inside_extended_ratio=inside_extended_ratio,
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
) -> PlayerTrackingResult:
    _validate_tracking_options(
        frame_interval=frame_interval,
        court_inclusion_margin_feet=court_inclusion_margin_feet,
        min_eligible_track_duration_seconds=min_eligible_track_duration_seconds,
        min_eligible_observation_count=min_eligible_observation_count,
        min_eligible_inside_extended_ratio=min_eligible_inside_extended_ratio,
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
            min_inside_extended_ratio=min_eligible_inside_extended_ratio,
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
        excluded_from_player_tracks=not inside_extended,
    )


def _validate_tracking_options(
    *,
    frame_interval: int,
    court_inclusion_margin_feet: float,
    min_eligible_track_duration_seconds: float,
    min_eligible_observation_count: int,
    min_eligible_inside_extended_ratio: float,
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
    if not 0 <= min_eligible_inside_extended_ratio <= 1:
        raise TrackingConfigurationError("Minimum inside-extended ratio must be between 0 and 1.")
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
    inside_extended_ratio: float,
    average_confidence: float,
    eligibility: EligibilityConfig,
) -> list[str]:
    reasons: list[str] = []
    if observation_count < eligibility.min_observation_count:
        reasons.append("insufficient_observations")
    if duration_seconds < eligibility.min_duration_seconds:
        reasons.append("insufficient_duration")
    if inside_extended_ratio < eligibility.min_inside_extended_ratio:
        reasons.append("mostly_outside_court")
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
