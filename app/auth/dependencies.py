from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.errors import AuthenticationError
from app.auth.service import AuthenticationService
from app.email.dependencies import get_account_email_service
from app.email.service import AccountEmailService
from app.persistence.models import User
from app.persistence.runtime import get_persistence

bearer = HTTPBearer(auto_error=False)


def get_authentication_service(
    email_service: Annotated[AccountEmailService, Depends(get_account_email_service)],
) -> AuthenticationService:
    runtime = get_persistence()
    from app.config import get_settings

    return AuthenticationService(runtime.session_factory, get_settings(), email_service)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("unauthorized", "Authentication is required.")
    return auth.resolve_access_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_verified_user(user: CurrentUser) -> User:
    if user.email_verified_at is None:
        raise AuthenticationError(
            "email_verification_required",
            "Verify your email before starting or re-running an analysis.",
            status_code=403,
        )
    return user


VerifiedUser = Annotated[User, Depends(require_verified_user)]
