from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Lock
from typing import cast
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select

from app.api.v1.analyses import development_router as analyses_development_router
from app.api.v1.analyses import router as analyses_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.auth.dependencies import require_verified_user
from app.auth.errors import AuthenticationError
from app.auth.rate_limit import auth_rate_limiter
from app.auth.service import AuthenticationService
from app.config import get_settings
from app.main import create_app
from app.persistence.models import AccountToken, RefreshSession, User
from app.persistence.runtime import get_persistence
from app.schemas.jobs import AnalysisJob, AnalysisStage, AnalysisStatus
from app.services.jobs import AnalysisJobRepository

PASSWORD = "correct horse battery staple"
ORIGIN = "http://localhost:3000"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_registration_normalizes_email_and_stores_only_argon2_hash(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  Player@EXAMPLE.com ", "password": PASSWORD},
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "player@example.com"
    assert response.json()["user"]["verification_delivery_mode"] == "development"
    assert "password_hash" not in response.text
    with get_persistence().session_factory() as session:
        user = session.scalar(select(User).where(User.email == "player@example.com"))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash


def test_duplicate_normalized_email_is_rejected(client: TestClient) -> None:
    assert _register(client, "Player@Example.com").status_code == 201
    duplicate = _register(client, " player@example.COM ")
    assert duplicate.status_code == 409
    assert "password" not in duplicate.text


def test_login_and_me(client: TestClient) -> None:
    registration = _register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "OWNER@example.COM", "password": PASSWORD},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == registration.json()["user"]["id"]
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"


def test_invalid_email_and_password_have_equivalent_public_errors(
    client: TestClient,
) -> None:
    _register(client)
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": PASSWORD},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": f"{PASSWORD}!wrong"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_refresh_rotates_and_reuse_revokes_family(client: TestClient) -> None:
    registration = _register(client)
    first_cookie = client.cookies.get("court4_refresh")
    assert first_cookie
    refreshed = client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert refreshed.status_code == 200
    second_cookie = client.cookies.get("court4_refresh")
    assert second_cookie and second_cookie != first_cookie

    replay = TestClient(create_app())
    replay.cookies.set("court4_refresh", first_cookie, path="/api/v1/auth")
    reused = replay.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert reused.status_code == 401

    successor = client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert successor.status_code == 401
    assert registration.json()["access_token"] != refreshed.json()["access_token"]


def test_expired_and_revoked_refresh_sessions_fail(client: TestClient) -> None:
    _register(client)
    raw_cookie = client.cookies.get("court4_refresh")
    assert raw_cookie
    session_id = UUID(raw_cookie.split(".", 1)[0])
    with get_persistence().session_factory.begin() as session:
        refresh_session = session.get(RefreshSession, session_id)
        assert refresh_session is not None
        refresh_session.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
    assert client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401

    other = TestClient(create_app())
    _register(other, "other@example.com")
    other_cookie = other.cookies.get("court4_refresh")
    assert other_cookie
    other_id = UUID(other_cookie.split(".", 1)[0])
    with get_persistence().session_factory.begin() as session:
        refresh_session = session.get(RefreshSession, other_id)
        assert refresh_session is not None
        refresh_session.revoked_at = datetime.now(tz=UTC)
        refresh_session.revocation_reason = "security_action"
    assert other.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401


def test_logout_is_idempotent_and_clears_session(client: TestClient) -> None:
    _register(client)
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401


def test_disabled_user_and_invalid_or_missing_tokens_are_rejected(
    client: TestClient,
) -> None:
    registration = _register(client)
    token = registration.json()["access_token"]
    user_id = UUID(registration.json()["user"]["id"])
    with get_persistence().session_factory.begin() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.account_status = "disabled"

    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed"}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )
    assert client.get("/api/v1/analyses").status_code == 401


