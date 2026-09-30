"""Bounded upload timing fields; never include exception text, object keys or hashes."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Literal

logger = logging.getLogger(__name__)
Phase = Literal[
    "completion",
    "integrity",
    "sha256",
    "verified_metadata",
    "source_materialization",
    "inspection",
    "artifact_persistence",
]
Event = Literal[
    "completion_received",
    "completion_accepted",
    "verification_start",
    "verification_end",
    "session_completed",
    "session_failed",
]


def upload_event(
    event: Event,
    analysis_id: str,
    *,
    duration_ms: float | None = None,
    outcome: Literal["success", "failure"] | None = None,
) -> None:
    logger.info(
        "upload_%s",
        event,
        extra={"analysis_id": analysis_id, "duration_ms": duration_ms, "outcome": outcome},
    )


@contextmanager
def upload_phase(phase: Phase, analysis_id: str) -> Iterator[None]:
    start = perf_counter()
    logger.info("upload_phase_start", extra={"analysis_id": analysis_id, "phase": phase})
    outcome = "success"
    try:
        yield
    except BaseException:
        outcome = "failure"
        raise
    finally:
        logger.info(
            "upload_phase_end",
            extra={
                "analysis_id": analysis_id,
                "phase": phase,
                "outcome": outcome,
                "duration_ms": (perf_counter() - start) * 1000,
            },
        )
