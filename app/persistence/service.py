from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.bootstrap import BootstrapIdentity
from app.persistence.errors import (
    ArtifactNotAvailableError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    OperationInProgressError,
    OptimisticConcurrencyError,
    OwnershipMismatchError,
    ResourceNotFoundError,
)
from app.persistence.models import (
    Analysis,
    AnalysisArtifact,
    AnalysisRun,
    AnalysisStageExecution,
    AnalysisStateEvent,
    CalibrationVerification,
    IdempotencyRecord,
    PlayerSelection,
    UploadedVideo,
    User,
    utc_now,
)
from app.schemas.stage_execution import ArtifactReference, StageProvenance


@dataclass(frozen=True)
class ArtifactInput:
    storage_key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    artifact_kind: str
    schema_version: int | None = None


@dataclass(frozen=True)
class PlayerSelectionInput:
    candidate_id: str | None
    track_id: int | None
    source_track_ids: list[int]


@dataclass(frozen=True)
class RunProvenance:
    pipeline_version: str
    schema_version: int
    policy_version: str
    configuration_fingerprint: str
    software_commit_identifier: str
    deployment_build_identifier: str


@dataclass(frozen=True)
class ReservationResult:
    analysis_id: str
    created: bool
    backend_pid: int = 0
    duplicate: DuplicateVideoMatch | None = None


@dataclass(frozen=True)
class DuplicateVideoMatch:
    uploaded_video_id: UUID
    existing_analysis_id: str
    uploaded_at: datetime


@dataclass(frozen=True)
class RunResult:
    run_id: UUID
    created: bool
    backend_pid: int = 0


@dataclass(frozen=True)
class TransitionResult:
    run_id: UUID
    state: str
    row_version: int
    backend_pid: int = 0


@dataclass(frozen=True)
class StageExecutionResult:
    stage_execution_id: UUID
    attempt_number: int
    state: str
    row_version: int
    created: bool