def test_cross_owner_analysis_artifact_and_histories_are_hidden(tmp_path: Path) -> None:
    owner_a = TestClient(create_app())
    owner_b = TestClient(create_app())
    a = _register(owner_a, "a@example.com").json()
    b = _register(owner_b, "b@example.com").json()
    _mark_verified(UUID(a["user"]["id"]))
    _mark_verified(UUID(b["user"]["id"]))
    owner_a.headers["Authorization"] = f"Bearer {a['access_token']}"
    owner_b.headers["Authorization"] = f"Bearer {b['access_token']}"
    settings = get_settings()
    repository = AnalysisJobRepository(
        output_dir=settings.analysis_output_dir,
        api_base_path=settings.api_base_path,
        owner_user_id=UUID(b["user"]["id"]),
    )
    job = AnalysisJob(
        analysis_id="owner-b-analysis",
        status=AnalysisStatus.processing,
        current_stage=AnalysisStage.inspected,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        inspection_completed=True,
    )
    artifact_dir = repository.analysis_dir(job.analysis_id) / "frames"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "private.jpg").write_bytes(b"private")
    repository.save_job(job)

    assert owner_a.get("/api/v1/analyses/owner-b-analysis").status_code == 404
    assert (
        owner_a.get("/api/v1/analyses/owner-b-analysis/artifacts/frames/private.jpg").status_code
        == 404
    )
    assert owner_a.get("/api/v1/analyses").json()["total"] == 0
    assert owner_a.get("/api/v1/play-history").json()["total_analyses"] == 0
    assert owner_b.get("/api/v1/analyses").json()["total"] == 1


def test_concurrent_same_email_registration_creates_one_user() -> None:
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)

    def register() -> str:
        barrier.wait()
        try:
            return str(auth.register("race@example.com", PASSWORD, user_agent=None)[0].id)
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: register(), range(2)))
    assert results.count("registration_failed") == 1
    with get_persistence().session_factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(User).where(User.email == "race@example.com")
            )
            == 1
        )


def test_concurrent_refresh_allows_only_one_rotation() -> None:
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    _user, tokens, _delivery = auth.register("refresh-race@example.com", PASSWORD, user_agent=None)
    barrier = Barrier(2)

    def rotate() -> str:
        barrier.wait()
        try:
            auth.refresh(tokens.refresh_token, user_agent=None)
            return "rotated"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: rotate(), range(2)))
    assert sorted(results) == ["invalid_session", "rotated"]


def test_registration_verification_is_hashed_single_use_and_unlocks_upload(
    client: TestClient,
) -> None:
    registration = _register(client)
    access_token = registration.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    blocked = client.post(
        "/api/v1/analyses",
        headers=headers,
        files={"file": ("match.mp4", b"not-a-real-video", "video/mp4")},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "email_verification_required"

    raw_token = _email_token(client, headers, "email_verification")
    with get_persistence().session_factory() as session:
        stored = session.scalar(
            select(AccountToken).where(AccountToken.purpose == "email_verification")
        )
        assert stored is not None
        assert stored.token_hash != raw_token
        assert raw_token not in stored.token_hash

    verified = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["access_token"]
    assert verified.json()["user"]["email_verified_at"] is not None
    reused = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_or_used_token"
    malformed = client.post("/api/v1/auth/verify-email", json={"token": "bad"})
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "invalid_or_used_token"
    allowed = client.post(
        "/api/v1/analyses",
        headers=headers,
        files={"file": ("match.mp4", b"not-a-real-video", "video/mp4")},
    )
    assert allowed.status_code != 403


def test_unverified_account_is_limited_to_activation_and_recovery_routes(
    client: TestClient,
) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/resend-verification", headers=headers).status_code == 200
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"}).status_code
        == 200
    )
    assert client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 200

    private_gets = [
        "/api/v1/analyses",
        "/api/v1/analyses/missing-analysis",
        "/api/v1/analyses/missing-analysis/frames",
        "/api/v1/analyses/missing-analysis/artifacts/private.json",
        "/api/v1/analyses/missing-analysis/player-candidates",
        "/api/v1/analyses/missing-analysis/players",
        "/api/v1/analyses/missing-analysis/analytics",
        "/api/v1/play-history",
        "/api/v1/auth/sessions",
    ]
    for path in private_gets:
        blocked = client.get(path, headers=headers)
        assert blocked.status_code == 403, path
        assert blocked.json()["error"]["code"] == "email_verification_required", path

    onboarding = client.post(
        "/api/v1/auth/onboarding",
        headers=headers,
        json={"display_name": "Pending Player"},
    )
    assert onboarding.status_code == 403
    assert onboarding.json()["error"]["code"] == "email_verification_required"

    password = client.post(
        "/api/v1/auth/change-password",
        headers={**headers, "Origin": ORIGIN},
        json={"current_password": PASSWORD, "new_password": f"{PASSWORD} updated"},
    )
    assert password.status_code == 403
    assert password.json()["error"]["code"] == "email_verification_required"

    assert client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 200


