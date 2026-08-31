from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.persistence.models import UploadSession, utc_now
from app.persistence.object_storage import (
    MultipartObjectStorage,
    ObjectStorageError,
    source_object_key,
)
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.schemas.jobs import UploadAnalysisResponse
from app.schemas.uploads import (
    CompleteUploadRequest,
    InitiateUploadRequest,
    InitiateUploadResponse,
    PresignedUploadPart,
    UploadPartUrlResponse,
    UploadSessionResponse,
)
from app.services.jobs import AnalysisWorkflowService
from app.services.jobs.exceptions import (
    JobConflictError,
    JobNotFoundError,
    JobRequestError,
    JobStorageBackendError,
    JobStorageCapacityError,
    JobTooLargeError,
    JobWorkflowError,
)
from app.services.jobs.repository import AnalysisJobRepository
from app.sports import SportType

logger = logging.getLogger(__name__)
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")
_UPLOAD_RESPONSE_ADAPTER: TypeAdapter[UploadAnalysisResponse] = TypeAdapter(UploadAnalysisResponse)
_ACTIVE_MULTIPART_STATES = {"initiated", "uploading"}
_EXPIRABLE_STATES = {"initiated", "uploading"}


class DirectUploadService:
    def __init__(
        self,
        *,
        settings: Settings,
        persistence: PersistenceRuntime | None = None,
        storage: MultipartObjectStorage | None = None,
    ) -> None:
        self.settings = settings
        self.persistence = persistence or get_persistence()
        self.storage = storage or cast(MultipartObjectStorage, self.persistence.storage)

    def initiate(
        self,
        *,
        owner_user_id: UUID,
        request: InitiateUploadRequest,
        idempotency_key: str,
    ) -> InitiateUploadResponse:
        filename, suffix = self._validate_metadata(request)
        key = self._validate_idempotency_key(idempotency_key)
        if self.settings.storage_backend == "local":
            return InitiateUploadResponse(
                transport="proxy",
                status="proxy_required",
                max_concurrency=1,
                max_attempts=1,
            )

        key_hash = hashlib.sha256(key.encode()).hexdigest()
        fingerprint = self._request_fingerprint(request, filename)
        now = utc_now()
        with self.persistence.session_factory.begin() as session:
            lock_name = f"direct-upload:{owner_user_id}:{key_hash}"
            session.scalar(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_name, 0))))
            existing = session.scalar(
                select(UploadSession).where(
                    UploadSession.owner_user_id == owner_user_id,
                    UploadSession.idempotency_key_hash == key_hash,
                )
            )
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise JobConflictError(
                        "upload_idempotency_conflict",
                        "Idempotency key was already used for different upload metadata.",
                    )
                self._expire_record_if_needed(existing)
                return self._initiate_response(existing)

            session.scalar(
                select(
                    func.pg_advisory_xact_lock(func.hashtextextended("direct-upload-capacity", 0))
                )
            )
            active_count = session.scalar(
                select(func.count())
                .select_from(UploadSession)
                .where(
                    UploadSession.status.in_(
                        ("initiated", "uploading", "completing", "verifying", "analyzing")
                    )
                )
            )
            if int(active_count or 0) >= self.settings.storage_max_active_uploads:
                raise JobStorageCapacityError(
                    "upload_capacity_busy",
                    "Another upload is already active. Try again after it completes.",
                    status_code=429,
                )

            upload_session_id = uuid4()
            analysis_id = upload_session_id.hex
            storage_key = source_object_key(owner_user_id, analysis_id, suffix)
            part_size = self.settings.direct_upload_part_size_bytes
            part_count = math.ceil(request.byte_size / part_size)
            expires_at = now + timedelta(seconds=self.settings.direct_upload_session_ttl_seconds)
            try:
                provider_upload_id = self.storage.initiate_multipart_upload(
                    key=storage_key,
                    content_type=self._clean_content_type(request.content_type),
                    upload_session_id=str(upload_session_id),
                    declared_size=request.byte_size,
                )
            except ObjectStorageError as exc:
                raise JobStorageBackendError("Direct upload could not be initiated.") from exc
            created = UploadSession(
                id=upload_session_id,
                owner_user_id=owner_user_id,
                analysis_id=analysis_id,
                sport=request.sport.value,
                original_filename=filename,
                content_type=self._clean_content_type(request.content_type),
                declared_size=request.byte_size,
                logical_key=f"uploads/source{suffix}",
                storage_key=storage_key,
                provider=self.storage.provider,
                provider_upload_id=provider_upload_id,
                status="initiated",
                part_size=part_size,
                part_count=part_count,
                expected_sha256=request.expected_sha256,
                idempotency_key_hash=key_hash,
                request_fingerprint=fingerprint,
                reanalyze=request.reanalyze,
                client_metadata=request.client_metadata,
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            session.add(created)
            try:
                session.flush()
            except IntegrityError as exc:  # pragma: no cover - advisory lock is authoritative
                raise JobConflictError(
                    "upload_session_conflict", "Upload session could not be created safely."
                ) from exc
        return self._initiate_response(created)

    def get(self, *, owner_user_id: UUID, upload_session_id: UUID) -> UploadSessionResponse:
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id)
            self._expire_record_if_needed(record)
            return self._status_response(record)

    def create_part_urls(
        self,
        *,
        owner_user_id: UUID,
        upload_session_id: UUID,
        part_numbers: list[int],
    ) -> UploadPartUrlResponse:
        self._expire_owned_if_needed(owner_user_id, upload_session_id)
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            self._ensure_not_expired(record)
            if record.status not in _ACTIVE_MULTIPART_STATES:
                raise JobConflictError(
                    "invalid_upload_state", "Upload parts are unavailable in the current state."
                )
            if any(number > record.part_count for number in part_numbers):
                raise JobRequestError(
                    "invalid_part_number", "Requested upload part is out of range."
                )
            if record.status == "initiated":
                record.status = "uploading"
                record.row_version += 1
                record.updated_at = utc_now()
            return UploadPartUrlResponse(
                upload_session_id=record.id,
                parts=self._presigned_parts(record, part_numbers),
            )

    def complete(
        self,
        *,
        owner_user_id: UUID,
        upload_session_id: UUID,
        request: CompleteUploadRequest,
    ) -> UploadSessionResponse:
        self._expire_owned_if_needed(owner_user_id, upload_session_id)
        verification_failed = False
        response: UploadSessionResponse | None = None
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            self._ensure_not_expired(record)
            if record.status in {"completed", "verifying", "analyzing"}:
                return self._status_response(record)
            if record.status not in _ACTIVE_MULTIPART_STATES:
                raise JobConflictError(
                    "invalid_upload_state", "Upload cannot be completed in the current state."
                )
            ordered = sorted(request.parts, key=lambda item: item.part_number)
            expected_numbers = list(range(1, record.part_count + 1))
            if [item.part_number for item in ordered] != expected_numbers:
                raise JobRequestError(
                    "missing_upload_part",
                    "Every multipart upload part must be provided exactly once.",
                )
            record.status = "completing"
            record.row_version += 1
            record.updated_at = utc_now()
            provider_parts = [
                {"PartNumber": item.part_number, "ETag": item.etag} for item in ordered
            ]
            storage_key = record.storage_key
            provider_upload_id = record.provider_upload_id

        try:
            self.storage.complete_multipart_upload(
                key=storage_key,
                upload_id=provider_upload_id,
                parts=provider_parts,
            )
        except ObjectStorageError as exc:
            try:
                head = self.storage.head_upload(key=storage_key)
            except ObjectStorageError:
                self._restore_uploading(upload_session_id)
                raise JobStorageBackendError(
                    "Object storage could not complete the upload."
                ) from exc
        else:
            try:
                head = self.storage.head_upload(key=storage_key)
            except ObjectStorageError as exc:
                self._fail(upload_session_id, "object_head_failed")
                raise JobStorageBackendError("Uploaded object could not be verified.") from exc

        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            if record.status != "completing":
                raise JobConflictError(
                    "invalid_upload_state", "Upload completion state changed unexpectedly."
                )
            metadata_session = head.custom_metadata.get("court4-upload-session")
            metadata_size = head.custom_metadata.get("court4-declared-size")
            if (
                head.size_bytes != record.declared_size
                or metadata_session != str(record.id)
                or metadata_size != str(record.declared_size)
                or self._clean_content_type(head.content_type) != record.content_type
            ):
                record.status = "failed"
                record.failure_reason = "object_metadata_mismatch"
                record.row_version += 1
                record.updated_at = utc_now()
                verification_failed = True
            else:
                record.status = "verifying"
                record.row_version += 1
                record.updated_at = utc_now()
                response = self._status_response(record)
        if verification_failed:
            raise JobRequestError(
                "object_verification_failed", "Uploaded object metadata did not match the session."
            )
        assert response is not None
        return response

    def verify_and_analyze(self, upload_session_id: UUID) -> None:
        now = utc_now()
        lease_cutoff = now - timedelta(
            seconds=self.settings.direct_upload_verification_lease_seconds
        )
        with self.persistence.session_factory.begin() as session:
            record = session.scalar(
                select(UploadSession).where(UploadSession.id == upload_session_id).with_for_update()
            )
            if record is None or record.status not in {"verifying", "analyzing"}:
                return
            if (
                record.verification_started_at is not None
                and record.verification_started_at > lease_cutoff
            ):
                return
            record.verification_started_at = now
            record.row_version += 1
            record.updated_at = now
            owner_user_id = record.owner_user_id
            storage_key = record.storage_key
            expected_sha256 = record.expected_sha256
            resumed_analysis = record.status == "analyzing"
            resumed_checksum = record.verified_sha256

        try:
            if resumed_analysis:
                if resumed_checksum is None:
                    self._fail(upload_session_id, "verified_checksum_missing")
                    return
                checksum = resumed_checksum
                with self.persistence.session_factory() as session:
                    record = session.get(UploadSession, upload_session_id)
                    if record is None or record.status != "analyzing":
                        return
                    snapshot = self._snapshot(record)
            else:
                checksum = self.storage.calculate_sha256(
                    key=storage_key,
                    chunk_size=self.settings.direct_upload_checksum_chunk_size_bytes,
                )
                if expected_sha256 is not None and checksum != expected_sha256:
                    self._fail(upload_session_id, "checksum_mismatch")
                    return
                verified = self.storage.set_verified_checksum(
                    key=storage_key, checksum_sha256=checksum
                )
                with self.persistence.session_factory.begin() as session:
                    record = session.scalar(
                        select(UploadSession)
                        .where(UploadSession.id == upload_session_id)
                        .with_for_update()
                    )
                    if record is None or record.status != "verifying":
                        return
                    if verified.size_bytes != record.declared_size:
                        record.status = "failed"
                        record.failure_reason = "object_size_mismatch"
                        record.row_version += 1
                        record.updated_at = utc_now()
                        return
                    record.verified_sha256 = checksum
                    record.status = "analyzing"
                    record.verification_started_at = utc_now()
                    record.row_version += 1
                    record.updated_at = utc_now()
                    snapshot = self._snapshot(record)

            workflow = AnalysisWorkflowService(
                settings=self.settings,
                owner_user_id=owner_user_id,
                repository=AnalysisJobRepository.from_settings(
                    settings=self.settings,
                    owner_user_id=owner_user_id,
                    persistence=self.persistence,
                    object_storage=self.storage,
                ),
            )
            try:
                result = workflow.create_analysis_from_verified_object(
                    analysis_id=snapshot.analysis_id,
                    storage_key=snapshot.storage_key,
                    filename=snapshot.original_filename,
                    content_type=snapshot.content_type,
                    size_bytes=snapshot.declared_size,
                    checksum_sha256=checksum,
                    idempotency_key=f"direct-upload:{upload_session_id}",
                    reanalyze=snapshot.reanalyze,
                    sport=snapshot.sport,
                )
            finally:
                workflow.close()
            with self.persistence.session_factory.begin() as session:
                record = session.scalar(
                    select(UploadSession)
                    .where(UploadSession.id == upload_session_id)
                    .with_for_update()
                )
                if record is None or record.status != "analyzing":
                    return
                record.status = "completed"
                record.result_payload = result.model_dump(mode="json")
                record.completed_at = utc_now()
                record.row_version += 1
                record.updated_at = utc_now()
        except JobWorkflowError as exc:
            self._fail(upload_session_id, exc.code)
        except ObjectStorageError:
            self._fail(upload_session_id, "object_verification_failed")
        except Exception:
            logger.error(
                "direct_upload_background_failure",
                extra={"upload_session_id": str(upload_session_id)},
            )
            self._fail(upload_session_id, "upload_finalization_failed")

    def abort(self, *, owner_user_id: UUID, upload_session_id: UUID) -> UploadSessionResponse:
        self._expire_owned_if_needed(owner_user_id, upload_session_id, allow_expired=True)
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            if record.status == "aborted":
                return self._status_response(record)
            if record.status not in _ACTIVE_MULTIPART_STATES and record.status != "expired":
                raise JobConflictError(
                    "invalid_upload_state", "Upload can no longer be aborted safely."
                )
            storage_key = record.storage_key
            provider_upload_id = record.provider_upload_id
        try:
            self.storage.abort_multipart_upload(key=storage_key, upload_id=provider_upload_id)
        except ObjectStorageError as exc:
            raise JobStorageBackendError("Object storage could not abort the upload.") from exc
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            if record.status == "aborted":
                return self._status_response(record)
            if record.status not in _ACTIVE_MULTIPART_STATES and record.status != "expired":
                raise JobConflictError(
                    "invalid_upload_state", "Upload state changed before it could be aborted."
                )
            record.status = "aborted"
            record.aborted_at = utc_now()
            record.row_version += 1
            record.updated_at = utc_now()
            return self._status_response(record)

    def _initiate_response(self, record: UploadSession) -> InitiateUploadResponse:
        parts = (
            self._presigned_parts(record, list(range(1, record.part_count + 1)))
            if record.status in _ACTIVE_MULTIPART_STATES
            else []
        )
        return InitiateUploadResponse(
            transport="direct",
            upload_session_id=record.id,
            status=record.status,
            part_size=record.part_size,
            part_count=record.part_count,
            max_concurrency=self.settings.direct_upload_max_concurrency,
            max_attempts=self.settings.direct_upload_part_max_attempts,
            expires_at=record.expires_at,
            parts=parts,
        )

    def _presigned_parts(
        self, record: UploadSession, part_numbers: list[int]
    ) -> list[PresignedUploadPart]:
        expires_at = min(
            record.expires_at,
            datetime.now(tz=UTC)
            + timedelta(seconds=self.settings.direct_upload_presign_ttl_seconds),
        )
        try:
            return [
                PresignedUploadPart(
                    part_number=part_number,
                    url=self.storage.presign_upload_part(
                        key=record.storage_key,
                        upload_id=record.provider_upload_id,
                        part_number=part_number,
                        expires_in=self.settings.direct_upload_presign_ttl_seconds,
                    ),
                    expires_at=expires_at,
                )
                for part_number in part_numbers
            ]
        except ObjectStorageError as exc:
            raise JobStorageBackendError(
                "Signed upload part URLs are temporarily unavailable."
            ) from exc

    @staticmethod
    def _load_owned(
        session: Session,
        owner_user_id: UUID,
        upload_session_id: UUID,
        *,
        for_update: bool = False,
    ) -> UploadSession:
        query = select(UploadSession).where(
            UploadSession.id == upload_session_id,
            UploadSession.owner_user_id == owner_user_id,
        )
        if for_update:
            query = query.with_for_update()
        record = session.scalar(query)
        if record is None:
            raise JobNotFoundError("Upload session not found.")
        return record

    @staticmethod
    def _status_response(record: UploadSession) -> UploadSessionResponse:
        result = (
            _UPLOAD_RESPONSE_ADAPTER.validate_python(record.result_payload)
            if record.result_payload is not None
            else None
        )
        return UploadSessionResponse(
            upload_session_id=record.id,
            status=record.status,
            byte_size=record.declared_size,
            verified_sha256=record.verified_sha256,
            result=result,
            failure_code=record.failure_reason,
            expires_at=record.expires_at,
        )

    def _validate_metadata(self, request: InitiateUploadRequest) -> tuple[str, str]:
        if request.byte_size > self.settings.max_upload_size_bytes:
            raise JobTooLargeError("Uploaded video exceeds the configured size limit.")
        filename = request.filename.strip()
        if "/" in filename or "\\" in filename:
            raise JobRequestError("invalid_filename", "Uploaded filename must not contain a path.")
        suffix = Path(filename).suffix.lower()
        if suffix not in {item.lower() for item in self.settings.supported_extensions}:
            raise JobRequestError("unsupported_extension", "Unsupported video extension.")
        if not _SAFE_STEM.sub("_", Path(filename).stem).strip("._-"):
            raise JobRequestError("invalid_filename", "Uploaded filename is invalid.")
        content_type = self._clean_content_type(request.content_type)
        if content_type != "application/octet-stream" and not content_type.startswith("video/"):
            raise JobRequestError("unsupported_media_type", "Unsupported upload content type.")
        if len(json.dumps(request.client_metadata, separators=(",", ":"))) > 4096:
            raise JobRequestError("client_metadata_too_large", "Client metadata is too large.")
        return filename, suffix

    @staticmethod
    def _clean_content_type(value: str) -> str:
        return value.split(";", maxsplit=1)[0].strip().lower()

    @staticmethod
    def _validate_idempotency_key(value: str) -> str:
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 256:
            raise JobRequestError(
                "invalid_idempotency_key", "Idempotency-Key must contain 1 to 256 characters."
            )
        return cleaned

    @staticmethod
    def _request_fingerprint(request: InitiateUploadRequest, filename: str) -> str:
        payload = {
            "filename": filename,
            "content_type": DirectUploadService._clean_content_type(request.content_type),
            "byte_size": request.byte_size,
            "sport": request.sport.value,
            "reanalyze": request.reanalyze,
            "expected_sha256": request.expected_sha256,
            "client_metadata": request.client_metadata,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _ensure_not_expired(record: UploadSession) -> None:
        if record.status == "expired":
            raise JobConflictError("upload_session_expired", "Upload session has expired.")

    @staticmethod
    def _expire_record_if_needed(record: UploadSession) -> bool:
        if record.status not in _EXPIRABLE_STATES or record.expires_at > utc_now():
            return False
        record.status = "expired"
        record.failure_reason = "upload_session_expired"
        record.row_version += 1
        record.updated_at = utc_now()
        return True

    def _expire_owned_if_needed(
        self,
        owner_user_id: UUID,
        upload_session_id: UUID,
        *,
        allow_expired: bool = False,
    ) -> None:
        expired = False
        with self.persistence.session_factory.begin() as session:
            record = self._load_owned(session, owner_user_id, upload_session_id, for_update=True)
            expired = self._expire_record_if_needed(record)
        if expired and not allow_expired:
            raise JobConflictError("upload_session_expired", "Upload session has expired.")

    def _restore_uploading(self, upload_session_id: UUID) -> None:
        with self.persistence.session_factory.begin() as session:
            record = session.scalar(
                select(UploadSession).where(UploadSession.id == upload_session_id).with_for_update()
            )
            if record is not None and record.status == "completing":
                record.status = "uploading"
                record.row_version += 1
                record.updated_at = utc_now()

    def _fail(self, upload_session_id: UUID, reason: str) -> None:
        with self.persistence.session_factory.begin() as session:
            record = session.scalar(
                select(UploadSession).where(UploadSession.id == upload_session_id).with_for_update()
            )
            if record is None or record.status in {"completed", "aborted"}:
                return
            record.status = "failed"
            record.failure_reason = reason[:256]
            record.row_version += 1
            record.updated_at = utc_now()

    @staticmethod
    def _snapshot(record: UploadSession) -> _UploadSnapshot:
        return _UploadSnapshot(
            analysis_id=record.analysis_id,
            storage_key=record.storage_key,
            original_filename=record.original_filename,
            content_type=record.content_type,
            declared_size=record.declared_size,
            reanalyze=record.reanalyze,
            sport=SportType(record.sport),
        )


@dataclass(frozen=True)
class _UploadSnapshot:
    analysis_id: str
    storage_key: str
    original_filename: str
    content_type: str
    declared_size: int
    reanalyze: bool
    sport: SportType
