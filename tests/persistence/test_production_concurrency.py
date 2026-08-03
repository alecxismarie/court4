from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from hashlib import sha256
from threading import Barrier, Event, Lock
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import Settings
from app.persistence.bootstrap import BootstrapIdentity, configured_bootstrap_identity
from app.persistence.errors import (
    IdempotencyConflictError,
    InvalidStateTransitionError,
    OptimisticConcurrencyError,
    PersistenceConfigurationError,
)
from app.persistence.models import (
    Analysis,
    AnalysisRun,
    AnalysisStateEvent,
    IdempotencyRecord,
    UploadedVideo,
)
from app.persistence.runtime import PersistenceRuntime, get_persistence
from app.persistence.service import ReservationResult, RunResult, TransitionResult

pytestmark = pytest.mark.production_postgres

ACTORS = 20
OWNERS = 10
REPETITIONS = 10


@pytest.fixture
def runtime() -> PersistenceRuntime:
    return get_persistence()


def test_a_same_key_same_payload_high_contention(runtime: PersistenceRuntime) -> None:
    for repetition in range(REPETITIONS):
        key = f"a-{repetition}"

        results, errors, pids = _contended(
            ACTORS, partial(_same_payload_action, runtime, key, repetition)
        )
        assert not errors
        assert len(set(pids)) == ACTORS
        assert len({result.analysis_id for result in results}) == 1
        assert Counter(result.created for result in results) == {True: 1, False: 19}
    with runtime.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == REPETITIONS


def test_b_same_key_conflicting_payloads(runtime: PersistenceRuntime) -> None:
    for repetition in range(REPETITIONS):

        results, errors, pids = _contended(
            ACTORS, partial(_conflicting_payload_action, runtime, repetition)
        )
        assert len(set(pids)) == ACTORS
        assert len(results) == 1
        assert len(errors) == ACTORS - 1
        assert all(isinstance(error, IdempotencyConflictError) for error in errors)


def test_c_multiple_concurrent_run_starts(runtime: PersistenceRuntime) -> None:
    for repetition in range(REPETITIONS):
        analysis_id = f"c-{repetition}"
        _complete_initial_run(runtime, analysis_id)

        results, errors, pids = _contended(
            ACTORS,
            partial(_competing_run_action, runtime, analysis_id, repetition),
        )
        assert not errors
        assert len(set(pids)) == ACTORS
        assert len({result.run_id for result in results}) == 1
        assert Counter(result.created for result in results) == {True: 1, False: 19}
        with runtime.session_factory() as session:
            active = session.scalar(
                select(func.count())
                .select_from(AnalysisRun)
                .where(
                    AnalysisRun.analysis_id == analysis_id,
                    AnalysisRun.state.in_(("queued", "processing")),
                )
            )
            records = session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(
                    IdempotencyRecord.owner_user_id == runtime.owner_user_id,
                    IdempotencyRecord.scope == "run_start",
                    IdempotencyRecord.resource_id == str(results[0].run_id),
                )
            )
        assert active == 1
        assert records == ACTORS


def test_d_independent_owner_workflows(runtime: PersistenceRuntime) -> None:
    owners = _owners(runtime, "d")

    def action(index: int, hook: Callable[[int], None]) -> ReservationResult:
        return _reserve(
            runtime,
            owner=owners[index],
            key=f"d-key-{index}",
            analysis_id=f"d-analysis-{index}",
            fingerprint=_digest(f"d-request-{index}"),
            synchronization_hook=hook,
        )

    results, errors, pids = _contended(OWNERS, action)
    assert not errors
    assert len(set(pids)) == OWNERS
    assert len({result.analysis_id for result in results}) == OWNERS
    with runtime.session_factory() as session:
        persisted = session.scalars(
            select(Analysis).where(Analysis.id.in_([item.analysis_id for item in results]))
        ).all()
    assert {(item.id, item.owner_user_id) for item in persisted} == {
        (f"d-analysis-{index}", owners[index]) for index in range(OWNERS)
    }


def test_e_lost_response_retry_has_no_duplicate_side_effects(
    runtime: PersistenceRuntime,
) -> None:
    first = _reserve(runtime, key="e-lost-response", analysis_id="e-original")
    replay = _reserve(runtime, key="e-lost-response", analysis_id="e-retry")
    assert first.created is True
    assert replay.created is False
    assert replay.analysis_id == first.analysis_id
    with runtime.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisRun)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisStateEvent)) == 2


