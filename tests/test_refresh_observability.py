from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.auth.errors import AuthenticationError
from app.auth.service import AuthenticationService
from app.config import get_settings
from app.core.logging import JsonFormatter
from app.main import create_app
from app.persistence.models import RefreshSession, User
from app.persistence.runtime import get_persistence

ORIGIN = {"Origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def enable_auth_log_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    # Migration tests run fileConfig, which disables existing non-Alembic loggers.
    # Isolate capture from that test-order side effect without changing runtime logging.
    monkeypatch.setattr(logging.getLogger("app.auth.service"), "disabled", False)


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("missing", "cookie_missing"),
        ("empty", "token_invalid"),
        ("malformed", "token_invalid"),
        ("oversized", "token_invalid"),
        ("short_secret", "token_invalid"),
        ("invalid_uuid", "token_invalid"),
        ("unknown", "session_not_found"),
        ("mismatch", "token_mismatch"),
        ("expired", "session_expired"),
        ("revoked", "session_revoked"),
        ("inactive", "account_inactive"),
        ("deleted_account", "session_not_found"),
        ("reuse", None),
        ("success", None),
    ],
)
def test_refresh_diagnostics_preserve_security(
    scenario: str, reason: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app())
    password = "observability test password only"
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "diagnostic@example.com", "password": password},
    )
    assert registration.status_code == 201
    original = client.cookies.get("court4_refresh")
    assert original is not None
    session_id = UUID(original.split(".", 1)[0])
    secrets = [original, registration.json()["access_token"], password]
    with get_persistence().session_factory.begin() as session:
        row = session.get(RefreshSession, session_id)
        assert row is not None
        user = session.get(User, row.user_id)
        assert user is not None
        secrets.extend([row.token_hash, user.password_hash])
        if scenario == "expired":
            row.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
        elif scenario == "revoked":
            row.revoked_at = datetime.now(tz=UTC)
            row.revocation_reason = "user_revoked"
        elif scenario == "inactive":
            user.account_status = "disabled"
        elif scenario == "deleted_account":
            session.delete(user)

    supplied = original
    if scenario == "reuse":
        assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 200
        successor = client.cookies.get("court4_refresh")
        assert successor is not None
        secrets.append(successor)
    elif scenario == "empty":
        supplied = ""
    elif scenario == "malformed":
        supplied = "invalid-test-cookie"
    elif scenario == "oversized":
        supplied = "x" * 257
    elif scenario == "short_secret":
        supplied = f"{session_id}.short"
    elif scenario == "invalid_uuid":
        supplied = f"not-a-uuid.{'x' * 64}"
    elif scenario == "unknown":
        supplied = f"{uuid4()}.{'x' * 64}"
    elif scenario == "mismatch":
        supplied = f"{session_id}.{'x' * 64}"
    client.cookies.clear()
    if scenario != "missing":
        client.cookies.set("court4_refresh", supplied, path="/api/v1/auth")
    if supplied:
        secrets.append(supplied)

    # create_app configures root logging; restore pytest capture after that setup.
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="app.auth.service")
    caplog.clear()
    response = client.post("/api/v1/auth/refresh", headers=ORIGIN)
    records = [record for record in caplog.records if record.name == "app.auth.service"]
    expected_event = (
        "auth_refresh_rotated"
        if scenario == "success"
        else "auth_refresh_reuse_detected"
        if scenario == "reuse"
        else "auth_refresh_rejected"
    )
    assert [record.getMessage() for record in records] == [expected_event]
    assert records[0].levelno == (logging.WARNING if scenario == "reuse" else logging.INFO)
    if reason is not None:
        assert records[0].__dict__["reason"] == reason
        assert json.loads(JsonFormatter().format(records[0]))["context"] == {"reason": reason}
    serialized = "\n".join(JsonFormatter().format(record) for record in records)
    assert all(secret not in serialized for secret in secrets)
    assert "diagnostic@example.com" not in serialized
    assert all(record.exc_info is None for record in records)
    assert all("exception" not in json.loads(JsonFormatter().format(r)) for r in records)
    if scenario == "success":
        assert response.status_code == 200
        assert response.cookies.get("court4_refresh") != original
    else:
        assert response.status_code == 401
        assert response.json() == {
            "error": {"code": "invalid_session", "message": "Session is invalid."}
        }
        assert "set-cookie" not in response.headers

    with get_persistence().session_factory() as session:
        row = session.get(RefreshSession, session_id)
        if scenario == "deleted_account":
            assert row is None  # FK cascade: do not manufacture an orphan account.
        else:
            assert row is not None
            expected_revocation = {
                "expired": "expired",
                "revoked": "user_revoked",
                "inactive": "account_unavailable",
                "reuse": "rotated",
                "success": "rotated",
            }.get(scenario)
            assert row.revocation_reason == expected_revocation
            if scenario == "reuse":
                replacement = session.get(RefreshSession, row.replaced_by_session_id)
                assert replacement is not None
                assert replacement.revocation_reason == "refresh_token_reuse"
    if scenario == "reuse":
        client.cookies.clear()
        client.cookies.set("court4_refresh", successor, path="/api/v1/auth")
        caplog.clear()
        assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 401
        rejected = [r for r in caplog.records if r.getMessage() == "auth_refresh_rejected"]
        assert len(rejected) == 1
        assert rejected[0].__dict__["reason"] == "session_revoked"


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("locked_missing", "session_not_found"),
        ("locked_mismatch", "token_mismatch"),
        ("account_missing", "account_missing"),
        ("transaction_failure", None),
    ],
)
def test_refresh_diagnostics_for_concurrent_state_and_transaction_failure(
    scenario: str, reason: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    # Simulate otherwise nondeterministic re-reads without creating invalid DB rows.
    session_id = uuid4()
    raw_token = f"{session_id}.{'s' * 64}"
    candidate = RefreshSession(
        id=session_id,
        user_id=uuid4(),
        token_family_id=uuid4(),
        token_hash=sha256(raw_token.encode()).hexdigest(),
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
    )
    locked = RefreshSession(
        id=session_id,
        token_hash="different-test-hash",
    )
    session = MagicMock(spec=Session)
    factory = MagicMock()
    transaction = factory.begin.return_value
    transaction.__enter__.return_value = session
    transaction.__exit__.return_value = False
    if scenario == "transaction_failure":
        session.scalar.return_value = None
        transaction.__exit__.side_effect = RuntimeError("test transaction failure")
    else:
        session.scalar.side_effect = [
            candidate,
            None if scenario == "account_missing" else User(id=candidate.user_id),
            None
            if scenario == "locked_missing"
            else locked
            if scenario == "locked_mismatch"
            else candidate,
        ]
    service = AuthenticationService(cast(sessionmaker[Session], factory), get_settings())
    caplog.set_level(logging.INFO, logger="app.auth.service")
    caplog.clear()
    if scenario == "transaction_failure":
        with pytest.raises(RuntimeError, match="test transaction failure"):
            service.refresh(raw_token, user_agent="private-test-user-agent")
    else:
        with pytest.raises(AuthenticationError) as caught:
            service.refresh(raw_token, user_agent="private-test-user-agent")
        assert caught.value.status_code == 401
        assert caught.value.code == "invalid_session"
        assert caught.value.message == "Session is invalid."
    records = [record for record in caplog.records if record.name == "app.auth.service"]
    if reason is None:
        assert records == []  # Failed transaction exit must not claim a completed 401.
    else:
        assert [record.getMessage() for record in records] == ["auth_refresh_rejected"]
        assert records[0].levelno == logging.INFO
        assert json.loads(JsonFormatter().format(records[0]))["context"] == {"reason": reason}
        assert records[0].exc_info is None
    transaction.__exit__.assert_called_once()
