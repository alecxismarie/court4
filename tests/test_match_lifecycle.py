from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.persistence.models import Analysis, AnalysisArtifact, AnalysisRun, UploadedVideo
from app.persistence.object_storage import ObjectStorageError
from app.services.history import HistoryProjectionService
from app.services.jobs.exceptions import JobConflictError, JobNotFoundError
from app.services.jobs.match_lifecycle import MatchLifecycleService
from app.services.jobs.source_media import SourceMediaService
from tests.test_source_media import setup_media


@pytest.mark.parametrize("provider", ["s3", "local"])
def test_whole_match_removes_content_and_recomputes_progress(tmp_path: Path, provider: str) -> None:
    client, repo, storage = setup_media(tmp_path, provider)
    history = HistoryProjectionService(repository=repo)
    before = history.play_history(recent_limit=10)
    old_job = repo.load_job_metadata("match-2")
    with repo.persistence.session_factory() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        video = session.get(UploadedVideo, analysis.uploaded_video_id)
        assert video is not None
        checksum = video.source_checksum
        assert checksum is not None
    assert client.delete("/api/v1/analyses/match-2").status_code == 204
    assert client.delete("/api/v1/analyses/match-2").status_code == 204
    assert client.get("/api/v1/analyses/match-2/lifecycle").json()["state"] == "deleted"
    for suffix in ("", "/analytics", "/frames", "/artifacts/frames/frame_000001.jpg"):
        assert client.get(f"/api/v1/analyses/match-2{suffix}").status_code == 404
    assert client.post("/api/v1/analyses/match-2/court-detection").status_code == 404
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 404
    assert history.analysis_history(limit=100, offset=0).total == 4
    after = history.play_history(recent_limit=10)
    assert after.progress.comparable_analysis_count == before.progress.comparable_analysis_count - 1
    assert "match-2" not in after.progress.contributing_analysis_ids
    assert repo.find_uploaded_video_by_owner_and_checksum(checksum) is None
    assert not any(p.is_file() for p in repo.analysis_dir("match-2").rglob("*"))
    with pytest.raises(JobNotFoundError):
        repo.save_job(old_job)
    with repo.persistence.session_factory() as session:
        assert not list(
            session.scalars(
                select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == "match-2")
            )
        )
        tombstone = session.get(Analysis, "match-2")
        assert tombstone is not None and tombstone.job_payload == {}
    assert client.get("/api/v1/analyses/match-1/analytics").status_code == 200


