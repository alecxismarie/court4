from __future__ import annotations

import hashlib
import io
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config.settings import Settings
from app.persistence.errors import PersistenceConfigurationError
from app.persistence.models import Analysis, AnalysisArtifact, UploadedVideo
from app.persistence.object_storage import (
    LocalObjectStorage,
    ObjectMetadata,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    S3ObjectStorage,
    artifact_object_key,
    source_object_key,
    validate_object_key,
)
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.services.jobs.exceptions import JobStorageBackendError
from app.services.jobs.repository import AnalysisJobRepository
from scripts.workspace_cleanup import CONFIRMATION, run_cleanup

OWNER_A = UUID("11111111-1111-4111-8111-111111111111")
OWNER_B = UUID("22222222-2222-4222-8222-222222222222")


def test_object_keys_are_deterministic_owner_scoped_and_attempt_safe() -> None:
    checksum = hashlib.sha256(b"artifact").hexdigest()
    source = source_object_key(OWNER_A, "analysis-1", ".MP4")
    first = artifact_object_key(
        OWNER_A,
        "analysis-1",
        "ball/attempt-0001/tracking-report.v1.json",
        checksum,
    )
    retry = artifact_object_key(
        OWNER_A,
        "analysis-1",
        "ball/attempt-0002/tracking-report.v1.json",
        checksum,
    )

    assert source == f"users/{OWNER_A}/analyses/analysis-1/source/video.mp4"
    assert first == artifact_object_key(
        OWNER_A,
        "analysis-1",
        "ball/attempt-0001/tracking-report.v1.json",
        checksum,
    )
    assert str(OWNER_A) in first
    assert artifact_object_key(OWNER_B, "analysis-1", "report.json", checksum) != first
    assert first != retry
    assert "attempt-0001" in first and "attempt-0002" in retry


@pytest.mark.parametrize("value", ["../source.mp4", "/source.mp4", "a/../../source.mp4", ""])
def test_object_keys_reject_path_traversal(value: str) -> None:
    with pytest.raises(PersistenceConfigurationError):
        validate_object_key(value)


def test_local_object_storage_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"private-video")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()

    stored = storage.put_file(
        key="users/owner/source/video.mp4",
        source=source,
        content_type="video/mp4",
        checksum_sha256=checksum,
    )
    destination = tmp_path / "workspace" / "video.mp4"
    downloaded = storage.download_file(key=stored.key, destination=destination)

    assert storage.ready() is True
    assert storage.exists(key=stored.key) is True
    assert destination.read_bytes() == b"private-video"
    assert downloaded.checksum_sha256 == checksum
    storage.delete(key=stored.key)
    assert storage.exists(key=stored.key) is False
    with pytest.raises(ObjectNotFoundError):
        storage.download_file(key=stored.key, destination=destination)


def test_local_storage_rejects_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"private-video")
    with pytest.raises(ObjectStorageError, match="checksum"):
        LocalObjectStorage(tmp_path / "objects").put_file(
            key="source/video.mp4",
            source=source,
            content_type="video/mp4",
            checksum_sha256="0" * 64,
        )


def test_s3_backend_round_trip_is_private_and_verifies_metadata(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = S3ObjectStorage(client=client, bucket="private-court4")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"s3-private-video")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()

    stored = storage.put_file(
        key="users/owner/analyses/analysis/source/video.mp4",
        source=source,
        content_type="video/mp4",
        checksum_sha256=checksum,
    )
    destination = tmp_path / "workspace" / "source.mp4"
    storage.download_file(key=stored.key, destination=destination)

    assert destination.read_bytes() == source.read_bytes()
    assert client.upload_extra_args == {
        "ContentType": "video/mp4",
        "Metadata": {"court4-sha256": checksum},
    }
    assert "ACL" not in client.upload_extra_args
    assert storage.stat(key=stored.key).provider_version == "test-version"
    storage.delete(key=stored.key)
    assert storage.exists(key=stored.key) is False


def test_s3_errors_do_not_log_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "app.persistence.object_storage.logger.warning",
        lambda *args, **kwargs: logged.append((*args, kwargs)),
    )
    storage = S3ObjectStorage(client=FailingS3Client(), bucket="private-court4")
    with pytest.raises(ObjectStorageError):
        storage.stat(key="users/owner/source.mp4")
    rendered = repr(logged)
    assert "highly-secret-credential" not in rendered
    assert "private_object_storage_operation_failed" in rendered


def test_s3_multipart_contract_presigns_completes_streams_and_aborts() -> None:
    client = FakeS3Client()
    client.multipart_data = b"direct-multipart-video"
    storage = S3ObjectStorage(client=client, bucket="private-court4")
    key = "users/owner/analyses/direct/source/video.mp4"

    upload_id = storage.initiate_multipart_upload(
        key=key,
        content_type="video/mp4",
        upload_session_id="session-123",
        declared_size=len(client.multipart_data),
    )
    url = storage.presign_upload_part(key=key, upload_id=upload_id, part_number=1, expires_in=900)
    storage.complete_multipart_upload(
        key=key,
        upload_id=upload_id,
        parts=[{"PartNumber": 1, "ETag": '"part-etag"'}],
    )
    head = storage.head_upload(key=key)
    checksum = storage.calculate_sha256(key=key, chunk_size=4)
    verified = storage.set_verified_checksum(key=key, checksum_sha256=checksum)

    assert url == "https://private.test/upload-part"
    assert head.size_bytes == len(client.multipart_data)
    assert head.custom_metadata == {
        "court4-upload-session": "session-123",
        "court4-declared-size": str(len(client.multipart_data)),
    }
    assert checksum == hashlib.sha256(client.multipart_data).hexdigest()
    assert verified.checksum_sha256 == checksum
    assert client.presign_params == {
        "Bucket": "private-court4",
        "Key": key,
        "UploadId": upload_id,
        "PartNumber": 1,
    }

    second = storage.initiate_multipart_upload(
        key="users/owner/analyses/aborted/source/video.mp4",
        content_type="video/mp4",
        upload_session_id="session-abort",
        declared_size=10,
    )
    storage.abort_multipart_upload(
        key="users/owner/analyses/aborted/source/video.mp4", upload_id=second
    )
    storage.abort_multipart_upload(
        key="users/owner/analyses/aborted/source/video.mp4", upload_id=second
    )
    assert second in client.aborted_upload_ids
    assert client.aborted_upload_ids.count(second) == 1


def test_s3_configuration_is_explicit_and_secrets_remain_wrapped() -> None:
    with pytest.raises(ValidationError, match="STORAGE_S3_ENDPOINT"):
        Settings.model_validate({"storage_backend": "s3"})

    settings = Settings.model_validate(
        {
            "storage_backend": "s3",
            "storage_s3_endpoint": "https://objects.example.test",
            "storage_s3_region": "eu-west-1",
            "storage_s3_bucket": "court4-private",
            "storage_s3_access_key_id": "access-id",
            "storage_s3_secret_access_key": "highly-secret-credential",
        }
    )
    assert settings.storage_s3_secret_access_key is not None
    assert "highly-secret-credential" not in repr(settings)
    assert settings.storage_backend == "s3"
    assert Settings().storage_backend == "local"


