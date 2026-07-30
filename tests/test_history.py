import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.schemas.analytics import (
    AnalyticsArtifacts,
    AnalyticsReport,
    DistanceMetrics,
    ZoneOccupancyMetric,
    ZoneOccupancyReport,
)
from app.schemas.history import (
    ContributionStatus,
    ProgressEligibilityDecision,
    ProgressEligibilityStatus,
)
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.schemas.match_iq import (
    ConfidenceLevel,
    MatchIQConfidence,
    MatchIQConfidenceRating,
    MatchIQReport,
)
from app.schemas.recording_quality import (
    AnalysisQualitySignals,
    PreflightStage,
    QualityCheck,
    QualityCheckStatus,
    RecordingQualityAssessment,
    RecordingQualityLevel,
)
from app.services.history import (
    PLAY_HISTORY_POLICY_VERSION,
    HistoryProjectionService,
    evaluate_contribution,
)
from app.services.history.comparability import (
    ComparableReport,
    evaluate_comparability,
)
from app.services.history.grouping import deterministic_split
from app.services.history.progress_policy import evaluate_trend_eligibility
from app.services.jobs import AnalysisJobRepository

NOW = datetime(2026, 7, 28, 10, 0, tzinfo=UTC)


def test_analysis_history_includes_every_persisted_analysis(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    ready = _job("ready", status=AnalysisStatus.completed, analytics_completed=True)
    unsuitable = _job(
        "unsuitable",
        status=AnalysisStatus.completed,
        analytics_completed=True,
        readiness=_readiness(status=RecordingQualityLevel.unsuitable, blocking=True),
    )
    failed = _job("failed", status=AnalysisStatus.failed)
    processing = _job("processing")
    for job in [ready, unsuitable, failed, processing]:
        repository.save_job(job)
    _write_analytics(repository, ready.analysis_id, _analytics(ready.analysis_id))
    _write_analytics(repository, unsuitable.analysis_id, _analytics(unsuitable.analysis_id))
    legacy_dir = repository.analysis_dir("legacy")
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "job.json").write_text("{not-json", encoding="utf-8")

    result = HistoryProjectionService(repository=repository).analysis_history(limit=100, offset=0)

    assert result.total == 4
    by_id = {item.analysis_id: item for item in result.items}
    assert set(by_id) == {"ready", "unsuitable", "failed", "processing"}
    assert by_id["unsuitable"].status == "UNSUITABLE"
    assert by_id["failed"].status == "FAILED"
    assert by_id["processing"].status == "PROCESSING"
    assert all(item.report_url.startswith("/matches/") for item in result.items)


def test_contribution_policy_includes_complete_qualified_analysis() -> None:
    job = _job("included", status=AnalysisStatus.completed, analytics_completed=True)

    decision = evaluate_contribution(
        job=job,
        analytics=_analytics(job.analysis_id),
        match_iq=None,
        evaluated_at=NOW,
    )

    assert decision.status == ContributionStatus.included
    assert decision.reason_codes == ["EVIDENCE_STANDARD_MET"]
    assert decision.policy_version == PLAY_HISTORY_POLICY_VERSION
    assert decision.evaluated_at == NOW


def test_weak_measurement_confidence_is_excluded_without_using_interpretation() -> None:
    job = _job("weak", status=AnalysisStatus.completed, analytics_completed=True)
    match_iq = _match_iq(job.analysis_id, measurement="LOW", interpretation="HIGH")

    decision = evaluate_contribution(
        job=job,
        analytics=_analytics(job.analysis_id),
        match_iq=match_iq,
        evaluated_at=NOW,
    )

    assert decision.status == ContributionStatus.excluded
    assert decision.reason_codes == ["WEAK_MEASUREMENT_CONFIDENCE"]


