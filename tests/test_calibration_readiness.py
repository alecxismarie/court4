import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.internal import get_readiness_service
from app.main import create_app
from app.schemas.calibration_readiness import ReadinessDataStatus, ReadinessVerdict
from app.services.calibration_readiness.policy import ReadinessFacts, evaluate_readiness
from app.services.calibration_readiness.service import CalibrationReadinessService

ROOT = Path(__file__).resolve().parents[1]


def test_current_two_sample_dataset_reports_evidence_gaps_without_inference(
    tmp_path: Path,
) -> None:
    service = _copy_current_sources(tmp_path)
    before = _source_hashes(tmp_path)

    first = service.get_summary()
    second = service.get_summary()

    assert first == second
    assert first.internal_only is True
    assert first.read_only is True
    assert first.dataset.total_samples == 2
    assert first.dataset.development_count == 1
    assert first.dataset.validation_count == 1
    assert first.dataset.holdout_count == 0
    assert first.dataset.reviewed_samples == 0
    assert first.dataset.partially_reviewed_samples == 2
    assert first.readiness.verdict == ReadinessVerdict.collecting_evidence
    assert first.active_play.reviewed_intervals == 0
    assert first.active_play.false_active.percentage is None
    assert first.active_play.false_idle.percentage is None
    assert first.policy_safety.holdout_protection_enabled is True
    assert any("holdout" in item.lower() for item in first.readiness.blockers)
    assert any("legacy" in item.readiness.lower() for item in first.artifact_readiness)
    assert _source_hashes(tmp_path) == before


def test_missing_or_invalid_manifest_returns_typed_not_ready_state(tmp_path: Path) -> None:
    service = _service(tmp_path)

    missing = service.get_summary()

    assert missing.source_status.manifest == ReadinessDataStatus.missing
    assert missing.source_status.overall == ReadinessDataStatus.missing
    assert missing.readiness.verdict == ReadinessVerdict.not_ready
    assert missing.dataset.total_samples == 0

    (tmp_path / "manifest.json").write_text("{invalid", encoding="utf-8")

    invalid = service.get_summary()

    assert invalid.source_status.manifest == ReadinessDataStatus.invalid
    assert invalid.readiness.verdict == ReadinessVerdict.not_ready


def test_report_manifest_mismatch_is_explicitly_stale(tmp_path: Path) -> None:
    service = _copy_current_sources(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_version"] = "2.0.1"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = service.get_summary()

    assert summary.source_status.report == ReadinessDataStatus.stale
    assert summary.source_status.overall == ReadinessDataStatus.stale
    assert summary.readiness.verdict == ReadinessVerdict.not_ready
    assert any("does not match" in message for message in summary.source_status.messages)


def test_readiness_verdict_transitions_require_evidence_then_explicit_approvals() -> None:
    collecting = replace(_complete_facts(), total_samples=2, holdout_count=0)
    reviewable = _complete_facts()
    approved = replace(
        reviewable,
        recording_policy_frozen=True,
        active_play_policy_frozen=True,
        false_active_budget_approved=True,
        false_idle_budget_approved=True,
    )

    assert evaluate_readiness(replace(collecting, source_current=False)).verdict == (
        ReadinessVerdict.not_ready
    )
    assert evaluate_readiness(collecting).verdict == ReadinessVerdict.collecting_evidence
    assert evaluate_readiness(reviewable).verdict == ReadinessVerdict.ready_for_policy_review
    assert evaluate_readiness(approved).verdict == ReadinessVerdict.ready_for_phase_1_6b


def test_internal_route_is_get_only_and_does_not_change_sources(tmp_path: Path) -> None:
    service = _copy_current_sources(tmp_path)
    application = create_app()
    application.dependency_overrides[get_readiness_service] = lambda: service
    client = TestClient(application)
    before = _source_hashes(tmp_path)

    response = client.get("/api/v1/internal/calibration-readiness")
    write_attempt = client.post("/api/v1/internal/calibration-readiness")

    assert response.status_code == 200
    assert response.json()["read_only"] is True
    assert response.json()["internal_only"] is True
    assert write_attempt.status_code == 405
    assert _source_hashes(tmp_path) == before


def _complete_facts() -> ReadinessFacts:
    return ReadinessFacts(
        source_current=True,
        total_samples=20,
        development_count=10,
        validation_count=5,
        holdout_count=5,
        fully_reviewed_samples=5,
        current_schema_samples=5,
        active_reviewed_seconds=300,
        active_reviewed_intervals=10,
        active_evidence_seconds=150,
        idle_evidence_seconds=150,
        reviewed_boundaries=10,
        missing_balance_values=0,
        underrepresented_balance_values=0,
        critical_disagreements=0,
        expensive_inference_runs=0,
        production_thresholds_unchanged=True,
        reviewer_labels_unchanged=True,
        deterministic_report_verified=True,
        holdout_protection_enabled=True,
        recording_policy_frozen=False,
        active_play_policy_frozen=False,
        false_active_budget_approved=False,
        false_idle_budget_approved=False,
    )


def _copy_current_sources(tmp_path: Path) -> CalibrationReadinessService:
    sources = {
        ROOT / "calibration" / "manifest.v2.json": tmp_path / "manifest.json",
        ROOT / "calibration-results.json": tmp_path / "results.json",
        ROOT / "CALIBRATION_REPORT.md": tmp_path / "report.md",
        ROOT / "CALIBRATION_DISAGREEMENTS.md": tmp_path / "disagreements.md",
        ROOT / "calibration-readiness-integrity.json": tmp_path / "integrity.json",
        ROOT / "calibration" / "readiness-governance.json": tmp_path / "governance.json",
    }
    for source, destination in sources.items():
        shutil.copyfile(source, destination)
    return _service(tmp_path)


def _service(tmp_path: Path) -> CalibrationReadinessService:
    return CalibrationReadinessService(
        manifest_path=tmp_path / "manifest.json",
        results_path=tmp_path / "results.json",
        calibration_report_path=tmp_path / "report.md",
        disagreements_report_path=tmp_path / "disagreements.md",
        integrity_path=tmp_path / "integrity.json",
        governance_path=tmp_path / "governance.json",
    )


def _source_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }
