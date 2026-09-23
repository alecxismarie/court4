from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.api.v1.analyses import get_workflow_service
from app.persistence.models import Analysis, AnalysisArtifact, UploadedVideo
from app.persistence.object_storage import LocalObjectStorage, ObjectMetadata, ObjectStorageError
from app.persistence.runtime import get_persistence
from app.services.history import HistoryProjectionService
from app.services.jobs import AnalysisJobRepository, AnalysisWorkflowService
from app.services.jobs.exceptions import JobConflictError
from app.services.jobs.source_media import SourceMediaService
from tests.test_direct_uploads import _client, _register_verified_user
from tests.test_history import _match_iq, _persist_qualified_report


def test_legacy_local_source_can_be_deleted_with_s3_as_active_backend(tmp_path: Path) -> None:
    from tests.test_direct_uploads import FakeMultipartStorage

    _client_instance, legacy, _storage = setup_media(tmp_path, "local")
    hybrid = AnalysisJobRepository(
        output_dir=tmp_path / "workspace",
        api_base_path="/api/v1",
        owner_user_id=legacy.owner_user_id,
        persistence=get_persistence(),
        object_storage=FakeMultipartStorage(),
        legacy_storage_root=legacy.output_dir,
    )
    before = HistoryProjectionService(repository=hybrid).play_history(recent_limit=5)
    cached = hybrid.resolve_artifact("match-2", "uploads/source.mp4")
    assert cached.exists()
    SourceMediaService(hybrid).delete("match-2")
    assert not cached.exists()
    assert not (legacy.analysis_dir("match-2") / "uploads/source.mp4").exists()
    assert (legacy.analysis_dir("match-2") / "frames/frame_000001.jpg").exists()
    assert HistoryProjectionService(repository=hybrid).play_history(recent_limit=5) == before


def setup_media(tmp_path: Path, provider: str = "s3") -> tuple[Any, AnalysisJobRepository, Any]:
    client, upload_service, storage, owner = _client(tmp_path)
    if provider == "local":
        storage = LocalObjectStorage(tmp_path / "output")
    repo = AnalysisJobRepository(
        output_dir=tmp_path / "output",
        api_base_path="/api/v1",
        owner_user_id=owner,
        persistence=get_persistence(),
        object_storage=storage,
    )
    workflow = AnalysisWorkflowService(settings=upload_service.settings, repository=repo)
    client.app.dependency_overrides[get_workflow_service] = lambda: workflow
    for day in range(5):
        analysis_id = f"match-{day}"
        _persist_qualified_report(repo, analysis_id, day=day, match_iq=_match_iq(analysis_id))
        source = repo.analysis_dir(analysis_id) / "uploads/source.mp4"
        source.parent.mkdir(parents=True)
        source.write_bytes(f"source-{day}".encode())
        frame = source.parent.parent / "frames/frame_000001.jpg"
        frame.parent.mkdir()
        frame.write_bytes(b"independent evidence")
        repo.save_job(
            repo.load_job_metadata(analysis_id).model_copy(
                update={
                    "source_video": "uploads/source.mp4",
                    "inspection_completed": True,
                }
            )
        )
    return client, repo, storage