def test_temporary_repository_workspace_is_removed_on_close(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace" / "request-1"
    workspace.mkdir(parents=True)
    (workspace / "scratch.bin").write_bytes(b"scratch")
    persistence = cast(PersistenceRuntime, SimpleNamespace())
    repository = AnalysisJobRepository(
        output_dir=workspace,
        api_base_path="/api/v1",
        owner_user_id=OWNER_A,
        persistence=persistence,
        object_storage=cast(ObjectStorage, SimpleNamespace(provider="s3")),
        cleanup_workspace=True,
    )

    repository.close()
    assert not workspace.exists()
    repository.close()


def test_s3_repository_persists_locator_and_rematerializes_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = get_persistence()
    storage = MemoryObjectStorage()
    monkeypatch.setattr(
        "app.services.jobs.repository.build_object_storage",
        lambda settings: storage,
    )
    settings = Settings.model_validate(
        {
            "storage_backend": "s3",
            "storage_s3_endpoint": "https://objects.example.test",
            "storage_s3_region": "eu-west-1",
            "storage_s3_bucket": "court4-private",
            "storage_s3_access_key_id": "access-id",
            "storage_s3_secret_access_key": "secret",
            "processing_workspace_root": tmp_path / "workspace",
            "local_storage_root": tmp_path / "legacy",
            "storage_warning_free_bytes": 1_000,
            "storage_hard_stop_free_bytes": 1,
        }
    )
    job = AnalysisJob(
        analysis_id="s3-lifecycle",
        status=AnalysisStatus.processing,
        current_stage=AnalysisStage.inspected,
        source_video="uploads/source.mp4",
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
        updated_at=datetime(2026, 8, 30, tzinfo=UTC),
        inspection_completed=True,
    )
    runtime.service.reserve_analysis(
        owner_user_id=runtime.owner_user_id,
        analysis_id=job.analysis_id,
        idempotency_key=job.analysis_id,
        request_fingerprint="a" * 64,
        original_filename="display-name.mp4",
        content_type="video/mp4",
        size_bytes=13,
        source_checksum=hashlib.sha256(b"durable-video").hexdigest(),
        job_payload=job.model_dump(mode="json"),
    )
    repository = AnalysisJobRepository.from_settings(
        settings=settings,
        owner_user_id=runtime.owner_user_id,
        persistence=runtime,
    )
    original_workspace = repository.output_dir
    source = repository.analysis_dir(job.analysis_id) / "uploads" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"durable-video")
    report = repository.analysis_dir(job.analysis_id) / "metadata.json"
    report.write_text("{}", encoding="utf-8")
    repository.save_job(job)

    with runtime.session_factory() as session:
        analysis = session.get(Analysis, job.analysis_id)
        assert analysis is not None
        video = session.get(UploadedVideo, analysis.uploaded_video_id)
        artifacts = list(
            session.scalars(
                select(AnalysisArtifact).where(AnalysisArtifact.analysis_id == job.analysis_id)
            )
        )
    assert video is not None
    assert video.storage_provider == "s3"
    assert video.storage_key is not None
    assert video.storage_key.startswith(f"users/{runtime.owner_user_id}/analyses/s3-lifecycle/")
    assert {artifact.logical_key for artifact in artifacts} == {
        "metadata.json",
        "uploads/source.mp4",
    }
    assert all(artifact.storage_provider == "s3" for artifact in artifacts)
    assert all(key in storage.objects for key in (artifact.storage_key for artifact in artifacts))
    repository.close()
    assert not original_workspace.exists()

    second = AnalysisJobRepository.from_settings(
        settings=settings,
        owner_user_id=runtime.owner_user_id,
        persistence=runtime,
    )
    second_workspace = second.output_dir
    loaded = second.load_job(job.analysis_id)
    assert loaded.source_video == "uploads/source.mp4"
    materialized = second.resolve_artifact(job.analysis_id, loaded.source_video)
    assert materialized.read_bytes() == b"durable-video"
    second.close()
    assert not second_workspace.exists()


def test_stale_workspace_cleanup_is_dry_run_first_and_scoped(tmp_path: Path) -> None:
    root = tmp_path / "workspace-root"
    expired = root / "court4-owner-expired"
    ignored = root / "unrelated-directory"
    expired.mkdir(parents=True)
    ignored.mkdir()
    (expired / "source.mp4").write_bytes(b"expired")
    (ignored / "keep.txt").write_text("keep", encoding="utf-8")
    old_timestamp = datetime.now(tz=UTC).timestamp() - 48 * 60 * 60
    os.utime(expired / "source.mp4", (old_timestamp, old_timestamp))
    os.utime(expired, (old_timestamp, old_timestamp))

    dry_run = run_cleanup(
        root,
        older_than_hours=24,
        apply=False,
        confirmation=None,
        max_files=10,
        max_bytes=1_000,
    )
    assert dry_run.expired_directories == ("court4-owner-expired",)
    assert expired.exists()

    applied = run_cleanup(
        root,
        older_than_hours=24,
        apply=True,
        confirmation=CONFIRMATION,
        max_files=10,
        max_bytes=1_000,
    )
    assert applied.quarantined_directories == ("_quarantine/workspaces/court4-owner-expired",)
    assert ignored.is_dir()


