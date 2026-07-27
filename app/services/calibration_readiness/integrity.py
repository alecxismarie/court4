import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from app.schemas.calibration_readiness import (
    CalibrationReadinessIntegrity,
    DeterministicHashStatus,
)
from app.schemas.evidence_calibration import CalibrationResults


def canonical_policy_sha256(policy: object) -> str:
    if not is_dataclass(policy):
        raise TypeError("Policy hashing requires a dataclass instance.")
    payload = json.dumps(
        asdict(policy),  # type: ignore[arg-type]
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_integrity_record(
    *,
    results: CalibrationResults,
    results_path: Path,
    report_path: Path,
    disagreements_path: Path,
    output_path: Path,
) -> CalibrationReadinessIntegrity:
    recording_policy_sha256 = results.recording_policy_sha256
    active_play_policy_sha256 = results.active_play_policy_sha256
    if recording_policy_sha256 is None or active_play_policy_sha256 is None:
        raise ValueError("Calibration results do not contain policy hashes.")
    calibration_results_sha256 = file_sha256(results_path)
    calibration_report_sha256 = file_sha256(report_path)
    disagreements_report_sha256 = file_sha256(disagreements_path)
    current = {
        "manifest_sha256": results.manifest_sha256,
        "recording_policy_sha256": recording_policy_sha256,
        "active_play_policy_sha256": active_play_policy_sha256,
        "calibration_results_sha256": calibration_results_sha256,
        "calibration_report_sha256": calibration_report_sha256,
        "disagreements_report_sha256": disagreements_report_sha256,
    }

    previous = _load_previous(output_path)
    comparable = (
        previous is not None
        and previous.manifest_sha256 == current["manifest_sha256"]
        and previous.recording_policy_sha256 == current["recording_policy_sha256"]
        and previous.active_play_policy_sha256 == current["active_play_policy_sha256"]
    )
    output_hashes_match = comparable and all(
        getattr(previous, key) == value
        for key, value in current.items()
        if key.endswith("_results_sha256")
        or key.endswith("_report_sha256")
        or key == "disagreements_report_sha256"
    )
    status = (
        DeterministicHashStatus.match
        if output_hashes_match
        else (
            DeterministicHashStatus.changed if comparable else DeterministicHashStatus.not_verified
        )
    )
    record = CalibrationReadinessIntegrity(
        manifest_sha256=results.manifest_sha256,
        recording_policy_sha256=recording_policy_sha256,
        active_play_policy_sha256=active_play_policy_sha256,
        calibration_results_sha256=calibration_results_sha256,
        calibration_report_sha256=calibration_report_sha256,
        disagreements_report_sha256=disagreements_report_sha256,
        deterministic_report_status=status,
        verified_at=datetime.now(tz=UTC),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return record


def _load_previous(path: Path) -> CalibrationReadinessIntegrity | None:
    if not path.is_file():
        return None
    try:
        return CalibrationReadinessIntegrity.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None