@pytest.mark.parametrize("provider", ["s3", "local"])
def test_media_only_deletion_retains_every_history_and_progress_input(
    tmp_path: Path, provider: str
) -> None:
    client, repo, storage = setup_media(tmp_path, provider)
    history = HistoryProjectionService(repository=repo)
    before_history = history.analysis_history(limit=100, offset=0)
    before_play = history.play_history(recent_limit=5)
    before_analytics = client.get("/api/v1/analyses/match-2/analytics").json()
    runtime = get_persistence()
    with runtime.session_factory() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        video = session.get(UploadedVideo, analysis.uploaded_video_id)
        assert video is not None
        identity = (
            video.source_checksum,
            video.storage_key,
            video.size_bytes,
            video.original_filename,
        )
        payload, version = analysis.job_payload, analysis.row_version
    response = client.delete("/api/v1/analyses/match-2/source-video")
    assert response.status_code == 204
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 204
    assert not (repo.analysis_dir("match-2") / "uploads/source.mp4").exists()
    if provider == "s3":
        assert not storage.exists(key=identity[1])
    assert history.analysis_history(limit=100, offset=0) == before_history
    assert history.play_history(recent_limit=5) == before_play
    assert before_play.progress.comparable_analysis_count == 5
    assert client.get("/api/v1/analyses/match-2/analytics").json() == before_analytics
    assert (
        repo.resolve_artifact("match-2", "frames/frame_000001.jpg").read_bytes()
        == b"independent evidence"
    )
    assert client.get("/api/v1/analyses/match-2").json()["source_media_state"] == "deleted"
    with runtime.session_factory() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None and (analysis.job_payload, analysis.row_version) == (
            payload,
            version,
        )
        video = session.get(UploadedVideo, analysis.uploaded_video_id)
        assert video is not None and video.state == "deleted"
        assert (
            video.source_checksum,
            video.storage_key,
            video.size_bytes,
            video.original_filename,
        ) == identity
        assert video.metadata_payload["source_deleted_at"]
        artifact = session.scalar(
            select(AnalysisArtifact).where(
                AnalysisArtifact.analysis_id == "match-2",
                AnalysisArtifact.artifact_kind == "source_video",
            )
        )
        assert artifact is not None and artifact.state == "deleted"
    duplicate = repo.find_uploaded_video_by_owner_and_checksum(identity[0])
    assert duplicate is not None and duplicate.existing_analysis_id == "match-2"
    unavailable = client.get("/api/v1/analyses/match-2/artifacts/uploads/source.mp4")
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "source_video_unavailable"
    assert client.post("/api/v1/analyses/match-2/court-detection").status_code == 409
    with pytest.raises(JobConflictError, match="source_video_unavailable"):
        repo.save_job(repo.load_job_metadata("match-2"))


def test_provider_failure_keeps_retryable_intent_and_never_claims_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, storage = setup_media(tmp_path)
    before = HistoryProjectionService(repository=repo).play_history(recent_limit=5)

    def fail(**kwargs: Any) -> None:
        raise ObjectStorageError("private-credential-and-provider-url")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "delete", fail)
        response = client.delete("/api/v1/analyses/match-2/source-video")
    assert response.status_code == 503
    assert "private-credential" not in response.text
    assert repo.load_job_metadata("match-2").source_media_state == "deleting"
    assert HistoryProjectionService(repository=repo).play_history(recent_limit=5) == before
    # A new service instance retries durable intent after a process interruption.
    SourceMediaService(repo).delete("match-2")
    assert repo.load_job_metadata("match-2").source_media_state == "deleted"


def test_unauthenticated_and_other_owner_are_concealed(tmp_path: Path) -> None:
    client, repo, storage = setup_media(tmp_path)
    # Use the real owner-aware workflow dependency rather than the test fixture override.
    client.app.dependency_overrides.pop(get_workflow_service)
    client.headers.pop("Authorization")
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 401
    token = _register_verified_user(client, "other-media@example.com")
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 404
    assert repo.load_job_metadata("match-2").source_media_state == "available"


def test_missing_source_is_deterministic_and_reprocessing_cannot_restore_it(tmp_path: Path) -> None:
    client, repo, storage = setup_media(tmp_path)
    source = next(key for key in storage.objects if "/match-2/" in key and "/source/" in key)
    storage.delete(key=source)
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 204
    (repo.analysis_dir("match-2") / "uploads/source.mp4").write_bytes(b"stale cached bytes")
    with pytest.raises(JobConflictError):
        repo.save_job(repo.load_job_metadata("match-2"))
    assert source not in storage.objects


def test_inflight_operation_blocks_deletion_across_repositories(tmp_path: Path) -> None:
    _client_instance, repo, storage = setup_media(tmp_path)
    other = AnalysisJobRepository(
        output_dir=repo.output_dir,
        api_base_path="/api/v1",
        owner_user_id=repo.owner_user_id,
        persistence=get_persistence(),
        object_storage=storage,
    )
    with (
        repo.media_operation("match-2"),
        pytest.raises(JobConflictError, match="source_media_busy"),
        other.media_operation("match-2", exclusive=True),
    ):
        pytest.fail("An exclusive lock cannot overlap a shared lock.")
    SourceMediaService(other).delete("match-2")


def test_deletion_cleans_exact_source_copies_in_owner_workspaces(tmp_path: Path) -> None:
    _client_instance, repo, storage = setup_media(tmp_path)
    workspace_root = tmp_path / "workspaces"
    abandoned = workspace_root / f"court4-{repo.owner_user_id}-abandoned"
    cached = abandoned / "match-2/uploads/source.mp4"
    temporary = cached.with_name(".source.mp4.court4-download")
    preserved = [
        abandoned / "match-2/frames/frame.jpg",
        abandoned / "match-2/uploads/unrelated.tmp",
        abandoned / "match-3/uploads/source.mp4",
        workspace_root / "court4-other-owner-workspace/match-2/uploads/source.mp4",
    ]
    for path in [cached, temporary, *preserved]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"retained bytes")
    deleter = AnalysisJobRepository(
        output_dir=workspace_root / f"court4-{repo.owner_user_id}-deleter",
        capacity_root=workspace_root,
        legacy_storage_root=repo.output_dir,
        api_base_path="/api/v1",
        owner_user_id=repo.owner_user_id,
        persistence=repo.persistence,
        object_storage=storage,
    )
    SourceMediaService(deleter).delete("match-2")
    assert not cached.exists()
    assert not temporary.exists()
    assert not (repo.analysis_dir("match-2") / "uploads/source.mp4").exists()
    assert all(path.read_bytes() == b"retained bytes" for path in preserved)


@pytest.mark.parametrize("download_first", [True, False])
@pytest.mark.parametrize("bulk", [True, False])
@pytest.mark.parametrize("separate_workspace", [True, False])
def test_materialization_and_deletion_are_serialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    download_first: bool,
    bulk: bool,
    separate_workspace: bool,
) -> None:
    client, repo, storage = setup_media(tmp_path)
    history = HistoryProjectionService(repository=repo)
    before_history = history.analysis_history(limit=100, offset=0)
    before_progress = history.play_history(recent_limit=5)
    before_results = client.get("/api/v1/analyses/match-2/analytics").json()
    with repo.persistence.session_factory() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        before_analysis = (analysis.job_payload, analysis.row_version, analysis.updated_at)
    workspace_root = tmp_path / "workspaces"

    def worker(name: str) -> AnalysisJobRepository:
        return AnalysisJobRepository(
            output_dir=(
                workspace_root / f"court4-{repo.owner_user_id}-{name}"
                if separate_workspace
                else repo.output_dir
            ),
            capacity_root=workspace_root if separate_workspace else repo.output_dir,
            legacy_storage_root=repo.output_dir,
            api_base_path="/api/v1",
            owner_user_id=repo.owner_user_id,
            persistence=repo.persistence,
            object_storage=storage,
        )

    reader, deleter = worker("reader"), worker("deleter")
    source = reader.analysis_dir("match-2") / "uploads/source.mp4"
    source.unlink(missing_ok=True)  # Force a provider download rather than a cache hit.
    key = next(key for key in storage.objects if "/match-2/" in key and "/source/" in key)
    entered, release, waiting, retry = Event(), Event(), Event(), Event()
    real_download, real_delete = storage.download_file, storage.delete
    source_downloads: list[str] = []

    def download(*, key: str, destination: Path) -> ObjectMetadata:
        if "/match-2/" not in key or "/source/" not in key:
            return real_download(key=key, destination=destination)
        source_downloads.append(key)
        # Capture provider bytes before deletion, pause before the local write.
        data, metadata = storage.objects[key]["data"], storage.stat(key=key)
        entered.set()
        assert release.wait(10), "Download was not released"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return metadata

    def delete(*, key: str) -> None:
        if not download_first:
            entered.set()
            assert release.wait(10), "Deletion was not released"
        real_delete(key=key)

    def wait_for_lock(_seconds: float) -> None:
        # Reached only after PostgreSQL refused the lock and the connection closed.
        waiting.set()
        assert retry.wait(10), "Waiting lock contender was not released"

    def materialize() -> Any:
        if bulk:
            return reader.load_job("match-2")
        return reader.resolve_artifact("match-2", "uploads/source.mp4")

    monkeypatch.setattr(storage, "download_file", download)
    monkeypatch.setattr(storage, "delete", delete)
    monkeypatch.setattr("app.services.jobs.repository.sleep", wait_for_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            materialize if download_first else SourceMediaService(deleter).delete,
            *(() if download_first else ("match-2",)),
        )
        second = None
        try:
            assert entered.wait(10), "First operation did not reach provider IO"
            second = pool.submit(
                SourceMediaService(deleter).delete if download_first else materialize,
                *(("match-2",) if download_first else ()),
            )
            assert waiting.wait(10), "Second operation did not wait on the media lock"
            assert not second.done()
            release.set()
            first.result(timeout=10)
            retry.set()
            if not download_first and not bulk:
                with pytest.raises(JobConflictError, match="source_video_unavailable"):
                    second.result(timeout=10)
            else:
                result = second.result(timeout=10)
                if not download_first:
                    assert result.source_media_state == "deleted"
                    assert all(a.path != "uploads/source.mp4" for a in result.available_artifacts)
        finally:
            release.set()
            retry.set()
    assert len(source_downloads) == int(download_first)
    assert key not in storage.objects
    assert not source.exists()
    assert not (repo.analysis_dir("match-2") / "uploads/source.mp4").exists()
    assert repo.load_job_metadata("match-2").source_media_state == "deleted"
    with pytest.raises(JobConflictError, match="source_video_unavailable"):
        reader.resolve_artifact("match-2", "uploads/source.mp4")
    assert client.post("/api/v1/analyses/match-2/court-detection").status_code == 409
    assert history.analysis_history(limit=100, offset=0) == before_history
    assert history.play_history(recent_limit=5) == before_progress
    assert client.get("/api/v1/analyses/match-2/analytics").json() == before_results
    with repo.persistence.session_factory() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        assert (analysis.job_payload, analysis.row_version, analysis.updated_at) == before_analysis