def test_f_deterministic_valid_invalid_transition_conflict(
    runtime: PersistenceRuntime,
) -> None:
    for repetition in range(REPETITIONS):
        analysis_id = f"f-{repetition}"
        _complete_initial_run(runtime, analysis_id)
        queued = runtime.service.start_run(
            owner_user_id=runtime.owner_user_id,
            analysis_id=analysis_id,
            idempotency_key=f"f-queued-{repetition}",
            request_fingerprint=_digest(f"f-queued-request-{repetition}"),
            state="queued",
        )
        outcomes, observations = _ordered_transition_pair(
            runtime,
            run_id=queued.run_id,
            valid_state="processing",
            losing_state="completed",
            expected_error=InvalidStateTransitionError,
            suffix=f"f-{repetition}",
        )
        assert outcomes[0].state == "processing"
        assert observations == [("queued", 1), ("queued", 1)]
        assert _run(runtime, queued.run_id).state == "processing"


def test_g_deterministic_optimistic_concurrency_conflict(
    runtime: PersistenceRuntime,
) -> None:
    for repetition in range(REPETITIONS):
        analysis_id = f"g-{repetition}"
        _reserve(runtime, key=analysis_id, analysis_id=analysis_id)
        run = _latest_run(runtime, analysis_id)
        outcomes, observations = _ordered_transition_pair(
            runtime,
            run_id=run.id,
            valid_state="completed",
            losing_state="failed",
            expected_error=OptimisticConcurrencyError,
            suffix=f"g-{repetition}",
        )
        assert outcomes[0].state == "completed"
        assert observations == [("processing", 1), ("processing", 1)]
        assert _run(runtime, run.id).state == "completed"


def test_h_stale_recognition_and_replacement(runtime: PersistenceRuntime) -> None:
    for repetition in range(REPETITIONS):
        analysis_id = f"h-{repetition}"
        _complete_initial_run(runtime, analysis_id)
        old = runtime.service.start_run(
            owner_user_id=runtime.owner_user_id,
            analysis_id=analysis_id,
            idempotency_key=f"h-old-{repetition}",
            request_fingerprint=_digest(f"h-old-request-{repetition}"),
            lease_expires_at=datetime.now(tz=UTC) - timedelta(minutes=1),
        )
        assert runtime.service.run_is_stale(old.run_id)
        old_row = _run(runtime, old.run_id)
        runtime.service.transition_run(
            owner_user_id=runtime.owner_user_id,
            run_id=old.run_id,
            expected_row_version=old_row.row_version,
            new_state="stale",
            reason="lease_expired",
        )

        results, errors, pids = _contended(
            ACTORS,
            partial(_replacement_run_action, runtime, analysis_id, repetition),
        )
        assert not errors
        assert len(set(pids)) == ACTORS
        assert len({result.run_id for result in results}) == 1
        replacement = _run(runtime, results[0].run_id)
        assert replacement.previous_run_id == old.run_id
        assert replacement.state == "processing"


def test_i_development_bootstrap_fail_closed_matrix() -> None:
    valid = Settings(
        environment="development",
        bootstrap_user_enabled=True,
        bootstrap_user_id=uuid4(),
        bootstrap_user_identity="development@example.invalid",
    )
    assert configured_bootstrap_identity(valid).identity_label.endswith(".invalid")
    invalid = [
        Settings(environment="development", bootstrap_user_enabled=False),
        Settings(
            environment="development",
            bootstrap_user_enabled=True,
            bootstrap_user_id=None,
            bootstrap_user_identity=None,
        ),
        Settings(
            environment="production",
            bootstrap_user_enabled=True,
            bootstrap_user_id=uuid4(),
            bootstrap_user_identity="production@example.invalid",
            auth_access_token_secret=SecretStr(
                "production-test-secret-value-at-least-32-characters"
            ),
            auth_frontend_base_url="https://court4.example",
            auth_email_backend="provider",
            auth_development_email_sink_enabled=False,
            auth_cookie_secure=True,
        ),
    ]
    for settings in invalid:
        with pytest.raises(PersistenceConfigurationError):
            configured_bootstrap_identity(settings)


def test_j_same_key_is_owner_scoped(runtime: PersistenceRuntime) -> None:
    owners = _owners(runtime, "j")

    def action(index: int, hook: Callable[[int], None]) -> ReservationResult:
        return _reserve(
            runtime,
            owner=owners[index],
            key="same-key-across-owners",
            analysis_id=f"j-analysis-{index}",
            fingerprint=_digest("same-owner-scoped-request"),
            synchronization_hook=hook,
        )

    results, errors, pids = _contended(OWNERS, action)
    assert not errors
    assert len(set(pids)) == OWNERS
    assert all(result.created for result in results)
    assert len({result.analysis_id for result in results}) == OWNERS


