from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import Barrier, Event, Lock
from time import perf_counter
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from spike.persistence.bootstrap import BootstrapUserPolicy, SpikeBootstrapSettings
from spike.persistence.db import database_diagnostics
from spike.persistence.errors import (
    BootstrapUserDisabledError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    OptimisticConcurrencyError,
    OwnershipMismatchError,
)
from spike.persistence.models import (
    Analysis,
    AnalysisRun,
    AnalysisStateEvent,
    IdempotencyRecord,
    UploadedVideo,
    User,
)
from spike.persistence.service import (
    PersistenceSpikeService,
    ProvenanceInput,
    ResourceResult,
    TransitionResult,
)

pytestmark = pytest.mark.postgres
ACTORS = 20
REPETITIONS = 5
TRANSITION_REPETITIONS = 10


@dataclass(frozen=True)
class _TransitionObservation:
    actor_index: int
    backend_pid: int
    state: str
    row_version: int


@dataclass(frozen=True)
class _TransitionOutcome:
    actor_index: int
    result: TransitionResult | None = None
    error: BaseException | None = None


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _provenance(suffix: str = "default") -> ProvenanceInput:
    return ProvenanceInput(
        source_video_checksum=_digest(f"source-{suffix}"),
        pipeline_version="phase-1.8b0",
        schema_version=1,
        policy_version="phase-1.8a-policy",
        configuration_fingerprint=_digest(f"configuration-{suffix}"),
        software_commit_identifier="working-tree",
        deployment_build_identifier="local-postgres-spike",
    )


def _contended(
    actors: int,
    operation: Callable[[int, Callable[[], None]], Any],
) -> tuple[list[Any], list[BaseException], float]:
    barrier = Barrier(actors)

    def invoke(index: int) -> Any:
        def synchronize() -> None:
            barrier.wait()

        return operation(index, synchronize)

    started = perf_counter()
    results: list[Any] = []
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=actors) as executor:
        futures = [executor.submit(invoke, index) for index in range(actors)]
        for future in futures:
            try:
                results.append(future.result(timeout=40))
            except BaseException as error:
                errors.append(error)
    return results, errors, perf_counter() - started


def _controlled_transition_race(
    operation: Callable[[int, Callable[[int, str, int], None]], TransitionResult],
) -> tuple[list[_TransitionOutcome], list[_TransitionObservation], float]:
    """Force both reads, then commit actor 0 before actor 1 attempts its update."""
    both_rows_loaded = Barrier(2)
    winner_committed = Event()
    observation_lock = Lock()
    observations: list[_TransitionObservation] = []

    def invoke(index: int) -> _TransitionOutcome:
        def observe(backend_pid: int, state: str, row_version: int) -> None:
            with observation_lock:
                observations.append(
                    _TransitionObservation(index, backend_pid, state, row_version)
                )
            both_rows_loaded.wait(timeout=10)
            if index == 1 and not winner_committed.wait(timeout=10):
                raise TimeoutError("Designated transition winner did not commit.")

        try:
            return _TransitionOutcome(index, result=operation(index, observe))
        except BaseException as error:
            return _TransitionOutcome(index, error=error)
        finally:
            if index == 0:
                winner_committed.set()

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(invoke, index) for index in range(2)]
        outcomes = [future.result(timeout=20) for future in futures]
    return outcomes, observations, perf_counter() - started


def _seed_owner_upload(
    service: PersistenceSpikeService, suffix: str
) -> tuple[UUID, UUID]:
    owner_id = service.create_user(identity_label=f"owner-{suffix}")
    upload = service.create_upload(
        owner_user_id=owner_id,
        idempotency_key=f"upload-{suffix}",
        request_fingerprint=_digest(f"upload-request-{suffix}"),
        original_filename=f"{suffix}.mp4",
        source_checksum=_digest(f"source-{suffix}"),
    )
    return owner_id, upload.resource_id


def _seed_analysis(
    service: PersistenceSpikeService,
    suffix: str,
    *,
    start_processing: bool = False,
) -> tuple[UUID, UUID]:
    owner_id, upload_id = _seed_owner_upload(service, suffix)
    analysis = service.create_analysis(
        owner_user_id=owner_id,
        uploaded_video_id=upload_id,
        idempotency_key=f"analysis-{suffix}",
        request_fingerprint=_digest(f"analysis-request-{suffix}"),
        provenance=_provenance(suffix),
        start_processing=start_processing,
    )
    return owner_id, analysis.resource_id