def test_repository_translates_object_backend_failure(tmp_path: Path) -> None:
    persistence = cast(PersistenceRuntime, SimpleNamespace())
    repository = AnalysisJobRepository(
        output_dir=tmp_path / "workspace",
        api_base_path="/api/v1",
        owner_user_id=OWNER_A,
        persistence=persistence,
        object_storage=FailingObjectStorage(),
    )
    source = repository.analysis_dir("backend-failure") / "uploads" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    now = datetime.now(tz=UTC)
    job = AnalysisJob(
        analysis_id="backend-failure",
        status=AnalysisStatus.processing,
        current_stage=AnalysisStage.uploaded,
        source_video="uploads/source.mp4",
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(JobStorageBackendError) as captured:
        repository.save_job(job)
    assert captured.value.status_code == 503


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, Any]]] = {}
        self.upload_extra_args: dict[str, Any] = {}
        self.multipart_uploads: dict[str, dict[str, Any]] = {}
        self.multipart_data = b""
        self.presign_params: dict[str, Any] = {}
        self.aborted_upload_ids: list[str] = []

    def head_bucket(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, Any],
    ) -> None:
        self.upload_extra_args = ExtraArgs
        self.objects[(bucket, key)] = (Path(filename).read_bytes(), ExtraArgs)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            data, extra = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeClientError("NoSuchKey") from exc
        return {
            "ContentLength": len(data),
            "ContentType": extra["ContentType"],
            "Metadata": extra["Metadata"],
            "VersionId": "test-version",
        }

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        try:
            data, _extra = self.objects[(bucket, key)]
        except KeyError as exc:
            raise FakeClientError("NoSuchKey") from exc
        Path(filename).write_bytes(data)

    def delete_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.objects.pop((Bucket, Key), None)
        return {}

    def create_multipart_upload(
        self, *, Bucket: str, Key: str, ContentType: str, Metadata: dict[str, str]
    ) -> dict[str, str]:
        upload_id = f"upload-{len(self.multipart_uploads) + 1}"
        self.multipart_uploads[upload_id] = {
            "bucket": Bucket,
            "key": Key,
            "content_type": ContentType,
            "metadata": Metadata,
        }
        return {"UploadId": upload_id}

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
        HttpMethod: str,
    ) -> str:
        assert operation == "upload_part"
        assert ExpiresIn == 900
        assert HttpMethod == "PUT"
        self.presign_params = Params
        return "https://private.test/upload-part"

    def complete_multipart_upload(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        MultipartUpload: dict[str, Any],
    ) -> dict[str, str]:
        assert MultipartUpload["Parts"]
        upload = self.multipart_uploads[UploadId]
        assert upload["bucket"] == Bucket
        assert upload["key"] == Key
        extra = {
            "ContentType": upload["content_type"],
            "Metadata": dict(upload["metadata"]),
        }
        self.objects[(Bucket, Key)] = (self.multipart_data, extra)
        return {"ETag": '"multipart-etag"'}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        data, _extra = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(data)}

    def copy_object(
        self,
        *,
        Bucket: str,
        Key: str,
        CopySource: dict[str, str],
        Metadata: dict[str, str],
        MetadataDirective: str,
        ContentType: str,
    ) -> dict[str, Any]:
        assert CopySource == {"Bucket": Bucket, "Key": Key}
        assert MetadataDirective == "REPLACE"
        data, _extra = self.objects[(Bucket, Key)]
        self.objects[(Bucket, Key)] = (
            data,
            {"ContentType": ContentType, "Metadata": Metadata},
        )
        return {}

    def abort_multipart_upload(self, *, Bucket: str, Key: str, UploadId: str) -> dict[str, Any]:
        try:
            upload = self.multipart_uploads.pop(UploadId)
        except KeyError as exc:
            raise FakeClientError("NoSuchUpload") from exc
        assert upload["bucket"] == Bucket
        assert upload["key"] == Key
        self.aborted_upload_ids.append(UploadId)
        return {}


class FailingS3Client:
    def head_object(self, **kwargs: Any) -> None:
        del kwargs
        raise RuntimeError("highly-secret-credential")


class FakeClientError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class MemoryObjectStorage:
    provider = "s3"

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, ObjectMetadata]] = {}

    def ready(self) -> bool:
        return True

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        data = source.read_bytes()
        metadata = ObjectMetadata(
            key=key,
            size_bytes=len(data),
            checksum_sha256=checksum_sha256,
            content_type=content_type,
            provider_version="memory-v1",
        )
        self.objects[key] = (data, metadata)
        return metadata

    def download_file(self, *, key: str, destination: Path) -> ObjectMetadata:
        try:
            data, metadata = self.objects[key]
        except KeyError as exc:
            raise ObjectNotFoundError("Private object was not found.") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return metadata

    def stat(self, *, key: str) -> ObjectMetadata:
        try:
            return self.objects[key][1]
        except KeyError as exc:
            raise ObjectNotFoundError("Private object was not found.") from exc

    def exists(self, *, key: str) -> bool:
        return key in self.objects

    def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)


class FailingObjectStorage(MemoryObjectStorage):
    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        del key, source, content_type, checksum_sha256
        raise ObjectStorageError("provider failed")
