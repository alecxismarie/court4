import hashlib
import json
import math
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from pydantic import ValidationError

from app.schemas.player_candidates import (
    AutomaticMergeEvidence,
    AverageBoundingBox,
    CandidateBuildPerformance,
    CandidatePreview,
    CandidateQuality,
    CandidateReviewStatus,
    CourtSide,
    ManualMergeDecision,
    PlayerCandidate,
    PlayerCandidateCollection,
    RecordingSuitability,
    RecordingSuitabilityStatus,
)
from app.schemas.player_tracking import BoundingBox, PlayerObservation, PlayerTrackingReport
from app.schemas.video import VideoMetadataReport
from app.services.detection.interfaces import ImageArray
from app.services.recording_quality import assess_analysis_readiness, assess_upload_preflight

CANDIDATE_SCHEMA_VERSION = 3
CANDIDATE_FILENAME = "player_candidates.json"
CANDIDATE_PREVIEW_DIR = "player_candidates"


@dataclass(frozen=True)
class AssociationThresholds:
    """Centralized, explainable Phase 1.3B fragment-association thresholds."""

    max_temporal_gap_seconds: float = 15.0
    short_gap_seconds: float = 0.75
    max_endpoint_distance_feet: float = 14.0
    max_required_speed_feet_per_second: float = 18.0
    max_bounding_box_area_ratio: float = 1.75
    min_appearance_similarity: float = 0.70
    min_reentry_appearance_similarity: float = 0.96
    min_reentry_fragment_duration_seconds: float = 0.5
    substantial_overlap_seconds: float = 0.0
    net_side_uncertainty_feet: float = 2.5
    strong_min_duration_seconds: float = 5.0
    usable_min_duration_seconds: float = 1.0
    strong_min_in_court_ratio: float = 0.65
    usable_min_in_court_ratio: float = 0.30
    strong_min_observations: int = 15
    usable_min_observations: int = 3
    small_subject_area_ratio: float = 0.002
    strong_min_court_position_span_feet: float = 4.0
    selectable_min_in_court_ratio: float = 0.65
    selectable_min_court_movement_rate_feet_per_second: float = 0.5
    selectable_max_fragment_count: int = 3
    max_selectable_candidates: int = 4
    manual_max_temporal_gap_seconds: float = 20.0
    manual_max_required_speed_feet_per_second: float = 25.0
    duplicate_frame_overlap_ratio: float = 0.10


THRESHOLDS = AssociationThresholds()


class CandidateError(Exception):
    """Base class for expected candidate generation and review errors."""


class CandidateNotFoundError(CandidateError):
    """Raised when a requested candidate does not exist."""


class CandidateImpossibleMergeError(CandidateError):
    """Raised when two candidates cannot safely represent one person."""


class CandidatePersistenceError(CandidateError):
    """Raised when candidate state cannot be read or persisted."""


@dataclass(frozen=True)
class _Fragment:
    track_id: int
    observations: tuple[PlayerObservation, ...]
    first_timestamp: float
    last_timestamp: float
    first_position: tuple[float, float]
    last_position: tuple[float, float]
    average_area: float
    court_side: CourtSide
    appearance_descriptor: tuple[float, ...] | None = None


@dataclass(frozen=True)
class _CandidateGroup:
    track_ids: tuple[int, ...]
    evidence: tuple[AutomaticMergeEvidence, ...]


def build_player_candidates(
    *,
    analysis_id: str,
    tracking_report: PlayerTrackingReport,
    observations_path: Path,
    source_video_path: Path,
    metadata_path: Path,
    tracking_dir: Path,
    preserve_review: bool = True,
) -> PlayerCandidateCollection:
    started = time.monotonic()
    previous = _load_optional_collection(tracking_dir / CANDIDATE_FILENAME)
    observations = _load_observations(observations_path)
    metadata = _load_metadata(metadata_path)
    fragments = _build_fragments(observations)
    fragments = _attach_appearance_descriptors(fragments, source_video_path)
    groups = associate_fragments(fragments)
    build_seconds = time.monotonic() - started

    preview_started = time.monotonic()
    candidates = [
        _build_candidate(
            analysis_id=analysis_id,
            group=group,
            fragments=fragments,
            metadata=metadata,
            source_video_path=source_video_path,
            tracking_dir=tracking_dir,
        )
        for group in groups
    ]
    preview_seconds = time.monotonic() - preview_started
    manual_decisions: list[ManualMergeDecision] = []
    if preserve_review and previous is not None:
        candidates = _preserve_rejections(candidates, previous)
        manual_decisions = list(previous.manual_merge_decisions)
        for decision in manual_decisions:
            if decision.active:
                candidates = _apply_persisted_merge(
                    candidates,
                    decision=decision,
                    analysis_id=analysis_id,
                    fragments=fragments,
                    metadata=metadata,
                    source_video_path=source_video_path,
                    tracking_dir=tracking_dir,
                )

    candidates.sort(key=_candidate_rank_key)
    selected_candidate_id = _preserved_selection(candidates, previous if preserve_review else None)
    if selected_candidate_id is None and previous is None:
        legacy_track_id = tracking_report.selected_player_track_id
        legacy_match = next(
            (
                candidate
                for candidate in candidates
                if legacy_track_id is not None and legacy_track_id in candidate.source_raw_track_ids
            ),
            None,
        )
        selected_candidate_id = legacy_match.candidate_id if legacy_match is not None else None
    candidates = _apply_selection_policy(
        candidates,
        selected_candidate_id=selected_candidate_id,
    )
    if not any(
        candidate.candidate_id == selected_candidate_id and candidate.selection_eligible
        for candidate in candidates
    ):
        selected_candidate_id = None
    candidates = [
        candidate.model_copy(
            update={
                "review_status": (
                    CandidateReviewStatus.selected
                    if candidate.candidate_id == selected_candidate_id
                    else candidate.review_status
                )
            }
        )
        for candidate in candidates
    ]
    active = [
        candidate
        for candidate in candidates
        if candidate.selection_eligible
        and candidate.review_status != CandidateReviewStatus.rejected
    ]
    excluded = [candidate for candidate in candidates if candidate not in active]
    now = datetime.now(tz=UTC)
    suitability = assess_recording_suitability(
        metadata=metadata,
        detected_people=len(fragments),
        candidates=active,
    )
    readiness = assess_analysis_readiness(
        upload_preflight=metadata.upload_preflight or assess_upload_preflight(metadata),
        calibration_completed=True,
        court_detection_status=None,
        court_detection_confidence=None,
        detected_people=len(fragments),
        candidates=active,
        selected_candidate_id=selected_candidate_id,
    )
    collection = PlayerCandidateCollection(
        schema_version=CANDIDATE_SCHEMA_VERSION,
        analysis_id=analysis_id,
        candidates=active,
        excluded_candidates=excluded,
        selected_candidate_id=selected_candidate_id,
        manual_merge_decisions=manual_decisions,
        recording_suitability=suitability,
        analysis_readiness=readiness,
        performance=CandidateBuildPerformance(
            candidate_build_seconds=build_seconds,
            preview_generation_seconds=preview_seconds,
        ),
        generated_at=previous.generated_at if previous is not None else now,
        updated_at=now,
    )
    _write_collection(collection, tracking_dir / CANDIDATE_FILENAME)
    if (
        tracking_report.selected_player_candidate_id is not None
        and selected_candidate_id is None
        and (tracking_dir / "tracking.json").is_file()
    ):
        _clear_tracking_selection(tracking_dir / "tracking.json")
    return collection