def test_interpretation_confidence_is_not_a_movement_gate() -> None:
    job = _job("movement-safe", status=AnalysisStatus.completed, analytics_completed=True)
    match_iq = _match_iq(job.analysis_id, measurement="MODERATE", interpretation="LOW")

    decision = evaluate_contribution(
        job=job,
        analytics=_analytics(job.analysis_id),
        match_iq=match_iq,
        evaluated_at=NOW,
    )

    assert decision.status == ContributionStatus.included


def test_play_history_aggregates_only_included_analyses(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    included = _job("included", status=AnalysisStatus.completed, analytics_completed=True)
    excluded = _job(
        "excluded",
        status=AnalysisStatus.completed,
        analytics_completed=True,
        readiness=_readiness(status=RecordingQualityLevel.unsuitable, blocking=True),
    )
    repository.save_job(included)
    repository.save_job(excluded)
    _write_analytics(
        repository,
        included.analysis_id,
        _analytics(included.analysis_id, observed=30, tracked=20, kitchen=10),
    )
    _write_analytics(
        repository,
        excluded.analysis_id,
        _analytics(excluded.analysis_id, observed=9_999, tracked=9_999, kitchen=9_999),
    )
    active_play = repository.analysis_dir(included.analysis_id) / "active_play"
    active_play.mkdir()
    (active_play / "active_play.json").write_text(
        json.dumps({"active_play_seconds": 8_888}),
        encoding="utf-8",
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.eligible_count == 1
    assert result.excluded_count == 1
    assert result.reliable_observation_seconds == 30
    assert result.qualified_movement_seconds == 20
    assert result.most_common_zone is not None
    assert result.most_common_zone.seconds == 10
    assert result.most_common_zone.denominator_seconds == 20
    assert result.most_common_zone.contributing_analyses == 1


def test_play_history_empty_state_uses_clear_player_facing_copy(tmp_path: Path) -> None:
    result = HistoryProjectionService(repository=_repository(tmp_path)).play_history(recent_limit=5)

    assert result.progress.baseline_status == "NO_QUALIFIED_REPORTS"
    assert result.progress.answer == "Your progress history hasn't started yet"
    assert result.progress.explanation == (
        "Court4 needs completed analyses with enough clear, reliable video before it "
        "can compare how your play changes over time."
    )
    assert (
        "Court4 needs reports with enough reliable information before it can compare them."
        in result.progress.limitations
    )
    assert (
        "Court4 will not guess when information is missing or cannot be compared."
        in result.progress.limitations
    )


def test_play_history_compares_qualified_reports_without_claiming_improvement(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for index in range(4):
        analysis_id = f"trend-{index}"
        timestamp = NOW + timedelta(days=index)
        job = _job(
            analysis_id,
            status=AnalysisStatus.completed,
            analytics_completed=True,
        ).model_copy(update={"created_at": timestamp, "updated_at": timestamp})
        repository.save_job(job)
        _write_analytics(
            repository,
            analysis_id,
            _analytics(
                analysis_id,
                tracked=100,
                kitchen=20 if index < 2 else 60,
                movement_mps=0.6 if index < 2 else 0.9,
            ),
        )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.progress.status == "COMPARISON_AVAILABLE"
    assert result.progress.answer == "Observed changes are ready to review"
    assert result.progress.provisional is True
    assert result.progress.earlier_analysis_count == 2
    assert result.progress.recent_analysis_count == 2
    trends = {metric.key: metric for metric in result.progress.trend_metrics}
    assert trends["movement_pace"].earlier_value == pytest.approx(0.6)
    assert trends["movement_pace"].recent_value == pytest.approx(0.9)
    assert trends["movement_pace"].direction == "HIGHER"
    assert (
        trends["movement_pace"].aggregation_method
        == "sum distance metres ÷ sum qualified tracked seconds"
    )
    assert trends["kitchen_share"].earlier_value == pytest.approx(20)
    assert trends["kitchen_share"].recent_value == pytest.approx(60)
    assert result.progress.play_style is not None
    assert result.progress.play_style.status == "PROVISIONAL_CHANGE"
    assert "reliably tracked positioning" in result.progress.play_style.summary
    assert "improved" not in result.progress.model_dump_json().lower()
    assert result.progress.earlier_group is not None
    assert result.progress.recent_group is not None
    assert result.progress.earlier_group.analysis_count == 2
    assert result.progress.recent_group.analysis_count == 2


def test_contribution_comparability_trend_and_interpretation_are_separate(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _persist_qualified_report(repository, "separate", day=0)

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.eligible_count == 1
    assert result.comparable_count == 1
    candidate = result.comparison_candidates[0]
    assert candidate.contribution_status == "INCLUDED"
    assert candidate.comparability.status == "PROVISIONAL"
    assert candidate.comparability.policy_version == "play-history-comparability-v1"
    assert candidate.comparability.reasons
    assert candidate.comparability.limitations
    assert candidate.comparability.source_versions
    assert result.progress.trend_eligibility.status == "INELIGIBLE"
    assert result.progress.trend_eligibility.policy_version == "play-history-trend-v1"
    assert result.progress.interpretation_eligibility.status == "NOT_EVALUATED"
    assert (
        result.progress.interpretation_eligibility.policy_version
        == "play-history-interpretation-v1"
    )
    assert result.policy_versions.grouping == "play-history-grouping-v1"
    assert result.policy_versions.aggregation == "play-history-aggregation-v1"


def test_exactly_three_reports_establish_baseline_without_trend(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    for day in range(3):
        _persist_qualified_report(repository, f"baseline-{day}", day=day)

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.progress.baseline_status == "BASELINE_ESTABLISHED"
    assert result.progress.answer == "Initial baseline established"
    assert result.progress.trend_eligibility.status == "PROVISIONAL"
    assert result.progress.earlier_group is None
    assert result.progress.recent_group is None
    assert result.progress.trend_metrics == []
    assert result.progress.provisional is True


def test_five_reports_omit_middle_report_and_use_non_overlapping_groups(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for day in range(5):
        _persist_qualified_report(repository, f"odd-{day}", day=day)

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.progress.earlier_group is not None
    assert result.progress.recent_group is not None
    earlier_ids = [item.analysis_id for item in result.progress.earlier_group.analyses]
    recent_ids = [item.analysis_id for item in result.progress.recent_group.analyses]
    assert earlier_ids == ["odd-0", "odd-1"]
    assert recent_ids == ["odd-3", "odd-4"]
    assert set(earlier_ids).isdisjoint(recent_ids)
    assert "odd-2" not in result.progress.contributing_analysis_ids
    assert any(
        "middle-report grouping rule" in limitation
        for limitation in result.progress.trend_eligibility.limitations
    )


def test_zone_aggregation_is_weighted_by_qualified_duration(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _persist_qualified_report(
        repository,
        "weighted-0",
        day=0,
        tracked=10,
        kitchen=10,
    )
    _persist_qualified_report(
        repository,
        "weighted-1",
        day=1,
        tracked=90,
        kitchen=0,
    )
    _persist_qualified_report(
        repository,
        "weighted-2",
        day=2,
        tracked=50,
        kitchen=25,
    )
    _persist_qualified_report(
        repository,
        "weighted-3",
        day=3,
        tracked=50,
        kitchen=25,
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)
    trends = {metric.key: metric for metric in result.progress.trend_metrics}

    assert trends["kitchen_share"].earlier_value == pytest.approx(10)
    assert trends["kitchen_share"].recent_value == pytest.approx(50)
    assert trends["kitchen_share"].normalization == "duration-weighted court-zone occupancy"
    assert trends["kitchen_share"].earlier_contributing_count == 2
    assert trends["kitchen_share"].earlier_qualified_observation_seconds == pytest.approx(100)


def test_movement_pace_is_normalized_by_qualified_tracked_time(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _persist_qualified_report(
        repository,
        "pace-0",
        day=0,
        tracked=10,
        movement_mps=1,
    )
    _persist_qualified_report(
        repository,
        "pace-1",
        day=1,
        tracked=90,
        movement_mps=1,
    )
    _persist_qualified_report(
        repository,
        "pace-2",
        day=2,
        tracked=20,
        movement_mps=2,
    )
    _persist_qualified_report(
        repository,
        "pace-3",
        day=3,
        tracked=80,
        movement_mps=2,
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)
    pace = next(metric for metric in result.progress.trend_metrics if metric.key == "movement_pace")

    assert pace.earlier_value == pytest.approx(1)
    assert pace.recent_value == pytest.approx(2)
    assert pace.earlier_qualified_observation_seconds == pytest.approx(100)
    assert set(pace.contributing_analysis_ids) == {
        "pace-0",
        "pace-1",
        "pace-2",
        "pace-3",
    }


def test_tracking_confidence_can_block_comparison_without_changing_contribution(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    match_iq = _match_iq("weak-tracking", tracking="LOW")
    _persist_qualified_report(
        repository,
        "weak-tracking",
        day=0,
        match_iq=match_iq,
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.eligible_count == 1
    assert result.comparable_count == 0
    assert result.comparison_candidates[0].contribution_status == "INCLUDED"
    assert result.comparison_candidates[0].comparability.status == "INELIGIBLE"
    assert "Tracking confidence" in result.comparison_candidates[0].comparability.reasons[0]


def test_limited_recording_remains_provisional_for_comparison(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _persist_qualified_report(
        repository,
        "limited-comparison",
        day=0,
        readiness=_readiness(status=RecordingQualityLevel.limited),
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.eligible_count == 1
    assert result.comparison_candidates[0].comparability.status == "PROVISIONAL"
    assert any(
        "quality limitations" in limitation
        for limitation in result.comparison_candidates[0].comparability.limitations
    )


def test_missing_measurements_are_unavailable_and_never_zero(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    job = _job(
        "missing-measurement",
        status=AnalysisStatus.completed,
        analytics_completed=True,
    )
    repository.save_job(job)
    analytics_dir = repository.analysis_dir(job.analysis_id) / "analytics"
    analytics_dir.mkdir(parents=True)
    (analytics_dir / "analytics.json").write_text(
        json.dumps({"analysis_id": job.analysis_id}),
        encoding="utf-8",
    )
    repository.register_current_artifacts(job.analysis_id)

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.eligible_count == 0
    assert result.reliable_observation_seconds is None
    assert result.qualified_movement_seconds is None
    assert result.progress.qualified_observation_seconds == 0
    assert result.progress.trend_metrics == []
    assert result.contributions[0].contribution.status == "NOT_EVALUATED"


def test_mixed_analytics_versions_are_ineligible_for_trend(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    reports: list[ComparableReport] = []
    for day in range(4):
        analysis_id = f"version-{day}"
        _persist_qualified_report(repository, analysis_id, day=day)
        item = (
            HistoryProjectionService(repository=repository)
            .analysis_history(
                limit=100,
                offset=0,
            )
            .items[0]
        )
        analytics = _analytics(analysis_id)
        decision = evaluate_comparability(item=item, analytics=analytics, match_iq=None)
        source = decision.source_versions[0].model_copy(
            update={"analytics_schema": "movement-analytics-v1" if day < 2 else "v2"}
        )
        mixed = ProgressEligibilityDecision(
            status=ProgressEligibilityStatus.provisional,
            reasons=decision.reasons,
            limitations=decision.limitations,
            source_versions=[source],
            policy_version=decision.policy_version,
        )
        reports.append(
            ComparableReport(
                item=item.model_copy(
                    update={
                        "analysis_id": analysis_id,
                        "created_at": NOW + timedelta(days=day),
                    }
                ),
                analytics=analytics,
                match_iq=None,
                decision=mixed,
            )
        )

    decision = evaluate_trend_eligibility(
        qualified_count=4,
        comparable_reports=reports,
        split=deterministic_split(reports),
    )

    assert decision.status == "INELIGIBLE"
    assert "incompatible progress source versions" in decision.reasons[0]


def test_progress_projection_is_deterministic_and_retains_outliers(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    for day, movement_pace in enumerate([1.0, 1.0, 10.0, 1.0, 1.0, 1.0]):
        _persist_qualified_report(
            repository,
            f"outlier-{day}",
            day=day,
            movement_mps=movement_pace,
        )
    service = HistoryProjectionService(repository=repository)

    first = service.play_history(recent_limit=5)
    second = service.play_history(recent_limit=5)
    pace_metric = next(
        metric for metric in first.progress.trend_metrics if metric.key == "movement_pace"
    )

    assert first == second
    assert pace_metric.earlier_value == pytest.approx(4)
    assert pace_metric.provisional is True
    assert any("outlier" in limitation for limitation in pace_metric.limitations)
    assert "active_play" not in first.model_dump_json().lower()


def test_play_history_deduplicates_source_ids(tmp_path: Path) -> None:
    repository = _DuplicateIdRepository(
        output_dir=tmp_path / "output",
        api_base_path="/api/v1",
    )
    job = _job("one", status=AnalysisStatus.completed, analytics_completed=True)
    repository.save_job(job)
    _write_analytics(
        repository,
        job.analysis_id,
        _analytics(job.analysis_id, observed=12, tracked=8),
    )

    result = HistoryProjectionService(repository=repository).play_history(recent_limit=5)

    assert result.total_analyses == 1
    assert result.eligible_count == 1
    assert result.reliable_observation_seconds == 12
    assert result.qualified_movement_seconds == 8


def test_contribution_output_is_deterministic_and_versioned() -> None:
    job = _job("stable", status=AnalysisStatus.completed, analytics_completed=True)
    analytics = _analytics(job.analysis_id)
    match_iq = _match_iq(job.analysis_id)

    first = evaluate_contribution(
        job=job,
        analytics=analytics,
        match_iq=match_iq,
        evaluated_at=NOW,
    )
    second = evaluate_contribution(
        job=job,
        analytics=analytics,
        match_iq=match_iq,
        evaluated_at=NOW,
    )

    assert first == second
    assert first.policy_version == "play-history-v1"
    assert first.source_analysis_version == "match-iq-rules-v2"


def test_history_api_uses_persisted_jobs_after_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "api-output"
    monkeypatch.setenv("PICKLEBALL_AI_ANALYSIS_OUTPUT_DIR", str(output_dir))
    get_settings.cache_clear()
    repository = AnalysisJobRepository(output_dir=output_dir, api_base_path="/api/v1")
    job = _job("persisted", status=AnalysisStatus.completed, analytics_completed=True)
    repository.save_job(job)
    _write_analytics(repository, job.analysis_id, _analytics(job.analysis_id))

    first_client = TestClient(create_app())
    first = first_client.get("/api/v1/analyses")
    refreshed_client = TestClient(create_app())
    refreshed = refreshed_client.get("/api/v1/play-history")

    assert first.status_code == 200
    assert first.json()["total"] == 1
    assert first.json()["items"][0]["analysis_id"] == "persisted"
    assert refreshed.status_code == 200
    assert refreshed.json()["eligible_count"] == 1
    assert "active_play" not in json.dumps(refreshed.json()).lower()


class _DuplicateIdRepository(AnalysisJobRepository):
    def list_job_ids(self) -> list[str]:
        return ["one", "one"]


def _repository(tmp_path: Path) -> AnalysisJobRepository:
    return AnalysisJobRepository(
        output_dir=tmp_path / "output",
        api_base_path="/api/v1",
    )


def _job(
    analysis_id: str,
    *,
    status: AnalysisStatus = AnalysisStatus.processing,
    analytics_completed: bool = False,
    readiness: RecordingQualityAssessment | None = None,
    include_readiness: bool = True,
) -> AnalysisJob:
    actual_readiness = readiness or (_readiness() if include_readiness else None)
    return AnalysisJob(
        analysis_id=analysis_id,
        status=status,
        current_stage=(AnalysisStage.analyzed if analytics_completed else AnalysisStage.inspected),
        source_video=f"uploads/{analysis_id}.mp4",
        created_at=NOW + timedelta(seconds=len(analysis_id)),
        updated_at=NOW + timedelta(minutes=1, seconds=len(analysis_id)),
        inspection_completed=True,
        calibration_completed=analytics_completed,
        tracking_completed=analytics_completed,
        player_selected=analytics_completed,
        analytics_completed=analytics_completed,
        analysis_readiness=actual_readiness,
    )


def _readiness(
    *,
    status: RecordingQualityLevel = RecordingQualityLevel.good,
    blocking: bool = False,
    coverage: float | None = 0.9,
) -> RecordingQualityAssessment:
    failure = QualityCheck(
        code="blocked",
        label="Evidence",
        status=QualityCheckStatus.failed,
        message="Blocked.",
    )
    return RecordingQualityAssessment(
        stage=PreflightStage.analysis,
        status=status,
        blocking_failures=[failure] if blocking else [],
        reason_codes=["blocked"] if blocking else [],
        analysis_signals=AnalysisQualitySignals(
            court_detection_status="detected",
            court_detection_confidence=0.9,
            calibration_completed=True,
            detected_people=2,
            selectable_candidate_count=1,
            candidate_quality="STRONG",
            player_visibility_ratio=coverage,
            tracked_duration_seconds=30,
            unobserved_gap_seconds=0,
            tracking_gap_ratio=0,
            fragment_count=1,
        ),
        assessed_at=NOW,
    )


def _analytics(
    analysis_id: str,
    *,
    observed: float = 30,
    tracked: float = 20,
    kitchen: float = 8,
    movement_mps: float = 0.6096,
) -> AnalyticsReport:
    transition = max(0.0, tracked - kitchen) / 2
    baseline = max(0.0, tracked - kitchen - transition)
    total_distance_meters = movement_mps * tracked
    return AnalyticsReport(
        analysis_id=analysis_id,
        source_tracking_report="tracking/tracking.json",
        source_observations="tracking/observations.jsonl",
        calibration_id="calibration",
        selected_player_track_id=1,
        source_fragment_count=1,
        source_raw_track_ids=[1],
        observed_duration_seconds=observed,
        unobserved_gap_seconds=0,
        distance=DistanceMetrics(
            total_distance_feet=total_distance_meters * 3.28084,
            total_distance_meters=total_distance_meters,
            average_movement_feet_per_second=movement_mps * 3.28084,
            average_movement_meters_per_second=movement_mps,
        ),
        timeline_observation_count=30,
        average_court_position=(10, 12),
        zone_occupancy=ZoneOccupancyReport(
            kitchen=ZoneOccupancyMetric(
                seconds=kitchen,
                percentage=(kitchen / tracked) * 100 if tracked else 0,
            ),
            transition_zone=ZoneOccupancyMetric(
                seconds=transition,
                percentage=(transition / tracked) * 100 if tracked else 0,
            ),
            baseline_area=ZoneOccupancyMetric(
                seconds=baseline,
                percentage=(baseline / tracked) * 100 if tracked else 0,
            ),
            tracked_time_seconds=tracked,
        ),
        artifacts=AnalyticsArtifacts(
            analytics_json="analytics.json",
            movement_summary_json="movement_summary.json",
            timeline_json="timeline.json",
            trajectory_png="trajectory.png",
            heatmap_png="heatmap.png",
        ),
        created_at=NOW + timedelta(minutes=2),
    )


def _match_iq(
    analysis_id: str,
    *,
    measurement: ConfidenceLevel = "MODERATE",
    tracking: ConfidenceLevel = "MODERATE",
    interpretation: ConfidenceLevel = "MODERATE",
) -> MatchIQReport:
    def rating(level: ConfidenceLevel) -> MatchIQConfidenceRating:
        return MatchIQConfidenceRating(level=level, rationale="Test evidence.")

    return MatchIQReport(
        analysis_id=analysis_id,
        status="generated",
        engine_version="match-iq-rules-v2",
        summary="Verified movement summary.",
        insights=[],
        focus=None,
        limitations=[],
        metrics_used=[],
        quality_gate="CAUTIOUS",
        confidence=MatchIQConfidence(
            recording=rating("MODERATE"),
            tracking=rating(tracking),
            measurement=rating(measurement),
            interpretation=rating(interpretation),
            recommendation=rating("LOW"),
        ),
        created_at=NOW + timedelta(minutes=3),
    )


def _write_analytics(
    repository: AnalysisJobRepository,
    analysis_id: str,
    analytics: AnalyticsReport,
) -> None:
    analytics_dir = repository.analysis_dir(analysis_id) / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    (analytics_dir / "analytics.json").write_text(
        json.dumps(analytics.model_dump(mode="json")),
        encoding="utf-8",
    )
    repository.register_current_artifacts(analysis_id)


def _write_match_iq(
    repository: AnalysisJobRepository,
    analysis_id: str,
    match_iq: MatchIQReport,
) -> None:
    analytics_dir = repository.analysis_dir(analysis_id) / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    (analytics_dir / "match_iq.json").write_text(
        json.dumps(match_iq.model_dump(mode="json")),
        encoding="utf-8",
    )
    repository.register_current_artifacts(analysis_id)


def _persist_qualified_report(
    repository: AnalysisJobRepository,
    analysis_id: str,
    *,
    day: int,
    tracked: float = 100,
    kitchen: float | None = None,
    movement_mps: float = 1,
    readiness: RecordingQualityAssessment | None = None,
    match_iq: MatchIQReport | None = None,
) -> None:
    timestamp = NOW + timedelta(days=day)
    job = _job(
        analysis_id,
        status=AnalysisStatus.completed,
        analytics_completed=True,
        readiness=readiness,
    ).model_copy(update={"created_at": timestamp, "updated_at": timestamp})
    repository.save_job(job)
    _write_analytics(
        repository,
        analysis_id,
        _analytics(
            analysis_id,
            observed=tracked,
            tracked=tracked,
            kitchen=tracked * 0.4 if kitchen is None else kitchen,
            movement_mps=movement_mps,
        ),
    )
    if match_iq is not None:
        _write_match_iq(repository, analysis_id, match_iq)


def test_contribution_policy_explicit_non_included_states() -> None:
    cases = [
        (
            _job(
                "unsuitable",
                status=AnalysisStatus.completed,
                analytics_completed=True,
                readiness=_readiness(
                    status=RecordingQualityLevel.unsuitable,
                    blocking=True,
                ),
            ),
            ContributionStatus.excluded,
            "UNSUITABLE_RECORDING",
        ),
        (
            _job("processing"),
            ContributionStatus.provisional,
            "ANALYSIS_IN_PROGRESS",
        ),
        (
            _job(
                "legacy",
                status=AnalysisStatus.completed,
                analytics_completed=True,
                include_readiness=False,
            ),
            ContributionStatus.not_evaluated,
            "LEGACY_EVIDENCE_UNAVAILABLE",
        ),
        (
            _job(
                "missing-coverage",
                status=AnalysisStatus.completed,
                analytics_completed=True,
                readiness=_readiness(coverage=None),
            ),
            ContributionStatus.excluded,
            "MISSING_OBSERVATION_COVERAGE",
        ),
    ]
    for job, expected_status, expected_reason in cases:
        decision = evaluate_contribution(
            job=job,
            analytics=_analytics(job.analysis_id),
            match_iq=None,
            evaluated_at=NOW,
        )

        assert decision.status == expected_status
        assert expected_reason in decision.reason_codes