def test_local_origin_is_exact_for_cors_and_cookie_csrf(client: TestClient) -> None:
    _register(client)

    allowed = client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert allowed.status_code == 200
    mixed = client.post(
        "/api/v1/auth/refresh",
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert mixed.status_code == 403
    assert mixed.json()["error"]["code"] == "invalid_origin"


def test_refresh_access_can_recover_authenticated_resend(client: TestClient) -> None:
    _register(client)
    refreshed = client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert refreshed.status_code == 200

    resent = client.post(
        "/api/v1/auth/resend-verification",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )

    assert resent.status_code == 200
    assert resent.json()["delivery_mode"] == "development"
    assert "captured" in resent.json()["message"]


def test_private_route_policy_matrix_requires_the_central_verified_dependency() -> None:
    verified_auth_paths = {
        "/auth/onboarding",
        "/auth/change-password",
        "/auth/sessions",
        "/auth/sessions/{session_id}",
        "/auth/sessions/revoke-all",
    }
    private_routes = [
        route
        for router in (
            analyses_router,
            analyses_development_router,
            history_router,
            auth_router,
        )
        for route in router.routes
        if isinstance(route, APIRoute)
        and (
            route.path.startswith("/analyses")
            or route.path.startswith("/play-history")
            or route.path in verified_auth_paths
        )
    ]

    assert private_routes
    for route in private_routes:
        assert _dependency_tree_contains(route.dependant, require_verified_user), (
            route.path,
            route.methods,
        )


def test_verification_rotates_existing_session_and_sets_normal_refresh_cookie(
    client: TestClient,
) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    original_cookie = client.cookies.get("court4_refresh")

    verified = client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert verified.status_code == 200
    assert verified.json()["token_type"] == "bearer"
    assert verified.json()["expires_in"] == get_settings().auth_access_token_minutes * 60
    assert client.cookies.get("court4_refresh") != original_cookie
    assert "HttpOnly" in verified.headers["set-cookie"]
    assert "SameSite=lax" in verified.headers["set-cookie"]
    with get_persistence().session_factory() as session:
        active_sessions = session.scalar(
            select(func.count())
            .select_from(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
        )
    assert active_sessions == 1


def test_verification_on_another_browser_creates_one_session_and_replay_creates_none(
    client: TestClient,
) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    other_browser = TestClient(create_app())

    verified = other_browser.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verified.status_code == 200
    assert other_browser.cookies.get("court4_refresh")
    refreshed = other_browser.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN})
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["id"] == str(user_id)

    replay_browser = TestClient(create_app())
    replay = replay_browser.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "invalid_or_used_token"
    assert replay_browser.cookies.get("court4_refresh") is None


def test_verification_refuses_to_replace_a_different_authenticated_user(
    client: TestClient,
) -> None:
    user_a = _register(client, "user-a@example.com")
    user_a_headers = {"Authorization": f"Bearer {user_a.json()['access_token']}"}
    user_b_browser = TestClient(create_app())
    user_b = _register(user_b_browser, "user-b@example.com")
    user_b_headers = {"Authorization": f"Bearer {user_b.json()['access_token']}"}
    raw_token = _email_token(user_b_browser, user_b_headers, "email_verification")

    mismatch = client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
        headers=user_a_headers,
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "verification_account_mismatch"

    verified = user_b_browser.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
        headers=user_b_headers,
    )
    assert verified.status_code == 200
    assert verified.json()["user"]["email"] == "user-b@example.com"


