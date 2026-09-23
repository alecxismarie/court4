from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.v1.uploads import get_upload_service
from app.config.settings import Settings
from app.main import create_app
from app.persistence.models import Analysis, UploadedVideo, UploadSession, User
from app.persistence.object_storage import (
    ObjectMetadata,
    ObjectNotFoundError,
    ObjectStorageError,
    UploadObjectMetadata,
)
from app.persistence.runtime import get_persistence
from app.schemas.uploads import CompletedUploadPart, CompleteUploadRequest, InitiateUploadRequest
from app.services.jobs.exceptions import (
    JobConflictError,
    JobRequestError,
    JobStorageBackendError,
    JobStorageCapacityError,
)
from app.services.uploads import DirectUploadService
from scripts.reconcile_multipart_uploads import reconcile_expired_multipart_uploads


@pytest.mark.parametrize("status", ["completed", "failed", "aborted", "expired"])
def test_terminal_session_permits_next_upload(tmp_path: Path, status: str) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    request = InitiateUploadRequest.model_validate(_metadata())
    first = service.initiate(owner_user_id=owner, request=request, idempotency_key="first")
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None
        record.status = status
        record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    second = service.initiate(owner_user_id=owner, request=request, idempotency_key="second")
    assert second.upload_session_id != first.upload_session_id
    if status == "expired":
        assert f"upload-{first.upload_session_id}" not in storage.uploads


def test_abandoned_upload_recovers_on_new_initiation_after_restart(tmp_path: Path) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    request = InitiateUploadRequest.model_validate(_metadata())
    first = service.initiate(owner_user_id=owner, request=request, idempotency_key="abandoned")
    restarted = DirectUploadService(
        settings=service.settings, persistence=get_persistence(), storage=storage
    )
    with pytest.raises(JobStorageCapacityError):
        restarted.initiate(owner_user_id=owner, request=request, idempotency_key="new")
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None
        record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    second = restarted.initiate(owner_user_id=owner, request=request, idempotency_key="new")
    assert second.upload_session_id != first.upload_session_id
    assert f"upload-{first.upload_session_id}" not in storage.uploads
    with get_persistence().session_factory() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None and record.status == "expired"
    with pytest.raises(JobStorageCapacityError):
        service.initiate(owner_user_id=owner, request=request, idempotency_key="third")


@pytest.mark.parametrize("abandoned", [False, True])
def test_concurrent_initiations_have_exactly_one_winner(tmp_path: Path, abandoned: bool) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    if abandoned:
        first = service.initiate(
            owner_user_id=owner,
            request=InitiateUploadRequest.model_validate(_metadata()),
            idempotency_key="abandoned",
        )
        with get_persistence().session_factory.begin() as session:
            record = session.get(UploadSession, first.upload_session_id)
            assert record is not None
            record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    barrier = threading.Barrier(2)

    def initiate(key: str) -> str:
        worker = DirectUploadService(
            settings=service.settings, persistence=get_persistence(), storage=storage
        )
        barrier.wait(timeout=5)
        try:
            worker.initiate(
                owner_user_id=owner,
                request=InitiateUploadRequest.model_validate(_metadata()),
                idempotency_key=key,
            )
            return "admitted"
        except JobStorageCapacityError:
            return "busy"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(initiate, ["one", "two"])) == ["admitted", "busy"]
    assert len(storage.uploads) == 1


def test_reconciliation_aborts_provider_and_database_under_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import reconcile_multipart_uploads as reconciliation

    _client_instance, service, storage, owner = _client(tmp_path)
    first = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata()),
        idempotency_key="reconcile",
    )
    assert first.upload_session_id is not None
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None
        record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    runtime = replace(get_persistence(), storage=storage)
    monkeypatch.setattr(reconciliation, "get_persistence", lambda: runtime)
    report = reconciliation.reconcile_expired_multipart_uploads(
        apply=True, confirmation=reconciliation.CONFIRMATION, max_sessions=1
    )
    assert report.aborted_session_ids == (str(first.upload_session_id),)
    assert not storage.uploads
    with runtime.session_factory() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None and record.status == "aborted"


def test_reconciliation_stale_snapshot_cannot_abort_completion(tmp_path: Path) -> None:
    from scripts.reconcile_multipart_uploads import _mark_aborted

    _client_instance, service, storage, owner = _client(tmp_path)
    first = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata()),
        idempotency_key="stale-reconcile",
    )
    assert first.upload_session_id is not None
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None
        record.status = "completing"
        record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert not _mark_aborted(first.upload_session_id, datetime.now(tz=UTC), storage)
    assert len(storage.uploads) == 1


def test_owner_admission_and_expiration_are_isolated(tmp_path: Path) -> None:
    client, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    request = InitiateUploadRequest.model_validate(_metadata())
    first = service.initiate(owner_user_id=owner, request=request, idempotency_key="owner-a")
    token = _register_verified_user(client, "owner-b@example.com")
    client.headers["Authorization"] = f"Bearer {token}"
    second = client.post(
        "/api/v1/uploads/initiate", headers={"Idempotency-Key": "owner-b"}, json=_metadata()
    )
    assert second.status_code == 201
    assert client.delete(f"/api/v1/uploads/{first.upload_session_id}").status_code == 404
    assert f"upload-{first.upload_session_id}" in storage.uploads
    assert len(storage.uploads) == 2


def test_expiry_provider_failure_keeps_admission_closed_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    request = InitiateUploadRequest.model_validate(_metadata())
    first = service.initiate(owner_user_id=owner, request=request, idempotency_key="old")
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None
        record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)

    def fail_abort(**kwargs: Any) -> None:
        raise ObjectStorageError("private-provider-secret")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "abort_multipart_upload", fail_abort)
        with pytest.raises(JobStorageBackendError, match="Please retry") as error:
            service.initiate(owner_user_id=owner, request=request, idempotency_key="new")
        assert "private-provider-secret" not in str(error.value)
    assert len(storage.uploads) == 1
    service.initiate(owner_user_id=owner, request=request, idempotency_key="new")
    assert len(storage.uploads) == 1


def test_failed_cancel_durably_fences_completion_and_next_attempt_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    service.settings.storage_max_active_uploads = 1
    request = InitiateUploadRequest.model_validate(_metadata())
    first = service.initiate(owner_user_id=owner, request=request, idempotency_key="cancel")
    assert first.upload_session_id is not None

    def fail_abort(**kwargs: Any) -> None:
        raise ObjectStorageError("provider-unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(storage, "abort_multipart_upload", fail_abort)
        with pytest.raises(JobStorageBackendError):
            service.abort(owner_user_id=owner, upload_session_id=first.upload_session_id)
    with get_persistence().session_factory() as session:
        record = session.get(UploadSession, first.upload_session_id)
        assert record is not None and record.status == "expired"
        assert record.failure_reason == "upload_cancel_requested"
    with pytest.raises(JobConflictError):
        service.complete(
            owner_user_id=owner,
            upload_session_id=first.upload_session_id,
            request=CompleteUploadRequest(parts=[CompletedUploadPart(part_number=1, etag="x")]),
        )
    assert storage.completion_calls == 0
    service.initiate(owner_user_id=owner, request=request, idempotency_key="next")
    assert len(storage.uploads) == 1


def test_initiate_requires_authentication(tmp_path: Path) -> None:
    client, _service, _storage, _owner = _client(tmp_path)
    client.headers.pop("Authorization")

    response = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "unauthenticated"},
        json=_metadata(),
    )

    assert response.status_code == 401


def test_initiate_validates_metadata_and_presigns_only_intended_parts(tmp_path: Path) -> None:
    client, _service, storage, _owner = _client(tmp_path)

    invalid = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "bad-type"},
        json={**_metadata(), "content_type": "text/plain"},
    )
    too_large = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "too-large"},
        json={**_metadata(), "byte_size": 1_073_741_825},
    )
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "valid-initiate"},
        json=_metadata(byte_size=8_388_609),
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "unsupported_media_type"
    assert too_large.status_code == 413
    assert initiated.status_code == 201
    payload = initiated.json()
    assert payload["transport"] == "direct"
    assert payload["part_size"] == 8_388_608
    assert payload["part_count"] == 2
    assert [part["part_number"] for part in payload["parts"]] == [1, 2]
    assert all("private.test" in part["url"] for part in payload["parts"])
    assert "access-id" not in initiated.text
    assert "secret" not in initiated.text
    assert storage.presigned == [1, 2]


def test_initiate_rejects_invalid_sport_and_extension(tmp_path: Path) -> None:
    client, _service, _storage, _owner = _client(tmp_path)

    invalid_sport = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "bad-sport"},
        json={**_metadata(), "sport": "tennis"},
    )
    invalid_extension = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "bad-extension"},
        json=_metadata(filename="match.exe"),
    )

    assert invalid_sport.status_code == 422
    assert invalid_extension.status_code == 400
    assert invalid_extension.json()["error"]["code"] == "unsupported_extension"


def test_initiate_is_idempotent_and_rejects_metadata_reuse(tmp_path: Path) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    headers = {"Idempotency-Key": "same-initiation"}

    first = client.post("/api/v1/uploads/initiate", headers=headers, json=_metadata())
    repeated = client.post("/api/v1/uploads/initiate", headers=headers, json=_metadata())
    conflict = client.post(
        "/api/v1/uploads/initiate",
        headers=headers,
        json=_metadata(byte_size=2_000),
    )

    assert first.status_code == repeated.status_code == 201
    assert first.json()["upload_session_id"] == repeated.json()["upload_session_id"]
    assert len(storage.uploads) == 1
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "upload_idempotency_conflict"


def test_complete_verifies_checksum_then_creates_analysis(
    tmp_path: Path,
    synthetic_video_factory: Any,
) -> None:
    client, _service, storage, owner = _client(tmp_path)
    video = synthetic_video_factory(tmp_path / "direct.avi", frame_count=5)
    data = video.read_bytes()
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "happy"},
        json=_metadata(filename="direct.avi", content_type="video/x-msvideo", byte_size=len(data)),
    ).json()
    storage.completed_data = data

    completed = client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json={"parts": [{"part_number": 1, "etag": '"part-etag"'}]},
    )
    status = client.get(f"/api/v1/uploads/{initiated['upload_session_id']}")

    assert completed.status_code == 202
    assert completed.json()["status"] == "verifying"
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["verified_sha256"] == hashlib.sha256(data).hexdigest()
    assert payload["result"]["analysis_id"] == initiated["upload_session_id"].replace("-", "")
    with get_persistence().session_factory() as session:
        analysis = session.get(Analysis, payload["result"]["analysis_id"])
        assert analysis is not None
        assert analysis.owner_user_id == owner
        video_record = session.get(UploadedVideo, analysis.uploaded_video_id)
        assert video_record is not None
        assert video_record.storage_provider == "s3"
        assert video_record.source_checksum == hashlib.sha256(data).hexdigest()


def test_checksum_mismatch_fails_without_creating_analysis(
    tmp_path: Path,
    synthetic_video_factory: Any,
) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    data = synthetic_video_factory(tmp_path / "mismatch.avi", frame_count=5).read_bytes()
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "mismatch"},
        json={
            **_metadata(
                filename="mismatch.avi",
                content_type="video/x-msvideo",
                byte_size=len(data),
            ),
            "expected_sha256": "0" * 64,
        },
    ).json()
    storage.completed_data = data

    client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json={"parts": [{"part_number": 1, "etag": '"etag"'}]},
    )
    status = client.get(f"/api/v1/uploads/{initiated['upload_session_id']}").json()

    assert status["status"] == "failed"
    assert status["failure_code"] == "checksum_mismatch"
    with get_persistence().session_factory() as session:
        assert session.get(Analysis, initiated["upload_session_id"].replace("-", "")) is None


def test_completion_requires_every_part_and_analysis_does_not_exist_before_verification(
    tmp_path: Path,
) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    request = InitiateUploadRequest.model_validate(_metadata(byte_size=8_388_609))
    initiated = service.initiate(
        owner_user_id=owner, request=request, idempotency_key="parts-required"
    )
    assert initiated.upload_session_id is not None
    with pytest.raises(JobRequestError, match="Every multipart upload part"):
        service.complete(
            owner_user_id=owner,
            upload_session_id=initiated.upload_session_id,
            request=CompleteUploadRequest(
                parts=[CompletedUploadPart(part_number=1, etag='"etag"')]
            ),
        )

    small = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata(byte_size=4)),
        idempotency_key="pre-verification",
    )
    assert small.upload_session_id is not None
    storage.completed_data = b"data"
    response = service.complete(
        owner_user_id=owner,
        upload_session_id=small.upload_session_id,
        request=CompleteUploadRequest(parts=[CompletedUploadPart(part_number=1, etag='"etag"')]),
    )
    assert response.status == "verifying"
    with get_persistence().session_factory() as session:
        assert session.get(Analysis, small.upload_session_id.hex) is None