def associate_fragments(fragments: dict[int, _Fragment]) -> list[_CandidateGroup]:
    """Associate fragments with deterministic constrained agglomeration."""
    groups: dict[int, set[int]] = {track_id: {track_id} for track_id in fragments}
    evidence_by_root: dict[int, list[AutomaticMergeEvidence]] = {
        track_id: [] for track_id in fragments
    }
    root_by_track = {track_id: track_id for track_id in fragments}
    edges: list[tuple[tuple[float, float, float, int, int], AutomaticMergeEvidence]] = []

    ordered = sorted(fragments.values(), key=lambda item: (item.first_timestamp, item.track_id))
    for first in ordered:
        for second in ordered:
            if first.track_id == second.track_id or second.first_timestamp < first.first_timestamp:
                continue
            evidence = _association_evidence(first, second)
            if evidence is None:
                continue
            score = (
                evidence.temporal_gap_seconds,
                evidence.endpoint_distance_feet,
                evidence.bounding_box_area_ratio,
                evidence.from_track_id,
                evidence.to_track_id,
            )
            edges.append((score, evidence))

    for _score, evidence in sorted(edges, key=lambda item: item[0]):
        first_root = root_by_track[evidence.from_track_id]
        second_root = root_by_track[evidence.to_track_id]
        if first_root == second_root:
            continue
        first_ids = groups[first_root]
        second_ids = groups[second_root]
        if not _groups_compatible(first_ids, second_ids, fragments):
            continue
        kept_root = min(first_root, second_root)
        removed_root = max(first_root, second_root)
        merged_ids = groups[first_root] | groups[second_root]
        merged_evidence = [
            *evidence_by_root[first_root],
            *evidence_by_root[second_root],
            evidence,
        ]
        groups[kept_root] = merged_ids
        evidence_by_root[kept_root] = merged_evidence
        if removed_root != kept_root:
            groups.pop(removed_root, None)
            evidence_by_root.pop(removed_root, None)
        for track_id in merged_ids:
            root_by_track[track_id] = kept_root

    return [
        _CandidateGroup(
            track_ids=tuple(sorted(track_ids)),
            evidence=tuple(
                sorted(
                    evidence_by_root[root],
                    key=lambda item: (item.from_track_id, item.to_track_id),
                )
            ),
        )
        for root, track_ids in sorted(groups.items(), key=lambda item: min(item[1]))
    ]