def test_disabled_account_cannot_verify_or_create_a_session(client: TestClient) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    with get_persistence().session_factory.begin() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.account_status = "disabled"
    browser = TestClient(create_app())

    response = browser.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_or_used_token"
    assert browser.cookies.get("court4_refresh") is None


def test_completed_onboarding_name_persists_across_login_contexts(client: TestClient) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    verified = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    verified_headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}

    completed = client.post(
        "/api/v1/auth/onboarding",
        json={"display_name": "  Alexis   Marie  "},
        headers=verified_headers,
    )
    assert completed.status_code == 200
    assert completed.json()["display_name"] == "Alexis Marie"

    next_browser = TestClient(create_app())
    logged_in = next_browser.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": PASSWORD},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"]["display_name"] == "Alexis Marie"


def test_resend_invalidates_previous_verification_link(client: TestClient) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    first_token = _email_token(client, headers, "email_verification")

    resent = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert resent.status_code == 200
    assert resent.json()["verified"] is False
    assert resent.json()["delivery_mode"] == "development"
    second_token = _email_token(client, headers, "email_verification", index=-1)
    assert second_token != first_token
    assert client.post("/api/v1/auth/verify-email", json={"token": first_token}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": second_token}).status_code == 200


def test_password_recovery_is_enumeration_safe_single_use_and_revokes_sessions(
    client: TestClient,
) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    original_refresh = client.cookies.get("court4_refresh")
    assert original_refresh
    with get_persistence().session_factory() as session:
        before_hash = session.scalar(
            select(User.password_hash).where(User.email == "owner@example.com")
        )
    known = client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    with get_persistence().session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AccountToken)
                .where(AccountToken.purpose == "password_reset")
            )
            == 1
        )

    reset_token = _email_token(client, headers, "password_reset")
    new_password = "a new correct horse battery staple"
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": new_password},
    )
    assert reset.status_code == 200
    with get_persistence().session_factory() as session:
        after_hash = session.scalar(
            select(User.password_hash).where(User.email == "owner@example.com")
        )
    assert after_hash and after_hash.startswith("$argon2id$")
    assert after_hash != before_hash
    email_categories = [
        item["category"]
        for item in client.get("/api/v1/auth/development/emails", headers=headers).json()["emails"]
    ]
    assert "password_changed" in email_categories
    assert (
        client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": f"{new_password}!"},
        ).status_code
        == 400
    )
    assert client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.com", "password": new_password},
        ).status_code
        == 200
    )


def test_change_password_rotates_current_and_revokes_other_sessions(
    client: TestClient,
) -> None:
    registration = _register(client)
    _mark_verified(UUID(registration.json()["user"]["id"]))
    client.headers["Authorization"] = f"Bearer {registration.json()['access_token']}"
    other = TestClient(create_app())
    other_login = other.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": PASSWORD},
    )
    assert other_login.status_code == 200
    previous_cookie = client.cookies.get("court4_refresh")

    changed = client.post(
        "/api/v1/auth/change-password",
        headers={"Origin": ORIGIN},
        json={
            "current_password": PASSWORD,
            "new_password": "a replacement password for Court4",
        },
    )
    assert changed.status_code == 200
    assert client.cookies.get("court4_refresh") != previous_cookie
    assert other.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 200


