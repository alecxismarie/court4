import json
from collections.abc import Callable
from pathlib import Path

import pytest

from app.services.video import (
    UnsupportedVideoExtensionError,
    VideoFileNotFoundError,
    VideoInspectionError,
    inspect_video,
)


def test_missing_file_raises_meaningful_error(tmp_path: Path) -> None:
    with pytest.raises(VideoFileNotFoundError, match="does not exist"):
        inspect_video(
            input_path=tmp_path / "missing.mp4",
            output_dir=tmp_path / "output",
            sample_interval_seconds=1,
            supported_extensions=(".mp4", ".avi"),
            max_file_size_bytes=1_000_000,
        )


def test_invalid_extension_raises_meaningful_error(tmp_path: Path) -> None:
    invalid_file = tmp_path / "notes.txt"
    invalid_file.write_text("not a video", encoding="utf-8")

    with pytest.raises(UnsupportedVideoExtensionError, match="Unsupported video extension"):
        inspect_video(
            input_path=invalid_file,
            output_dir=tmp_path / "output",
            sample_interval_seconds=1,
            supported_extensions=(".mp4", ".avi"),
            max_file_size_bytes=1_000_000,
        )


def test_unreadable_video_raises_meaningful_error(tmp_path: Path) -> None:
    unreadable_file = tmp_path / "broken.mp4"
    unreadable_file.write_text("not a decodable video", encoding="utf-8")

    with pytest.raises(VideoInspectionError, match="OpenCV|valid|No frames"):
        inspect_video(
            input_path=unreadable_file,
            output_dir=tmp_path / "output",
            sample_interval_seconds=1,
            supported_extensions=(".mp4", ".avi"),
            max_file_size_bytes=1_000_000,
        )


def test_metadata_extraction(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
) -> None:
    video_path = synthetic_video_factory(
        tmp_path / "match.avi",
        frame_count=30,
        fps=10.0,
        width=64,
        height=48,
    )

    result = inspect_video(
        input_path=video_path,
        output_dir=tmp_path / "output",
        sample_interval_seconds=1,
        supported_extensions=(".avi",),
        max_file_size_bytes=1_000_000,
        analysis_id="metadata-test",
    )

    assert result.report.filename == "match.avi"
    assert result.report.file_size_bytes == video_path.stat().st_size
    assert result.report.width == 64
    assert result.report.height == 48
    assert result.report.fps == pytest.approx(10.0)
    assert result.report.frame_count == 30
    assert result.report.duration_seconds == pytest.approx(3.0)
    assert result.report.codec is not None


def test_frame_sampling(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
) -> None:
    video_path = synthetic_video_factory(tmp_path / "match.avi", frame_count=30, fps=10.0)

    result = inspect_video(
        input_path=video_path,
        output_dir=tmp_path / "output",
        sample_interval_seconds=1,
        supported_extensions=(".avi",),
        max_file_size_bytes=1_000_000,
        analysis_id="frame-test",
    )

    assert result.report.sampled_frames == 3
    assert len(result.frame_paths) == 3
    assert [path.name for path in result.frame_paths] == [
        "frame_000001.jpg",
        "frame_000011.jpg",
        "frame_000021.jpg",
    ]
    assert all(path.exists() for path in result.frame_paths)


def test_output_directory_generation(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
) -> None:
    video_path = synthetic_video_factory(tmp_path / "match.avi")

    result = inspect_video(
        input_path=video_path,
        output_dir=tmp_path / "output",
        sample_interval_seconds=2,
        supported_extensions=(".avi",),
        max_file_size_bytes=1_000_000,
        analysis_id="output-test",
    )

    assert result.analysis_dir == tmp_path / "output" / "output-test"
    assert result.frames_dir == result.analysis_dir / "frames"
    assert result.analysis_dir.is_dir()
    assert result.frames_dir.is_dir()


def test_json_report_generation(
    tmp_path: Path,
    synthetic_video_factory: Callable[..., Path],
) -> None:
    video_path = synthetic_video_factory(tmp_path / "match.avi", frame_count=12, fps=6.0)

    result = inspect_video(
        input_path=video_path,
        output_dir=tmp_path / "output",
        sample_interval_seconds=1,
        supported_extensions=(".avi",),
        max_file_size_bytes=1_000_000,
        analysis_id="json-test",
    )

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert result.metadata_path == tmp_path / "output" / "json-test" / "metadata.json"
    assert metadata["analysis_id"] == "json-test"
    assert metadata["filename"] == "match.avi"
    assert metadata["sample_interval_seconds"] == 1
    assert metadata["sampled_frames"] == 2
    assert metadata["created_at"]
