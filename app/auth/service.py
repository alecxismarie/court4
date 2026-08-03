from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from typing import NoReturn
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.errors import AuthenticationError
from app.config.settings import Settings
from app.email.service import AccountEmailService
from app.persistence.models import AccountToken, RefreshSession, User

logger = logging.getLogger(__name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
GENERIC_LOGIN_ERROR = "Email or password is incorrect."
GENERIC_RECOVERY_MESSAGE = (
    "If an active account exists for that email, a password reset link has been sent."
)


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    access_expires_in: int


@dataclass(frozen=True)
class ManagedSession:
    id: UUID
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None
    client_label: str
    current: bool


@dataclass(frozen=True)
class SessionMutation:
    revoked_count: int
    current_session_preserved: bool
    replacement_tokens: SessionTokens | None = None


def normalize_email(value: str) -> str:
    """Trim and case-fold the complete address; no provider-specific rewriting."""
    normalized = value.strip().casefold()
    if len(normalized) > 320 or not EMAIL_PATTERN.fullmatch(normalized):
        raise AuthenticationError(
            "invalid_registration", "Enter a valid email address.", status_code=422
        )
    return normalized


class AuthenticationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        email_service: AccountEmailService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._email_service = email_service
        self._passwords = PasswordHasher()

    def register(
        self, email: str, password: str, *, user_agent: str | None
    ) -> tuple[User, SessionTokens]:
        normalized = normalize_email(email)
        self._validate_new_password(password, code="invalid_registration")
        password_hash = self._passwords.hash(password)
        raw_verification_token: str | None = None
        token_id: UUID | None = None
        try:
            with self._session_factory.begin() as session:
                user = User(email=normalized, password_hash=password_hash, account_status="active")
                session.add(user)
                session.flush()
                raw_verification_token, token_id = self._create_account_token(
                    session,
                    user.id,
                    purpose="email_verification",
                    lifetime=timedelta(hours=self._settings.auth_verification_token_hours),
                    user_agent=user_agent,
                )
                tokens = self._create_session(session, user, user_agent=user_agent)
        except IntegrityError:
            logger.info("auth_registration_failed", extra={"category": "duplicate"})
            raise AuthenticationError(
                "registration_failed",
                "An account with that email cannot be created.",
                status_code=409,
            ) from None
        self._send_verification(user, raw_verification_token, token_id)
        logger.info("auth_registration_succeeded", extra={"user_id": str(user.id)})
        return user, tokens

    def login(
        self, email: str, password: str, *, user_agent: str | None
    ) -> tuple[User, SessionTokens]:
        if len(password) > self._settings.auth_max_password_length:
            self._login_failed()
        try:
            normalized = normalize_email(email)
        except AuthenticationError:
            self._login_failed()
        with self._session_factory.begin() as session:
            candidate = session.scalar(select(User).where(User.email == normalized))
            if candidate is None:
                self._login_failed()
            self._lock_user_security(session, candidate.id)
            user = session.scalar(select(User).where(User.email == normalized).with_for_update())
            if user is None or user.account_status != "active":
                self._login_failed()
            try:
                valid = self._passwords.verify(user.password_hash, password)
            except (InvalidHashError, VerifyMismatchError):
                self._login_failed()
            if not valid:
                self._login_failed()
            if self._passwords.check_needs_rehash(user.password_hash):
                user.password_hash = self._passwords.hash(password)
            user.last_login_at = datetime.now(tz=UTC)
            tokens = self._create_session(session, user, user_agent=user_agent)
        logger.info("auth_login_succeeded", extra={"user_id": str(user.id)})
        return user, tokens

    def refresh(
        self, raw_token: str | None, *, user_agent: str | None
    ) -> tuple[User, SessionTokens]:
        session_id = self._parse_refresh_session_id(raw_token)
        now = datetime.now(tz=UTC)
        user: User | None = None
        tokens: SessionTokens | None = None
        failed = False
        with self._session_factory.begin() as session:
            candidate = session.scalar(
                select(RefreshSession).where(RefreshSession.id == session_id)
            )
            if (
                candidate is None
                or raw_token is None
                or not compare_digest(candidate.token_hash, _token_hash(raw_token))
            ):
                failed = True
                refresh_session = candidate
            else:
                self._lock_user_security(session, candidate.user_id)
                user = session.scalar(
                    select(User).where(User.id == candidate.user_id).with_for_update()
                )
                refresh_session = session.scalar(
                    select(RefreshSession)
                    .where(RefreshSession.id == session_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            if (
                not failed
                and refresh_session is not None
                and (
                    raw_token is None
                    or not compare_digest(refresh_session.token_hash, _token_hash(raw_token))
                )
            ):
                failed = True
            elif (
                not failed
                and refresh_session is not None
                and refresh_session.revoked_at is not None
            ):
                if refresh_session.revocation_reason == "rotated":
                    self._revoke_family(
                        session, refresh_session.token_family_id, "refresh_token_reuse", now
                    )
                    logger.warning(
                        "auth_refresh_reuse_detected",
                        extra={"user_id": str(refresh_session.user_id)},
                    )
                failed = True
            elif not failed and refresh_session is not None and refresh_session.expires_at <= now:
                refresh_session.revoked_at = now
                refresh_session.revocation_reason = "expired"
                failed = True
            if (
                not failed
                and refresh_session is not None
                and (user is None or user.account_status != "active")
            ):
                self._revoke_family(
                    session, refresh_session.token_family_id, "account_unavailable", now
                )
                failed = True
            if not failed and user is not None and refresh_session is not None:
                refresh_session.revoked_at = now
                refresh_session.last_used_at = now
                refresh_session.revocation_reason = "rotated"
                tokens, replacement_id = self._create_session_tokens(
                    session,
                    user,
                    user_agent=user_agent,
                    family_id=refresh_session.token_family_id,
                )
                refresh_session.replaced_by_session_id = replacement_id
        if failed or user is None or tokens is None:
            self._refresh_failed()
        logger.info("auth_refresh_rotated", extra={"user_id": str(user.id)})
        return user, tokens

    def logout(self, raw_token: str | None) -> None:
        try:
            session_id = self._parse_refresh_session_id(raw_token)
        except AuthenticationError:
            return
        now = datetime.now(tz=UTC)
        with self._session_factory.begin() as session:
            refresh_session = session.scalar(
                select(RefreshSession).where(RefreshSession.id == session_id).with_for_update()
            )
            if (
                refresh_session is not None
                and raw_token is not None
                and compare_digest(refresh_session.token_hash, _token_hash(raw_token))
                and refresh_session.revoked_at is None
            ):
                refresh_session.revoked_at = now
                refresh_session.revocation_reason = "logout"
                logger.info("auth_logout", extra={"user_id": str(refresh_session.user_id)})

    def resend_verification(self, user_id: UUID, *, user_agent: str | None) -> bool:
        raw_token: str | None = None
        token_id: UUID | None = None
        with self._session_factory.begin() as session:
            self._lock_user_security(session, user_id)
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or user.account_status != "active":
                raise AuthenticationError("unauthorized", "Authentication is required.")
            if user.email_verified_at is not None:
                return False
            self._invalidate_active_tokens(
                session, user.id, "email_verification", datetime.now(tz=UTC)
            )
            raw_token, token_id = self._create_account_token(
                session,
                user.id,
                purpose="email_verification",
                lifetime=timedelta(hours=self._settings.auth_verification_token_hours),
                user_agent=user_agent,
            )
        self._send_verification(user, raw_token, token_id)
        logger.info("auth_verification_resent", extra={"user_id": str(user.id)})
        return True

    def verify_email(self, raw_token: str) -> User:
        now = datetime.now(tz=UTC)
        with self._session_factory.begin() as session:
            account_token = self._lock_account_token(session, raw_token, "email_verification")
            self._validate_account_token(account_token, now)
            user = session.scalar(
                select(User).where(User.id == account_token.user_id).with_for_update()
            )
            if user is None or user.account_status != "active":
                self._invalid_account_token()
            account_token.consumed_at = now
            if user.email_verified_at is None:
                user.email_verified_at = now
            self._invalidate_active_tokens(
                session,
                user.id,
                "email_verification",
                now,
                exclude_id=account_token.id,
            )
        logger.info("auth_email_verified", extra={"user_id": str(user.id)})
        return user

    def request_password_reset(self, email: str, *, user_agent: str | None) -> None:
        try:
            normalized = normalize_email(email)
        except AuthenticationError:
            logger.info("auth_password_reset_requested", extra={"category": "generic"})
            return
        raw_token: str | None = None
        token_id: UUID | None = None
        user: User | None = None
        with self._session_factory.begin() as session:
            candidate = session.scalar(select(User).where(User.email == normalized))
            if candidate is not None:
                self._lock_user_security(session, candidate.id)
                user = session.scalar(
                    select(User).where(User.email == normalized).with_for_update()
                )
            if user is not None and user.account_status == "active":
                self._invalidate_active_tokens(
                    session, user.id, "password_reset", datetime.now(tz=UTC)
                )
                raw_token, token_id = self._create_account_token(
                    session,
                    user.id,
                    purpose="password_reset",
                    lifetime=timedelta(minutes=self._settings.auth_password_reset_token_minutes),
                    user_agent=user_agent,
                )
        if (
            user is not None
            and raw_token is not None
            and token_id is not None
            and self._email_service is not None
        ):
            self._email_service.send_password_reset_email(
                user.email, raw_token, correlation_id=str(token_id)
            )
        logger.info("auth_password_reset_requested", extra={"category": "generic"})

    def reset_password(self, raw_token: str, new_password: str) -> User:
        self._validate_new_password(new_password, code="invalid_password")
        password_hash = self._passwords.hash(new_password)
        now = datetime.now(tz=UTC)
        revoked_count = 0
        with self._session_factory.begin() as session:
            account_token = self._lock_account_token(session, raw_token, "password_reset")
            self._validate_account_token(account_token, now)
            user = session.scalar(
                select(User).where(User.id == account_token.user_id).with_for_update()
            )
            if user is None or user.account_status != "active":
                self._invalid_account_token()
            refresh_sessions = list(
                session.scalars(
                    select(RefreshSession)
                    .where(RefreshSession.user_id == account_token.user_id)
                    .order_by(RefreshSession.id)
                    .with_for_update()
                )
            )
            account_token.consumed_at = now
            user.password_hash = password_hash
            user.password_changed_at = now
            for refresh_session in refresh_sessions:
                if refresh_session.revoked_at is None:
                    refresh_session.revoked_at = now
                    refresh_session.revocation_reason = "password_reset"
                    revoked_count += 1
            self._invalidate_active_tokens(
                session,
                user.id,
                "password_reset",
                now,
                exclude_id=account_token.id,
            )
        if self._email_service is not None:
            self._email_service.send_password_changed_email(user.email, correlation_id=uuid4().hex)
        logger.info(
            "auth_password_reset_completed",
            extra={"user_id": str(user.id), "revoked_count": revoked_count},
        )
        return user

    def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        *,
        raw_refresh_token: str | None,
        user_agent: str | None,
    ) -> tuple[User, SessionTokens]:
        self._validate_new_password(new_password, code="invalid_password")
        current_session_id = self._parse_refresh_session_id(raw_refresh_token)
        now = datetime.now(tz=UTC)
        with self._session_factory.begin() as session:
            self._lock_user_security(session, user_id)
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or user.account_status != "active":
                raise AuthenticationError("unauthorized", "Authentication is required.")
            refresh_sessions = list(
                session.scalars(
                    select(RefreshSession)
                    .where(RefreshSession.user_id == user_id)
                    .order_by(RefreshSession.id)
                    .with_for_update()
                )
            )
            current_session = next(
                (
                    refresh_session
                    for refresh_session in refresh_sessions
                    if refresh_session.id == current_session_id
                ),
                None,
            )
            self._require_active_matching_session(current_session, raw_refresh_token, now)
            valid: bool
            try:
                valid = self._passwords.verify(user.password_hash, current_password)
            except (InvalidHashError, VerifyMismatchError):
                valid = False
            if not valid:
                raise AuthenticationError(
                    "invalid_current_password",
                    "Current password is incorrect.",
                    status_code=400,
                )
            same_password: bool
            try:
                same_password = self._passwords.verify(user.password_hash, new_password)
            except (InvalidHashError, VerifyMismatchError):
                same_password = False
            if same_password:
                raise AuthenticationError(
                    "password_unchanged",
                    "New password must be different from the current password.",
                    status_code=422,
                )
            user.password_hash = self._passwords.hash(new_password)
            user.password_changed_at = now
            for refresh_session in refresh_sessions:
                if refresh_session.id == current_session_id:
                    continue
                if refresh_session.revoked_at is None:
                    refresh_session.revoked_at = now
                    refresh_session.revocation_reason = "password_changed"
            assert current_session is not None
            current_session.revoked_at = now
            current_session.last_used_at = now
            current_session.revocation_reason = "rotated"
            tokens, replacement_id = self._create_session_tokens(
                session,
                user,
                user_agent=user_agent,
                family_id=current_session.token_family_id,
            )
            current_session.replaced_by_session_id = replacement_id
            self._invalidate_active_tokens(session, user.id, "password_reset", now)
        if self._email_service is not None:
            self._email_service.send_password_changed_email(user.email, correlation_id=uuid4().hex)
        logger.info("auth_password_changed", extra={"user_id": str(user.id)})
        return user, tokens

    def list_sessions(
        self, user_id: UUID, *, raw_refresh_token: str | None
    ) -> list[ManagedSession]:
        current_id = self._matching_current_session_id(user_id, raw_refresh_token)
        now = datetime.now(tz=UTC)
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(RefreshSession)
                    .where(RefreshSession.user_id == user_id)
                    .order_by(RefreshSession.created_at.desc())
                )
            )
            return [
                ManagedSession(
                    id=row.id,
                    created_at=row.created_at,
                    last_used_at=row.last_used_at,
                    expires_at=row.expires_at,
                    revoked_at=row.revoked_at,
                    client_label=_client_label(row.user_agent),
                    current=row.id == current_id,
                )
                for row in rows
                if row.revoked_at is None and row.expires_at > now
            ]

    def revoke_session(
        self, user_id: UUID, session_id: UUID, *, raw_refresh_token: str | None
    ) -> bool:
        now = datetime.now(tz=UTC)
        current_id = self._matching_current_session_id(user_id, raw_refresh_token)
        with self._session_factory.begin() as session:
            self._lock_user_security(session, user_id)
            refresh_session = session.scalar(
                select(RefreshSession)
                .where(
                    RefreshSession.id == session_id,
                    RefreshSession.user_id == user_id,
                )
                .with_for_update()
            )
            if refresh_session is None:
                raise AuthenticationError(
                    "session_not_found", "Session was not found.", status_code=404
                )
            if refresh_session.revoked_at is None:
                refresh_session.revoked_at = now
                refresh_session.revocation_reason = "user_revoked"
        logger.info(
            "auth_session_revoked",
            extra={"user_id": str(user_id), "current": session_id == current_id},
        )
        return session_id == current_id

    def revoke_all_managed_sessions(
        self,
        user_id: UUID,
        *,
        preserve_current_session: bool,
        raw_refresh_token: str | None,
        user_agent: str | None,
    ) -> SessionMutation:
        now = datetime.now(tz=UTC)
        current_id: UUID | None = None
        current_session: RefreshSession | None = None
        replacement_tokens: SessionTokens | None = None
        if preserve_current_session:
            current_id = self._parse_refresh_session_id(raw_refresh_token)
        with self._session_factory.begin() as session:
            self._lock_user_security(session, user_id)
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or user.account_status != "active":
                raise AuthenticationError("unauthorized", "Authentication is required.")
            refresh_sessions = list(
                session.scalars(
                    select(RefreshSession)
                    .where(RefreshSession.user_id == user_id)
                    .order_by(RefreshSession.id)
                    .with_for_update()
                )
            )
            if current_id is not None:
                current_session = next(
                    (
                        refresh_session
                        for refresh_session in refresh_sessions
                        if refresh_session.id == current_id
                    ),
                    None,
                )
                self._require_active_matching_session(current_session, raw_refresh_token, now)
            revoked_count = 0
            for refresh_session in refresh_sessions:
                if current_id is not None and refresh_session.id == current_id:
                    continue
                if refresh_session.revoked_at is None:
                    refresh_session.revoked_at = now
                    refresh_session.revocation_reason = "user_revoke_all"
                    revoked_count += 1
            if current_session is not None:
                current_session.revoked_at = now
                current_session.last_used_at = now
                current_session.revocation_reason = "rotated"
                replacement_tokens, replacement_id = self._create_session_tokens(
                    session,
                    user,
                    user_agent=user_agent,
                    family_id=current_session.token_family_id,
                )
                current_session.replaced_by_session_id = replacement_id
        if self._email_service is not None and revoked_count:
            self._email_service.send_sessions_revoked_email(user.email, correlation_id=uuid4().hex)
        logger.info(
            "auth_sessions_revoked",
            extra={
                "user_id": str(user_id),
                "revoked_count": revoked_count,
                "current_preserved": preserve_current_session,
            },
        )
        return SessionMutation(
            revoked_count=revoked_count,
            current_session_preserved=preserve_current_session,
            replacement_tokens=replacement_tokens,
        )

    def revoke_all_sessions(self, user_id: UUID, *, reason: str) -> None:
        """Internal security primitive for account-state actions."""
        now = datetime.now(tz=UTC)
        with self._session_factory.begin() as session:
            session.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.user_id == user_id,
                    RefreshSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, revocation_reason=reason[:64])
            )
        logger.info("auth_sessions_revoked", extra={"user_id": str(user_id), "reason": reason})

    def resolve_access_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self._settings.auth_access_token_secret.get_secret_value(),
                algorithms=["HS256"],
                audience=self._settings.auth_token_audience,
                issuer=self._settings.auth_token_issuer,
                options={"require": ["sub", "exp", "iat", "jti"]},
            )
            user_id = UUID(payload["sub"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise AuthenticationError("unauthorized", "Authentication is required.") from None
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None:
                raise AuthenticationError("unauthorized", "Authentication is required.")
            if user.account_status != "active":
                logger.warning("auth_disabled_account_access", extra={"user_id": str(user.id)})
                raise AuthenticationError("unauthorized", "Authentication is required.")
            session.expunge(user)
            return user

    def _validate_new_password(self, password: str, *, code: str) -> None:
        if "\x00" in password:
            raise AuthenticationError(
                code, "Password contains an invalid character.", status_code=422
            )
        if len(password) < self._settings.auth_min_password_length:
            raise AuthenticationError(
                code,
                "Password must contain at least "
                f"{self._settings.auth_min_password_length} characters.",
                status_code=422,
            )
        if len(password) > self._settings.auth_max_password_length:
            raise AuthenticationError(code, "Password is too long.", status_code=422)

    def _create_session(
        self, session: Session, user: User, *, user_agent: str | None
    ) -> SessionTokens:
        tokens, _ = self._create_session_tokens(
            session, user, user_agent=user_agent, family_id=uuid4()
        )
        return tokens

    def _create_session_tokens(
        self,
        session: Session,
        user: User,
        *,
        user_agent: str | None,
        family_id: UUID,
    ) -> tuple[SessionTokens, UUID]:
        now = datetime.now(tz=UTC)
        session_id = uuid4()
        refresh_token = f"{session_id}.{secrets.token_urlsafe(48)}"
        session.add(
            RefreshSession(
                id=session_id,
                user_id=user.id,
                token_hash=_token_hash(refresh_token),
                token_family_id=family_id,
                expires_at=now + timedelta(days=self._settings.auth_refresh_token_days),
                user_agent=(user_agent or "")[:512] or None,
            )
        )
        session.flush()
        expires_in = self._settings.auth_access_token_minutes * 60
        access_token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": now,
                "exp": now + timedelta(seconds=expires_in),
                "iss": self._settings.auth_token_issuer,
                "aud": self._settings.auth_token_audience,
                "jti": uuid4().hex,
            },
            self._settings.auth_access_token_secret.get_secret_value(),
            algorithm="HS256",
        )
        return SessionTokens(access_token, refresh_token, expires_in), session_id

    def _create_account_token(
        self,
        session: Session,
        user_id: UUID,
        *,
        purpose: str,
        lifetime: timedelta,
        user_agent: str | None,
    ) -> tuple[str, UUID]:
        raw_token = secrets.token_urlsafe(48)
        token_id = uuid4()
        session.add(
            AccountToken(
                id=token_id,
                user_id=user_id,
                purpose=purpose,
                token_hash=_token_hash(raw_token),
                expires_at=datetime.now(tz=UTC) + lifetime,
                request_user_agent=(user_agent or "")[:512] or None,
            )
        )
        session.flush()
        return raw_token, token_id

    @staticmethod
    def _invalidate_active_tokens(
        session: Session,
        user_id: UUID,
        purpose: str,
        invalidated_at: datetime,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        conditions = [
            AccountToken.user_id == user_id,
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
            AccountToken.invalidated_at.is_(None),
        ]
        if exclude_id is not None:
            conditions.append(AccountToken.id != exclude_id)
        session.execute(
            update(AccountToken).where(*conditions).values(invalidated_at=invalidated_at)
        )

    def _lock_account_token(self, session: Session, raw_token: str, purpose: str) -> AccountToken:
        if not raw_token or len(raw_token) > 256:
            self._invalid_account_token()
        token_hash = _token_hash(raw_token)
        candidate = session.scalar(
            select(AccountToken).where(
                AccountToken.token_hash == token_hash,
                AccountToken.purpose == purpose,
            )
        )
        if candidate is None:
            self._invalid_account_token()
        self._lock_user_security(session, candidate.user_id)
        account_token = session.scalar(
            select(AccountToken)
            .where(
                AccountToken.token_hash == token_hash,
                AccountToken.purpose == purpose,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if account_token is None:
            self._invalid_account_token()
        return account_token

    def _validate_account_token(self, account_token: AccountToken, now: datetime) -> None:
        if account_token.consumed_at is not None or account_token.invalidated_at is not None:
            self._invalid_account_token()
        if account_token.expires_at <= now:
            account_token.invalidated_at = now
            logger.info(
                "auth_account_token_failed",
                extra={"category": "expired", "purpose": account_token.purpose},
            )
            raise AuthenticationError(
                "token_expired",
                "This link has expired. Request a new one.",
                status_code=400,
            )

    def _send_verification(self, user: User, raw_token: str | None, token_id: UUID | None) -> None:
        if self._email_service is not None and raw_token is not None and token_id is not None:
            self._email_service.send_verification_email(
                user.email, raw_token, correlation_id=str(token_id)
            )

    @staticmethod
    def _lock_user_security(session: Session, user_id: UUID) -> None:
        """Serialize security mutations for one account within PostgreSQL."""
        key = int.from_bytes(user_id.bytes[:8], byteorder="big", signed=True)
        session.execute(
            text("SELECT pg_advisory_xact_lock(:security_key)"),
            {"security_key": key},
        )

    def _matching_current_session_id(self, user_id: UUID, raw_token: str | None) -> UUID | None:
        try:
            session_id = self._parse_refresh_session_id(raw_token)
        except AuthenticationError:
            return None
        with self._session_factory() as session:
            refresh_session = session.scalar(
                select(RefreshSession).where(
                    RefreshSession.id == session_id,
                    RefreshSession.user_id == user_id,
                )
            )
            if (
                refresh_session is None
                or raw_token is None
                or refresh_session.revoked_at is not None
                or refresh_session.expires_at <= datetime.now(tz=UTC)
                or not compare_digest(refresh_session.token_hash, _token_hash(raw_token))
            ):
                return None
            return session_id

    @staticmethod
    def _require_active_matching_session(
        refresh_session: RefreshSession | None,
        raw_token: str | None,
        now: datetime,
    ) -> None:
        if (
            refresh_session is None
            or raw_token is None
            or refresh_session.revoked_at is not None
            or refresh_session.expires_at <= now
            or not compare_digest(refresh_session.token_hash, _token_hash(raw_token))
        ):
            raise AuthenticationError("invalid_session", "Session is invalid.")

    @staticmethod
    def _parse_refresh_session_id(raw_token: str | None) -> UUID:
        if not raw_token or len(raw_token) > 256:
            raise AuthenticationError("invalid_session", "Session is invalid.")
        try:
            session_id, secret = raw_token.split(".", 1)
            if len(secret) < 32:
                raise ValueError
            return UUID(session_id)
        except ValueError:
            raise AuthenticationError("invalid_session", "Session is invalid.") from None

    @staticmethod
    def _revoke_family(
        session: Session, family_id: UUID, reason: str, revoked_at: datetime
    ) -> None:
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_family_id == family_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at, revocation_reason=reason)
        )

    @staticmethod
    def _invalid_account_token() -> NoReturn:
        logger.info("auth_account_token_failed", extra={"category": "invalid_or_used"})
        raise AuthenticationError(
            "invalid_or_used_token",
            "This link is invalid or has already been used.",
            status_code=400,
        )

    @staticmethod
    def _login_failed() -> NoReturn:
        logger.info("auth_login_failed", extra={"category": "invalid_credentials"})
        raise AuthenticationError("invalid_credentials", GENERIC_LOGIN_ERROR)

    @staticmethod
    def _refresh_failed() -> NoReturn:
        raise AuthenticationError("invalid_session", "Session is invalid.")


def _token_hash(raw_token: str) -> str:
    return sha256(raw_token.encode()).hexdigest()


def _client_label(user_agent: str | None) -> str:
    value = (user_agent or "").casefold()
    if "edg/" in value:
        browser = "Edge"
    elif "firefox/" in value:
        browser = "Firefox"
    elif "chrome/" in value or "crios/" in value:
        browser = "Chrome"
    elif "safari/" in value:
        browser = "Safari"
    else:
        browser = "Browser"
    if "iphone" in value or "ipad" in value:
        platform = "iOS"
    elif "android" in value:
        platform = "Android"
    elif "windows" in value:
        platform = "Windows"
    elif "macintosh" in value or "mac os" in value:
        platform = "macOS"
    elif "linux" in value:
        platform = "Linux"
    else:
        platform = "Unknown device"
    return f"{browser} on {platform}"