def test_completion_size_mismatch_fails_without_analysis(tmp_path: Path) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "size-mismatch"},
        json=_metadata(byte_size=4),
    ).json()
    storage.completed_data = b"wrong-size"

    response = client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json={"parts": [{"part_number": 1, "etag": '"etag"'}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "object_verification_failed"
    with get_persistence().session_factory() as session:
        upload = session.get(UploadSession, UUID(initiated["upload_session_id"]))
        assert upload is not None
        assert upload.status == "failed"
        assert session.get(Analysis, UUID(initiated["upload_session_id"]).hex) is None


def test_repeated_completion_returns_the_existing_result(
    tmp_path: Path, synthetic_video_factory: Any
) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    data = synthetic_video_factory(tmp_path / "repeated.avi", frame_count=5).read_bytes()
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "repeated-completion"},
        json=_metadata(
            filename="repeated.avi", content_type="video/x-msvideo", byte_size=len(data)
        ),
    ).json()
    storage.completed_data = data
    completion_body = {"parts": [{"part_number": 1, "etag": '"etag"'}]}

    first = client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json=completion_body,
    )
    repeated = client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json=completion_body,
    )

    assert first.status_code == 202
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "completed"
    assert repeated.json()["result"]["analysis_id"] == UUID(initiated["upload_session_id"]).hex
    assert storage.completion_calls == 1


def test_abort_is_idempotent_and_owner_is_concealed(tmp_path: Path) -> None:
    client, _service, _storage, _owner = _client(tmp_path)
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "abort"},
        json=_metadata(),
    ).json()

    first = client.delete(f"/api/v1/uploads/{initiated['upload_session_id']}")
    second = client.delete(f"/api/v1/uploads/{initiated['upload_session_id']}")
    other_token = _register_verified_user(client, "other-upload-owner@example.com")
    client.headers["Authorization"] = f"Bearer {other_token}"
    concealed = client.get(f"/api/v1/uploads/{initiated['upload_session_id']}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "aborted"
    assert concealed.status_code == 404


def test_duplicate_completion_preserves_existing_duplicate_semantics(
    tmp_path: Path,
    synthetic_video_factory: Any,
) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    data = synthetic_video_factory(tmp_path / "duplicate.avi", frame_count=5).read_bytes()

    first = _direct_round_trip(client, storage, data, "duplicate-first")
    second = _direct_round_trip(client, storage, data, "duplicate-second")

    assert "analysis_id" in first
    assert second["status"] == "duplicate"
    assert second["existing_analysis_id"] == first["analysis_id"]


def test_provider_failure_is_sanitized(tmp_path: Path) -> None:
    client, _service, storage, _owner = _client(tmp_path)
    storage.fail_initiate = True

    response = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": "provider-failure"},
        json=_metadata(),
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "storage_backend_unavailable",
        "message": "Direct upload could not be initiated.",
    }
    assert "highly-secret-provider-error" not in response.text


def test_expired_reconciliation_is_dry_run_by_default(tmp_path: Path) -> None:
    _client_instance, service, _storage, owner = _client(tmp_path)
    initiated = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata()),
        idempotency_key="expired-dry-run",
    )
    assert initiated.upload_session_id is not None
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, initiated.upload_session_id)
        assert record is not None
        record.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)

    report = reconcile_expired_multipart_uploads(apply=False, confirmation=None, max_sessions=10)

    assert report.mode == "dry-run"
    assert [candidate.upload_session_id for candidate in report.candidates] == [
        str(initiated.upload_session_id)
    ]
    with get_persistence().session_factory() as session:
        record = session.get(UploadSession, initiated.upload_session_id)
        assert record is not None
        assert record.status == "initiated"


def test_expired_session_is_persisted_and_remains_abortable(tmp_path: Path) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    initiated = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata()),
        idempotency_key="expired-lifecycle",
    )
    assert initiated.upload_session_id is not None
    with get_persistence().session_factory.begin() as session:
        record = session.get(UploadSession, initiated.upload_session_id)
        assert record is not None
        record.expires_at = datetime.now(tz=UTC) - timedelta(minutes=1)

    with pytest.raises(JobConflictError, match="expired"):
        service.create_part_urls(
            owner_user_id=owner,
            upload_session_id=initiated.upload_session_id,
            part_numbers=[1],
        )
    with get_persistence().session_factory() as session:
        expired = session.get(UploadSession, initiated.upload_session_id)
        assert expired is not None
        assert expired.status == "expired"
        assert expired.failure_reason == "upload_session_expired"

    aborted = service.abort(owner_user_id=owner, upload_session_id=initiated.upload_session_id)
    assert aborted.status == "aborted"
    assert storage.uploads == {}


