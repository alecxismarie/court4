from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.jobs import UploadAnalysisResponse
from app.sports import SportType


class InitiateUploadRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0)
    sport: SportType = SportType.PICKLEBALL
    reanalyze: bool = False
    expected_sha256: str | None = None
    client_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("expected_sha256")
    @classmethod
    def validate_expected_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if len(cleaned) != 64 or any(char not in "0123456789abcdef" for char in cleaned):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
        return cleaned


class PresignedUploadPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    part_number: int = Field(ge=1, le=10_000)
    url: str = Field(min_length=1)
    expires_at: datetime


class InitiateUploadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    transport: Literal["direct", "proxy"]
    upload_session_id: UUID | None = None
    status: str
    part_size: int | None = None
    part_count: int | None = None
    max_concurrency: int
    max_attempts: int
    expires_at: datetime | None = None
    parts: list[PresignedUploadPart] = Field(default_factory=list)


class UploadPartUrlRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    part_numbers: list[int] = Field(min_length=1, max_length=200)

    @field_validator("part_numbers")
    @classmethod
    def validate_part_numbers(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(part < 1 or part > 10_000 for part in value):
            raise ValueError("part_numbers must be unique values from 1 through 10000")
        return value


class UploadPartUrlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    upload_session_id: UUID
    parts: list[PresignedUploadPart]


class CompletedUploadPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=512)

    @field_validator("etag")
    @classmethod
    def validate_etag(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "\r" in cleaned or "\n" in cleaned:
            raise ValueError("etag is invalid")
        return cleaned


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    parts: list[CompletedUploadPart] = Field(min_length=1, max_length=10_000)


class UploadSessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    upload_session_id: UUID
    status: str
    byte_size: int
    verified_sha256: str | None = None
    result: UploadAnalysisResponse | None = None
    failure_code: str | None = None
    expires_at: datetime