def test_session_listing_and_owner_scoped_revocation(client: TestClient) -> None:
    registration = _register(client)
    _mark_verified(UUID(registration.json()["user"]["id"]))
    client.headers["Authorization"] = f"Bearer {registration.json()['access_token']}"
    other = TestClient(create_app())
    other_login = other.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": PASSWORD},
        headers={"User-Agent": "Firefox/120 Windows"},
    )
    assert other_login.status_code == 200

    listed = client.get("/api/v1/auth/sessions")
    assert listed.status_code == 200
    sessions = listed.json()["sessions"]
    assert len(sessions) == 2
    assert sum(item["current"] for item in sessions) == 1
    other_session = next(item for item in sessions if not item["current"])
    revoked = client.delete(
        f"/api/v1/auth/sessions/{other_session['id']}",
        headers={"Origin": ORIGIN},
    )
    assert revoked.status_code == 200
    assert other.post("/api/v1/auth/refresh", headers={"Origin": ORIGIN}).status_code == 401

    unrelated = TestClient(create_app())
    unrelated_registration = _register(unrelated, "unrelated@example.com")
    _mark_verified(UUID(unrelated_registration.json()["user"]["id"]))
    unrelated.headers["Authorization"] = f"Bearer {unrelated_registration.json()['access_token']}"
    hidden = unrelated.delete(
        f"/api/v1/auth/sessions/{sessions[0]['id']}",
        headers={"Origin": ORIGIN},
    )
    assert hidden.status_code == 404


def test_expired_verification_link_has_typed_failure(client: TestClient) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    with get_persistence().session_factory.begin() as session:
        token = session.scalar(
            select(AccountToken).where(AccountToken.purpose == "email_verification")
        )
        assert token is not None
        token.created_at = datetime.now(tz=UTC) - timedelta(hours=2)
        token.expires_at = datetime.now(tz=UTC) - timedelta(hours=1)
    response = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "token_expired"


def test_concurrent_verification_consumes_token_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_token = _email_token(client, headers, "email_verification")
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)
    event_lock = Lock()
    events: list[str] = []

    def capture_event(message: str, *args: object, **kwargs: object) -> None:
        del args, kwargs
        with event_lock:
            events.append(message)

    monkeypatch.setattr("app.auth.service.logger.info", capture_event)

    def verify() -> str:
        barrier.wait()
        try:
            auth.verify_email(raw_token, user_agent="verification-race")
            return "verified"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: verify(), range(2)))
    assert sorted(results) == ["invalid_or_used_token", "verified"]
    with get_persistence().session_factory() as session:
        race_sessions = session.scalar(
            select(func.count())
            .select_from(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.user_agent == "verification-race",
            )
        )
    assert race_sessions == 1
    assert events.count("auth_email_verified") == 1
    assert events.count("auth_verification_session_established") == 1
    assert all(raw_token not in event for event in events)


def test_resend_is_rate_limited_and_already_verified_is_safe(
    client: TestClient,
) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    for _ in range(3):
        assert client.post("/api/v1/auth/resend-verification", headers=headers).status_code == 200
    limited = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert limited.status_code == 429

    auth_rate_limiter.reset()
    token = _email_token(client, headers, "email_verification", index=-1)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    already = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert already.status_code == 200
    assert already.json()["verified"] is True


def test_concurrent_password_reset_consumes_token_once(client: TestClient) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"})
    raw_token = _email_token(client, headers, "password_reset")
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)

    def reset(index: int) -> str:
        barrier.wait()
        try:
            auth.reset_password(raw_token, f"a concurrent replacement password {index}")
            return "reset"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reset, range(2)))
    assert sorted(results) == ["invalid_or_used_token", "reset"]


def test_password_reset_racing_login_leaves_no_old_password_session(
    client: TestClient,
) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"})
    raw_token = _email_token(client, headers, "password_reset")
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)
    login_refresh: list[str] = []

    def reset() -> str:
        barrier.wait()
        auth.reset_password(raw_token, "a race-safe replacement password")
        return "reset"

    def login() -> str:
        barrier.wait()
        try:
            _user, tokens = auth.login("owner@example.com", PASSWORD, user_agent="race")
            login_refresh.append(tokens.refresh_token)
            return "login"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [executor.submit(reset), executor.submit(login)]
        results = [future.result() for future in outcomes]
    assert "reset" in results
    for refresh_token in login_refresh:
        with pytest.raises(AuthenticationError):
            auth.refresh(refresh_token, user_agent="race-check")


