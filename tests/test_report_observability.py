import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.core.logging import JsonFormatter
from app.services import report_observability as obs


def test_report_metrics_are_bounded_and_do_not_leak_exception_details(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(obs.logger, "disabled", False)
    caplog.set_level("INFO", logger=obs.__name__)
    times = iter([10.0, 10.5, 11.0, 12.0])
    monkeypatch.setattr(obs, "perf_counter", lambda: next(times))
    with pytest.raises(RuntimeError), obs.report_read(), obs.report_phase("hydration"):
        obs.report_artifact("private-key", 123)
        obs.report_artifact("private-key", 123)
        obs.report_artifact("private-key", 123, hydrated=True)
        raise RuntimeError("Bearer secret Cookie password https://private/?X-Amz-Signature=key")
    assert len(caplog.records) == 1
    logged = json.loads(JsonFormatter().format(caplog.records[0]))
    assert logged["context"] == {
        "outcome": "failure",
        "duration_ms": 2000,
        "phase_duration_ms": {"hydration": 500},
        "selected_artifact_count": 1,
        "selected_bytes": 123,
        "hydrated_artifact_count": 1,
        "hydrated_bytes": 123,
    }
    assert all(
        word not in json.dumps(logged)
        for word in (
            "private-key",
            "Bearer",
            "secret",
            "Cookie",
            "password",
            "X-Amz",
            "exception",
        )
    )
    # After failure the context is reset; ordinary processing emits no report event.
    obs.report_artifact("outside", 999)
    with obs.report_phase("registry"):
        pass
    assert len(caplog.records) == 1


def test_report_metrics_are_isolated_across_requests(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(obs.logger, "disabled", False)
    caplog.set_level("INFO", logger=obs.__name__)

    def run(size: int) -> None:
        with obs.report_read():
            obs.report_artifact("same-key", size)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [10, 20]))
    with obs.report_read():
        pass
    assert sorted(r.__dict__["selected_bytes"] for r in caplog.records) == [0, 10, 20]
    assert len(caplog.records) == 3


def test_logging_failure_cannot_break_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(obs.logger, "info", fail)
    with obs.report_read():
        obs.report_artifact("private-key", 123)


def test_logging_failure_cannot_mask_report_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(obs.logger, "info", fail)
    with pytest.raises(ValueError, match="original report failure"), obs.report_read():
        raise ValueError("original report failure")
