import hashlib
import json
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.active_play import (
    ActivePlayArtifacts,
    ActivePlayReport,
    ActivePlaySourceArtifacts,
    ActivePlayState,
    ActivePlaySummary,
)
from app.schemas.player_candidates import PlayerCandidateCollection
from app.schemas.player_tracking import PlayerObservation, PlayerTrackingReport
from app.services.active_play.engine import (
    BASE_LIMITATIONS,
    classify_motion_windows,
    confidence_distribution,
    merge_active_play_windows,
    reason_distribution,
)
from app.services.active_play.features import build_motion_feature_windows
from app.services.active_play.policy import ACTIVE_PLAY_POLICY, ActivePlayPolicy
from app.services.candidates import load_player_candidates
from app.services.candidates.service import CANDIDATE_SCHEMA_VERSION, CandidatePersistenceError
from app.services.tracking.exceptions import TrackingError
from app.services.video.player_selection import load_tracking_report

ACTIVE_PLAY_DIRNAME = "active_play"
ACTIVE_PLAY_REPORT_FILENAME = "active_play.json"
ACTIVE_PLAY_FEATURES_FILENAME = "features.jsonl"
ACTIVE_PLAY_WINDOWS_FILENAME = "windows.jsonl"


class ActivePlayError(Exception):
    """Base class for expected shadow Active Play failures."""


class ActivePlayNotReadyError(ActivePlayError):
    """Raised when required tracking or candidate evidence is absent."""


class ActivePlayPersistenceError(ActivePlayError):
    """Raised when an Active Play artifact cannot be safely loaded or written."""


def generate_active_play(
    *,
    analysis_id: str,
    analysis_dir: Path,
    created_at: datetime | None = None,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> ActivePlayReport:
    tracking_path = analysis_dir / "tracking" / "tracking.json"
    observations_path = analysis_dir / "tracking" / "observations.jsonl"
    candidates_path = analysis_dir / "tracking" / "player_candidates.json"
    required = [tracking_path, observations_path, candidates_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ActivePlayNotReadyError(
            "Active Play requires tracking, observations, and player candidates: "
            + ", ".join(missing)
        )

    source = _source_artifacts(
        tracking_path=tracking_path,
        observations_path=observations_path,
        candidates_path=candidates_path,
    )
    report_path = analysis_dir / ACTIVE_PLAY_DIRNAME / ACTIVE_PLAY_REPORT_FILENAME
    if report_path.is_file():
        current = load_active_play_report(report_path)
        if current.policy_version == policy.version and current.source_artifacts == source:
            return current
        raise ActivePlayPersistenceError(
            "Saved Active Play output is stale for the current source artifacts or policy."
        )

    try:
        tracking = load_tracking_report(tracking_path)
        candidates = load_player_candidates(candidates_path)
        observations = _load_observations(observations_path)
    except (CandidatePersistenceError, OSError, TrackingError, ValidationError) as exc:
        raise ActivePlayPersistenceError(
            "Active Play source artifacts could not be loaded."
        ) from exc

    report = build_active_play_report(
        analysis_id=analysis_id,
        tracking_report=tracking,
        candidates=candidates,
        observations=observations,
        source_artifacts=source,
        created_at=created_at or datetime.now(tz=UTC),
        policy=policy,
    )
    active_dir = report_path.parent
    try:
        with tempfile.TemporaryDirectory(
            prefix=".active-play-",
            dir=analysis_dir,
        ) as temporary:
            temporary_dir = Path(temporary)
            _write_jsonl(
                temporary_dir / ACTIVE_PLAY_FEATURES_FILENAME,
                build_motion_feature_windows(
                    tracking_report=tracking,
                    candidates=candidates,
                    observations=observations,
                    policy=policy,
                ),
            )
            _write_jsonl(temporary_dir / ACTIVE_PLAY_WINDOWS_FILENAME, report.windows)
            (temporary_dir / ACTIVE_PLAY_REPORT_FILENAME).write_text(
                json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary_dir.replace(active_dir)
    except OSError as exc:
        raise ActivePlayPersistenceError("Active Play artifacts could not be written.") from exc
    return report


def build_active_play_report(
    *,
    analysis_id: str,
    tracking_report: PlayerTrackingReport,
    candidates: PlayerCandidateCollection,
    observations: Sequence[PlayerObservation],
    source_artifacts: ActivePlaySourceArtifacts,
    created_at: datetime,
    policy: ActivePlayPolicy = ACTIVE_PLAY_POLICY,
) -> ActivePlayReport:
    features = build_motion_feature_windows(
        tracking_report=tracking_report,
        candidates=candidates,
        observations=observations,
        policy=policy,
    )
    windows = classify_motion_windows(
        features,
        source_duration_seconds=tracking_report.performance.source_duration_seconds,
        recording_quality=candidates.analysis_readiness,
        source_artifacts_current=(
            source_artifacts.candidate_schema_version == CANDIDATE_SCHEMA_VERSION
        ),
        policy=policy,
    )
    intervals = merge_active_play_windows(windows, policy=policy)
    duration_by_state = {
        state: sum(
            interval.end_seconds - interval.start_seconds
            for interval in intervals
            if interval.state == state
        )
        for state in ActivePlayState
    }
    source_duration = tracking_report.performance.source_duration_seconds
    classifiable = (
        duration_by_state[ActivePlayState.likely_active]
        + duration_by_state[ActivePlayState.likely_idle]
    )
    return ActivePlayReport(
        analysis_id=analysis_id,
        policy_version=policy.version,
        source_artifacts=source_artifacts,
        summary=ActivePlaySummary(
            source_duration_seconds=source_duration,
            likely_active_seconds=duration_by_state[ActivePlayState.likely_active],
            likely_idle_seconds=duration_by_state[ActivePlayState.likely_idle],
            unknown_seconds=duration_by_state[ActivePlayState.unknown],
            classifiable_seconds=classifiable,
            classifiable_ratio=classifiable / source_duration if source_duration > 0 else 0.0,
            interval_count=len(intervals),
            window_count=len(windows),
            confidence_distribution=confidence_distribution(windows),
            reason_distribution=reason_distribution(windows),
        ),
        windows=windows,
        intervals=intervals,
        artifacts=ActivePlayArtifacts(
            report_json=ACTIVE_PLAY_REPORT_FILENAME,
            features_jsonl=ACTIVE_PLAY_FEATURES_FILENAME,
            windows_jsonl=ACTIVE_PLAY_WINDOWS_FILENAME,
        ),
        limitations=[
            *BASE_LIMITATIONS,
            "Output is internal shadow evidence and is excluded from player-facing analytics.",
        ],
        created_at=created_at,
    )


def load_active_play_report(path: Path) -> ActivePlayReport:
    try:
        return ActivePlayReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ActivePlayPersistenceError("Saved Active Play report could not be loaded.") from exc


def _source_artifacts(
    *,
    tracking_path: Path,
    observations_path: Path,
    candidates_path: Path,
) -> ActivePlaySourceArtifacts:
    try:
        candidate_payload = json.loads(candidates_path.read_text(encoding="utf-8"))
        schema_version = int(candidate_payload.get("schema_version", 1))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ActivePlayPersistenceError("Candidate schema version could not be read.") from exc
    return ActivePlaySourceArtifacts(
        tracking_report="tracking/tracking.json",
        observations="tracking/observations.jsonl",
        player_candidates="tracking/player_candidates.json",
        tracking_sha256=_sha256(tracking_path),
        observations_sha256=_sha256(observations_path),
        candidates_sha256=_sha256(candidates_path),
        candidate_schema_version=schema_version,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_observations(path: Path) -> list[PlayerObservation]:
    observations: list[PlayerObservation] = []
    try:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                observations.append(PlayerObservation.model_validate_json(line))
            except ValidationError as exc:
                raise ActivePlayPersistenceError(
                    f"Invalid Active Play observation at line {line_number}."
                ) from exc
    except OSError as exc:
        raise ActivePlayPersistenceError("Observation artifact could not be read.") from exc
    return observations


def _write_jsonl(path: Path, models: Sequence[BaseModel]) -> None:
    lines = [
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        for model in models
    ]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