def test_password_reset_racing_refresh_revokes_any_replacement(
    client: TestClient,
) -> None:
    registration = _register(client)
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    raw_refresh = client.cookies.get("court4_refresh")
    assert raw_refresh
    client.post("/api/v1/auth/forgot-password", json={"email": "owner@example.com"})
    raw_token = _email_token(client, headers, "password_reset")
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)
    replacements: list[str] = []

    def reset() -> str:
        barrier.wait()
        auth.reset_password(raw_token, "a refresh-race replacement password")
        return "reset"

    def refresh() -> str:
        barrier.wait()
        try:
            _user, tokens = auth.refresh(raw_refresh, user_agent="race")
            replacements.append(tokens.refresh_token)
            return "refreshed"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(reset), executor.submit(refresh)]
        assert "reset" in [future.result() for future in results]
    for replacement in replacements:
        with pytest.raises(AuthenticationError):
            auth.refresh(replacement, user_agent="race-check")


def test_revoke_all_racing_refresh_leaves_no_active_session(
    client: TestClient,
) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    raw_refresh = client.cookies.get("court4_refresh")
    assert raw_refresh
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)
    replacements: list[str] = []

    def revoke() -> str:
        barrier.wait()
        auth.revoke_all_managed_sessions(
            user_id,
            preserve_current_session=False,
            raw_refresh_token=raw_refresh,
            user_agent="race",
        )
        return "revoked"

    def refresh() -> str:
        barrier.wait()
        try:
            _user, tokens = auth.refresh(raw_refresh, user_agent="race")
            replacements.append(tokens.refresh_token)
            return "refreshed"
        except AuthenticationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(revoke), executor.submit(refresh)]
        assert "revoked" in [future.result() for future in results]
    for token in [raw_refresh, *replacements]:
        with pytest.raises(AuthenticationError):
            auth.refresh(token, user_agent="race-check")


def test_concurrent_resend_leaves_one_active_verification_token(
    client: TestClient,
) -> None:
    registration = _register(client)
    user_id = UUID(registration.json()["user"]["id"])
    auth = AuthenticationService(get_persistence().session_factory, get_settings())
    barrier = Barrier(2)

    def resend() -> tuple[bool, object]:
        barrier.wait()
        return auth.resend_verification(user_id, user_agent="race")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: resend(), range(2)))
        assert [sent for sent, _delivery in results] == [True, True]
    with get_persistence().session_factory() as session:
        active_count = session.scalar(
            select(func.count())
            .select_from(AccountToken)
            .where(
                AccountToken.user_id == user_id,
                AccountToken.purpose == "email_verification",
                AccountToken.consumed_at.is_(None),
                AccountToken.invalidated_at.is_(None),
            )
        )
    assert active_count == 1


def _register(client: TestClient, email: str = "owner@example.com") -> Response:
    return cast(
        Response,
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD},
        ),
    )


def _dependency_tree_contains(dependant: Dependant, dependency: object) -> bool:
    if dependant.call is dependency:
        return True
    return any(_dependency_tree_contains(child, dependency) for child in dependant.dependencies)


def _mark_verified(user_id: UUID) -> None:
    with get_persistence().session_factory.begin() as session:
        user = session.get(User, user_id)
        assert user is not None
        user.email_verified_at = datetime.now(tz=UTC)


def _email_token(
    client: TestClient,
    headers: dict[str, str],
    category: str,
    *,
    index: int = 0,
) -> str:
    response = client.get("/api/v1/auth/development/emails", headers=headers)
    assert response.status_code == 200
    messages = [item for item in response.json()["emails"] if item["category"] == category]
    url = next(
        part
        for part in messages[index]["text_body"].split()
        if part.startswith("http://") or part.startswith("https://")
    )
    token = parse_qs(urlparse(url).query).get("token", [None])[0]
    assert token
    return str(token)
