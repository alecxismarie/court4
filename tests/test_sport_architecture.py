from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.services.history.policy import evaluate_contribution
from app.sports import SportType, get_sport_config
from app.sports.padel import PADEL_COURT


def test_sport_contract_accepts_supported_values_and_rejects_unknown_values() -> None:
    assert (
        AnalysisJob(
            analysis_id="pickleball",
            sport=SportType.PICKLEBALL,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.uploaded,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ).sport
        == SportType.PICKLEBALL
    )
    assert (
        AnalysisJob(
            analysis_id="padel",
            sport=SportType.PADEL,
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.uploaded,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ).sport
        == SportType.PADEL
    )

    with pytest.raises(ValidationError):
        AnalysisJob(
            analysis_id="unknown",
            sport="tennis",  # type: ignore[arg-type]
            status=AnalysisStatus.processing,
            current_stage=AnalysisStage.uploaded,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        )


def test_padel_court_definition_keeps_enclosure_boundary_semantics_explicit() -> None:
    assert PADEL_COURT.width_metres == 10.0
    assert PADEL_COURT.length_metres == 20.0
    assert PADEL_COURT.net == ((0.0, 10.0), (10.0, 10.0))
    assert PADEL_COURT.near_service_line_y_metres == pytest.approx(3.05)
    assert len(PADEL_COURT.boundaries) == 4
    assert "wall_interactions_unmodelled" in PADEL_COURT.boundary_semantics


def test_padel_policy_cannot_enable_pickleball_interpretation_or_history() -> None:
    config = get_sport_config(SportType.PADEL)
    assert config.capability_status == "experimental"
    assert config.policy.match_iq is False
    assert config.policy.play_history_contribution is False

    now = datetime.now(tz=UTC)
    job = AnalysisJob(
        analysis_id="padel-history",
        sport=SportType.PADEL,
        status=AnalysisStatus.completed,
        current_stage=AnalysisStage.analyzed,
        created_at=now,
        updated_at=now,
        analytics_completed=True,
    )
    decision = evaluate_contribution(
        job=job,
        analytics=None,
        match_iq=None,
        evaluated_at=now,
    )
    assert decision.status == "EXCLUDED"
    assert decision.reason_codes == ["SPORT_INTERPRETATION_UNAVAILABLE"]
