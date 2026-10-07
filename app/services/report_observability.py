"""One bounded timing event per report handler; no payloads or provider identifiers.

Handler duration includes workflow locks/authority checks, but excludes FastAPI's
authentication dependency, response serialization and transport. Phase durations
can nest (registry within persistence, persistence within evidence validation).
Counts deduplicate resolved logical artifacts within this request, not across reads.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import Literal, ParamSpec, TypeVar

logger = logging.getLogger(__name__)
Phase = Literal[
    "persistence", "registry", "evidence", "hydration", "analytics_json", "match_iq_json"
]
P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class ReportReadMetrics:
    durations_ms: dict[str, float] = field(default_factory=dict)
    selected: dict[str, int] = field(default_factory=dict)
    hydrated: dict[str, int] = field(default_factory=dict)


_active: ContextVar[ReportReadMetrics | None] = ContextVar("report_read_metrics", default=None)


@contextmanager
def report_read() -> Iterator[None]:
    metrics = ReportReadMetrics()
    token = _active.set(metrics)
    started = perf_counter()
    outcome = "success"
    try:
        yield
    except BaseException:
        outcome = "failure"
        raise
    finally:
        _active.reset(token)
        # Only telemetry emission is best-effort; report execution exceptions propagate.
        with suppress(Exception):
            logger.info(
                "report_read_completed",
                extra={
                    "outcome": outcome,
                    "duration_ms": (perf_counter() - started) * 1000,
                    "phase_duration_ms": metrics.durations_ms,
                    "selected_artifact_count": len(metrics.selected),
                    "selected_bytes": sum(metrics.selected.values()),
                    "hydrated_artifact_count": len(metrics.hydrated),
                    "hydrated_bytes": sum(metrics.hydrated.values()),
                },
            )


@contextmanager
def report_phase(phase: Phase) -> Iterator[None]:
    metrics = _active.get()
    if metrics is None:
        yield
        return
    started = perf_counter()
    try:
        yield
    finally:
        metrics.durations_ms[phase] = (
            metrics.durations_ms.get(phase, 0) + (perf_counter() - started) * 1000
        )


def report_timed(phase: Phase) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(method: Callable[P, R]) -> Callable[P, R]:
        @wraps(method)
        def measured(*args: P.args, **kwargs: P.kwargs) -> R:
            with report_phase(phase):
                return method(*args, **kwargs)

        return measured

    return decorate


def report_artifact(logical_key: str, size_bytes: int, *, hydrated: bool = False) -> None:
    metrics = _active.get()
    if metrics is not None:
        # Keys stay in memory only; logging exposes counts and byte totals.
        target = metrics.hydrated if hydrated else metrics.selected
        target[logical_key] = size_bytes
