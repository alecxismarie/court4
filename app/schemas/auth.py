from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CredentialsRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str

    @field_validator("password")
    @classmethod
    def reject_nul_password(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Password contains an invalid character.")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    account_status: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    email_verified_at: datetime | None
    password_changed_at: datetime | None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class LogoutResponse(BaseModel):
    logged_out: bool = True


class TokenRequest(BaseModel):
    token: str = Field(max_length=256)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetPasswordRequest(TokenRequest):
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class RevokeAllSessionsRequest(BaseModel):
    preserve_current_session: bool = True


class MessageResponse(BaseModel):
    message: str


class VerificationResponse(MessageResponse):
    verified: bool
    user: UserResponse | None = None


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    revoked_at: datetime | None
    client_label: str
    current: bool


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class SessionMutationResponse(BaseModel):
    revoked_count: int = 0
    current_session_preserved: bool = False


class DevelopmentEmailResponse(BaseModel):
    subject: str
    text_body: str
    html_body: str
    category: str
    correlation_id: str


class DevelopmentEmailListResponse(BaseModel):
    emails: list[DevelopmentEmailResponse]
