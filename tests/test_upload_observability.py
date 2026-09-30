import json

import pytest

from app.core.logging import JsonFormatter
from app.services import upload_observability


def test_timing_does_not_log_exception_details(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level("INFO", logger="app.services.upload_observability")
    times = iter([10.0, 12.5])
    monkeypatch.setattr(upload_observability, "perf_counter", lambda: next(times))
    with (
        pytest.raises(RuntimeError),
        upload_observability.upload_phase("source_materialization", "a" * 32),
    ):
        raise RuntimeError(
            "https://private/?X-Amz-Signature=secret Authorization: Bearer token "
            "Cookie: cookie /private/path file-content"
        )
    records = caplog.records
    assert len(records) == 2
    assert records[-1].__dict__["duration_ms"] == 2500
    assert records[-1].__dict__["outcome"] == "failure"
    formatted = [json.loads(JsonFormatter().format(record)) for record in records]
    assert formatted[-1]["context"] == {
        "analysis_id": "a" * 32,
        "phase": "source_materialization",
        "outcome": "failure",
        "duration_ms": 2500,
    }
    for secret in (
        "X-Amz",
        "secret",
        "token",
        "cookie",
        "/private",
        "exception",
        "Authorization",
        "Bearer",
        "Cookie",
        "file-content",
    ):
        assert secret not in json.dumps(formatted)