def test_local_backend_explicitly_uses_the_legacy_proxy(tmp_path: Path) -> None:
    settings = Settings.model_validate(
        {
            "environment": "test",
            "storage_backend": "local",
            "local_storage_root": tmp_path / "legacy",
            "processing_workspace_root": tmp_path / "workspace",
        }
    )
    owner = get_persistence().owner_user_id
    service = DirectUploadService(settings=settings, persistence=get_persistence())

    response = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata()),
        idempotency_key="local-proxy",
    )

    assert response.transport == "proxy"
    assert response.upload_session_id is None
    with get_persistence().session_factory() as session:
        assert list(session.scalars(select(UploadSession))) == []


def test_concurrent_completion_allows_only_one_provider_completion(tmp_path: Path) -> None:
    _client_instance, service, storage, owner = _client(tmp_path)
    initiated = service.initiate(
        owner_user_id=owner,
        request=InitiateUploadRequest.model_validate(_metadata(byte_size=4)),
        idempotency_key="completion-race",
    )
    assert initiated.upload_session_id is not None
    storage.completed_data = b"data"
    storage.block_completion = True
    request = CompleteUploadRequest(parts=[CompletedUploadPart(part_number=1, etag='"etag"')])

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            service.complete,
            owner_user_id=owner,
            upload_session_id=initiated.upload_session_id,
            request=request,
        )
        assert storage.completion_entered.wait(timeout=5)
        with pytest.raises(JobConflictError, match="current state"):
            service.complete(
                owner_user_id=owner,
                upload_session_id=initiated.upload_session_id,
                request=request,
            )
        storage.completion_release.set()
        assert future.result(timeout=5).status == "verifying"
    assert storage.completion_calls == 1


def _direct_round_trip(
    client: TestClient, storage: FakeMultipartStorage, data: bytes, key: str
) -> dict[str, Any]:
    initiated = client.post(
        "/api/v1/uploads/initiate",
        headers={"Idempotency-Key": key},
        json=_metadata(
            filename="duplicate.avi", content_type="video/x-msvideo", byte_size=len(data)
        ),
    ).json()
    storage.completed_data = data
    client.post(
        f"/api/v1/uploads/{initiated['upload_session_id']}/complete",
        json={"parts": [{"part_number": 1, "etag": '"etag"'}]},
    )
    return cast(
        dict[str, Any],
        client.get(f"/api/v1/uploads/{initiated['upload_session_id']}").json()["result"],
    )


def _metadata(
    *,
    filename: str = "match.mp4",
    content_type: str = "video/mp4",
    byte_size: int = 1_000,
) -> dict[str, Any]:
    return {
        "filename": filename,
        "content_type": content_type,
        "byte_size": byte_size,
        "sport": "pickleball",
    }


def _client(
    tmp_path: Path,
) -> tuple[TestClient, DirectUploadService, FakeMultipartStorage, UUID]:
    settings = Settings.model_validate(
        {
            "environment": "test",
            "storage_backend": "s3",
            "storage_s3_endpoint": "https://objects.example.test",
            "storage_s3_region": "test-region",
            "storage_s3_bucket": "private-court4",
            "storage_s3_access_key_id": "access-id",
            "storage_s3_secret_access_key": "secret",
            "processing_workspace_root": tmp_path / "workspace",
            "local_storage_root": tmp_path / "legacy",
            "storage_warning_free_bytes": 2,
            "storage_hard_stop_free_bytes": 1,
            "storage_max_active_uploads": 10,
            "default_sample_interval_seconds": 0.5,
        }
    )
    storage = FakeMultipartStorage()
    service = DirectUploadService(
        settings=settings,
        persistence=get_persistence(),
        storage=storage,
    )
    application = create_app()
    application.dependency_overrides[get_upload_service] = lambda: service
    client = TestClient(application)
    token = _register_verified_user(client, "direct-upload@example.com")
    client.headers["Authorization"] = f"Bearer {token}"
    owner = UUID(client.get("/api/v1/auth/me").json()["id"])
    return client, service, storage, owner