def test_partial_failure_hides_immediately_and_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, storage = setup_media(tmp_path)
    real_delete = storage.delete
    calls = 0

    def fail_second(*, key: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ObjectStorageError("secret-provider-url")
        real_delete(key=key)

    with monkeypatch.context() as patch:
        patch.setattr(storage, "delete", fail_second)
        response = client.delete("/api/v1/analyses/match-2")
    assert response.status_code == 503 and "secret" not in response.text
    assert MatchLifecycleService(repo).status("match-2")["state"] == "deletion_pending"
    assert (
        HistoryProjectionService(repository=repo).analysis_history(limit=100, offset=0).total == 4
    )
    assert (
        HistoryProjectionService(repository=repo).play_history(recent_limit=5).total_analyses == 4
    )
    assert client.get("/api/v1/analyses/match-2/analytics").status_code == 404
    assert client.delete("/api/v1/analyses/match-2").status_code == 204


def test_database_finalization_failure_keeps_retry_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client, repo, _storage = setup_media(tmp_path)
    begin = repo.persistence.session_factory.begin
    calls = 0

    @contextmanager
    def failing_commit() -> Any:
        nonlocal calls
        calls += 1
        with begin() as session:
            yield session
            if calls == 2:
                raise RuntimeError("commit interrupted")

    with monkeypatch.context() as patch:
        patch.setattr(repo.persistence.session_factory, "begin", failing_commit)
        with pytest.raises(RuntimeError, match="commit interrupted"):
            MatchLifecycleService(repo).delete("match-2")
    assert MatchLifecycleService(repo).status("match-2")["state"] == "deletion_pending"
    MatchLifecycleService(repo).delete("match-2")
    assert MatchLifecycleService(repo).status("match-2")["state"] == "deleted"


def test_busy_owner_safety_failed_padel_and_deleted_source(tmp_path: Path) -> None:
    from uuid import uuid4

    from app.services.jobs import AnalysisJobRepository

    _client, repo, storage = setup_media(tmp_path)
    other = AnalysisJobRepository(
        output_dir=repo.output_dir,
        api_base_path="/api/v1",
        owner_user_id=uuid4(),
        persistence=repo.persistence,
        object_storage=storage,
    )
    with pytest.raises(JobNotFoundError):
        MatchLifecycleService(other).delete("match-2")
    with repo.media_operation("match-2"), pytest.raises(JobConflictError):
        MatchLifecycleService(repo).delete("match-2")
    with repo.persistence.session_factory.begin() as session:
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.analysis_id == "match-2"))
        assert run is not None
        run.state = "processing"
    worker = AnalysisJobRepository(
        output_dir=repo.output_dir,
        api_base_path="/api/v1",
        owner_user_id=repo.owner_user_id,
        persistence=repo.persistence,
        object_storage=storage,
    )
    with (
        worker.media_operation("match-2"),
        pytest.raises(JobConflictError, match="source_media_busy"),
    ):
        MatchLifecycleService(repo).delete("match-2")
    assert MatchLifecycleService(repo).status("match-2")["state"] == "live"
    # A processing reservation waiting for user input is not an active worker.
    MatchLifecycleService(repo).delete("match-2")
    with repo.persistence.session_factory.begin() as session:
        run = session.scalar(select(AnalysisRun).where(AnalysisRun.analysis_id == "match-1"))
        assert run is not None
        run.state = "failed"
        analysis = session.get(Analysis, "match-1")
        assert analysis is not None
        analysis.state = "failed"
        padel = session.get(Analysis, "match-3")
        assert padel is not None
        padel.sport = "padel"
    MatchLifecycleService(repo).delete("match-1")
    MatchLifecycleService(repo).delete("match-3")
    SourceMediaService(repo).delete("match-4")
    MatchLifecycleService(repo).delete("match-4")


def test_media_only_removes_all_playback_versions_retains_evidence(tmp_path: Path) -> None:
    client, repo, storage = setup_media(tmp_path)
    root = repo.analysis_dir("match-2")
    for name in (
        "tracking/tracked_players.mp4",
        "ball/overlay.v1.mp4",
        "active_play/evidence.json",
        "tracking/crops/player.jpg",
        "share/card.png",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"evidence-v1")
    repo.save_job(repo.load_job_metadata("match-2"))
    (root / "tracking/tracked_players.mp4").write_bytes(b"evidence-v2")
    repo.save_job(repo.load_job_metadata("match-2"))
    before = HistoryProjectionService(repository=repo).play_history(recent_limit=5)
    staged = repo.staging_dir("match-2") / "source.mp4"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_bytes(b"abandoned staging copy")
    SourceMediaService(repo).delete("match-2")
    assert not staged.exists()
    for name in ("tracking/tracked_players.mp4", "ball/overlay.v1.mp4"):
        assert not (root / name).exists()
        assert client.get(f"/api/v1/analyses/match-2/artifacts/{name}").status_code == 409
    assert not any("/match-2/" in key and key.endswith(".mp4") for key in storage.objects)
    assert (root / "tracking/crops/player.jpg").exists()
    assert (root / "active_play/evidence.json").exists()
    assert (root / "share/card.png").exists()
    assert HistoryProjectionService(repository=repo).play_history(recent_limit=5) == before
    MatchLifecycleService(repo).delete("match-2")
    assert not any("/match-2/" in key for key in storage.objects)