def test_k_exact_duplicate_detection_is_owner_scoped_and_reanalyzable(
    runtime: PersistenceRuntime,
) -> None:
    owners = _owners(runtime, "k")
    checksum = _digest("shared-video-bytes")

    first = _reserve(
        runtime,
        owner=owners[0],
        key="k-owner-one-first",
        analysis_id="k-owner-one-first",
        source_checksum=checksum,
    )
    renamed_duplicate = _reserve(
        runtime,
        owner=owners[0],
        key="k-owner-one-renamed",
        analysis_id="k-owner-one-renamed",
        source_checksum=checksum,
        original_filename="renamed-copy.mp4",
    )
    other_owner = _reserve(
        runtime,
        owner=owners[1],
        key="k-owner-two-first",
        analysis_id="k-owner-two-first",
        source_checksum=checksum,
    )
    reanalyzed = _reserve(
        runtime,
        owner=owners[0],
        key="k-owner-one-reanalyze",
        analysis_id="k-owner-one-reanalyze",
        source_checksum=checksum,
        allow_duplicate=True,
    )

    assert first.created is True
    assert renamed_duplicate.created is False
    assert renamed_duplicate.duplicate is not None
    assert renamed_duplicate.duplicate.existing_analysis_id == first.analysis_id
    assert other_owner.created is True
    assert other_owner.duplicate is None
    assert reanalyzed.created is True
    assert reanalyzed.analysis_id != first.analysis_id
    assert (
        runtime.service.find_uploaded_video_by_owner_and_checksum(
            owner_user_id=owners[0],
            checksum_sha256=checksum,
        )
        is not None
    )
    with runtime.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 3
        assert session.scalar(select(func.count()).select_from(UploadedVideo)) == 3


def test_l_concurrent_exact_duplicates_create_one_analysis(
    runtime: PersistenceRuntime,
) -> None:
    checksum = _digest("same-concurrent-video")

    def action(
        index: int,
        hook: Callable[[int], None],
    ) -> ReservationResult:
        return _reserve(
            runtime,
            key=f"l-key-{index}",
            analysis_id=f"l-analysis-{index}",
            fingerprint=_digest(f"l-request-{index}"),
            source_checksum=checksum,
            synchronization_hook=hook,
        )

    results, errors, pids = _contended(ACTORS, action)

    assert not errors
    assert len(set(pids)) == ACTORS
    assert Counter(result.created for result in results) == {True: 1, False: ACTORS - 1}
    created = next(result for result in results if result.created)
    assert all(
        result.duplicate is not None
        and result.duplicate.existing_analysis_id == created.analysis_id
        for result in results
        if not result.created
    )
    with runtime.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 1
        assert session.scalar(select(func.count()).select_from(UploadedVideo)) == 1


def _contended[ResultT](
    actors: int,
    action: Callable[[int, Callable[[int], None]], ResultT],
) -> tuple[list[ResultT], list[BaseException], list[int]]:
    gate = Barrier(actors)
    observed_pids: list[int] = []
    observation_lock = Lock()

    def invoke(index: int) -> ResultT:
        def synchronize(backend_pid: int) -> None:
            with observation_lock:
                observed_pids.append(backend_pid)
            gate.wait(timeout=15)

        return action(index, synchronize)

    results: list[ResultT] = []
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=actors) as pool:
        futures = [pool.submit(invoke, index) for index in range(actors)]
        for future in futures:
            try:
                results.append(future.result(timeout=30))
            except BaseException as error:
                errors.append(error)
    return results, errors, observed_pids


def _same_payload_action(
    runtime: PersistenceRuntime,
    key: str,
    repetition: int,
    index: int,
    hook: Callable[[int], None],
) -> ReservationResult:
    return _reserve(
        runtime,
        key=key,
        analysis_id=f"a-{repetition}-{index}",
        fingerprint=_digest(f"a-request-{repetition}"),
        synchronization_hook=hook,
    )


def _conflicting_payload_action(
    runtime: PersistenceRuntime,
    repetition: int,
    index: int,
    hook: Callable[[int], None],
) -> ReservationResult:
    return _reserve(
        runtime,
        key=f"b-{repetition}",
        analysis_id=f"b-{repetition}-{index}",
        fingerprint=_digest(f"b-request-{repetition}-{index}"),
        synchronization_hook=hook,
    )