def load_player_candidates(candidate_path: Path) -> PlayerCandidateCollection:
    try:
        return PlayerCandidateCollection.model_validate_json(
            candidate_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        raise CandidatePersistenceError("Player candidate state could not be loaded.") from exc


def select_player_candidate(
    *,
    candidate_path: Path,
    candidate_id: str,
    tracking_report_path: Path,
) -> PlayerCandidateCollection:
    collection = load_player_candidates(candidate_path)
    candidate = _find_active_candidate(collection, candidate_id)
    if not candidate.selection_eligible or candidate.quality == CandidateQuality.rejected:
        raise CandidateNotFoundError("Ineligible candidate cannot be selected.")
    active = [
        item.model_copy(
            update={
                "review_status": (
                    CandidateReviewStatus.selected
                    if item.candidate_id == candidate_id
                    else CandidateReviewStatus.pending
                )
            }
        )
        for item in collection.candidates
    ]
    updated = collection.model_copy(
        update={
            "candidates": active,
            "selected_candidate_id": candidate_id,
            "updated_at": datetime.now(tz=UTC),
        }
    )
    _write_collection(updated, candidate_path)
    _write_candidate_selection_to_tracking(candidate, tracking_report_path)
    return updated


def reject_player_candidate(
    *,
    candidate_path: Path,
    candidate_id: str,
    reason: str,
    tracking_report_path: Path,
) -> PlayerCandidateCollection:
    collection = load_player_candidates(candidate_path)
    candidate = _find_active_candidate(collection, candidate_id)
    rejected = candidate.model_copy(
        update={
            "review_status": CandidateReviewStatus.rejected,
            "rejection_reason": _structured_rejection_reason(reason),
        }
    )
    selected_id = (
        None
        if collection.selected_candidate_id == candidate_id
        else collection.selected_candidate_id
    )
    updated = collection.model_copy(
        update={
            "candidates": [
                item for item in collection.candidates if item.candidate_id != candidate_id
            ],
            "excluded_candidates": [*collection.excluded_candidates, rejected],
            "selected_candidate_id": selected_id,
            "updated_at": datetime.now(tz=UTC),
        }
    )
    _write_collection(updated, candidate_path)
    if selected_id is None and collection.selected_candidate_id == candidate_id:
        _clear_tracking_selection(tracking_report_path)
    return updated


def restore_player_candidate(
    *,
    candidate_path: Path,
    candidate_id: str,
) -> PlayerCandidateCollection:
    collection = load_player_candidates(candidate_path)
    candidate = next(
        (item for item in collection.excluded_candidates if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None:
        raise CandidateNotFoundError("Excluded player candidate was not found.")
    if not candidate.selection_eligible:
        raise CandidateNotFoundError("Automatically excluded candidate cannot be restored.")
    restored = candidate.model_copy(
        update={
            "review_status": CandidateReviewStatus.pending,
            "rejection_reason": None,
        }
    )
    updated = collection.model_copy(
        update={
            "candidates": sorted([*collection.candidates, restored], key=_candidate_rank_key),
            "excluded_candidates": [
                item for item in collection.excluded_candidates if item.candidate_id != candidate_id
            ],
            "updated_at": datetime.now(tz=UTC),
        }
    )
    _write_collection(updated, candidate_path)
    return updated


def merge_player_candidates(
    *,
    candidate_path: Path,
    candidate_ids: Sequence[str],
    tracking_report_path: Path,
    observations_path: Path,
    source_video_path: Path,
    metadata_path: Path,
) -> PlayerCandidateCollection:
    if len(candidate_ids) != 2 or len(set(candidate_ids)) != 2:
        raise CandidateImpossibleMergeError("Exactly two distinct candidates are required.")
    collection = load_player_candidates(candidate_path)
    first = _find_active_candidate(collection, candidate_ids[0])
    second = _find_active_candidate(collection, candidate_ids[1])
    observations = _load_observations(observations_path)
    _validate_manual_merge(first, second, observations)

    raw_ids = tuple(sorted({*first.source_raw_track_ids, *second.source_raw_track_ids}))
    merge_id = _stable_id("merge", collection.analysis_id, raw_ids)
    merged_id = _candidate_id(collection.analysis_id, raw_ids)
    now = datetime.now(tz=UTC)
    decision = ManualMergeDecision(
        merge_id=merge_id,
        source_candidate_ids=sorted(candidate_ids),
        source_raw_track_ids=list(raw_ids),
        merged_candidate_id=merged_id,
        active=True,
        created_at=now,
    )
    fragments = _build_fragments(observations)
    metadata = _load_metadata(metadata_path)
    merged = _build_candidate(
        analysis_id=collection.analysis_id,
        group=_CandidateGroup(track_ids=raw_ids, evidence=()),
        fragments=fragments,
        metadata=metadata,
        source_video_path=source_video_path,
        tracking_dir=candidate_path.parent,
        manual_merge_id=merge_id,
    )
    was_selected = collection.selected_candidate_id in set(candidate_ids)
    if was_selected:
        merged = merged.model_copy(update={"review_status": CandidateReviewStatus.selected})
    remaining = [
        candidate
        for candidate in collection.candidates
        if candidate.candidate_id not in set(candidate_ids)
    ]
    updated = collection.model_copy(
        update={
            "candidates": sorted([*remaining, merged], key=_candidate_rank_key),
            "selected_candidate_id": (
                merged.candidate_id if was_selected else collection.selected_candidate_id
            ),
            "manual_merge_decisions": [*collection.manual_merge_decisions, decision],
            "updated_at": now,
        }
    )
    _write_collection(updated, candidate_path)
    if was_selected:
        _write_candidate_selection_to_tracking(merged, tracking_report_path)
    return updated


def unmerge_player_candidates(
    *,
    candidate_path: Path,
    candidate_id: str,
    tracking_report_path: Path,
    observations_path: Path,
    source_video_path: Path,
    metadata_path: Path,
) -> PlayerCandidateCollection:
    collection = load_player_candidates(candidate_path)
    decision = next(
        (
            item
            for item in reversed(collection.manual_merge_decisions)
            if item.active and item.merged_candidate_id == candidate_id
        ),
        None,
    )
    if decision is None:
        raise CandidateNotFoundError("Active manual merge not found.")

    now = datetime.now(tz=UTC)
    decisions = [
        item.model_copy(update={"active": False, "undone_at": now})
        if item.merge_id == decision.merge_id
        else item
        for item in collection.manual_merge_decisions
    ]
    interim = collection.model_copy(
        update={
            "manual_merge_decisions": decisions,
            "selected_candidate_id": None
            if collection.selected_candidate_id == candidate_id
            else collection.selected_candidate_id,
            "updated_at": now,
        }
    )
    _write_collection(interim, candidate_path)
    regenerated = build_player_candidates(
        analysis_id=collection.analysis_id,
        tracking_report=_load_tracking_report(tracking_report_path),
        observations_path=observations_path,
        source_video_path=source_video_path,
        metadata_path=metadata_path,
        tracking_dir=candidate_path.parent,
        preserve_review=True,
    )
    if collection.selected_candidate_id == candidate_id:
        _clear_tracking_selection(tracking_report_path)
    return regenerated


def assess_recording_suitability(
    *,
    metadata: VideoMetadataReport,
    detected_people: int,
    candidates: Sequence[PlayerCandidate],
) -> RecordingSuitability:
    reasons: list[str] = []
    guidance: list[str] = []
    orientation = "vertical" if metadata.height > metadata.width else "landscape"
    status = RecordingSuitabilityStatus.suitable

    if orientation == "vertical":
        status = RecordingSuitabilityStatus.limited
        reasons.append("vertical_video_limitation")
        guidance.append("Use landscape orientation when possible.")
    if min(metadata.width, metadata.height) < 480:
        status = RecordingSuitabilityStatus.limited
        reasons.append("limited_resolution")
        guidance.append("Record at a higher resolution so players occupy more pixels.")
    if metadata.duration_seconds < 3:
        status = RecordingSuitabilityStatus.unsuitable
        reasons.append("recording_too_short")
        guidance.append("Record a longer continuous section of play.")
    if detected_people == 0:
        status = RecordingSuitabilityStatus.unsuitable
        reasons.append("no_person_detections")
        guidance.append("Keep players large enough to detect and the full court visible.")
    elif not candidates:
        status = RecordingSuitabilityStatus.unsuitable
        reasons.append("detections_without_candidates")
    elif all(candidate.quality == CandidateQuality.uncertain for candidate in candidates):
        if status != RecordingSuitabilityStatus.unsuitable:
            status = RecordingSuitabilityStatus.limited
        reasons.append("only_uncertain_candidates")

    if status != RecordingSuitabilityStatus.suitable:
        guidance.extend(
            [
                "Keep the full court visible.",
                "Place the camera behind the baseline and keep it stable.",
            ]
        )
    return RecordingSuitability(
        status=status,
        reasons=list(dict.fromkeys(reasons)),
        guidance=list(dict.fromkeys(guidance)),
        orientation=orientation,
        detected_people=detected_people,
        usable_candidate_count=sum(
            candidate.quality in {CandidateQuality.strong, CandidateQuality.usable}
            for candidate in candidates
        ),
    )


def _build_fragments(observations: Sequence[PlayerObservation]) -> dict[int, _Fragment]:
    by_track: dict[int, list[PlayerObservation]] = {}
    for observation in observations:
        by_track.setdefault(observation.track_id, []).append(observation)
    fragments: dict[int, _Fragment] = {}
    for track_id, items in sorted(by_track.items()):
        items.sort(key=lambda item: (item.timestamp_seconds, item.frame_index))
        in_court = [item for item in items if item.inside_court]
        positional = in_court or items
        fragments[track_id] = _Fragment(
            track_id=track_id,
            observations=tuple(items),
            first_timestamp=items[0].timestamp_seconds,
            last_timestamp=items[-1].timestamp_seconds,
            first_position=positional[0].court_position,
            last_position=positional[-1].court_position,
            average_area=sum(item.bounding_box.area for item in items) / len(items),
            court_side=_court_side(positional),
        )
    return fragments


def _association_evidence(
    first: _Fragment,
    second: _Fragment,
) -> AutomaticMergeEvidence | None:
    if second.first_timestamp <= first.last_timestamp:
        return None
    gap = second.first_timestamp - first.last_timestamp
    if gap > THRESHOLDS.max_temporal_gap_seconds:
        return None
    if _opposite_sides(first.court_side, second.court_side):
        return None
    distance = _distance(first.last_position, second.first_position)
    if distance > THRESHOLDS.max_endpoint_distance_feet:
        return None
    effective_gap = max(gap, _median_observation_interval(first, second))
    required_speed = distance / effective_gap if effective_gap > 0 else math.inf
    if required_speed > THRESHOLDS.max_required_speed_feet_per_second:
        return None
    area_ratio = _ratio(first.average_area, second.average_area)
    if area_ratio > THRESHOLDS.max_bounding_box_area_ratio:
        return None
    appearance_similarity = _appearance_similarity(
        first.appearance_descriptor,
        second.appearance_descriptor,
    )
    if (
        appearance_similarity is not None
        and appearance_similarity < THRESHOLDS.min_appearance_similarity
    ):
        return None
    if gap > THRESHOLDS.short_gap_seconds and (
        appearance_similarity is None
        or appearance_similarity < THRESHOLDS.min_reentry_appearance_similarity
        or first.last_timestamp - first.first_timestamp
        < THRESHOLDS.min_reentry_fragment_duration_seconds
        or second.last_timestamp - second.first_timestamp
        < THRESHOLDS.min_reentry_fragment_duration_seconds
    ):
        return None
    reasons = [
        "non_overlapping_fragments",
        "short_temporal_gap",
        "plausible_endpoint_distance",
        "plausible_movement_speed",
        "similar_bounding_box_size",
        "court_side_consistent",
    ]
    if appearance_similarity is not None:
        reasons.append("appearance_histogram_consistent")
    if gap > THRESHOLDS.short_gap_seconds:
        reasons.append("appearance_supported_reentry")
    return AutomaticMergeEvidence(
        from_track_id=first.track_id,
        to_track_id=second.track_id,
        temporal_gap_seconds=gap,
        endpoint_distance_feet=distance,
        required_speed_feet_per_second=required_speed,
        bounding_box_area_ratio=area_ratio,
        appearance_similarity=appearance_similarity,
        court_side_consistent=not _opposite_sides(first.court_side, second.court_side),
        reasons=reasons,
    )


def _groups_compatible(
    first_ids: set[int],
    second_ids: set[int],
    fragments: dict[int, _Fragment],
) -> bool:
    for first_id in first_ids:
        for second_id in second_ids:
            first = fragments[first_id]
            second = fragments[second_id]
            overlap = min(first.last_timestamp, second.last_timestamp) - max(
                first.first_timestamp, second.first_timestamp
            )
            if overlap > THRESHOLDS.substantial_overlap_seconds:
                return False
            if _opposite_sides(first.court_side, second.court_side):
                return False
    return True


def _build_candidate(
    *,
    analysis_id: str,
    group: _CandidateGroup,
    fragments: dict[int, _Fragment],
    metadata: VideoMetadataReport,
    source_video_path: Path,
    tracking_dir: Path,
    manual_merge_id: str | None = None,
) -> PlayerCandidate:
    observations = sorted(
        (
            observation
            for track_id in group.track_ids
            for observation in fragments[track_id].observations
        ),
        key=lambda item: (item.timestamp_seconds, item.frame_index, item.track_id),
    )
    unique_frames = {(item.frame_index, item.track_id) for item in observations}
    in_court_count = sum(item.inside_court for item in observations)
    in_court_ratio = in_court_count / len(observations) if observations else 0.0
    average_width = sum(item.bounding_box.width for item in observations) / len(observations)
    average_height = sum(item.bounding_box.height for item in observations) / len(observations)
    frame_area = metadata.width * metadata.height
    average_area_ratio = (
        sum(item.bounding_box.area for item in observations) / len(observations) / frame_area
        if frame_area > 0
        else 0.0
    )
    observed_duration = sum(
        max(0.0, fragments[track_id].last_timestamp - fragments[track_id].first_timestamp)
        for track_id in group.track_ids
    )
    court_distance = _candidate_court_distance(group.track_ids, fragments)
    movement_rate = court_distance / observed_duration if observed_duration > 0 else 0.0
    court_position_span = _court_position_span(observations)
    sides = {fragments[track_id].court_side for track_id in group.track_ids}
    court_side = _combined_side(sides)
    candidate_id = _candidate_id(analysis_id, group.track_ids)
    preview_warranted = (
        observed_duration >= THRESHOLDS.usable_min_duration_seconds
        and len(unique_frames) >= THRESHOLDS.usable_min_observations
    )
    previews = (
        _write_candidate_previews(
            candidate_id=candidate_id,
            observations=observations,
            source_video_path=source_video_path,
            tracking_dir=tracking_dir,
        )
        if preview_warranted
        else []
    )
    representative = previews[len(previews) // 2] if previews else None
    quality, reasons, warnings = _classify_quality(
        duration=observed_duration,
        observation_count=len(unique_frames),
        in_court_ratio=in_court_ratio,
        fragment_count=len(group.track_ids),
        has_preview=bool(previews),
        area_ratio=average_area_ratio,
        court_side=court_side,
        vertical=metadata.height > metadata.width,
        court_position_span=court_position_span,
    )
    selection_exclusion_reasons = _selection_exclusion_reasons(
        quality=quality,
        in_court_ratio=in_court_ratio,
        movement_rate=movement_rate,
        fragment_count=len(group.track_ids),
    )
    return PlayerCandidate(
        candidate_id=candidate_id,
        source_raw_track_ids=list(group.track_ids),
        first_observed_timestamp=observations[0].timestamp_seconds,
        last_observed_timestamp=observations[-1].timestamp_seconds,
        total_observed_duration=observed_duration,
        total_observed_frames=len(unique_frames),
        court_distance_feet=court_distance,
        court_movement_rate_feet_per_second=movement_rate,
        in_court_observation_ratio=in_court_ratio,
        selection_eligible=not selection_exclusion_reasons,
        selection_exclusion_reasons=selection_exclusion_reasons,
        representative_frame=representative.frame_index if representative else None,
        representative_crop_artifact=representative.crop_artifact if representative else None,
        representative_full_frame_artifact=(
            representative.full_frame_artifact if representative else None
        ),
        preview_frames=previews,
        average_bounding_box=AverageBoundingBox(
            width_pixels=average_width,
            height_pixels=average_height,
            area_ratio=min(1.0, average_area_ratio),
        ),
        court_side_estimate=court_side,
        quality=quality,
        quality_reasons=reasons,
        warnings=warnings,
        automatic_merge_evidence=list(group.evidence),
        manual_merge_id=manual_merge_id,
    )


def _attach_appearance_descriptors(
    fragments: dict[int, _Fragment],
    source_video_path: Path,
) -> dict[int, _Fragment]:
    if not fragments or not source_video_path.is_file():
        return fragments
    representatives = {
        track_id: max(
            fragment.observations,
            key=lambda item: (
                item.confidence * math.sqrt(item.bounding_box.area),
                -item.frame_index,
            ),
        )
        for track_id, fragment in fragments.items()
    }
    by_frame: dict[int, list[tuple[int, PlayerObservation]]] = {}
    for track_id, observation in representatives.items():
        by_frame.setdefault(observation.frame_index, []).append((track_id, observation))
    descriptors: dict[int, tuple[float, ...]] = {}
    capture = cv2.VideoCapture(str(source_video_path))
    try:
        if not capture.isOpened():
            return fragments
        last_target = max(by_frame)
        frame_index = 0
        while frame_index <= last_target:
            success, frame = capture.read()
            if not success:
                break
            for track_id, observation in by_frame.get(frame_index, []):
                crop = _crop(cast(ImageArray, frame), observation.bounding_box)
                descriptor = _appearance_descriptor(crop)
                if descriptor is not None:
                    descriptors[track_id] = descriptor
            frame_index += 1
    finally:
        capture.release()
    return {
        track_id: _Fragment(
            track_id=fragment.track_id,
            observations=fragment.observations,
            first_timestamp=fragment.first_timestamp,
            last_timestamp=fragment.last_timestamp,
            first_position=fragment.first_position,
            last_position=fragment.last_position,
            average_area=fragment.average_area,
            court_side=fragment.court_side,
            appearance_descriptor=descriptors.get(track_id),
        )
        for track_id, fragment in fragments.items()
    }


def _appearance_descriptor(crop: ImageArray) -> tuple[float, ...] | None:
    if crop.size == 0:
        return None
    resized = cv2.resize(crop, (32, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    flattened = histogram.flatten().astype(float)
    norm = float(np.linalg.norm(flattened))
    if norm <= 0:
        return None
    return tuple(float(value / norm) for value in flattened)


def _appearance_similarity(
    first: tuple[float, ...] | None,
    second: tuple[float, ...] | None,
) -> float | None:
    if first is None or second is None or len(first) != len(second):
        return None
    similarity = sum(a * b for a, b in zip(first, second, strict=True))
    return max(0.0, min(1.0, similarity))


def _write_candidate_previews(
    *,
    candidate_id: str,
    observations: Sequence[PlayerObservation],
    source_video_path: Path,
    tracking_dir: Path,
) -> list[CandidatePreview]:
    if not observations or not source_video_path.is_file():
        return []
    indices = sorted({0, len(observations) // 2, len(observations) - 1})
    selected = [observations[index] for index in indices]
    output_dir = tracking_dir / CANDIDATE_PREVIEW_DIR / candidate_id
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(source_video_path))
    previews: list[CandidatePreview] = []
    try:
        if not capture.isOpened():
            return []
        for position, observation in enumerate(selected):
            capture.set(cv2.CAP_PROP_POS_FRAMES, observation.frame_index)
            success, frame = capture.read()
            if not success:
                continue
            image = cast(ImageArray, frame)
            full_path = output_dir / f"frame_{position + 1}.jpg"
            crop_path = output_dir / f"crop_{position + 1}.jpg"
            annotated = image.copy()
            _draw_candidate_box(annotated, observation.bounding_box)
            crop = _crop(image, observation.bounding_box)
            full_artifact = None
            crop_artifact = None
            if cv2.imwrite(str(full_path), annotated):
                full_artifact = _relative_candidate_artifact(candidate_id, full_path.name)
            if crop.size and cv2.imwrite(str(crop_path), crop):
                crop_artifact = _relative_candidate_artifact(candidate_id, crop_path.name)
            previews.append(
                CandidatePreview(
                    timestamp_seconds=observation.timestamp_seconds,
                    frame_index=observation.frame_index,
                    full_frame_artifact=full_artifact,
                    crop_artifact=crop_artifact,
                )
            )
    finally:
        capture.release()
    return previews


def _classify_quality(
    *,
    duration: float,
    observation_count: int,
    in_court_ratio: float,
    fragment_count: int,
    has_preview: bool,
    area_ratio: float,
    court_side: CourtSide,
    vertical: bool,
    court_position_span: float,
) -> tuple[CandidateQuality, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    if duration < THRESHOLDS.usable_min_duration_seconds:
        reasons.append("short_track_duration")
    if in_court_ratio < THRESHOLDS.usable_min_in_court_ratio:
        reasons.append("low_in_court_ratio")
    if fragment_count > 3:
        reasons.append("high_fragment_count")
    if not has_preview:
        reasons.append("candidate_preview_generation_failure")
    if area_ratio < THRESHOLDS.small_subject_area_ratio:
        reasons.append("small_subject")
    if court_side == CourtSide.mixed:
        reasons.append("court_side_inconsistent")
    if vertical:
        reasons.append("vertical_video_limitation")
    if court_position_span < THRESHOLDS.strong_min_court_position_span_feet:
        reasons.append("limited_court_movement")
    warnings.extend(reasons)

    if (
        duration >= THRESHOLDS.strong_min_duration_seconds
        and observation_count >= THRESHOLDS.strong_min_observations
        and in_court_ratio >= THRESHOLDS.strong_min_in_court_ratio
        and has_preview
        and fragment_count <= 3
        and court_side != CourtSide.mixed
        and court_position_span >= THRESHOLDS.strong_min_court_position_span_feet
    ):
        quality = CandidateQuality.strong
    elif (
        duration >= THRESHOLDS.usable_min_duration_seconds
        and observation_count >= THRESHOLDS.usable_min_observations
        and in_court_ratio >= THRESHOLDS.usable_min_in_court_ratio
    ):
        quality = CandidateQuality.usable
    else:
        quality = CandidateQuality.uncertain
    return quality, reasons, warnings


def _selection_exclusion_reasons(
    *,
    quality: CandidateQuality,
    in_court_ratio: float,
    movement_rate: float,
    fragment_count: int,
) -> list[str]:
    reasons: list[str] = []
    if quality not in {CandidateQuality.strong, CandidateQuality.usable}:
        reasons.append("uncertain_player_candidate")
    if in_court_ratio < THRESHOLDS.selectable_min_in_court_ratio:
        reasons.append("mostly_outside_detected_court")
    if movement_rate < THRESHOLDS.selectable_min_court_movement_rate_feet_per_second:
        reasons.append("limited_court_movement")
    if fragment_count > THRESHOLDS.selectable_max_fragment_count:
        reasons.append("excessive_track_fragmentation")
    return reasons


def _apply_selection_policy(
    candidates: Sequence[PlayerCandidate],
    *,
    selected_candidate_id: str | None,
) -> list[PlayerCandidate]:
    eligible = [candidate for candidate in candidates if candidate.selection_eligible]
    if len(eligible) <= THRESHOLDS.max_selectable_candidates:
        return list(candidates)

    kept_ids = {
        candidate.candidate_id
        for candidate in sorted(eligible, key=_candidate_rank_key)[
            : THRESHOLDS.max_selectable_candidates
        ]
    }
    selected = next(
        (candidate for candidate in eligible if candidate.candidate_id == selected_candidate_id),
        None,
    )
    if selected is not None and selected.candidate_id not in kept_ids:
        lowest_ranked_kept = max(
            (candidate for candidate in eligible if candidate.candidate_id in kept_ids),
            key=_candidate_rank_key,
        )
        kept_ids.remove(lowest_ranked_kept.candidate_id)
        kept_ids.add(selected.candidate_id)

    return [
        candidate
        if not candidate.selection_eligible or candidate.candidate_id in kept_ids
        else candidate.model_copy(
            update={
                "selection_eligible": False,
                "selection_exclusion_reasons": [
                    *candidate.selection_exclusion_reasons,
                    "outside_top_four_court_players",
                ],
            }
        )
        for candidate in candidates
    ]


def _candidate_court_distance(
    track_ids: Sequence[int],
    fragments: dict[int, _Fragment],
) -> float:
    """Sum observed motion without inventing travel across fragment gaps."""
    distance = 0.0
    for track_id in track_ids:
        observations = fragments[track_id].observations
        for previous, current in zip(observations, observations[1:], strict=False):
            gap = current.timestamp_seconds - previous.timestamp_seconds
            if gap <= 0 or gap > 1.0 or not previous.inside_court or not current.inside_court:
                continue
            step = math.dist(previous.court_position, current.court_position)
            if step <= 15.0:
                distance += step
    return distance


def _court_position_span(observations: Sequence[PlayerObservation]) -> float:
    in_court = [item.court_position for item in observations if item.inside_court]
    if not in_court:
        return 0.0
    x_values = [position[0] for position in in_court]
    y_values = [position[1] for position in in_court]
    return max(max(x_values) - min(x_values), max(y_values) - min(y_values))


def _validate_manual_merge(
    first: PlayerCandidate,
    second: PlayerCandidate,
    observations: Sequence[PlayerObservation],
) -> None:
    first_obs = [o for o in observations if o.track_id in set(first.source_raw_track_ids)]
    second_obs = [o for o in observations if o.track_id in set(second.source_raw_track_ids)]
    first_frames = {item.frame_index for item in first_obs}
    second_frames = {item.frame_index for item in second_obs}
    overlap = first_frames & second_frames
    denominator = max(1, min(len(first_frames), len(second_frames)))
    if len(overlap) >= 3 or len(overlap) / denominator > THRESHOLDS.duplicate_frame_overlap_ratio:
        raise CandidateImpossibleMergeError(
            "These candidates appear at the same time and cannot be merged safely."
        )
    if _opposite_sides(first.court_side_estimate, second.court_side_estimate):
        raise CandidateImpossibleMergeError("These candidates remain on incompatible court sides.")
    earlier, later = (
        (first_obs, second_obs)
        if first.first_observed_timestamp <= second.first_observed_timestamp
        else (second_obs, first_obs)
    )
    if not earlier or not later:
        raise CandidateImpossibleMergeError("Candidate observations are unavailable.")
    gap = later[0].timestamp_seconds - earlier[-1].timestamp_seconds
    if gap < 0:
        raise CandidateImpossibleMergeError(
            "These candidates have overlapping observations and cannot be merged safely."
        )
    if gap > THRESHOLDS.manual_max_temporal_gap_seconds:
        raise CandidateImpossibleMergeError("The gap between these candidates is too long.")
    distance = _distance(earlier[-1].court_position, later[0].court_position)
    effective_gap = max(gap, 1 / 30)
    if distance / effective_gap > THRESHOLDS.manual_max_required_speed_feet_per_second:
        raise CandidateImpossibleMergeError(
            "The movement required between these candidates is not physically plausible."
        )


def _apply_persisted_merge(
    candidates: list[PlayerCandidate],
    *,
    decision: ManualMergeDecision,
    analysis_id: str,
    fragments: dict[int, _Fragment],
    metadata: VideoMetadataReport,
    source_video_path: Path,
    tracking_dir: Path,
) -> list[PlayerCandidate]:
    raw_ids = set(decision.source_raw_track_ids)
    source = [
        candidate
        for candidate in candidates
        if set(candidate.source_raw_track_ids).issubset(raw_ids)
    ]
    covered = {track for candidate in source for track in candidate.source_raw_track_ids}
    if covered != raw_ids:
        return candidates
    merged = _build_candidate(
        analysis_id=analysis_id,
        group=_CandidateGroup(track_ids=tuple(sorted(raw_ids)), evidence=()),
        fragments=fragments,
        metadata=metadata,
        source_video_path=source_video_path,
        tracking_dir=tracking_dir,
        manual_merge_id=decision.merge_id,
    )
    if any(candidate.review_status == CandidateReviewStatus.rejected for candidate in source):
        merged = merged.model_copy(
            update={
                "review_status": CandidateReviewStatus.rejected,
                "rejection_reason": next(
                    (
                        candidate.rejection_reason
                        for candidate in source
                        if candidate.rejection_reason is not None
                    ),
                    "not_a_player",
                ),
            }
        )
    remaining = [candidate for candidate in candidates if candidate not in source]
    return [*remaining, merged]


def _preserve_rejections(
    candidates: list[PlayerCandidate],
    previous: PlayerCandidateCollection,
) -> list[PlayerCandidate]:
    rejected_by_tracks = {
        tuple(candidate.source_raw_track_ids): candidate
        for candidate in previous.excluded_candidates
        if candidate.selection_eligible
        and candidate.review_status == CandidateReviewStatus.rejected
    }
    preserved = []
    for candidate in candidates:
        prior = rejected_by_tracks.get(tuple(candidate.source_raw_track_ids))
        if prior is None:
            preserved.append(candidate)
        else:
            preserved.append(
                candidate.model_copy(
                    update={
                        "review_status": CandidateReviewStatus.rejected,
                        "rejection_reason": prior.rejection_reason,
                    }
                )
            )
    return preserved


def _preserved_selection(
    candidates: Sequence[PlayerCandidate],
    previous: PlayerCandidateCollection | None,
) -> str | None:
    if previous is None or previous.selected_candidate_id is None:
        return None
    if any(candidate.candidate_id == previous.selected_candidate_id for candidate in candidates):
        return previous.selected_candidate_id
    prior = next(
        (
            candidate
            for candidate in [*previous.candidates, *previous.excluded_candidates]
            if candidate.candidate_id == previous.selected_candidate_id
        ),
        None,
    )
    if prior is None:
        return None
    prior_tracks = set(prior.source_raw_track_ids)
    match = next(
        (
            candidate
            for candidate in candidates
            if set(candidate.source_raw_track_ids) == prior_tracks
        ),
        None,
    )
    return match.candidate_id if match is not None else None


def _court_side(observations: Sequence[PlayerObservation]) -> CourtSide:
    in_court = [item.court_position[1] for item in observations if item.inside_court]
    if not in_court:
        return CourtSide.unknown
    ordered = sorted(in_court)
    median_y = ordered[len(ordered) // 2]
    net_y = 22.0
    if abs(median_y - net_y) <= THRESHOLDS.net_side_uncertainty_feet:
        return CourtSide.unknown
    return CourtSide.near if median_y < net_y else CourtSide.far


def _combined_side(sides: set[CourtSide]) -> CourtSide:
    known = sides - {CourtSide.unknown}
    if not known:
        return CourtSide.unknown
    if len(known) == 1:
        return next(iter(known))
    return CourtSide.mixed


def _opposite_sides(first: CourtSide, second: CourtSide) -> bool:
    return {first, second} == {CourtSide.near, CourtSide.far}


def _candidate_rank_key(
    candidate: PlayerCandidate,
) -> tuple[int, float, float, float, int, str]:
    quality_rank = {
        CandidateQuality.strong: 0,
        CandidateQuality.usable: 1,
        CandidateQuality.uncertain: 2,
        CandidateQuality.rejected: 3,
    }
    return (
        quality_rank[candidate.quality],
        -candidate.court_distance_feet,
        -candidate.in_court_observation_ratio,
        -candidate.total_observed_duration,
        len(candidate.source_raw_track_ids),
        candidate.candidate_id,
    )


def _candidate_id(analysis_id: str, track_ids: Iterable[int]) -> str:
    return _stable_id("pc", analysis_id, track_ids)


def _stable_id(prefix: str, analysis_id: str, track_ids: Iterable[int]) -> str:
    membership = ",".join(str(track_id) for track_id in sorted(set(track_ids)))
    digest = hashlib.sha256(f"{analysis_id}|{membership}".encode()).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _median_observation_interval(first: _Fragment, second: _Fragment) -> float:
    intervals: list[float] = []
    for fragment in (first, second):
        intervals.extend(
            current.timestamp_seconds - previous.timestamp_seconds
            for previous, current in zip(
                fragment.observations,
                fragment.observations[1:],
                strict=False,
            )
            if current.timestamp_seconds > previous.timestamp_seconds
        )
    if not intervals:
        return 1 / 30
    ordered = sorted(intervals)
    return ordered[len(ordered) // 2]


def _ratio(first: float, second: float) -> float:
    smaller = min(first, second)
    return max(first, second) / smaller if smaller > 0 else math.inf


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _draw_candidate_box(frame: ImageArray, box: BoundingBox) -> None:
    start = (max(0, int(round(box.x1))), max(0, int(round(box.y1))))
    end = (
        min(frame.shape[1] - 1, int(round(box.x2))),
        min(frame.shape[0] - 1, int(round(box.y2))),
    )
    cv2.rectangle(frame, start, end, (44, 203, 112), 3)
    cv2.putText(
        frame,
        "Player candidate",
        (start[0], max(20, start[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (44, 203, 112),
        2,
        cv2.LINE_AA,
    )


def _crop(frame: ImageArray, box: BoundingBox) -> ImageArray:
    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, int(math.floor(box.x1))))
    y1 = max(0, min(height - 1, int(math.floor(box.y1))))
    x2 = max(x1 + 1, min(width, int(math.ceil(box.x2))))
    y2 = max(y1 + 1, min(height, int(math.ceil(box.y2))))
    return cast(ImageArray, frame[y1:y2, x1:x2].copy())


def _relative_candidate_artifact(candidate_id: str, filename: str) -> str:
    return f"tracking/{CANDIDATE_PREVIEW_DIR}/{candidate_id}/{filename}"


def _find_active_candidate(
    collection: PlayerCandidateCollection,
    candidate_id: str,
) -> PlayerCandidate:
    candidate = next(
        (item for item in collection.candidates if item.candidate_id == candidate_id),
        None,
    )
    if candidate is None:
        raise CandidateNotFoundError("Player candidate was not found.")
    return candidate


def _structured_rejection_reason(reason: str) -> str:
    cleaned = reason.strip().lower().replace(" ", "_")
    allowed = {"spectator", "background_person", "duplicate", "not_me", "not_a_player"}
    return cleaned if cleaned in allowed else "not_a_player"


def _load_observations(path: Path) -> list[PlayerObservation]:
    try:
        observations = [
            PlayerObservation.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValidationError) as exc:
        raise CandidatePersistenceError("Raw tracking observations could not be loaded.") from exc
    observations.sort(key=lambda item: (item.timestamp_seconds, item.frame_index, item.track_id))
    return observations


def _load_metadata(path: Path) -> VideoMetadataReport:
    try:
        return VideoMetadataReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise CandidatePersistenceError("Video metadata could not be loaded.") from exc


def _load_tracking_report(path: Path) -> PlayerTrackingReport:
    try:
        return PlayerTrackingReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise CandidatePersistenceError("Tracking report could not be loaded.") from exc


def _load_optional_collection(path: Path) -> PlayerCandidateCollection | None:
    if not path.is_file():
        return None
    return load_player_candidates(path)


def _write_collection(collection: PlayerCandidateCollection, path: Path) -> None:
    temporary = path.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(collection.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        raise CandidatePersistenceError("Player candidate state could not be saved.") from exc


def _write_candidate_selection_to_tracking(
    candidate: PlayerCandidate,
    tracking_report_path: Path,
) -> None:
    report = _load_tracking_report(tracking_report_path)
    updated = report.model_copy(
        update={
            "selected_player_track_id": candidate.source_raw_track_ids[0],
            "selected_player_candidate_id": candidate.candidate_id,
            "selected_player_source_track_ids": candidate.source_raw_track_ids,
            "selected_player_saved_at": datetime.now(tz=UTC),
        }
    )
    tracking_report_path.write_text(
        json.dumps(updated.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _clear_tracking_selection(tracking_report_path: Path) -> None:
    report = _load_tracking_report(tracking_report_path)
    updated = report.model_copy(
        update={
            "selected_player_track_id": None,
            "selected_player_candidate_id": None,
            "selected_player_source_track_ids": [],
            "selected_player_saved_at": None,
        }
    )
    tracking_report_path.write_text(
        json.dumps(updated.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
