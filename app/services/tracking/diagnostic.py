"""Bounded, read-only summary of persisted Pickleball tracking evidence."""

import json
import time
from bisect import bisect_right
from collections import Counter
from typing import Any

from pydantic import ValidationError

from app.schemas.analytics import AnalyticsReport
from app.schemas.player_candidates import CandidateReviewStatus, PlayerCandidateCollection
from app.schemas.player_tracking import PlayerObservation, PlayerTrackingReport
from app.schemas.video import VideoMetadataReport
from app.services.analytics.movement import _deduplicate_observations
from app.services.jobs.exceptions import JobConflictError, JobStorageCapacityError
from app.services.jobs.repository import AnalysisJobRepository
from app.services.tracking.continuity import is_observed_court_position, supports_observed_interval

MAX_OBSERVATION_ROWS = 100_000
MAX_RESPONSE_BYTES = 512 * 1024
MAX_SECONDS = 15.0


def tracking_evidence_diagnostic(
    repository: AnalysisJobRepository, analysis_id: str
) -> dict[str, Any]:
    """Summarize saved facts; never infer identity from another raw ID."""
    with repository.verified_diagnostic_artifacts(analysis_id) as paths:
        # This bounds local computation. Network calls use separate socket timeouts;
        # neither bound is a hard end-to-end request deadline.
        deadline = time.monotonic() + MAX_SECONDS
        _check_limits(deadline, 0)
        try:
            tracking = PlayerTrackingReport.model_validate_json(
                paths["tracking/tracking.json"].read_text(encoding="utf-8")
            )
            candidates = PlayerCandidateCollection.model_validate_json(
                paths["tracking/player_candidates.json"].read_text(encoding="utf-8")
            )
            analytics = AnalyticsReport.model_validate_json(
                paths["analytics/analytics.json"].read_text(encoding="utf-8")
            )
            metadata = VideoMetadataReport.model_validate_json(
                paths["metadata.json"].read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError):
            raise JobConflictError(
                "diagnostic_invalid_evidence", "Saved structured evidence is invalid."
            ) from None
        _check_limits(deadline, 0)
        selected = next(
            (
                item
                for item in candidates.candidates
                if item.candidate_id == candidates.selected_candidate_id
            ),
            None,
        )
        persisted_selection = repository.current_diagnostic_selection(analysis_id)
        from app.services.candidates.service import CANDIDATE_SCHEMA_VERSION

        if (
            selected is None
            or not selected.source_raw_track_ids
            or candidates.schema_version != CANDIDATE_SCHEMA_VERSION
            or not selected.selection_eligible
            or selected.review_status != CandidateReviewStatus.selected
            or persisted_selection is None
            or persisted_selection.candidate_id != selected.candidate_id
            or persisted_selection.track_id != selected.source_raw_track_ids[0]
            or persisted_selection.source_track_ids != selected.source_raw_track_ids
            or any(raw_id < 0 for raw_id in selected.source_raw_track_ids)
            or tracking.analysis_id != analysis_id
            or candidates.analysis_id != analysis_id
            or analytics.analysis_id != analysis_id
            or metadata.analysis_id != analysis_id
            or tracking.selected_player_candidate_id != selected.candidate_id
            or analytics.selected_player_candidate_id != selected.candidate_id
            or tracking.selected_player_source_track_ids != selected.source_raw_track_ids
            or analytics.source_raw_track_ids != selected.source_raw_track_ids
            or tracking.selected_player_track_id != analytics.selected_player_track_id
            or tracking.selected_player_track_id != selected.source_raw_track_ids[0]
            or tracking.calibration_id != analytics.calibration_id
            or tracking.artifacts.tracking_json != "tracking.json"
            or tracking.artifacts.observations_jsonl != "observations.jsonl"
            or analytics.source_tracking_report != "tracking/tracking.json"
            or analytics.source_observations != "tracking/observations.jsonl"
            or analytics.artifacts.analytics_json != "analytics.json"
            or analytics.source_fragment_count != len(selected.source_raw_track_ids)
        ):
            raise JobConflictError("diagnostic_lineage_changed", "Saved evidence does not agree.")

        selected_ids = set(selected.source_raw_track_ids)
        selected_rows: list[PlayerObservation] = []
        other_rows: list[tuple[float, int]] = []
        counts: Counter[str] = Counter()
        raw_spans: dict[int, list[float]] = {}
        try:
            with paths["tracking/observations.jsonl"].open(encoding="utf-8") as rows:
                for row_number, line in enumerate(rows, 1):
                    _check_limits(deadline, row_number)
                    if not line.strip():
                        continue
                    observation = PlayerObservation.model_validate_json(line)
                    if observation.track_id in selected_ids:
                        selected_rows.append(observation)
                        spans = raw_spans.setdefault(
                            observation.track_id,
                            [observation.timestamp_seconds, observation.timestamp_seconds],
                        )
                        spans[0] = min(spans[0], observation.timestamp_seconds)
                        spans[1] = max(spans[1], observation.timestamp_seconds)
                        count_key = (
                            "valid_court"
                            if is_observed_court_position(observation)
                            else "excluded_court"
                        )
                        counts[count_key] += 1
                        if not observation.inside_court:
                            counts["outside_court"] += 1
                        if observation.excluded_from_player_tracks:
                            counts["excluded_from_player_tracks"] += 1
                        if observation.interpolated:
                            counts["interpolated"] += 1
                    else:
                        other_rows.append((observation.timestamp_seconds, observation.track_id))
        except (OSError, UnicodeError, ValidationError):
            raise JobConflictError(
                "diagnostic_invalid_evidence", "Saved structured evidence is invalid."
            ) from None

        ordered = _deduplicate_observations(selected_rows)
        if set(raw_spans) != selected_ids:
            raise JobConflictError("diagnostic_lineage_changed", "Saved evidence does not agree.")
        if len(ordered) < 2:
            raise JobConflictError(
                "diagnostic_insufficient_evidence", "Selected observations are unavailable."
            )
        other_rows.sort()
        other_times = [item[0] for item in other_rows]
        other_spans: dict[int, dict[str, float | int]] = {}
        for timestamp, track_id in other_rows:
            span = other_spans.setdefault(
                track_id,
                {"first_seconds": timestamp, "last_seconds": timestamp, "observation_count": 0},
            )
            span["last_seconds"] = timestamp
            span["observation_count"] += 1
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        observed_seconds = 0.0
        for index, (first, second) in enumerate(zip(ordered, ordered[1:], strict=False), 1):
            _check_limits(deadline, index)
            if supports_observed_interval(first, second):
                observed_seconds += second.timestamp_seconds - first.timestamp_seconds
                if (
                    accepted
                    and accepted[-1]["end_seconds"] == first.timestamp_seconds
                    and accepted[-1]["raw_id"] == first.track_id
                ):
                    accepted[-1]["end_seconds"] = second.timestamp_seconds
                else:
                    accepted.append(
                        {
                            "start_seconds": first.timestamp_seconds,
                            "end_seconds": second.timestamp_seconds,
                            "raw_id": first.track_id,
                        }
                    )
                continue
            reasons = _rejection_reasons(first, second)
            start = bisect_right(other_times, first.timestamp_seconds)
            end = bisect_right(other_times, second.timestamp_seconds)
            other_ids = sorted({track_id for _, track_id in other_rows[start:end]})
            rejected.append(
                {
                    "start_seconds": first.timestamp_seconds,
                    "end_seconds": second.timestamp_seconds,
                    "duration_seconds": max(
                        0.0, second.timestamp_seconds - first.timestamp_seconds
                    ),
                    "reasons": reasons,
                    "other_raw_ids_present": other_ids[:12],
                    "other_raw_ids_truncated": len(other_ids) > 12,
                }
            )
        if abs(observed_seconds - analytics.observed_duration_seconds) > 0.05:
            raise JobConflictError(
                "diagnostic_duration_mismatch", "Saved duration does not match observations."
            )
        first_time = ordered[0].timestamp_seconds
        last_time = ordered[-1].timestamp_seconds
        valid_frames = sum(is_observed_court_position(row) for row in ordered)
        if valid_frames != analytics.timeline_observation_count:
            raise JobConflictError(
                "diagnostic_duration_mismatch", "Saved position count does not match observations."
            )
        if last_time > metadata.duration_seconds:
            raise JobConflictError(
                "diagnostic_duration_mismatch", "Saved timestamps exceed video duration."
            )
        internal_unobserved = max(0.0, last_time - first_time - observed_seconds)
        if abs(internal_unobserved - analytics.unobserved_gap_seconds) > 0.05:
            raise JobConflictError(
                "diagnostic_duration_mismatch", "Saved gap duration does not match observations."
            )
        other_candidates = [
            {
                "candidate_id": item.candidate_id,
                "raw_ids": item.source_raw_track_ids,
                "first_seconds": item.first_observed_timestamp,
                "last_seconds": item.last_observed_timestamp,
                "selection_eligible": item.selection_eligible,
                "exclusion_reasons": item.selection_exclusion_reasons,
                "accepted_association_edges": [
                    [edge.from_track_id, edge.to_track_id] for edge in item.automatic_merge_evidence
                ],
            }
            for item in [*candidates.candidates, *candidates.excluded_candidates]
            if item.candidate_id != selected.candidate_id
        ]
        for interval in accepted:
            interval["duration_seconds"] = interval["end_seconds"] - interval["start_seconds"]
        result = {
            "analysis_id": analysis_id,
            "selected_candidate_id": selected.candidate_id,
            "selected_primary_raw_id": tracking.selected_player_track_id,
            "selected_raw_ids": selected.source_raw_track_ids,
            "raw_id_spans": raw_spans,
            "video_duration_seconds": metadata.duration_seconds,
            "processed_frame_count": tracking.processed_frame_count,
            "valid_selected_frame_count": analytics.timeline_observation_count,
            "selected_first_seconds": first_time,
            "selected_last_seconds": last_time,
            "before_first_seconds": first_time,
            "after_last_seconds": max(0.0, metadata.duration_seconds - last_time),
            "observed_seconds": observed_seconds,
            "internal_unobserved_seconds": internal_unobserved,
            "full_video_unobserved_or_uncertain_seconds": max(
                0.0, metadata.duration_seconds - observed_seconds
            ),
            "coverage_percent": 100 * observed_seconds / metadata.duration_seconds,
            "selected_court_observation_counts": dict(counts),
            "accepted_intervals": accepted,
            "rejected_intervals": rejected,
            "other_raw_id_spans": other_spans,
            "other_raw_ids_before_first": sorted(
                {track_id for timestamp, track_id in other_rows if timestamp < first_time}
            ),
            "other_raw_ids_after_last": sorted(
                {track_id for timestamp, track_id in other_rows if timestamp > last_time}
            ),
            "other_candidate_groups": other_candidates,
            "identity_of_other_raw_ids": "Unknown",
            "rejected_association_conditions_not_persisted": "Unknown",
            "missing_person_detections_vs_unassigned_track_ids": "Unknown",
        }
        if len(json.dumps(result, separators=(",", ":")).encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise JobStorageCapacityError(
                "diagnostic_response_limit",
                "Diagnostic summary exceeds the response limit.",
                status_code=413,
            )
        return result


def _rejection_reasons(first: PlayerObservation, second: PlayerObservation) -> list[str]:
    reasons: list[str] = []
    if first.track_id != second.track_id:
        reasons.append("raw_id_changed")
    if second.frame_index <= first.frame_index:
        reasons.append("frame_not_increasing")
    gap = second.timestamp_seconds - first.timestamp_seconds
    if gap <= 0:
        reasons.append("time_not_increasing")
    elif gap > 1.0:
        reasons.append("gap_over_one_second")
    if not first.inside_court or not second.inside_court:
        reasons.append("outside_court")
    if first.excluded_from_player_tracks or second.excluded_from_player_tracks:
        reasons.append("excluded_from_player_tracks")
    if first.interpolated or second.interpolated:
        reasons.append("interpolated")
    return reasons


def _check_limits(deadline: float, count: int) -> None:
    if count > MAX_OBSERVATION_ROWS or time.monotonic() > deadline:
        raise JobStorageCapacityError(
            "diagnostic_execution_limit",
            "Tracking diagnostic resource limit reached.",
            status_code=413,
        )
