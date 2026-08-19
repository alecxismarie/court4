from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from app.schemas.ball_feasibility import BallFeasibilityManifest, ManualBallFrameLabel


class FeasibilityDatasetError(ValueError):
    pass


@dataclass(frozen=True)
class FeasibilityDatasetSummary:
    dataset_id: str
    clip_count: int
    labeled_frame_count: int


def validate_feasibility_dataset(manifest_path: Path) -> FeasibilityDatasetSummary:
    """Validate consent evidence, checksums, and manual labels without running inference."""
    resolved_manifest = manifest_path.expanduser().resolve()
    try:
        manifest = BallFeasibilityManifest.model_validate_json(
            resolved_manifest.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise FeasibilityDatasetError("Feasibility manifest is missing or invalid.") from exc
    dataset_root = resolved_manifest.parent
    label_count = 0
    for clip in manifest.clips:
        video_path = _inside_dataset(dataset_root, clip.video_path)
        labels_path = _inside_dataset(dataset_root, clip.labels_path)
        if not video_path.is_file() or _file_sha256(video_path) != clip.video_sha256:
            raise FeasibilityDatasetError(
                f"Clip '{clip.clip_id}' bytes are missing or do not match the manifest."
            )
        label_count += _validate_manual_labels(labels_path, clip.clip_id)
    return FeasibilityDatasetSummary(
        dataset_id=manifest.dataset_id,
        clip_count=len(manifest.clips),
        labeled_frame_count=label_count,
    )


def _validate_manual_labels(path: Path, clip_id: str) -> int:
    if not path.is_file():
        raise FeasibilityDatasetError(f"Manual labels are missing for clip '{clip_id}'.")
    previous_frame = -1
    count = 0
    line_number = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for _line_number, line in enumerate(handle, start=1):
                line_number = _line_number
                if not line.strip():
                    continue
                label = ManualBallFrameLabel.model_validate(json.loads(line))
                if label.frame_index <= previous_frame:
                    raise FeasibilityDatasetError(
                        f"Labels for clip '{clip_id}' are not strictly frame ordered."
                    )
                previous_frame = label.frame_index
                count += 1
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise FeasibilityDatasetError(
            f"Manual labels for clip '{clip_id}' are invalid near line {line_number}."
        ) from exc
    if count == 0:
        raise FeasibilityDatasetError(f"Manual labels are empty for clip '{clip_id}'.")
    return count


def _inside_dataset(root: Path, relative: str) -> Path:
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FeasibilityDatasetError("Dataset path escapes the manifest directory.") from exc
    return resolved


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
