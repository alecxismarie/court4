from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from spike.persistence.bootstrap import BootstrapUserPolicy
from spike.persistence.errors import (
    IdempotencyConflictError,
    InvalidStateTransitionError,
    OperationInProgressError,
    OptimisticConcurrencyError,
    OwnershipMismatchError,
    ResourceNotFoundError,
)
from spike.persistence.models import (
    Analysis,
    AnalysisRun,
    AnalysisStateEvent,
    IdempotencyRecord,
    UploadedVideo,
    User,
    utc_now,
)

SynchronizationHook = Callable[[], None]
TransitionObservationHook = Callable[[int, str, int], None]
_HEX_DIGITS = frozenset("0123456789abcdef")
_RUN_TRANSITIONS = {
    "queued": frozenset({"processing", "cancelled"}),
    "processing": frozenset({"completed", "failed", "cancelled", "stale"}),
}
_TERMINAL_RUN_TO_ANALYSIS = {
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}


@dataclass(frozen=True)
class ProvenanceInput:
    source_video_checksum: str
    pipeline_version: str
    schema_version: int
    policy_version: str
    configuration_fingerprint: str
    software_commit_identifier: str
    deployment_build_identifier: str

    def validated(self) -> ProvenanceInput:
        _validate_fingerprint(self.source_video_checksum, "source video checksum")
        _validate_fingerprint(
            self.configuration_fingerprint, "configuration fingerprint"
        )
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        for label, value, maximum in (
            ("pipeline_version", self.pipeline_version, 64),
            ("policy_version", self.policy_version, 64),
            ("software_commit_identifier", self.software_commit_identifier, 64),
            ("deployment_build_identifier", self.deployment_build_identifier, 128),
        ):
            if not value or len(value) > maximum:
                raise ValueError(f"{label} must be 1-{maximum} characters")
        return self


@dataclass(frozen=True)
class ResourceResult:
    resource_id: UUID
    created: bool
    resolution: str
    backend_pid: int


@dataclass(frozen=True)
class TransitionResult:
    run_id: UUID
    state: str
    row_version: int
    backend_pid: int


