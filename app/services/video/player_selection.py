import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.schemas.player_tracking import PlayerTrackingReport
from app.services.tracking.exceptions import (
    IneligibleTrackSelectionError,
    TrackingConfigurationError,
    UnknownTrackSelectionError,
)


def select_player_track(*, tracking_report_path: Path, track_id: int) -> PlayerTrackingReport:
    if track_id < 0:
        raise TrackingConfigurationError("Selected track ID must be non-negative.")
    report = load_tracking_report(tracking_report_path)
    summaries_by_id = {summary.track_id: summary for summary in report.track_summaries}

    if track_id not in summaries_by_id:
        raise UnknownTrackSelectionError(f"Track ID {track_id} does not exist in tracking report.")

    summary = summaries_by_id[track_id]
    if not summary.eligible_for_selection:
        reasons = ", ".join(summary.rejection_reasons) or "unknown"
        raise IneligibleTrackSelectionError(
            f"Track ID {track_id} is not eligible for selection: {reasons}."
        )

    updated_report = report.model_copy(
        update={
            "selected_player_track_id": track_id,
            "selected_player_saved_at": datetime.now(tz=UTC),
        }
    )
    _write_tracking_report(updated_report, tracking_report_path)
    return updated_report


def load_tracking_report(tracking_report_path: Path) -> PlayerTrackingReport:
    if not tracking_report_path.exists():
        raise TrackingConfigurationError(f"Tracking report does not exist: {tracking_report_path}")
    if not tracking_report_path.is_file():
        raise TrackingConfigurationError(
            f"Tracking report path is not a file: {tracking_report_path}"
        )

    try:
        payload = json.loads(tracking_report_path.read_text(encoding="utf-8"))
        return PlayerTrackingReport.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise TrackingConfigurationError(
            f"Tracking report could not be parsed: {tracking_report_path}"
        ) from exc


def _write_tracking_report(report: PlayerTrackingReport, tracking_report_path: Path) -> None:
    tracking_report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
