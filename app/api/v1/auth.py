from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.auth.dependencies import (
    CurrentUser,
    OptionalCurrentUser,
    VerifiedUser,
    get_authentication_service,
)
from app.auth.errors import AuthenticationError
from app.auth.rate_limit import auth_rate_limiter
from app.auth.service import (
    GENERIC_RECOVERY_MESSAGE,
    AuthenticationService,
    normalize_email,
)
from app.config import get_settings
from app.config.settings import Settings
from app.email.dependencies import get_development_email_sink
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    CompleteOnboardingRequest,
    CredentialsRequest,
    DevelopmentEmailListResponse,
    DevelopmentEmailResponse,
    ForgotPasswordRequest,
    LogoutResponse,
    MessageResponse,
    ResetPasswordRequest,
    RevokeAllSessionsRequest,
    SessionListResponse,
    SessionMutationResponse,
    SessionResponse,
    TokenRequest,
    UserResponse,
    VerificationAuthResponse,
    VerificationResponse,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
development_router = APIRouter(prefix="/auth", tags=["development-email"], include_in_schema=False)
AuthDependency = Annotated[AuthenticationService, Depends(get_authentication_service)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    credentials: CredentialsRequest,
    request: Request,
    response: Response,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    _limit(request, "register", settings.auth_register_rate_limit, settings)
    if not settings.registration_open:
        raise AuthenticationError(
            "REGISTRATION_CLOSED",
            "Private-alpha registration is currently closed. Existing users can still log in.",
            status_code=403,
        )
    normalized_email = normalize_email(credentials.email)
    if (
        settings.private_alpha_allowlist_enabled
        and normalized_email not in settings.private_alpha_allowed_emails
    ):
        raise AuthenticationError(
            "PRIVATE_ALPHA_NOT_APPROVED",
            "This email is not approved for the Court4 private alpha.",
            status_code=403,
        )
    user, tokens = auth.register(
        normalized_email,
        credentials.password,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    credentials: CredentialsRequest,
    request: Request,
    response: Response,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    _limit(request, "login", settings.auth_login_rate_limit, settings)
    user, tokens = auth.login(
        credentials.email,
        credentials.password,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    _validate_cookie_origin(request, settings)
    _limit(request, "refresh", settings.auth_refresh_rate_limit, settings)
    # Read by configured name so deployments may rename the cookie.
    raw_token = request.cookies.get(settings.auth_refresh_cookie_name)
    user, tokens = auth.refresh(raw_token, user_agent=request.headers.get("user-agent"))
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> LogoutResponse:
    _validate_cookie_origin(request, settings)
    auth.logout(request.cookies.get(settings.auth_refresh_cookie_name))
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_base_path}/auth",
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )
    return LogoutResponse()


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/resend-verification", response_model=VerificationResponse)
def resend_verification(
    request: Request,
    user: CurrentUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> VerificationResponse:
    _limit(
        request,
        f"resend-verification:{user.id}",
        settings.auth_resend_verification_rate_limit,
        settings,
    )
    sent = auth.resend_verification(user.id, user_agent=request.headers.get("user-agent"))
    return VerificationResponse(
        verified=not sent,
        message=(
            "A new verification link has been sent." if sent else "Your email is already verified."
        ),
        user=UserResponse.model_validate(user) if not sent else None,
    )


@router.post("/verify-email", response_model=VerificationAuthResponse)
def verify_email(
    payload: TokenRequest,
    request: Request,
    response: Response,
    current_user: OptionalCurrentUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> VerificationAuthResponse:
    user, tokens = auth.verify_email(
        payload.token,
        user_agent=request.headers.get("user-agent"),
        current_user_id=current_user.id if current_user is not None else None,
        raw_refresh_token=request.cookies.get(settings.auth_refresh_cookie_name),
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return VerificationAuthResponse(
        verified=True,
        message="Your email has been verified.",
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/onboarding", response_model=UserResponse)
def complete_onboarding(
    payload: CompleteOnboardingRequest,
    user: VerifiedUser,
    auth: AuthDependency,
) -> UserResponse:
    completed_user = auth.complete_onboarding(user.id, payload.display_name)
    return UserResponse.model_validate(completed_user)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> MessageResponse:
    _limit(
        request,
        "forgot-password",
        settings.auth_forgot_password_rate_limit,
        settings,
    )
    auth.request_password_reset(payload.email, user_agent=request.headers.get("user-agent"))
    return MessageResponse(message=GENERIC_RECOVERY_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> MessageResponse:
    _limit(
        request,
        "reset-password",
        settings.auth_reset_password_rate_limit,
        settings,
    )
    auth.reset_password(payload.token, payload.new_password)
    return MessageResponse(message="Your password has been reset. Sign in with your new password.")


@router.post("/change-password", response_model=AuthResponse)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: VerifiedUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    _validate_cookie_origin(request, settings)
    _limit(
        request,
        f"change-password:{user.id}",
        settings.auth_change_password_rate_limit,
        settings,
    )
    changed_user, tokens = auth.change_password(
        user.id,
        payload.current_password,
        payload.new_password,
        raw_refresh_token=request.cookies.get(settings.auth_refresh_cookie_name),
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, tokens.refresh_token, settings)
    return AuthResponse(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        user=UserResponse.model_validate(changed_user),
    )


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    user: VerifiedUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> SessionListResponse:
    sessions = auth.list_sessions(
        user.id,
        raw_refresh_token=request.cookies.get(settings.auth_refresh_cookie_name),
    )
    return SessionListResponse(
        sessions=[SessionResponse.model_validate(item, from_attributes=True) for item in sessions]
    )


@router.delete("/sessions/{session_id}", response_model=SessionMutationResponse)
def revoke_session(
    session_id: UUID,
    request: Request,
    response: Response,
    user: VerifiedUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> SessionMutationResponse:
    _validate_cookie_origin(request, settings)
    _limit(
        request,
        f"session-action:{user.id}",
        settings.auth_session_action_rate_limit,
        settings,
    )
    current_revoked = auth.revoke_session(
        user.id,
        session_id,
        raw_refresh_token=request.cookies.get(settings.auth_refresh_cookie_name),
    )
    if current_revoked:
        _delete_refresh_cookie(response, settings)
    return SessionMutationResponse(revoked_count=1, current_session_preserved=not current_revoked)


@router.post("/sessions/revoke-all", response_model=SessionMutationResponse)
def revoke_all_sessions(
    payload: RevokeAllSessionsRequest,
    request: Request,
    response: Response,
    user: VerifiedUser,
    auth: AuthDependency,
    settings: SettingsDependency,
) -> SessionMutationResponse:
    _validate_cookie_origin(request, settings)
    _limit(
        request,
        f"session-action:{user.id}",
        settings.auth_session_action_rate_limit,
        settings,
    )
    result = auth.revoke_all_managed_sessions(
        user.id,
        preserve_current_session=payload.preserve_current_session,
        raw_refresh_token=request.cookies.get(settings.auth_refresh_cookie_name),
        user_agent=request.headers.get("user-agent"),
    )
    if result.replacement_tokens is not None:
        _set_refresh_cookie(response, result.replacement_tokens.refresh_token, settings)
    elif not result.current_session_preserved:
        _delete_refresh_cookie(response, settings)
    return SessionMutationResponse(
        revoked_count=result.revoked_count,
        current_session_preserved=result.current_session_preserved,
    )


@development_router.get("/development/emails", response_model=DevelopmentEmailListResponse)
def development_emails(
    user: CurrentUser, settings: SettingsDependency
) -> DevelopmentEmailListResponse:
    if (
        settings.environment not in {"development", "test"}
        or settings.auth_email_backend != "development"
        or not settings.auth_development_email_sink_enabled
    ):
        raise AuthenticationError("not_found", "Resource was not found.", status_code=404)
    messages = get_development_email_sink().messages_for(user.email)
    return DevelopmentEmailListResponse(
        emails=[
            DevelopmentEmailResponse(
                subject=message.subject,
                text_body=message.text_body,
                html_body=message.html_body,
                category=message.category,
                correlation_id=message.correlation_id,
            )
            for message in messages
        ]
    )


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.auth_refresh_cookie_name,
        token,
        max_age=settings.auth_refresh_token_days * 24 * 60 * 60,
        expires=settings.auth_refresh_token_days * 24 * 60 * 60,
        path=f"{settings.api_base_path}/auth",
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_base_path}/auth",
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_cookie_samesite,
    )


def _validate_cookie_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("origin", "").rstrip("/")
    if origin not in settings.frontend_allowed_origins:
        raise AuthenticationError(
            "invalid_origin", "Request origin is not allowed.", status_code=403
        )


def _limit(request: Request, operation: str, limit: int, settings: Settings) -> None:
    address = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(
        f"{operation}:{address}",
        limit=limit,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
