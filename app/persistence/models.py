from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("account_status in ('active','disabled')", name="ck_user_account_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    account_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_name: Mapped[str | None] = mapped_column(String(36))


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_session_user", "user_id", "created_at"),
        Index("ix_refresh_session_family", "token_family_id"),
        Index("ix_refresh_session_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_family_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, default=uuid4)
    replaced_by_session_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("refresh_sessions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class AccountToken(Base):
    __tablename__ = "account_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose in ('email_verification','password_reset')",
            name="ck_account_token_purpose",
        ),
        CheckConstraint("expires_at > created_at", name="ck_account_token_expiry"),
        CheckConstraint(
            "consumed_at is null or invalidated_at is null",
            name="ck_account_token_terminal_state",
        ),
        Index("ix_account_token_hash", "token_hash", unique=True),
        Index("ix_account_token_user_purpose", "user_id", "purpose", "created_at"),
        Index("ix_account_token_expiry", "expires_at"),
        Index(
            "uq_account_token_active_purpose",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=text("consumed_at is null and invalidated_at is null"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_user_agent: Mapped[str | None] = mapped_column(String(512))


class UploadedVideo(Base):
    __tablename__ = "uploaded_videos"
    __table_args__ = (
        UniqueConstraint("id", "owner_user_id", name="uq_uploaded_video_id_owner"),
        CheckConstraint("state in ('pending','available','failed')", name="ck_video_state"),
        CheckConstraint("row_version > 0", name="ck_video_row_version"),
        CheckConstraint(
            "source_checksum is null or source_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_video_checksum",
        ),
        Index("ix_video_owner_created", "owner_user_id", "created_at"),
        Index("ix_video_owner_checksum", "owner_user_id", "source_checksum"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    content_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["uploaded_video_id", "owner_user_id"],
            ["uploaded_videos.id", "uploaded_videos.owner_user_id"],
            name="fk_analysis_video_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["promoted_run_id", "id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_analysis_promoted_run",
            use_alter=True,
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "owner_user_id", name="uq_analysis_id_owner"),
        CheckConstraint(
            "state in ('pending','processing','completed','failed','cancelled')",
            name="ck_analysis_state",
        ),
        CheckConstraint("row_version > 0", name="ck_analysis_row_version"),
        CheckConstraint(
            "current_stage in "
            "('uploaded','inspected','calibrated','tracked','player_selected','analyzed')",
            name="ck_analysis_stage",
        ),
        Index("ix_analysis_owner_created", "owner_user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_video_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    job_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    promoted_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("id", "analysis_id", name="uq_run_id_analysis"),
        UniqueConstraint("analysis_id", "attempt_number", name="uq_run_analysis_attempt"),
        CheckConstraint(
            "state in ('queued','processing','completed','failed','cancelled','stale')",
            name="ck_run_state",
        ),
        CheckConstraint("row_version > 0", name="ck_run_row_version"),
        CheckConstraint("schema_version > 0", name="ck_run_schema_version"),
        CheckConstraint(
            "source_video_checksum is null or source_video_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_run_source_checksum",
        ),
        CheckConstraint(
            "configuration_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_run_configuration_fingerprint",
        ),
        Index(
            "uq_run_one_active",
            "analysis_id",
            unique=True,
            postgresql_where=text("state in ('queued','processing')"),
        ),
        Index("ix_run_stale_scan", "state", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="RESTRICT")
    )
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    source_video_checksum: Mapped[str | None] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    software_commit_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_build_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnalysisStateEvent(Base):
    __tablename__ = "analysis_state_events"
    __table_args__ = (
        CheckConstraint(
            "(subject_type='analysis' and analysis_run_id is null) or "
            "(subject_type='run' and analysis_run_id is not null)",
            name="ck_state_event_subject",
        ),
        Index("ix_state_event_analysis_created", "analysis_id", "created_at"),
        Index("ix_state_event_run_created", "analysis_run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analyses.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="RESTRICT")
    )
    previous_state: Mapped[str | None] = mapped_column(String(24))
    new_state: Mapped[str] = mapped_column(String(24), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256))
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_row_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "scope", "key_hash", name="uq_idempotency_owner_scope_key"
        ),
        CheckConstraint(
            "status in ('in_progress','completed','failed')", name="ck_idempotency_status"
        ),
        CheckConstraint("key_hash ~ '^[a-f0-9]{64}$'", name="ck_idempotency_key_hash"),
        CheckConstraint(
            "request_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_idempotency_request_fingerprint",
        ),
        Index("ix_idempotency_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "analysis_id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_artifact_run_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_artifact_analysis_owner",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "analysis_id", "storage_provider", "storage_key", name="uq_artifact_storage_key"
        ),
        CheckConstraint("size_bytes >= 0", name="ck_artifact_size"),
        CheckConstraint("checksum_sha256 ~ '^[a-f0-9]{64}$'", name="ck_artifact_checksum"),
        CheckConstraint(
            "state in ('pending','available','quarantined','deleted')",
            name="ck_artifact_state",
        ),
        Index("ix_artifact_owner_analysis", "owner_user_id", "analysis_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PlayerSelection(Base):
    __tablename__ = "player_selections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_run_id", "analysis_id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_player_selection_run_analysis",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_player_selection_analysis_owner",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_player_selection_current",
            "analysis_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(128))
    track_id: Mapped[int | None] = mapped_column(BigInteger)
    source_track_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
