import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import cv2

from app.schemas.video import VideoMetadataReport
from app.services.video.exceptions import (
    FrameSamplingError,
    OutputDirectoryExistsError,
    UnsupportedVideoExtensionError,
    VideoFileNotFoundError,
    VideoFileTooLargeError,
    VideoMetadataError,
    VideoOpenError,
    VideoValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VideoInspectionResult:
    report: VideoMetadataReport
    analysis_dir: Path
    frames_dir: Path
    metadata_path: Path
    frame_paths: tuple[Path, ...]


@dataclass(frozen=True)
class _ValidatedVideo:
    path: Path
    file_size_bytes: int


@dataclass(frozen=True)
class _RawVideoMetadata:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_seconds: float
    codec: str | None


def inspect_video(
    *,
    input_path: Path,
    output_dir: Path,
    sample_interval_seconds: float,
    supported_extensions: Sequence[str],
    max_file_size_bytes: int,
    analysis_id: str | None = None,
) -> VideoInspectionResult:
    """Validate a video, extract metadata, sample frames, and write a JSON report."""
    if sample_interval_seconds <= 0:
        raise VideoValidationError("Sample interval must be greater than zero seconds.")
    if max_file_size_bytes <= 0:
        raise VideoValidationError("Maximum file size must be greater than zero bytes.")

    validated_video = _validate_video_input(
        input_path=input_path,
        supported_extensions=supported_extensions,
        max_file_size_bytes=max_file_size_bytes,
    )
    resolved_analysis_id = analysis_id or uuid4().hex

    capture = cv2.VideoCapture(str(validated_video.path))
    try:
        if not capture.isOpened():
            raise VideoOpenError(f"OpenCV could not open video: {validated_video.path}")

        raw_metadata = _extract_metadata(capture)
        analysis_dir, frames_dir = _create_output_directories(output_dir, resolved_analysis_id)
        frame_paths = _sample_frames(
            capture=capture,
            frames_dir=frames_dir,
            frame_count=raw_metadata.frame_count,
            fps=raw_metadata.fps,
            sample_interval_seconds=sample_interval_seconds,
        )
        report = VideoMetadataReport(
            analysis_id=resolved_analysis_id,
            filename=validated_video.path.name,
            file_size_bytes=validated_video.file_size_bytes,
            width=raw_metadata.width,
            height=raw_metadata.height,
            fps=raw_metadata.fps,
            frame_count=raw_metadata.frame_count,
            duration_seconds=raw_metadata.duration_seconds,
            codec=raw_metadata.codec,
            sample_interval_seconds=sample_interval_seconds,
            sampled_frames=len(frame_paths),
            created_at=datetime.now(tz=UTC),
        )
        metadata_path = analysis_dir / "metadata.json"
        _write_metadata_report(report, metadata_path)

        logger.info(
            "video_inspection_completed",
            extra={
                "analysis_id": resolved_analysis_id,
                "input_path": str(validated_video.path),
                "metadata_path": str(metadata_path),
                "sampled_frames": len(frame_paths),
            },
        )
        return VideoInspectionResult(
            report=report,
            analysis_dir=analysis_dir,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            frame_paths=frame_paths,
        )
    finally:
        capture.release()


def _validate_video_input(
    *,
    input_path: Path,
    supported_extensions: Sequence[str],
    max_file_size_bytes: int,
) -> _ValidatedVideo:
    video_path = input_path.expanduser()
    if not video_path.exists():
        raise VideoFileNotFoundError(f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise VideoValidationError(f"Video input is not a file: {video_path}")

    normalized_extensions = _normalize_extensions(supported_extensions)
    extension = video_path.suffix.lower()
    if extension not in normalized_extensions:
        supported = ", ".join(normalized_extensions)
        raise UnsupportedVideoExtensionError(
            f"Unsupported video extension '{extension}'. Supported extensions: {supported}."
        )

    file_size_bytes = video_path.stat().st_size
    if file_size_bytes > max_file_size_bytes:
        raise VideoFileTooLargeError(
            "Video file exceeds the configured maximum size "
            f"({file_size_bytes} > {max_file_size_bytes} bytes): {video_path}"
        )

    return _ValidatedVideo(path=video_path, file_size_bytes=file_size_bytes)


def _normalize_extensions(supported_extensions: Sequence[str]) -> tuple[str, ...]:
    normalized = []
    for extension in supported_extensions:
        cleaned = extension.strip().lower()
        if not cleaned:
            continue
        normalized.append(cleaned if cleaned.startswith(".") else f".{cleaned}")
    if not normalized:
        raise VideoValidationError("At least one supported video extension is required.")
    return tuple(dict.fromkeys(normalized))


def _extract_metadata(capture: cv2.VideoCapture) -> _RawVideoMetadata:
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    if width <= 0 or height <= 0:
        raise VideoMetadataError("OpenCV could not determine a valid video resolution.")
    if fps <= 0:
        raise VideoMetadataError("OpenCV could not determine a valid video frame rate.")
    if frame_count <= 0:
        raise VideoMetadataError("OpenCV could not determine a valid video frame count.")

    return _RawVideoMetadata(
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_seconds=frame_count / fps,
        codec=_extract_codec(capture),
    )


def _extract_codec(capture: cv2.VideoCapture) -> str | None:
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
    if fourcc <= 0:
        return None

    chars = [chr((fourcc >> (8 * index)) & 0xFF) for index in range(4)]
    codec = "".join(chars).strip().strip("\x00")
    if not codec or not codec.isprintable():
        return None
    return codec


def _create_output_directories(output_dir: Path, analysis_id: str) -> tuple[Path, Path]:
    analysis_dir = output_dir.expanduser() / analysis_id
    frames_dir = analysis_dir / "frames"

    if analysis_dir.exists():
        raise OutputDirectoryExistsError(
            f"Analysis output directory already exists: {analysis_dir}"
        )

    frames_dir.mkdir(parents=True, exist_ok=False)
    return analysis_dir, frames_dir


def _sample_frames(
    *,
    capture: cv2.VideoCapture,
    frames_dir: Path,
    frame_count: int,
    fps: float,
    sample_interval_seconds: float,
) -> tuple[Path, ...]:
    frame_paths: list[Path] = []
    for frame_index in _iter_sample_frame_indices(
        frame_count=frame_count,
        fps=fps,
        sample_interval_seconds=sample_interval_seconds,
    ):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = capture.read()
        if not success:
            logger.warning(
                "sample_frame_read_failed",
                extra={"frame_index": frame_index, "frames_dir": str(frames_dir)},
            )
            continue

        frame_path = frames_dir / f"frame_{frame_index + 1:06d}.jpg"
        if not cv2.imwrite(str(frame_path), frame):
            raise FrameSamplingError(f"OpenCV could not write sampled frame: {frame_path}")
        frame_paths.append(frame_path)

    if not frame_paths:
        raise FrameSamplingError("No frames could be sampled from the video.")

    return tuple(frame_paths)


def _iter_sample_frame_indices(
    *,
    frame_count: int,
    fps: float,
    sample_interval_seconds: float,
) -> Iterator[int]:
    interval_frames = max(1, int(round(fps * sample_interval_seconds)))
    frame_index = 0
    while frame_index < frame_count:
        yield frame_index
        frame_index += interval_frames


def _write_metadata_report(report: VideoMetadataReport, metadata_path: Path) -> None:
    metadata = report.model_dump(mode="json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