def _count(
    factory: sessionmaker[Session], model: type[Any], *criteria: Any
) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model).where(*criteria)))


def _print_metric(name: str, repetitions: list[float], actors: int) -> None:
    milliseconds = [round(value * 1000, 2) for value in repetitions]
    print(
        f"SPIKE_METRIC scenario={name} actors={actors} repetitions={len(milliseconds)} "
        f"durations_ms={milliseconds} max_ms={max(milliseconds)}"
    )


def _print_backend_pids(name: str, repetitions: list[tuple[int, int]]) -> None:
    print(
        f"SPIKE_CONNECTIONS scenario={name} "
        f"backend_pid_pairs={repetitions} all_pairs_distinct=true"
    )


def test_database_diagnostics_and_bootstrap_user(
    spike_engine: Any,
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    diagnostics = database_diagnostics(spike_engine)
    assert "PostgreSQL 16" in diagnostics["version"]
    assert diagnostics["isolation_level"] == "read committed"
    assert diagnostics["lock_timeout"] == "5s"
    assert diagnostics["statement_timeout"] == "10s"
    assert diagnostics["idle_in_transaction_session_timeout"] == "15s"

    with pytest.raises(BootstrapUserDisabledError):
        spike_service.ensure_bootstrap_user(
            BootstrapUserPolicy(
                SpikeBootstrapSettings(
                    environment="production",
                    enabled_value="true",
                    user_id_value="ce1d11a6-1112-4bc7-9d8f-da474f4a13e2",
                    identity_label="must-not-exist",
                )
            )
        )
    assert _count(session_factory, User) == 0

    user_id = spike_service.ensure_bootstrap_user(
        BootstrapUserPolicy(
            SpikeBootstrapSettings(
                environment="development",
                enabled_value="true",
                user_id_value="37de0fc7-b7d2-47b9-917c-48d2b882d6db",
                identity_label="explicit-local-spike-user",
            )
        )
    )
    assert str(user_id) == "37de0fc7-b7d2-47b9-917c-48d2b882d6db"
    assert spike_service.ensure_bootstrap_user(
        BootstrapUserPolicy(
            SpikeBootstrapSettings(
                environment="development",
                enabled_value="true",
                user_id_value=str(user_id),
                identity_label="explicit-local-spike-user",
            )
        )
    ) == user_id
    assert _count(session_factory, UploadedVideo) == 0


def test_scenario_a_duplicate_analysis_creation_same_key(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    for repetition in range(REPETITIONS):
        suffix = f"a-{repetition}"
        owner_id, upload_id = _seed_owner_upload(spike_service, suffix)

        def create_current_analysis(
            _index: int,
            hook: Callable[[], None],
            current_owner: UUID = owner_id,
            current_upload: UUID = upload_id,
            current_suffix: str = suffix,
        ) -> ResourceResult:
            return spike_service.create_analysis(
                owner_user_id=current_owner,
                uploaded_video_id=current_upload,
                idempotency_key=f"same-analysis-key-{current_suffix}",
                request_fingerprint=_digest(
                    f"same-analysis-request-{current_suffix}"
                ),
                provenance=_provenance(current_suffix),
                start_processing=True,
                synchronization_hook=hook,
            )

        results, errors, duration = _contended(
            ACTORS,
            create_current_analysis,
        )
        timings.append(duration)
        assert not errors
        assert len(results) == ACTORS
        assert len({result.resource_id for result in results}) == 1
        assert len({result.backend_pid for result in results}) == ACTORS
        assert Counter(result.created for result in results) == {True: 1, False: 19}
        analysis_id = results[0].resource_id
        assert _count(session_factory, Analysis, Analysis.id == analysis_id) == 1
        assert (
            _count(
                session_factory,
                AnalysisRun,
                AnalysisRun.analysis_id == analysis_id,
            )
            == 1
        )
        assert (
            _count(
                session_factory,
                AnalysisStateEvent,
                AnalysisStateEvent.analysis_id == analysis_id,
            )
            == 2
        )
    _print_metric("A_duplicate_analysis", timings, ACTORS)


def test_scenario_b_same_key_different_fingerprints_conflict(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    for repetition in range(REPETITIONS):
        owner_id = spike_service.create_user(identity_label=f"owner-b-{repetition}")

        def create_conflicting_upload(
            index: int,
            hook: Callable[[], None],
            current_owner: UUID = owner_id,
            current_repetition: int = repetition,
        ) -> ResourceResult:
            return spike_service.create_upload(
                owner_user_id=current_owner,
                idempotency_key=f"same-conflicting-key-{current_repetition}",
                request_fingerprint=_digest(
                    f"different-request-{current_repetition}-{index}"
                ),
                original_filename=f"candidate-{index}.mp4",
                source_checksum=_digest(
                    f"source-b-{current_repetition}-{index}"
                ),
                synchronization_hook=hook,
            )

        results, errors, duration = _contended(
            ACTORS,
            create_conflicting_upload,
        )
        timings.append(duration)
        assert len(results) == 1
        assert len(errors) == ACTORS - 1
        assert all(isinstance(error, IdempotencyConflictError) for error in errors)
        assert (
            _count(
                session_factory,
                UploadedVideo,
                UploadedVideo.owner_user_id == owner_id,
            )
            == 1
        )
    _print_metric("B_conflicting_fingerprints", timings, ACTORS)


def test_scenario_c_competing_run_start_requests(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    for repetition in range(REPETITIONS):
        suffix = f"c-{repetition}"
        owner_id, analysis_id = _seed_analysis(spike_service, suffix)

        def start_competing_run(
            index: int,
            hook: Callable[[], None],
            current_owner: UUID = owner_id,
            current_analysis: UUID = analysis_id,
            current_suffix: str = suffix,
        ) -> ResourceResult:
            return spike_service.start_run(
                owner_user_id=current_owner,
                analysis_id=current_analysis,
                idempotency_key=f"distinct-run-start-{current_suffix}-{index}",
                request_fingerprint=_digest(
                    f"run-start-{current_suffix}-{index}"
                ),
                provenance=_provenance(current_suffix),
                synchronization_hook=hook,
            )

        results, errors, duration = _contended(
            ACTORS,
            start_competing_run,
        )
        timings.append(duration)
        assert not errors
        assert len({result.resource_id for result in results}) == 1
        assert len({result.backend_pid for result in results}) == ACTORS
        assert Counter(result.created for result in results) == {True: 1, False: 19}
        assert (
            _count(
                session_factory,
                AnalysisRun,
                AnalysisRun.analysis_id == analysis_id,
            )
            == 1
        )
        assert (
            _count(
                session_factory,
                IdempotencyRecord,
                IdempotencyRecord.owner_user_id == owner_id,
                IdempotencyRecord.scope == "run_start",
            )
            == ACTORS
        )
        with session_factory() as session:
            analysis = session.get(Analysis, analysis_id)
            active_run = session.scalar(
                select(AnalysisRun).where(AnalysisRun.analysis_id == analysis_id)
            )
            assert analysis is not None
            assert active_run is not None
            assert analysis.state == active_run.state == "processing"
        assert (
            _count(
                session_factory,
                AnalysisStateEvent,
                AnalysisStateEvent.analysis_id == analysis_id,
            )
            == 3
        )
    _print_metric("C_competing_run_starts", timings, ACTORS)


def test_scenarios_d_and_j_independent_requests_and_owner_scoped_keys(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    for repetition in range(REPETITIONS):
        owners = [
            spike_service.create_user(
                identity_label=f"owner-d-{repetition}-{index}"
            )
            for index in range(10)
        ]

        def create_independent_workflow(
            index: int,
            hook: Callable[[], None],
            current_owners: tuple[UUID, ...] = tuple(owners),
            current_repetition: int = repetition,
        ) -> tuple[ResourceResult, ResourceResult]:
            upload = spike_service.create_upload(
                owner_user_id=current_owners[index],
                idempotency_key="same-key-across-owners",
                request_fingerprint=_digest("same-request-across-owners"),
                original_filename=f"independent-{current_repetition}-{index}.mp4",
                source_checksum=_digest(
                    f"independent-source-{current_repetition}-{index}"
                ),
                synchronization_hook=hook,
            )
            analysis = spike_service.create_analysis(
                owner_user_id=current_owners[index],
                uploaded_video_id=upload.resource_id,
                idempotency_key=(
                    f"independent-analysis-{current_repetition}-{index}"
                ),
                request_fingerprint=_digest(
                    f"independent-analysis-request-{current_repetition}-{index}"
                ),
                provenance=_provenance(f"d-{current_repetition}-{index}"),
            )
            return upload, analysis

        results, errors, duration = _contended(
            10,
            create_independent_workflow,
        )
        timings.append(duration)
        assert not errors
        uploads = [result[0] for result in results]
        analyses = [result[1] for result in results]
        assert len({result.resource_id for result in uploads}) == 10
        assert len({result.resource_id for result in analyses}) == 10
        assert len({result.backend_pid for result in uploads}) == 10
        assert all(result.created for result in (*uploads, *analyses))
        with session_factory() as session:
            persisted = session.scalars(
                select(Analysis).where(Analysis.id.in_([item.resource_id for item in analyses]))
            ).all()
            assert len(persisted) == 10
            assert {
                (item.owner_user_id, item.uploaded_video_id) for item in persisted
            } == {
                (owners[index], uploads[index].resource_id) for index in range(10)
            }
    _print_metric("D_J_independent_owner_scoped", timings, 10)


def test_scenario_e_replay_after_commit_has_no_duplicate_side_effects(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    owner_id, upload_id = _seed_owner_upload(spike_service, "e")
    first = spike_service.create_analysis(
        owner_user_id=owner_id,
        uploaded_video_id=upload_id,
        idempotency_key="replay-analysis-e",
        request_fingerprint=_digest("replay-analysis-request-e"),
        provenance=_provenance("e"),
        start_processing=True,
    )
    second = spike_service.create_analysis(
        owner_user_id=owner_id,
        uploaded_video_id=upload_id,
        idempotency_key="replay-analysis-e",
        request_fingerprint=_digest("replay-analysis-request-e"),
        provenance=_provenance("e"),
        start_processing=True,
    )
    assert first.resource_id == second.resource_id
    assert first.created is True
    assert second.created is False
    assert _count(session_factory, AnalysisRun) == 1
    assert _count(session_factory, AnalysisStateEvent) == 2


def test_scenario_f_valid_and_invalid_transition_race(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    backend_pid_pairs: list[tuple[int, int]] = []
    for repetition in range(TRANSITION_REPETITIONS):
        suffix = f"f-{repetition}"
        owner_id, analysis_id = _seed_analysis(spike_service, suffix)
        run = spike_service.start_run(
            owner_user_id=owner_id,
            analysis_id=analysis_id,
            idempotency_key=f"queued-run-{suffix}",
            request_fingerprint=_digest(f"queued-run-request-{suffix}"),
            provenance=_provenance(suffix),
            state="queued",
        )
        before_events = _count(session_factory, AnalysisStateEvent)
        valid_reason = f"{suffix}-valid"
        rejected_reason = f"{suffix}-invalid"

        def attempt_transition(
            index: int,
            hook: Callable[[int, str, int], None],
            current_run_id: UUID = run.resource_id,
            current_valid_reason: str = valid_reason,
            current_rejected_reason: str = rejected_reason,
        ) -> TransitionResult:
            return spike_service.transition_run(
                run_id=current_run_id,
                expected_version=1,
                to_state="processing" if index == 0 else "completed",
                reason=(
                    current_valid_reason if index == 0 else current_rejected_reason
                ),
                observation_hook=hook,
            )

        outcomes, observations, duration = _controlled_transition_race(
            attempt_transition
        )
        timings.append(duration)
        assert [(item.state, item.row_version) for item in observations] == [
            ("queued", 1),
            ("queued", 1),
        ]
        observed_pids = sorted(item.backend_pid for item in observations)
        assert len(set(observed_pids)) == 2
        backend_pid_pairs.append((observed_pids[0], observed_pids[1]))
        assert outcomes[0].error is None
        assert outcomes[0].result is not None
        assert outcomes[0].result.state == "processing"
        assert outcomes[1].result is None
        assert isinstance(outcomes[1].error, InvalidStateTransitionError)

        with session_factory() as session:
            persisted_run = session.get(AnalysisRun, run.resource_id)
            persisted_analysis = session.get(Analysis, analysis_id)
            assert persisted_run is not None
            assert persisted_analysis is not None
            assert (persisted_run.state, persisted_run.row_version) == ("processing", 2)
            assert persisted_run.completed_at is None
            assert persisted_run.failed_at is None
            assert (persisted_analysis.state, persisted_analysis.row_version) == (
                "processing",
                2,
            )
            race_events = session.scalars(
                select(AnalysisStateEvent).where(
                    AnalysisStateEvent.analysis_id == analysis_id,
                    AnalysisStateEvent.reason.in_((valid_reason, rejected_reason)),
                )
            ).all()
        assert Counter(
            (
                event.subject_type,
                event.analysis_run_id,
                event.previous_state,
                event.new_state,
                event.event_type,
                event.subject_row_version,
                event.reason,
            )
            for event in race_events
        ) == Counter(
            {
                (
                    "run",
                    run.resource_id,
                    "queued",
                    "processing",
                    "run_state_transitioned",
                    2,
                    valid_reason,
                ): 1,
                (
                    "analysis",
                    None,
                    "created",
                    "processing",
                    "analysis_state_reflected",
                    2,
                    valid_reason,
                ): 1,
            }
        )
        assert _count(session_factory, AnalysisStateEvent) == before_events + 2
    _print_metric("F_valid_invalid_transition", timings, 2)
    _print_backend_pids("F_valid_invalid_transition", backend_pid_pairs)


def test_scenario_g_optimistic_transition_conflict(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    backend_pid_pairs: list[tuple[int, int]] = []
    for repetition in range(TRANSITION_REPETITIONS):
        suffix = f"g-{repetition}"
        owner_id, analysis_id = _seed_analysis(spike_service, suffix)
        run = spike_service.start_run(
            owner_user_id=owner_id,
            analysis_id=analysis_id,
            idempotency_key=f"processing-run-{suffix}",
            request_fingerprint=_digest(f"processing-run-request-{suffix}"),
            provenance=_provenance(suffix),
        )
        before_events = _count(session_factory, AnalysisStateEvent)
        winning_reason = f"{suffix}-winner"
        stale_reason = f"{suffix}-stale"

        def attempt_transition(
            index: int,
            hook: Callable[[int, str, int], None],
            current_run_id: UUID = run.resource_id,
            current_winning_reason: str = winning_reason,
            current_stale_reason: str = stale_reason,
        ) -> TransitionResult:
            return spike_service.transition_run(
                run_id=current_run_id,
                expected_version=1,
                to_state="completed" if index == 0 else "failed",
                reason=(
                    current_winning_reason if index == 0 else current_stale_reason
                ),
                observation_hook=hook,
            )

        outcomes, observations, duration = _controlled_transition_race(
            attempt_transition
        )
        timings.append(duration)
        assert [(item.state, item.row_version) for item in observations] == [
            ("processing", 1),
            ("processing", 1),
        ]
        observed_pids = sorted(item.backend_pid for item in observations)
        assert len(set(observed_pids)) == 2
        backend_pid_pairs.append((observed_pids[0], observed_pids[1]))
        assert outcomes[0].error is None
        assert outcomes[0].result is not None
        assert outcomes[0].result.state == "completed"
        assert outcomes[1].result is None
        assert isinstance(outcomes[1].error, OptimisticConcurrencyError)

        with session_factory() as session:
            persisted_run = session.get(AnalysisRun, run.resource_id)
            persisted_analysis = session.get(Analysis, analysis_id)
            assert persisted_run is not None
            assert persisted_analysis is not None
            assert (persisted_run.state, persisted_run.row_version) == ("completed", 2)
            assert persisted_run.completed_at is not None
            assert persisted_run.failed_at is None
            assert (persisted_analysis.state, persisted_analysis.row_version) == (
                "completed",
                3,
            )
            race_events = session.scalars(
                select(AnalysisStateEvent).where(
                    AnalysisStateEvent.analysis_id == analysis_id,
                    AnalysisStateEvent.reason.in_((winning_reason, stale_reason)),
                )
            ).all()
        assert Counter(
            (
                event.subject_type,
                event.analysis_run_id,
                event.previous_state,
                event.new_state,
                event.event_type,
                event.subject_row_version,
                event.reason,
            )
            for event in race_events
        ) == Counter(
            {
                (
                    "run",
                    run.resource_id,
                    "processing",
                    "completed",
                    "run_state_transitioned",
                    2,
                    winning_reason,
                ): 1,
                (
                    "analysis",
                    None,
                    "processing",
                    "completed",
                    "analysis_state_reflected",
                    3,
                    winning_reason,
                ): 1,
            }
        )
        assert _count(session_factory, AnalysisStateEvent) == before_events + 2
    _print_metric("G_optimistic_conflict", timings, 2)
    _print_backend_pids("G_optimistic_conflict", backend_pid_pairs)


def test_scenario_h_stale_detection_and_replacement_run_race(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    timings: list[float] = []
    for repetition in range(REPETITIONS):
        suffix = f"h-{repetition}"
        owner_id, analysis_id = _seed_analysis(spike_service, suffix)
        expired = datetime.now(tz=UTC) - timedelta(minutes=1)
        old_run = spike_service.start_run(
            owner_user_id=owner_id,
            analysis_id=analysis_id,
            idempotency_key=f"expired-run-{suffix}",
            request_fingerprint=_digest(f"expired-run-request-{suffix}"),
            provenance=_provenance(f"{suffix}-old"),
            lease_expires_at=expired,
        )
        assert spike_service.run_is_stale(old_run.resource_id)

        def mark_current_run_stale(
            _index: int,
            hook: Callable[[], None],
            current_run_id: UUID = old_run.resource_id,
        ) -> TransitionResult:
            return spike_service.transition_run(
                run_id=current_run_id,
                expected_version=1,
                to_state="stale",
                synchronization_hook=hook,
            )

        transitions, transition_errors, stale_duration = _contended(
            ACTORS,
            mark_current_run_stale,
        )
        assert len(transitions) == 1
        assert len(transition_errors) == ACTORS - 1
        assert all(
            isinstance(error, OptimisticConcurrencyError)
            for error in transition_errors
        )

        def start_current_replacement(
            index: int,
            hook: Callable[[], None],
            current_owner: UUID = owner_id,
            current_analysis: UUID = analysis_id,
            current_suffix: str = suffix,
            current_old_run_id: UUID = old_run.resource_id,
        ) -> ResourceResult:
            return spike_service.start_run(
                owner_user_id=current_owner,
                analysis_id=current_analysis,
                idempotency_key=f"replacement-run-{current_suffix}-{index}",
                request_fingerprint=_digest(
                    f"replacement-run-request-{current_suffix}-{index}"
                ),
                provenance=_provenance(f"{current_suffix}-new"),
                previous_run_id=current_old_run_id,
                synchronization_hook=hook,
            )

        replacements, replacement_errors, replacement_duration = _contended(
            ACTORS,
            start_current_replacement,
        )
        timings.append(stale_duration + replacement_duration)
        assert not replacement_errors
        assert len({result.resource_id for result in replacements}) == 1
        replacement_id = replacements[0].resource_id
        with session_factory() as session:
            replacement = session.get(AnalysisRun, replacement_id)
            old_persisted = session.get(AnalysisRun, old_run.resource_id)
            assert replacement is not None
            assert old_persisted is not None
            assert old_persisted.state == "stale"
            assert replacement.previous_run_id == old_run.resource_id
        assert (
            _count(
                session_factory,
                AnalysisRun,
                AnalysisRun.analysis_id == analysis_id,
                AnalysisRun.state.in_(("queued", "processing")),
            )
            == 1
        )
        assert (
            _count(
                session_factory,
                AnalysisRun,
                AnalysisRun.analysis_id == analysis_id,
            )
            == 2
        )
    _print_metric("H_stale_and_replacement", timings, ACTORS)


def test_database_ownership_boundary_rejects_cross_owner_analysis(
    spike_service: PersistenceSpikeService,
    session_factory: sessionmaker[Session],
) -> None:
    first_owner, upload_id = _seed_owner_upload(spike_service, "ownership-first")
    second_owner = spike_service.create_user(identity_label="ownership-second")
    assert first_owner != second_owner
    with pytest.raises(OwnershipMismatchError):
        spike_service.create_analysis(
            owner_user_id=second_owner,
            uploaded_video_id=upload_id,
            idempotency_key="cross-owner-analysis",
            request_fingerprint=_digest("cross-owner-analysis-request"),
            provenance=_provenance("cross-owner"),
        )

    with pytest.raises(IntegrityError), session_factory.begin() as session:
        session.add(
            Analysis(
                owner_user_id=second_owner,
                uploaded_video_id=upload_id,
                state="created",
            )
        )
        session.flush()