SynchronizationHook = Callable[[int], None]
TransitionObservationHook = Callable[[int, str, int], None]
_STAGE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class PersistenceService:
    """Owner-scoped transactional persistence used by the production runtime."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        provenance: RunProvenance | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provenance = provenance or RunProvenance(
            pipeline_version="court4-1.8b",
            schema_version=1,
            policy_version="phase-1.8b",
            configuration_fingerprint=sha256(b"court4-phase-1.8b").hexdigest(),
            software_commit_identifier="working-tree",
            deployment_build_identifier="local",
        )

    def ensure_bootstrap_user(self, identity: BootstrapIdentity) -> UUID:
        with self._session_factory.begin() as session:
            user = session.get(User, identity.user_id)
            if user is None:
                session.add(
                    User(
                        id=identity.user_id,
                        email=identity.identity_label.lower(),
                        password_hash="!development-bootstrap-user-cannot-login",
                        account_status="disabled",
                    )
                )
            elif user.email != identity.identity_label.lower():
                raise IdempotencyConflictError(
                    "Bootstrap UUID is already associated with another identity."
                )
        return identity.user_id

    def reserve_analysis(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        original_filename: str,
        content_type: str | None,
        size_bytes: int,
        source_checksum: str,
        job_payload: dict[str, Any],
        allow_duplicate: bool = False,
        synchronization_hook: SynchronizationHook | None = None,
    ) -> ReservationResult:
        try:
            return self._reserve_analysis_once(
                owner_user_id=owner_user_id,
                analysis_id=analysis_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=size_bytes,
                source_checksum=source_checksum,
                job_payload=job_payload,
                allow_duplicate=allow_duplicate,
                synchronization_hook=synchronization_hook,
            )
        except IntegrityError:
            with self._session_factory() as session:
                record = session.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.owner_user_id == owner_user_id,
                        IdempotencyRecord.scope == "analysis_upload",
                        IdempotencyRecord.key_hash == sha256(idempotency_key.encode()).hexdigest(),
                    )
                )
                if record is None:
                    raise
                if record.request_fingerprint != request_fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency key was already used for a different upload."
                    ) from None
                if record.resource_id is None:
                    raise OperationInProgressError(
                        "The original upload is still in progress."
                    ) from None
                return self._reservation_from_record(
                    session,
                    record,
                    owner_user_id=owner_user_id,
                )

    def find_uploaded_video_by_owner_and_checksum(
        self,
        *,
        owner_user_id: UUID,
        checksum_sha256: str,
    ) -> DuplicateVideoMatch | None:
        with self._session_factory() as session:
            return self._find_uploaded_video_by_owner_and_checksum(
                session,
                owner_user_id=owner_user_id,
                checksum_sha256=checksum_sha256,
            )

    def _reserve_analysis_once(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        original_filename: str,
        content_type: str | None,
        size_bytes: int,
        source_checksum: str,
        job_payload: dict[str, Any],
        allow_duplicate: bool,
        synchronization_hook: SynchronizationHook | None,
    ) -> ReservationResult:
        key_hash = sha256(idempotency_key.encode()).hexdigest()
        with self._session_factory.begin() as session:
            backend_pid = self._connection_pid(session)
            record = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.owner_user_id == owner_user_id,
                    IdempotencyRecord.scope == "analysis_upload",
                    IdempotencyRecord.key_hash == key_hash,
                )
            )
            if record is not None:
                if record.request_fingerprint != request_fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency key was already used for a different upload."
                    )
                if record.resource_id is None:
                    raise OperationInProgressError("The original upload is still in progress.")
                return self._reservation_from_record(
                    session,
                    record,
                    owner_user_id=owner_user_id,
                    backend_pid=backend_pid,
                )

            if synchronization_hook is not None:
                synchronization_hook(backend_pid)

            if not allow_duplicate:
                self._lock_owner_checksum(session, owner_user_id, source_checksum)
                duplicate = self._find_uploaded_video_by_owner_and_checksum(
                    session,
                    owner_user_id=owner_user_id,
                    checksum_sha256=source_checksum,
                )
                if duplicate is not None:
                    session.add(
                        IdempotencyRecord(
                            owner_user_id=owner_user_id,
                            scope="analysis_upload",
                            key_hash=key_hash,
                            request_fingerprint=request_fingerprint,
                            status="completed",
                            resource_type="exact_duplicate_analysis",
                            resource_id=duplicate.existing_analysis_id,
                            response_payload={
                                "duplicate_type": "exact",
                                "existing_analysis_id": duplicate.existing_analysis_id,
                                "uploaded_at": duplicate.uploaded_at.isoformat(),
                            },
                        )
                    )
                    return ReservationResult(
                        duplicate.existing_analysis_id,
                        False,
                        backend_pid,
                        duplicate,
                    )

            record = IdempotencyRecord(
                owner_user_id=owner_user_id,
                scope="analysis_upload",
                key_hash=key_hash,
                request_fingerprint=request_fingerprint,
                status="in_progress",
            )
            session.add(record)
            video = UploadedVideo(
                owner_user_id=owner_user_id,
                state="pending",
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=size_bytes,
                source_checksum=source_checksum,
            )
            session.add(video)
            session.flush()
            analysis = Analysis(
                id=analysis_id,
                owner_user_id=owner_user_id,
                uploaded_video_id=video.id,
                state="processing",
                current_stage="uploaded",
                job_payload=job_payload,
            )
            session.add(analysis)
            session.flush()
            run = self._insert_run(session, analysis, source_checksum)
            self._add_event(
                session, analysis, None, "processing", "analysis_created", "development"
            )
            self._add_run_event(session, run, None, "processing", "run_started")
            record.status = "completed"
            record.resource_type = "analysis"
            record.resource_id = analysis.id
        return ReservationResult(analysis_id, True, backend_pid)

    @staticmethod
    def _find_uploaded_video_by_owner_and_checksum(
        session: Session,
        *,
        owner_user_id: UUID,
        checksum_sha256: str,
    ) -> DuplicateVideoMatch | None:
        row = session.execute(
            select(UploadedVideo, Analysis)
            .join(
                Analysis,
                (Analysis.uploaded_video_id == UploadedVideo.id)
                & (Analysis.owner_user_id == UploadedVideo.owner_user_id),
            )
            .where(
                UploadedVideo.owner_user_id == owner_user_id,
                UploadedVideo.source_checksum == checksum_sha256,
                Analysis.owner_user_id == owner_user_id,
            )
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(1)
        ).one_or_none()
        if row is None:
            return None
        video, analysis = row
        return DuplicateVideoMatch(
            uploaded_video_id=video.id,
            existing_analysis_id=analysis.id,
            uploaded_at=video.created_at,
        )

    @staticmethod
    def _duplicate_match_for_analysis(
        session: Session,
        *,
        owner_user_id: UUID,
        analysis_id: str,
    ) -> DuplicateVideoMatch | None:
        row = session.execute(
            select(UploadedVideo, Analysis)
            .join(
                Analysis,
                (Analysis.uploaded_video_id == UploadedVideo.id)
                & (Analysis.owner_user_id == UploadedVideo.owner_user_id),
            )
            .where(
                Analysis.id == analysis_id,
                Analysis.owner_user_id == owner_user_id,
                UploadedVideo.owner_user_id == owner_user_id,
            )
        ).one_or_none()
        if row is None:
            return None
        video, analysis = row
        return DuplicateVideoMatch(
            uploaded_video_id=video.id,
            existing_analysis_id=analysis.id,
            uploaded_at=video.created_at,
        )

    def _reservation_from_record(
        self,
        session: Session,
        record: IdempotencyRecord,
        *,
        owner_user_id: UUID,
        backend_pid: int = 0,
    ) -> ReservationResult:
        if record.resource_id is None:
            raise OperationInProgressError("The original upload is still in progress.")
        duplicate = None
        if record.resource_type == "exact_duplicate_analysis":
            duplicate = self._duplicate_match_for_analysis(
                session,
                owner_user_id=owner_user_id,
                analysis_id=record.resource_id,
            )
            if duplicate is None:
                raise ResourceNotFoundError("The duplicate analysis was not found.")
        return ReservationResult(record.resource_id, False, backend_pid, duplicate)

    @staticmethod
    def _lock_owner_checksum(
        session: Session,
        owner_user_id: UUID,
        source_checksum: str,
    ) -> None:
        lock_bytes = sha256(f"{owner_user_id}:{source_checksum}".encode()).digest()[:8]
        lock_key = int.from_bytes(lock_bytes, byteorder="big", signed=True)
        session.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def start_run(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        state: str = "processing",
        lease_expires_at: datetime | None = None,
        synchronization_hook: SynchronizationHook | None = None,
    ) -> RunResult:
        if state not in {"queued", "processing"}:
            raise ValueError("A run must start queued or processing.")
        key_hash = sha256(idempotency_key.encode()).hexdigest()
        backend_pid = 0
        try:
            with self._session_factory.begin() as session:
                backend_pid = self._connection_pid(session)
                existing = session.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.owner_user_id == owner_user_id,
                        IdempotencyRecord.scope == "run_start",
                        IdempotencyRecord.key_hash == key_hash,
                    )
                )
                if existing is not None:
                    return self._resolve_run_record(existing, request_fingerprint)
                analysis = self._owned_analysis(session.get(Analysis, analysis_id), owner_user_id)
                if synchronization_hook is not None:
                    synchronization_hook(backend_pid)
                record = IdempotencyRecord(
                    owner_user_id=owner_user_id,
                    scope="run_start",
                    key_hash=key_hash,
                    request_fingerprint=request_fingerprint,
                    status="in_progress",
                )
                session.add(record)
                run = self._insert_run(
                    session,
                    analysis,
                    _source_checksum(session, analysis),
                    state=state,
                    lease_expires_at=lease_expires_at,
                )
                self._add_run_event(session, run, None, state, "run_started")
                if state == "processing" and analysis.state != "processing":
                    previous_state = analysis.state
                    analysis.state = "processing"
                    analysis.row_version += 1
                    analysis.updated_at = utc_now()
                    self._add_event(
                        session,
                        analysis,
                        previous_state,
                        "processing",
                        "run_started",
                        "system",
                    )
                record.status = "completed"
                record.resource_type = "analysis_run"
                record.resource_id = str(run.id)
            return RunResult(run.id, True, backend_pid)
        except IntegrityError:
            with self._session_factory.begin() as session:
                existing = session.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.owner_user_id == owner_user_id,
                        IdempotencyRecord.scope == "run_start",
                        IdempotencyRecord.key_hash == key_hash,
                    )
                )
                if existing is not None:
                    return self._resolve_run_record(existing, request_fingerprint)
                self._owned_analysis(session.get(Analysis, analysis_id), owner_user_id)
                active = session.scalar(
                    select(AnalysisRun).where(
                        AnalysisRun.analysis_id == analysis_id,
                        AnalysisRun.state.in_(("queued", "processing")),
                    )
                )
                if active is not None:
                    session.add(
                        IdempotencyRecord(
                            owner_user_id=owner_user_id,
                            scope="run_start",
                            key_hash=key_hash,
                            request_fingerprint=request_fingerprint,
                            status="completed",
                            resource_type="analysis_run",
                            resource_id=str(active.id),
                        )
                    )
                    return RunResult(active.id, False, backend_pid)
                raise

    def transition_run(
        self,
        *,
        owner_user_id: UUID,
        run_id: UUID,
        expected_row_version: int,
        new_state: str,
        reason: str | None = None,
        observation_hook: TransitionObservationHook | None = None,
    ) -> TransitionResult:
        allowed = {
            "queued": {"processing", "cancelled"},
            "processing": {"completed", "failed", "cancelled", "stale"},
        }
        now = utc_now()
        with self._session_factory.begin() as session:
            backend_pid = self._connection_pid(session)
            current = session.scalar(
                select(AnalysisRun)
                .join(Analysis, Analysis.id == AnalysisRun.analysis_id)
                .where(AnalysisRun.id == run_id, Analysis.owner_user_id == owner_user_id)
            )
            if current is None:
                raise ResourceNotFoundError("Run was not found.")
            if current.state == new_state:
                return TransitionResult(current.id, current.state, current.row_version, backend_pid)
            if observation_hook is not None:
                observation_hook(backend_pid, current.state, current.row_version)
            if new_state not in allowed.get(current.state, set()):
                raise InvalidStateTransitionError(
                    f"Run cannot transition from {current.state} to {new_state}."
                )
            previous_run_state = current.state
            values: dict[str, Any] = {
                "state": new_state,
                "row_version": expected_row_version + 1,
                "updated_at": now,
            }
            timestamp_column = {
                "processing": "started_at",
                "completed": "completed_at",
                "failed": "failed_at",
                "cancelled": "cancelled_at",
                "stale": "stale_at",
            }[new_state]
            values[timestamp_column] = now
            transitioned = session.execute(
                update(AnalysisRun)
                .where(
                    AnalysisRun.id == run_id,
                    AnalysisRun.row_version == expected_row_version,
                    AnalysisRun.state == previous_run_state,
                )
                .values(**values)
                .returning(
                    AnalysisRun.id,
                    AnalysisRun.analysis_id,
                    AnalysisRun.state,
                    AnalysisRun.row_version,
                )
            ).one_or_none()
            if transitioned is None:
                raise OptimisticConcurrencyError("Run changed concurrently.")
            analysis = session.get(Analysis, transitioned.analysis_id)
            if analysis is None:
                raise ResourceNotFoundError("Analysis was not found.")
            if new_state in {"processing", "completed", "failed", "cancelled"}:
                previous_analysis_state = analysis.state
                analysis.state = new_state
                analysis.row_version += 1
                analysis.updated_at = now
                if new_state != "processing":
                    setattr(analysis, f"{new_state}_at", now)
                if new_state == "completed":
                    analysis.promoted_run_id = run_id
                self._add_event(
                    session,
                    analysis,
                    previous_analysis_state,
                    new_state,
                    f"run_{new_state}",
                    "system",
                    reason=reason,
                )
            session.add(
                AnalysisStateEvent(
                    subject_type="run",
                    analysis_id=transitioned.analysis_id,
                    analysis_run_id=run_id,
                    previous_state=previous_run_state,
                    new_state=new_state,
                    event_type=f"run_{new_state}",
                    reason=reason,
                    actor_type="system",
                    subject_row_version=transitioned.row_version,
                    event_metadata={},
                )
            )
            return TransitionResult(run_id, new_state, transitioned.row_version, backend_pid)

    def run_is_stale(self, run_id: UUID, *, now: datetime | None = None) -> bool:
        at = now or utc_now()
        with self._session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise ResourceNotFoundError("Run was not found.")
            return (
                run.state == "processing"
                and run.lease_expires_at is not None
                and run.lease_expires_at <= at
            )

    def state_events(self, *, analysis_id: str) -> list[AnalysisStateEvent]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(AnalysisStateEvent)
                    .where(AnalysisStateEvent.analysis_id == analysis_id)
                    .order_by(AnalysisStateEvent.created_at, AnalysisStateEvent.id)
                )
            )

    def start_stage_execution(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        analysis_run_id: UUID,
        stage_type: str,
        configuration_fingerprint: str,
        provenance_payload: dict[str, Any],
        input_artifact_references: list[dict[str, Any]],
        state: str = "processing",
        is_optional: bool = True,
        shadow_mode: bool = True,
    ) -> StageExecutionResult:
        """Start one optional stage attempt without changing the parent analysis state."""
        if state not in {"queued", "processing"}:
            raise ValueError("A stage execution must start queued or processing.")
        _validate_stage_type(stage_type)
        _validate_sha256(configuration_fingerprint, "configuration fingerprint")
        provenance = StageProvenance.model_validate(provenance_payload)
        if provenance.stage_name != stage_type:
            raise ValueError("Stage provenance name must match the stage execution type.")
        if provenance.configuration_fingerprint != configuration_fingerprint:
            raise ValueError("Stage provenance fingerprint must match the execution fingerprint.")
        input_references = [
            ArtifactReference.model_validate(reference).model_dump(mode="json")
            for reference in input_artifact_references
        ]
        try:
            with self._session_factory.begin() as session:
                analysis = self._owned_analysis(session.get(Analysis, analysis_id), owner_user_id)
                run = session.scalar(
                    select(AnalysisRun).where(
                        AnalysisRun.id == analysis_run_id,
                        AnalysisRun.analysis_id == analysis.id,
                    )
                )
                if run is None:
                    raise ResourceNotFoundError("Analysis run was not found.")
                active = session.scalar(
                    select(AnalysisStageExecution).where(
                        AnalysisStageExecution.analysis_id == analysis_id,
                        AnalysisStageExecution.stage_type == stage_type,
                        AnalysisStageExecution.state.in_(("queued", "processing")),
                    )
                )
                if active is not None:
                    return _stage_result(active, created=False)
                latest = session.scalar(
                    select(AnalysisStageExecution)
                    .where(
                        AnalysisStageExecution.analysis_id == analysis_id,
                        AnalysisStageExecution.stage_type == stage_type,
                    )
                    .order_by(AnalysisStageExecution.attempt_number.desc())
                    .limit(1)
                    .with_for_update()
                )
                execution = AnalysisStageExecution(
                    owner_user_id=owner_user_id,
                    analysis_id=analysis_id,
                    analysis_run_id=analysis_run_id,
                    stage_type=stage_type,
                    attempt_number=(latest.attempt_number + 1) if latest else 1,
                    state=state,
                    is_optional=is_optional,
                    shadow_mode=shadow_mode,
                    configuration_fingerprint=configuration_fingerprint,
                    provenance_payload=provenance.model_dump(mode="json"),
                    input_artifact_references=input_references,
                    output_artifact_references=[],
                    started_at=utc_now() if state == "processing" else None,
                )
                session.add(execution)
                session.flush()
                return _stage_result(execution, created=True)
        except IntegrityError:
            with self._session_factory() as session:
                active = session.scalar(
                    select(AnalysisStageExecution)
                    .join(Analysis, Analysis.id == AnalysisStageExecution.analysis_id)
                    .where(
                        Analysis.owner_user_id == owner_user_id,
                        AnalysisStageExecution.analysis_id == analysis_id,
                        AnalysisStageExecution.stage_type == stage_type,
                        AnalysisStageExecution.state.in_(("queued", "processing")),
                    )
                )
                if active is not None:
                    return _stage_result(active, created=False)
            raise

    def transition_stage_execution(
        self,
        *,
        owner_user_id: UUID,
        stage_execution_id: UUID,
        expected_row_version: int,
        new_state: str,
        failure_category: str | None = None,
    ) -> StageExecutionResult:
        allowed = {
            "queued": {"processing", "cancelled", "unavailable"},
            "processing": {"completed", "failed", "cancelled", "stale", "unavailable"},
        }
        if new_state == "failed" and not (failure_category or "").strip():
            raise ValueError("A failed stage execution requires a safe failure category.")
        now = utc_now()
        with self._session_factory.begin() as session:
            current = session.scalar(
                select(AnalysisStageExecution)
                .join(Analysis, Analysis.id == AnalysisStageExecution.analysis_id)
                .where(
                    AnalysisStageExecution.id == stage_execution_id,
                    Analysis.owner_user_id == owner_user_id,
                )
            )
            if current is None:
                raise ResourceNotFoundError("Stage execution was not found.")
            if current.state == new_state:
                return _stage_result(current, created=False)
            if new_state not in allowed.get(current.state, set()):
                raise InvalidStateTransitionError(
                    f"Stage execution cannot transition from {current.state} to {new_state}."
                )
            values: dict[str, Any] = {
                "state": new_state,
                "row_version": expected_row_version + 1,
                "updated_at": now,
            }
            timestamp_column = {
                "processing": "started_at",
                "completed": "completed_at",
                "failed": "failed_at",
                "cancelled": "cancelled_at",
                "stale": "stale_at",
                "unavailable": "unavailable_at",
            }[new_state]
            values[timestamp_column] = now
            if new_state == "failed":
                values["failure_category"] = (failure_category or "").strip()[:64]
            transitioned = session.execute(
                update(AnalysisStageExecution)
                .where(
                    AnalysisStageExecution.id == stage_execution_id,
                    AnalysisStageExecution.row_version == expected_row_version,
                    AnalysisStageExecution.state == current.state,
                )
                .values(**values)
                .returning(AnalysisStageExecution)
            ).scalar_one_or_none()
            if transitioned is None:
                raise OptimisticConcurrencyError("Stage execution changed concurrently.")
            if new_state == "completed":
                historical_execution_ids = select(AnalysisStageExecution.id).where(
                    AnalysisStageExecution.analysis_id == transitioned.analysis_id,
                    AnalysisStageExecution.stage_type == transitioned.stage_type,
                    AnalysisStageExecution.id != transitioned.id,
                )
                session.execute(
                    update(AnalysisArtifact)
                    .where(
                        AnalysisArtifact.stage_execution_id.in_(historical_execution_ids),
                        AnalysisArtifact.is_current.is_(True),
                    )
                    .values(is_current=False, updated_at=now)
                )
            return _stage_result(transitioned, created=False)

    def list_stage_executions(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        stage_type: str | None = None,
    ) -> list[AnalysisStageExecution]:
        with self._session_factory() as session:
            self._assert_owner(session.get(Analysis, analysis_id), owner_user_id)
            statement = select(AnalysisStageExecution).where(
                AnalysisStageExecution.analysis_id == analysis_id,
                AnalysisStageExecution.owner_user_id == owner_user_id,
            )
            if stage_type is not None:
                statement = statement.where(AnalysisStageExecution.stage_type == stage_type)
            return list(
                session.scalars(
                    statement.order_by(
                        AnalysisStageExecution.stage_type,
                        AnalysisStageExecution.attempt_number,
                    )
                )
            )

    def register_stage_artifacts(
        self,
        *,
        owner_user_id: UUID,
        stage_execution_id: UUID,
        artifacts: list[ArtifactInput],
    ) -> list[AnalysisArtifact]:
        with self._session_factory.begin() as session:
            execution = session.scalar(
                select(AnalysisStageExecution)
                .join(Analysis, Analysis.id == AnalysisStageExecution.analysis_id)
                .where(
                    AnalysisStageExecution.id == stage_execution_id,
                    Analysis.owner_user_id == owner_user_id,
                )
            )
            if execution is None:
                raise ResourceNotFoundError("Stage execution was not found.")
            if execution.state not in {"queued", "processing"}:
                raise InvalidStateTransitionError(
                    "Artifacts cannot be added to a terminal stage execution."
                )
            expected_prefix = stage_artifact_prefix(execution.stage_type, execution.attempt_number)
            if any(not artifact.storage_key.startswith(expected_prefix) for artifact in artifacts):
                raise ValueError(
                    "Stage artifact storage keys must be namespaced by stage and attempt."
                )
            analysis = self._owned_analysis(
                session.get(Analysis, execution.analysis_id), owner_user_id
            )
            registered = self._register_artifacts(
                session,
                owner_user_id=owner_user_id,
                analysis=analysis,
                run=session.get(AnalysisRun, execution.analysis_run_id),
                artifacts=artifacts,
                stage_execution=execution,
            )
            execution.output_artifact_references = [
                {
                    "artifact_id": str(artifact.id),
                    "storage_key": artifact.storage_key,
                    "checksum_sha256": artifact.checksum_sha256,
                    "schema_version": artifact.schema_version,
                }
                for artifact in registered
            ]
            execution.updated_at = utc_now()
            return registered

    def record_calibration_verification(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: str,
        calibration_id: str,
        calibration_checksum_sha256: str,
        verification_state: str,
        verification_method: str,
        reviewer_context: str | None = None,
        verified_at: datetime | None = None,
    ) -> CalibrationVerification:
        if verification_state not in {"verified", "rejected"}:
            raise ValueError("Calibration review must be verified or rejected.")
        _validate_sha256(calibration_checksum_sha256, "calibration checksum")
        with self._session_factory.begin() as session:
            self._assert_owner(session.get(Analysis, analysis_id), owner_user_id)
            existing = session.scalar(
                select(CalibrationVerification).where(
                    CalibrationVerification.analysis_id == analysis_id,
                    CalibrationVerification.calibration_id == calibration_id,
                    CalibrationVerification.calibration_checksum_sha256
                    == calibration_checksum_sha256,
                )
            )
            if existing is not None:
                return existing
            verification = CalibrationVerification(
                owner_user_id=owner_user_id,
                analysis_id=analysis_id,
                calibration_id=calibration_id,
                calibration_checksum_sha256=calibration_checksum_sha256,
                verification_state=verification_state,
                verification_method=verification_method.strip()[:64],
                reviewer_context=(reviewer_context or "").strip()[:256] or None,
                schema_version=1,
                verified_at=verified_at or utc_now(),
            )
            session.add(verification)
            session.flush()
            return verification

    def load_job(self, *, owner_user_id: UUID, analysis_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            analysis = self._owned_analysis(session.get(Analysis, analysis_id), owner_user_id)
            return dict(analysis.job_payload)

    def list_analysis_ids(self, *, owner_user_id: UUID) -> list[str]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Analysis.id)
                    .where(Analysis.owner_user_id == owner_user_id)
                    .order_by(Analysis.created_at, Analysis.id)
                )
            )

    def persist_job(
        self,
        *,
        owner_user_id: UUID,
        payload: dict[str, Any],
        artifacts: list[ArtifactInput],
        player_selection: PlayerSelectionInput | None = None,
        compatibility_import: bool = False,
    ) -> None:
        analysis_id = str(payload["analysis_id"])
        now = utc_now()
        with self._session_factory.begin() as session:
            analysis = session.get(Analysis, analysis_id)
            if analysis is None:
                if not compatibility_import:
                    raise ResourceNotFoundError("Analysis was not reserved.")
                video = UploadedVideo(
                    owner_user_id=owner_user_id,
                    state="available",
                    original_filename=str(payload.get("source_video") or "legacy"),
                )
                session.add(video)
                session.flush()
                analysis = Analysis(
                    id=analysis_id,
                    owner_user_id=owner_user_id,
                    uploaded_video_id=video.id,
                    state=str(payload["status"]),
                    current_stage=str(payload["current_stage"]),
                    job_payload=payload,
                    created_at=_as_datetime(payload.get("created_at"), now),
                    updated_at=_as_datetime(payload.get("updated_at"), now),
                )
                session.add(analysis)
                session.flush()
                initial_run = self._insert_run(session, analysis, None)
                self._add_event(
                    session, analysis, None, analysis.state, "legacy_imported", "development"
                )
                self._add_run_event(session, initial_run, None, "processing", "run_started")
            else:
                analysis = self._owned_analysis(analysis, owner_user_id)

            previous_state = analysis.state
            new_state = str(payload["status"])
            run: AnalysisRun | None = self._active_or_latest_run(session, analysis.id)
            if new_state == "processing" and (
                run is None or run.state not in {"queued", "processing"}
            ):
                run = self._insert_run(session, analysis, _source_checksum(session, analysis))
                self._add_run_event(session, run, None, "processing", "run_started")

            analysis.state = new_state
            analysis.current_stage = str(payload["current_stage"])
            analysis.job_payload = payload
            analysis.row_version += 1
            analysis.updated_at = now
            if new_state == "completed":
                analysis.completed_at = now
            elif new_state == "failed":
                analysis.failed_at = now
            if previous_state != new_state:
                self._add_event(
                    session,
                    analysis,
                    previous_state,
                    new_state,
                    "job_state_changed",
                    "system",
                )

            persisted_video = session.get(UploadedVideo, analysis.uploaded_video_id)
            source_video = payload.get("source_video")
            if persisted_video is not None and isinstance(source_video, str):
                persisted_video.state = "available"
                persisted_video.storage_key = source_video
                persisted_video.row_version += 1
                persisted_video.updated_at = now

            if (
                run is not None
                and new_state in {"completed", "failed"}
                and run.state in {"queued", "processing"}
            ):
                previous_run_state = run.state
                run.state = new_state
                run.row_version += 1
                run.updated_at = now
                if new_state == "completed":
                    run.completed_at = now
                    analysis.promoted_run_id = run.id
                else:
                    run.failed_at = now
                    run.error_detail = str(payload.get("error") or "")[:4000] or None
                self._add_run_event(session, run, previous_run_state, new_state, f"run_{new_state}")

            self._register_artifacts(
                session,
                owner_user_id=owner_user_id,
                analysis=analysis,
                run=run,
                artifacts=artifacts,
            )
            self._persist_player_selection(
                session,
                owner_user_id=owner_user_id,
                analysis=analysis,
                run=run,
                selection=player_selection,
            )

    def list_artifacts(self, *, owner_user_id: UUID, analysis_id: str) -> list[AnalysisArtifact]:
        with self._session_factory() as session:
            analysis = session.get(Analysis, analysis_id)
            self._assert_owner(analysis, owner_user_id)
            return list(
                session.scalars(
                    select(AnalysisArtifact)
                    .where(
                        AnalysisArtifact.analysis_id == analysis_id,
                        AnalysisArtifact.owner_user_id == owner_user_id,
                        AnalysisArtifact.state == "available",
                        AnalysisArtifact.is_current.is_(True),
                    )
                    .order_by(AnalysisArtifact.storage_key)
                )
            )

    def get_artifact(
        self, *, owner_user_id: UUID, analysis_id: str, storage_key: str
    ) -> AnalysisArtifact:
        with self._session_factory() as session:
            artifact = session.scalar(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.owner_user_id == owner_user_id,
                    AnalysisArtifact.analysis_id == analysis_id,
                    AnalysisArtifact.storage_key == storage_key,
                    AnalysisArtifact.state == "available",
                    AnalysisArtifact.is_current.is_(True),
                )
            )
            if artifact is None:
                raise ArtifactNotAvailableError("Artifact was not found.")
            return artifact

    def ready(self) -> bool:
        try:
            with self._session_factory() as session:
                session.scalar(select(func.now()))
        except Exception:
            return False
        return True

    @staticmethod
    def _resolve_run_record(record: IdempotencyRecord, request_fingerprint: str) -> RunResult:
        if record.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError(
                "Idempotency key was already used for a different run request."
            )
        if record.resource_id is None:
            raise OperationInProgressError("The original run request is still in progress.")
        return RunResult(UUID(record.resource_id), False)

    def list_artifact_history(
        self, *, owner_user_id: UUID, analysis_id: str
    ) -> list[AnalysisArtifact]:
        with self._session_factory() as session:
            self._assert_owner(session.get(Analysis, analysis_id), owner_user_id)
            return list(
                session.scalars(
                    select(AnalysisArtifact)
                    .where(
                        AnalysisArtifact.owner_user_id == owner_user_id,
                        AnalysisArtifact.analysis_id == analysis_id,
                    )
                    .order_by(AnalysisArtifact.storage_key, AnalysisArtifact.created_at)
                )
            )

    def _register_artifacts(
        self,
        session: Session,
        *,
        owner_user_id: UUID,
        analysis: Analysis,
        run: AnalysisRun | None,
        artifacts: list[ArtifactInput],
        stage_execution: AnalysisStageExecution | None = None,
    ) -> list[AnalysisArtifact]:
        registered: list[AnalysisArtifact] = []
        for artifact in artifacts:
            current = session.scalar(
                select(AnalysisArtifact).where(
                    AnalysisArtifact.analysis_id == analysis.id,
                    AnalysisArtifact.storage_provider == "local",
                    AnalysisArtifact.storage_key == artifact.storage_key,
                    AnalysisArtifact.is_current.is_(True),
                )
            )
            if (
                current is not None
                and current.checksum_sha256 == artifact.checksum_sha256
                and current.size_bytes == artifact.size_bytes
            ):
                registered.append(current)
                continue
            if current is not None:
                current.is_current = False
                current.updated_at = utc_now()
            created = AnalysisArtifact(
                owner_user_id=owner_user_id,
                analysis_id=analysis.id,
                analysis_run_id=run.id if run else None,
                stage_execution_id=stage_execution.id if stage_execution else None,
                artifact_kind=artifact.artifact_kind,
                storage_provider="local",
                storage_key=artifact.storage_key,
                content_type=artifact.content_type,
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                schema_version=artifact.schema_version,
                state="available",
                is_current=True,
            )
            session.add(created)
            session.flush()
            registered.append(created)
        return registered

    @staticmethod
    def _persist_player_selection(
        session: Session,
        *,
        owner_user_id: UUID,
        analysis: Analysis,
        run: AnalysisRun | None,
        selection: PlayerSelectionInput | None,
    ) -> None:
        current = session.scalar(
            select(PlayerSelection).where(
                PlayerSelection.analysis_id == analysis.id,
                PlayerSelection.is_current.is_(True),
            )
        )
        if selection is None:
            if current is not None:
                current.is_current = False
            return
        if (
            current is not None
            and current.candidate_id == selection.candidate_id
            and current.track_id == selection.track_id
            and current.source_track_ids == selection.source_track_ids
        ):
            return
        if current is not None:
            current.is_current = False
        if run is None:
            raise ResourceNotFoundError("Player selection requires an analysis run.")
        session.add(
            PlayerSelection(
                owner_user_id=owner_user_id,
                analysis_id=analysis.id,
                analysis_run_id=run.id,
                candidate_id=selection.candidate_id,
                track_id=selection.track_id,
                source_track_ids=selection.source_track_ids,
                is_current=True,
            )
        )

    def _insert_run(
        self,
        session: Session,
        analysis: Analysis,
        source_checksum: str | None,
        *,
        state: str = "processing",
        lease_expires_at: datetime | None = None,
    ) -> AnalysisRun:
        latest = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.analysis_id == analysis.id)
            .order_by(AnalysisRun.attempt_number.desc())
            .limit(1)
            .with_for_update()
        )
        run = AnalysisRun(
            analysis_id=analysis.id,
            attempt_number=(latest.attempt_number + 1) if latest else 1,
            state=state,
            previous_run_id=latest.id if latest else None,
            source_video_checksum=source_checksum,
            pipeline_version=self._provenance.pipeline_version,
            schema_version=self._provenance.schema_version,
            policy_version=self._provenance.policy_version,
            configuration_fingerprint=self._provenance.configuration_fingerprint,
            software_commit_identifier=self._provenance.software_commit_identifier,
            deployment_build_identifier=self._provenance.deployment_build_identifier,
            lease_expires_at=lease_expires_at,
            started_at=utc_now() if state == "processing" else None,
        )
        session.add(run)
        session.flush()
        return run

    @staticmethod
    def _active_or_latest_run(session: Session, analysis_id: str) -> AnalysisRun | None:
        return session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.analysis_id == analysis_id)
            .order_by(
                AnalysisRun.state.in_(("queued", "processing")).desc(),
                AnalysisRun.attempt_number.desc(),
            )
            .limit(1)
            .with_for_update()
        )

    @staticmethod
    def _assert_owner(analysis: Analysis | None, owner_user_id: UUID) -> None:
        PersistenceService._owned_analysis(analysis, owner_user_id)

    @staticmethod
    def _owned_analysis(analysis: Analysis | None, owner_user_id: UUID) -> Analysis:
        if analysis is None:
            raise ResourceNotFoundError("Analysis was not found.")
        if analysis.owner_user_id != owner_user_id:
            raise OwnershipMismatchError("Analysis is owned by another user.")
        return analysis

    @staticmethod
    def _add_event(
        session: Session,
        analysis: Analysis,
        previous: str | None,
        new: str,
        event_type: str,
        actor_type: str,
        reason: str | None = None,
    ) -> None:
        session.add(
            AnalysisStateEvent(
                subject_type="analysis",
                analysis_id=analysis.id,
                previous_state=previous,
                new_state=new,
                event_type=event_type,
                reason=reason,
                actor_type=actor_type,
                subject_row_version=analysis.row_version,
                event_metadata={},
            )
        )

    @staticmethod
    def _add_run_event(
        session: Session,
        run: AnalysisRun,
        previous: str | None,
        new: str,
        event_type: str,
    ) -> None:
        session.add(
            AnalysisStateEvent(
                subject_type="run",
                analysis_id=run.analysis_id,
                analysis_run_id=run.id,
                previous_state=previous,
                new_state=new,
                event_type=event_type,
                actor_type="system",
                subject_row_version=run.row_version,
                event_metadata={},
            )
        )

    @staticmethod
    def _connection_pid(session: Session) -> int:
        backend_pid = session.scalar(text("select pg_backend_pid()"))
        if backend_pid is None:
            raise RuntimeError("PostgreSQL did not return a backend PID.")
        return int(backend_pid)


def _as_datetime(value: object, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return fallback


def _source_checksum(session: Session, analysis: Analysis) -> str | None:
    video = session.get(UploadedVideo, analysis.uploaded_video_id)
    return video.source_checksum if video else None


def stage_artifact_prefix(stage_type: str, attempt_number: int) -> str:
    _validate_stage_type(stage_type)
    if attempt_number < 1:
        raise ValueError("Stage attempt number must be positive.")
    root = "ball" if stage_type == "ball_tracking" else f"stages/{stage_type}"
    return f"{root}/attempt-{attempt_number:04d}/"


def _validate_stage_type(stage_type: str) -> str:
    if not _STAGE_TYPE_PATTERN.fullmatch(stage_type):
        raise ValueError("Stage type must be a lowercase stable identifier.")
    return stage_type


def _validate_sha256(value: str, label: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError(f"{label.capitalize()} must be a lowercase SHA-256 digest.")
    return value


def _stage_result(execution: AnalysisStageExecution, *, created: bool) -> StageExecutionResult:
    return StageExecutionResult(
        stage_execution_id=execution.id,
        attempt_number=execution.attempt_number,
        state=execution.state,
        row_version=execution.row_version,
        created=created,
    )