def test_source_media_migration_roundtrip_and_drift(tmp_path: Path) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.persistence.models import Base

    _client_instance, repo, _storage = setup_media(tmp_path)
    config = Config("alembic.ini")
    command.downgrade(config, "0010_direct_multipart")
    command.upgrade(config, "head")
    assert repo.load_job_metadata("match-2").source_media_state == "available"
    with get_persistence().engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    SourceMediaService(repo).delete("match-2")
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        command.downgrade(config, "0010_direct_multipart")
    command.upgrade(config, "head")


def test_provider_success_database_failure_is_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, repo, storage = setup_media(tmp_path)
    real_begin = repo.persistence.session_factory.begin
    calls = 0

    @contextmanager
    def failing_commit() -> Any:
        nonlocal calls
        calls += 1
        with real_begin() as session:
            yield session
            if calls == 2:
                raise RuntimeError("simulated commit interruption")

    with monkeypatch.context() as patch:
        patch.setattr(repo.persistence.session_factory, "begin", failing_commit)
        with pytest.raises(RuntimeError, match="simulated commit"):
            SourceMediaService(repo).delete("match-2")
    assert repo.load_job_metadata("match-2").source_media_state == "deleting"
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 204
    assert repo.load_job_metadata("match-2").source_media_state == "deleted"


def test_incomplete_analysis_rejected_and_padel_remains_inspection_only(tmp_path: Path) -> None:
    client, repo, storage = setup_media(tmp_path)
    with repo.persistence.session_factory.begin() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        analysis.job_payload = {**analysis.job_payload, "analytics_completed": False}
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 409
    assert repo.load_job_metadata("match-2").source_media_state == "available"
    with repo.persistence.session_factory.begin() as session:
        analysis = session.get(Analysis, "match-2")
        assert analysis is not None
        analysis.sport = "padel"
        analysis.job_payload = {**analysis.job_payload, "sport": "padel"}
    assert client.delete("/api/v1/analyses/match-2/source-video").status_code == 204
    assert client.get("/api/v1/analyses/match-2/analytics").status_code == 409