def test_migration_defaults_and_downgrade_guard(tmp_path: Path) -> None:
    _client, repo, _storage = setup_media(tmp_path)
    config = Config("alembic.ini")
    command.downgrade(config, "0011_source_media")
    command.upgrade(config, "head")
    assert MatchLifecycleService(repo).status("match-2")["state"] == "live"
    MatchLifecycleService(repo).delete("match-2")
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(config, "0011_source_media")
    command.upgrade(config, "head")


def test_run_admission_cannot_race_deletion(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from app.persistence.errors import ResourceNotFoundError

    _client, repo, _storage = setup_media(tmp_path)
    entered, resume = Event(), Event()

    def before_admission(_pid: int) -> None:
        entered.set()
        assert resume.wait(10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            repo.persistence.service.start_run,
            owner_user_id=repo.owner_user_id,
            analysis_id="match-2",
            idempotency_key="racing-run",
            request_fingerprint="a" * 64,
            synchronization_hook=before_admission,
        )
        try:
            assert entered.wait(10)
            MatchLifecycleService(repo).delete("match-2")
        finally:
            resume.set()
        with pytest.raises(ResourceNotFoundError):
            future.result(timeout=10)
    assert MatchLifecycleService(repo).status("match-2")["state"] == "deleted"


def test_untrusted_registry_key_never_deletes_other_match(tmp_path: Path) -> None:
    _client, repo, storage = setup_media(tmp_path)
    with repo.persistence.session_factory.begin() as session:
        first = session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.analysis_id == "match-1",
                AnalysisArtifact.artifact_kind == "source_video",
            )
        )
        target = session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.analysis_id == "match-2",
                AnalysisArtifact.artifact_kind == "source_video",
            )
        )
        assert first is not None and target is not None
        other_key = first.storage_key
        target.storage_key = other_key
    with pytest.raises(JobConflictError, match="unsafe_media_key"):
        MatchLifecycleService(repo).delete("match-2")
    assert other_key in storage.objects


def test_fresh_reupload_and_old_idempotency_after_deletion(
    tmp_path: Path, synthetic_video_factory: Any
) -> None:
    from app.schemas.uploads import InitiateUploadRequest
    from app.services.jobs import AnalysisJobRepository
    from tests.test_direct_uploads import _client, _direct_round_trip, _metadata

    client, service, storage, owner = _client(tmp_path)
    data = synthetic_video_factory(tmp_path / "duplicate.avi", frame_count=5).read_bytes()
    first = _direct_round_trip(client, storage, data, "first")
    again = _direct_round_trip(client, storage, data, "again", reanalyze=True)
    repo = AnalysisJobRepository.from_settings(
        settings=service.settings,
        owner_user_id=owner,
        persistence=service.persistence,
        object_storage=storage,
    )
    storage.fail_delete = True
    assert _direct_round_trip(client, storage, data, "duplicate") is None
    pending = client.get("/api/v1/uploads/recoverable").json()[0]
    storage.fail_delete = False
    MatchLifecycleService(repo).delete(first["analysis_id"])
    MatchLifecycleService(repo).delete(again["analysis_id"])
    # Cleanup still owns only the extra upload, even if its target was removed.
    assert (
        client.post(f"/api/v1/uploads/{pending['upload_session_id']}/retry-cleanup").status_code
        == 200
    )
    with pytest.raises(JobConflictError, match="match_deleted"):
        service.initiate(
            owner_user_id=owner,
            idempotency_key="first",
            request=InitiateUploadRequest.model_validate(
                {
                    **_metadata(
                        filename="duplicate.avi",
                        content_type="video/x-msvideo",
                        byte_size=len(data),
                    ),
                    "reanalyze": False,
                }
            ),
        )
    fresh = _direct_round_trip(client, storage, data, "fresh")
    assert fresh["analysis_id"] not in {first["analysis_id"], again["analysis_id"]}