def _competing_run_action(
    runtime: PersistenceRuntime,
    analysis_id: str,
    repetition: int,
    index: int,
    hook: Callable[[int], None],
) -> RunResult:
    return runtime.service.start_run(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        idempotency_key=f"c-run-{repetition}-{index}",
        request_fingerprint=_digest(f"c-run-request-{repetition}-{index}"),
        synchronization_hook=hook,
    )


def _replacement_run_action(
    runtime: PersistenceRuntime,
    analysis_id: str,
    repetition: int,
    index: int,
    hook: Callable[[int], None],
) -> RunResult:
    return runtime.service.start_run(
        owner_user_id=runtime.owner_user_id,
        analysis_id=analysis_id,
        idempotency_key=f"h-replacement-{repetition}-{index}",
        request_fingerprint=_digest(f"h-replacement-request-{repetition}-{index}"),
        synchronization_hook=hook,
    )


def _ordered_transition_pair(
    runtime: PersistenceRuntime,
    *,
    run_id: UUID,
    valid_state: str,
    losing_state: str,
    expected_error: type[BaseException],
    suffix: str,
) -> tuple[list[TransitionResult], list[tuple[str, int]]]:
    gate = Barrier(2)
    winner_finished = Event()
    observations: list[tuple[int, str, int]] = []
    lock = Lock()

    def transition(index: int) -> TransitionResult:
        def observe(pid: int, state: str, version: int) -> None:
            with lock:
                observations.append((pid, state, version))
            gate.wait(timeout=15)
            if index == 1:
                assert winner_finished.wait(timeout=15)

        try:
            return runtime.service.transition_run(
                owner_user_id=runtime.owner_user_id,
                run_id=run_id,
                expected_row_version=1,
                new_state=valid_state if index == 0 else losing_state,
                reason=f"{suffix}-{'winner' if index == 0 else 'loser'}",
                observation_hook=observe,
            )
        finally:
            if index == 0:
                winner_finished.set()

    results: list[TransitionResult] = []
    errors: list[BaseException] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(transition, index) for index in range(2)]
        for future in futures:
            try:
                results.append(future.result(timeout=30))
            except BaseException as error:
                errors.append(error)
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], expected_error)
    assert len({item[0] for item in observations}) == 2
    ordered = sorted((state, version) for _pid, state, version in observations)
    return results, ordered


def _reserve(
    runtime: PersistenceRuntime,
    *,
    key: str,
    analysis_id: str,
    owner: UUID | None = None,
    fingerprint: str | None = None,
    source_checksum: str | None = None,
    original_filename: str = "match.mp4",
    allow_duplicate: bool = False,
    synchronization_hook: Callable[[int], None] | None = None,
) -> ReservationResult:
    now = datetime.now(tz=UTC).isoformat()
    return runtime.service.reserve_analysis(
        owner_user_id=owner or runtime.owner_user_id,
        analysis_id=analysis_id,
        idempotency_key=key,
        request_fingerprint=fingerprint or _digest(f"request-{key}"),
        original_filename=original_filename,
        content_type="video/mp4",
        size_bytes=4,
        source_checksum=source_checksum or _digest(f"source-{key}"),
        job_payload={
            "analysis_id": analysis_id,
            "status": "processing",
            "current_stage": "uploaded",
            "created_at": now,
            "updated_at": now,
        },
        allow_duplicate=allow_duplicate,
        synchronization_hook=synchronization_hook,
    )


def _complete_initial_run(runtime: PersistenceRuntime, analysis_id: str) -> None:
    _reserve(runtime, key=f"seed-{analysis_id}", analysis_id=analysis_id)
    run = _latest_run(runtime, analysis_id)
    runtime.service.transition_run(
        owner_user_id=runtime.owner_user_id,
        run_id=run.id,
        expected_row_version=run.row_version,
        new_state="completed",
    )


def _owners(runtime: PersistenceRuntime, suffix: str) -> list[UUID]:
    owners: list[UUID] = []
    for index in range(OWNERS):
        owner = uuid4()
        runtime.service.ensure_bootstrap_user(
            BootstrapIdentity(owner, f"{suffix}-owner-{index}@example.invalid")
        )
        owners.append(owner)
    return owners


def _latest_run(runtime: PersistenceRuntime, analysis_id: str) -> AnalysisRun:
    with runtime.session_factory() as session:
        run = session.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.analysis_id == analysis_id)
            .order_by(AnalysisRun.attempt_number.desc())
            .limit(1)
        )
        assert run is not None
        return run


def _run(runtime: PersistenceRuntime, run_id: UUID) -> AnalysisRun:
    with runtime.session_factory() as session:
        run = session.get(AnalysisRun, run_id)
        assert run is not None
        return run


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()