class PersistenceSpikeService:
    """Isolated transactional service used only by the Phase 1.8B0 spike."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def ensure_bootstrap_user(self, policy: BootstrapUserPolicy) -> UUID:
        user_id, identity_label = policy.validated_identity()
        with self._session_factory.begin() as session:
            existing = session.get(User, user_id)
            if existing is not None:
                if existing.identity_label != identity_label:
                    raise IdempotencyConflictError(
                        "The bootstrap UUID already has a different identity label."
                    )
                return existing.id
            session.add(
                User(
                    id=user_id,
                    identity_label=identity_label,
                    account_status="active",
                )
            )
        return user_id

    def create_user(self, *, identity_label: str, user_id: UUID | None = None) -> UUID:
        with self._session_factory.begin() as session:
            user = User(
                id=user_id or uuid4(),
                identity_label=identity_label,
                account_status="active",
            )
            session.add(user)
        return user.id

    def create_upload(
        self,
        *,
        owner_user_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        original_filename: str,
        source_checksum: str,
        synchronization_hook: SynchronizationHook | None = None,
    ) -> ResourceResult:
        _validate_fingerprint(request_fingerprint, "request fingerprint")
        _validate_fingerprint(source_checksum, "source checksum")
        return self._create_idempotent(
            owner_user_id=owner_user_id,
            scope="upload_reservation",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            resource_type="uploaded_video",
            synchronization_hook=synchronization_hook,
            create_resource=lambda session: self._insert_upload(
                session,
                owner_user_id=owner_user_id,
                original_filename=original_filename,
                source_checksum=source_checksum,
            ),
        )

    def create_analysis(
        self,
        *,
        owner_user_id: UUID,
        uploaded_video_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        provenance: ProvenanceInput,
        start_processing: bool = False,
        synchronization_hook: SynchronizationHook | None = None,
    ) -> ResourceResult:
        _validate_fingerprint(request_fingerprint, "request fingerprint")
        provenance.validated()
        return self._create_idempotent(
            owner_user_id=owner_user_id,
            scope="analysis_create",
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            resource_type="analysis",
            synchronization_hook=synchronization_hook,
            create_resource=lambda session: self._insert_analysis(
                session,
                owner_user_id=owner_user_id,
                uploaded_video_id=uploaded_video_id,
                provenance=provenance,
                start_processing=start_processing,
            ),
        )

    def start_run(
        self,
        *,
        owner_user_id: UUID,
        analysis_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        provenance: ProvenanceInput,
        state: str = "processing",
        lease_expires_at: datetime | None = None,
        previous_run_id: UUID | None = None,
        synchronization_hook: SynchronizationHook | None = None,
    ) -> ResourceResult:
        if state not in {"queued", "processing"}:
            raise ValueError("A new run must start in queued or processing state.")
        _validate_fingerprint(request_fingerprint, "request fingerprint")
        provenance.validated()
        key_hash = _hash_key(idempotency_key)
        existing = self._resolve_idempotency(
            owner_user_id=owner_user_id,
            scope="run_start",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if existing is not None:
            return existing

        backend_pid = 0
        try:
            with self._session_factory.begin() as session:
                backend_pid = self._connection_pid(session)
                if synchronization_hook is not None:
                    synchronization_hook()
                self._assert_analysis_owner(session, analysis_id, owner_user_id)
                record = IdempotencyRecord(
                    owner_user_id=owner_user_id,
                    scope="run_start",
                    key_hash=key_hash,
                    request_fingerprint=request_fingerprint,
                    status="in_progress",
                )
                session.add(record)
                session.flush()
                run = self._insert_run(
                    session,
                    analysis_id=analysis_id,
                    provenance=provenance,
                    state=state,
                    lease_expires_at=lease_expires_at,
                    previous_run_id=previous_run_id,
                )
                if state == "processing":
                    self._reflect_run_state_on_analysis(
                        session,
                        analysis_id=analysis_id,
                        to_state=state,
                        actor_type="test",
                        reason="run_started",
                        at=utc_now(),
                    )
                record.status = "completed"
                record.resource_type = "analysis_run"
                record.resource_id = run.id
            return ResourceResult(run.id, True, "created", backend_pid)
        except IntegrityError as error:
            if not _is_constraint(
                error,
                {
                    "uq_spike_run_one_active",
                    "uq_spike_idempotency_owner_scope_key",
                },
            ):
                raise

        existing = self._resolve_idempotency(
            owner_user_id=owner_user_id,
            scope="run_start",
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
            backend_pid=backend_pid,
        )
        if existing is not None:
            return existing

        with self._session_factory.begin() as session:
            active_run = session.scalar(
                select(AnalysisRun)
                .where(
                    AnalysisRun.analysis_id == analysis_id,
                    AnalysisRun.state.in_(("queued", "processing")),
                )
                .with_for_update()
            )
            if active_run is None:
                raise OperationInProgressError(
                    "The active-run contention winner could not be resolved."
                )
            record = IdempotencyRecord(
                owner_user_id=owner_user_id,
                scope="run_start",
                key_hash=key_hash,
                request_fingerprint=request_fingerprint,
                status="completed",
                resource_type="analysis_run",
                resource_id=active_run.id,
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError as error:
                if not _is_constraint(
                    error, {"uq_spike_idempotency_owner_scope_key"}
                ):
                    raise
                raise OperationInProgressError(
                    "Concurrent idempotency resolution must be retried."
                ) from error
        return ResourceResult(active_run.id, False, "existing_active_run", backend_pid)

    def transition_run(
        self,
        *,
        run_id: UUID,
        expected_version: int,
        to_state: str,
        actor_type: str = "test",
        reason: str | None = None,
        synchronization_hook: SynchronizationHook | None = None,
        observation_hook: TransitionObservationHook | None = None,
        now: datetime | None = None,
    ) -> TransitionResult:
        transition_time = now or utc_now()
        with self._session_factory.begin() as session:
            backend_pid = self._connection_pid(session)
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise ResourceNotFoundError("Analysis run does not exist.")
            from_state = run.state
            observed_version = run.row_version
            if observation_hook is not None:
                observation_hook(backend_pid, from_state, observed_version)
            if synchronization_hook is not None:
                synchronization_hook()
            if observed_version != expected_version:
                raise OptimisticConcurrencyError(
                    "The supplied run row version is stale."
                )
            if to_state not in _RUN_TRANSITIONS.get(from_state, frozenset()):
                raise InvalidStateTransitionError(
                    f"Run transition {from_state!r} -> {to_state!r} is invalid."
                )
            if to_state == "stale" and not _lease_is_expired(run, transition_time):
                raise InvalidStateTransitionError(
                    "A processing run is stale only after its lease expires."
                )

            values: dict[str, object] = {
                "state": to_state,
                "row_version": expected_version + 1,
                "updated_at": transition_time,
            }
            if to_state == "processing":
                values["started_at"] = transition_time
            elif to_state == "completed":
                values["completed_at"] = transition_time
            elif to_state == "failed":
                values["failed_at"] = transition_time

            result = cast(
                CursorResult[Any],
                session.execute(
                    update(AnalysisRun)
                    .where(
                        AnalysisRun.id == run_id,
                        AnalysisRun.row_version == expected_version,
                        AnalysisRun.state == from_state,
                    )
                    .values(**values)
                ),
            )
            if result.rowcount != 1:
                raise OptimisticConcurrencyError(
                    "A competing run transition committed first."
                )
            session.add(
                _run_event(
                    run_id=run.id,
                    analysis_id=run.analysis_id,
                    previous_state=from_state,
                    new_state=to_state,
                    row_version=expected_version + 1,
                    actor_type=actor_type,
                    event_type="run_state_transitioned",
                    reason=reason,
                )
            )
            self._reflect_run_state_on_analysis(
                session,
                analysis_id=run.analysis_id,
                to_state=to_state,
                actor_type=actor_type,
                reason=reason,
                at=transition_time,
            )
        return TransitionResult(
            run_id=run_id,
            state=to_state,
            row_version=expected_version + 1,
            backend_pid=backend_pid,
        )

    def run_is_stale(self, run_id: UUID, *, now: datetime | None = None) -> bool:
        with self._session_factory() as session:
            run = session.get(AnalysisRun, run_id)
            if run is None:
                raise ResourceNotFoundError("Analysis run does not exist.")
            return _lease_is_expired(run, now or datetime.now(tz=UTC))

    def _create_idempotent(
        self,
        *,
        owner_user_id: UUID,
        scope: str,
        idempotency_key: str,
        request_fingerprint: str,
        resource_type: str,
        synchronization_hook: SynchronizationHook | None,
        create_resource: Callable[[Session], UUID],
    ) -> ResourceResult:
        key_hash = _hash_key(idempotency_key)
        existing = self._resolve_idempotency(
            owner_user_id=owner_user_id,
            scope=scope,
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
        )
        if existing is not None:
            return existing

        backend_pid = 0
        resource_id: UUID
        try:
            with self._session_factory.begin() as session:
                backend_pid = self._connection_pid(session)
                if synchronization_hook is not None:
                    synchronization_hook()
                record = IdempotencyRecord(
                    owner_user_id=owner_user_id,
                    scope=scope,
                    key_hash=key_hash,
                    request_fingerprint=request_fingerprint,
                    status="in_progress",
                )
                session.add(record)
                session.flush()
                resource_id = create_resource(session)
                record.status = "completed"
                record.resource_type = resource_type
                record.resource_id = resource_id
            return ResourceResult(resource_id, True, "created", backend_pid)
        except IntegrityError as error:
            if not _is_constraint(
                error, {"uq_spike_idempotency_owner_scope_key"}
            ):
                raise

        existing = self._resolve_idempotency(
            owner_user_id=owner_user_id,
            scope=scope,
            key_hash=key_hash,
            request_fingerprint=request_fingerprint,
            backend_pid=backend_pid,
        )
        if existing is None:
            raise OperationInProgressError(
                "The idempotent contention winner has not committed a result."
            )
        return existing

    def _resolve_idempotency(
        self,
        *,
        owner_user_id: UUID,
        scope: str,
        key_hash: str,
        request_fingerprint: str,
        backend_pid: int = 0,
    ) -> ResourceResult | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.owner_user_id == owner_user_id,
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.key_hash == key_hash,
                )
            )
            if record is None:
                return None
            if record.request_fingerprint != request_fingerprint:
                raise IdempotencyConflictError(
                    "The idempotency key was reused with a different request."
                )
            if record.status != "completed" or record.resource_id is None:
                raise OperationInProgressError(
                    "The idempotent operation has no committed resource yet."
                )
            return ResourceResult(
                resource_id=record.resource_id,
                created=False,
                resolution="idempotent_replay",
                backend_pid=backend_pid,
            )

    @staticmethod
    def _connection_pid(session: Session) -> int:
        return int(session.scalar(text("select pg_backend_pid()")))

    @staticmethod
    def _insert_upload(
        session: Session,
        *,
        owner_user_id: UUID,
        original_filename: str,
        source_checksum: str,
    ) -> UUID:
        upload = UploadedVideo(
            owner_user_id=owner_user_id,
            state="available",
            original_filename=original_filename,
            source_checksum=source_checksum,
        )
        session.add(upload)
        session.flush()
        return upload.id

    def _insert_analysis(
        self,
        session: Session,
        *,
        owner_user_id: UUID,
        uploaded_video_id: UUID,
        provenance: ProvenanceInput,
        start_processing: bool,
    ) -> UUID:
        upload = session.scalar(
            select(UploadedVideo).where(
                UploadedVideo.id == uploaded_video_id,
                UploadedVideo.owner_user_id == owner_user_id,
            )
        )
        if upload is None:
            if session.get(UploadedVideo, uploaded_video_id) is not None:
                raise OwnershipMismatchError(
                    "The uploaded video belongs to a different user."
                )
            raise ResourceNotFoundError("Uploaded video does not exist.")
        if upload.state != "available":
            raise InvalidStateTransitionError(
                "An analysis requires an available uploaded video."
            )
        initial_state = "processing" if start_processing else "created"
        analysis = Analysis(
            owner_user_id=owner_user_id,
            uploaded_video_id=uploaded_video_id,
            state=initial_state,
        )
        session.add(analysis)
        session.flush()
        session.add(
            _analysis_event(
                analysis_id=analysis.id,
                previous_state=None,
                new_state=initial_state,
                row_version=1,
                event_type="analysis_created",
            )
        )
        if start_processing:
            self._insert_run(
                session,
                analysis_id=analysis.id,
                provenance=provenance,
                state="processing",
            )
        return analysis.id

    @staticmethod
    def _insert_run(
        session: Session,
        *,
        analysis_id: UUID,
        provenance: ProvenanceInput,
        state: str,
        lease_expires_at: datetime | None = None,
        previous_run_id: UUID | None = None,
    ) -> AnalysisRun:
        now = utc_now()
        run = AnalysisRun(
            analysis_id=analysis_id,
            state=state,
            previous_run_id=previous_run_id,
            source_video_checksum=provenance.source_video_checksum,
            pipeline_version=provenance.pipeline_version,
            schema_version=provenance.schema_version,
            policy_version=provenance.policy_version,
            configuration_fingerprint=provenance.configuration_fingerprint,
            software_commit_identifier=provenance.software_commit_identifier,
            deployment_build_identifier=provenance.deployment_build_identifier,
            lease_expires_at=lease_expires_at,
            heartbeat_at=now if state == "processing" else None,
            started_at=now if state == "processing" else None,
        )
        session.add(run)
        session.flush()
        session.add(
            _run_event(
                run_id=run.id,
                analysis_id=analysis_id,
                previous_state=None,
                new_state=state,
                row_version=1,
                actor_type="test",
                event_type="run_started",
            )
        )
        return run

    @staticmethod
    def _assert_analysis_owner(
        session: Session, analysis_id: UUID, owner_user_id: UUID
    ) -> None:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            raise ResourceNotFoundError("Analysis does not exist.")
        if analysis.owner_user_id != owner_user_id:
            raise OwnershipMismatchError("The analysis belongs to a different user.")

    @staticmethod
    def _reflect_run_state_on_analysis(
        session: Session,
        *,
        analysis_id: UUID,
        to_state: str,
        actor_type: str,
        reason: str | None,
        at: datetime,
    ) -> None:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            raise ResourceNotFoundError("Analysis does not exist.")
        analysis_state = (
            "processing" if to_state == "processing" else _TERMINAL_RUN_TO_ANALYSIS.get(to_state)
        )
        if analysis_state is None or analysis.state == analysis_state:
            return
        previous_state = analysis.state
        analysis.state = analysis_state
        analysis.row_version += 1
        analysis.updated_at = at
        if analysis_state == "completed":
            analysis.completed_at = at
        elif analysis_state == "failed":
            analysis.failed_at = at
        elif analysis_state == "cancelled":
            analysis.cancelled_at = at
        session.add(
            _analysis_event(
                analysis_id=analysis.id,
                previous_state=previous_state,
                new_state=analysis_state,
                row_version=analysis.row_version,
                actor_type=actor_type,
                event_type="analysis_state_reflected",
                reason=reason,
            )
        )


def _hash_key(raw_key: str) -> str:
    if not raw_key:
        raise ValueError("The idempotency key must not be empty.")
    return sha256(raw_key.encode("utf-8")).hexdigest()


def _validate_fingerprint(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex digest.")


def _lease_is_expired(run: AnalysisRun, now: datetime) -> bool:
    return (
        run.state == "processing"
        and run.lease_expires_at is not None
        and run.lease_expires_at <= now
    )


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _is_constraint(error: IntegrityError, names: set[str]) -> bool:
    return _constraint_name(error) in names


def _analysis_event(
    *,
    analysis_id: UUID,
    previous_state: str | None,
    new_state: str,
    row_version: int,
    actor_type: str = "test",
    event_type: str,
    reason: str | None = None,
) -> AnalysisStateEvent:
    return AnalysisStateEvent(
        subject_type="analysis",
        analysis_id=analysis_id,
        previous_state=previous_state,
        new_state=new_state,
        event_type=event_type,
        reason=reason,
        actor_type=actor_type,
        subject_row_version=row_version,
        event_metadata={},
    )


def _run_event(
    *,
    run_id: UUID,
    analysis_id: UUID,
    previous_state: str | None,
    new_state: str,
    row_version: int,
    actor_type: str,
    event_type: str,
    reason: str | None = None,
) -> AnalysisStateEvent:
    return AnalysisStateEvent(
        subject_type="run",
        analysis_id=analysis_id,
        analysis_run_id=run_id,
        previous_state=previous_state,
        new_state=new_state,
        event_type=event_type,
        reason=reason,
        actor_type=actor_type,
        subject_row_version=row_version,
        event_metadata={},
    )
