import errno

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize(
    "error", [RuntimeError("private details"), OSError(errno.EIO, "private path")]
)
def test_unexpected_errors_preserve_cors_policy(
    monkeypatch: pytest.MonkeyPatch, allowed: bool, error: Exception
) -> None:
    settings = get_settings().model_copy(
        update={"frontend_allowed_origins": ("https://web.example.test",)}
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    application = create_app()

    @application.get("/test-unexpected-error")
    def fail() -> None:
        raise error

    origin = "https://web.example.test" if allowed else "https://untrusted.example.test"
    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/test-unexpected-error", headers={"Origin": origin})

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Unexpected internal server error."}
    }
    assert "private" not in response.text
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        assert "Origin" in response.headers["vary"]
    else:
        assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/test-unexpected-error",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == (200 if allowed else 400)