def _register_verified_user(client: TestClient, email: str) -> str:
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a sufficiently long password"},
    ).json()
    owner = UUID(registered["user"]["id"])
    with get_persistence().session_factory.begin() as session:
        user = session.get(User, owner)
        assert user is not None
        user.email_verified_at = datetime.now(tz=UTC)
    return cast(str, registered["access_token"])


class FakeMultipartStorage:
    provider = "s3"

    def __init__(self) -> None:
        self.uploads: dict[str, dict[str, Any]] = {}
        self.objects: dict[str, dict[str, Any]] = {}
        self.completed_data = b""
        self.presigned: list[int] = []
        self.fail_initiate = False
        self.block_completion = False
        self.completion_entered = threading.Event()
        self.completion_release = threading.Event()
        self.completion_calls = 0

    def ready(self) -> bool:
        return True

    def initiate_multipart_upload(
        self,
        *,
        key: str,
        content_type: str,
        upload_session_id: str,
        declared_size: int,
    ) -> str:
        if self.fail_initiate:
            raise ObjectStorageError("highly-secret-provider-error")
        upload_id = f"upload-{upload_session_id}"
        self.uploads[upload_id] = {
            "key": key,
            "content_type": content_type,
            "metadata": {
                "court4-upload-session": upload_session_id,
                "court4-declared-size": str(declared_size),
            },
        }
        return upload_id

    def presign_upload_part(
        self, *, key: str, upload_id: str, part_number: int, expires_in: int
    ) -> str:
        del key, expires_in
        assert upload_id in self.uploads
        self.presigned.append(part_number)
        return f"https://private.test/{upload_id}/part/{part_number}"

    def complete_multipart_upload(
        self, *, key: str, upload_id: str, parts: list[dict[str, object]]
    ) -> None:
        self.completion_calls += 1
        self.completion_entered.set()
        if self.block_completion:
            assert self.completion_release.wait(timeout=5)
        assert parts
        upload = self.uploads[upload_id]
        assert upload["key"] == key
        self.objects[key] = {
            "data": self.completed_data,
            "content_type": upload["content_type"],
            "metadata": dict(upload["metadata"]),
        }

    def abort_multipart_upload(self, *, key: str, upload_id: str) -> None:
        upload = self.uploads.pop(upload_id, None)
        if upload is not None:
            assert upload["key"] == key

    def head_upload(self, *, key: str) -> UploadObjectMetadata:
        try:
            stored = self.objects[key]
        except KeyError as exc:
            raise ObjectNotFoundError() from exc
        return UploadObjectMetadata(
            key=key,
            size_bytes=len(stored["data"]),
            content_type=stored["content_type"],
            custom_metadata=dict(stored["metadata"]),
        )

    def calculate_sha256(self, *, key: str, chunk_size: int) -> str:
        del chunk_size
        return hashlib.sha256(self.objects[key]["data"]).hexdigest()

    def set_verified_checksum(self, *, key: str, checksum_sha256: str) -> ObjectMetadata:
        self.objects[key]["metadata"]["court4-sha256"] = checksum_sha256
        return self.stat(key=key)

    def put_file(
        self,
        *,
        key: str,
        source: Path,
        content_type: str,
        checksum_sha256: str,
    ) -> ObjectMetadata:
        data = source.read_bytes()
        assert hashlib.sha256(data).hexdigest() == checksum_sha256
        self.objects[key] = {
            "data": data,
            "content_type": content_type,
            "metadata": {"court4-sha256": checksum_sha256},
        }
        return self.stat(key=key)

    def download_file(self, *, key: str, destination: Path) -> ObjectMetadata:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[key]["data"])
        return self.stat(key=key)

    def stat(self, *, key: str) -> ObjectMetadata:
        try:
            stored = self.objects[key]
        except KeyError as exc:
            raise ObjectNotFoundError() from exc
        checksum = stored["metadata"].get("court4-sha256")
        if checksum is None:
            raise ObjectStorageError("checksum missing")
        return ObjectMetadata(
            key=key,
            size_bytes=len(stored["data"]),
            checksum_sha256=checksum,
            content_type=stored["content_type"],
        )

    def exists(self, *, key: str) -> bool:
        return key in self.objects

    def delete(self, *, key: str) -> None:
        self.objects.pop(key, None)
