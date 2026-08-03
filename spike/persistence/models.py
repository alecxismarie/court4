from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "spike_users"
    __table_args__ = (
        CheckConstraint(
            "account_status in ('active', 'disabled')",
            name="ck_spike_users_account_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    identity_label: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    account_status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UploadedVideo(Base):
    __tablename__ = "spike_uploaded_videos"
    __table_args__ = (
        UniqueConstraint("id", "owner_user_id", name="uq_spike_video_id_owner"),
        CheckConstraint(
            "state in ('pending', 'available', 'failed')",
            name="ck_spike_video_state",
        ),
        CheckConstraint("row_version > 0", name="ck_spike_video_row_version"),
        CheckConstraint(
            "source_checksum is null or source_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_spike_video_checksum",
        ),
        Index("ix_spike_video_owner_created", "owner_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("spike_users.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Analysis(Base):
    __tablename__ = "spike_analyses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["uploaded_video_id", "owner_user_id"],
            ["spike_uploaded_videos.id", "spike_uploaded_videos.owner_user_id"],
            name="fk_spike_analysis_video_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "state in ('created', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_spike_analysis_state",
        ),
        CheckConstraint("row_version > 0", name="ck_spike_analysis_row_version"),
        Index("ix_spike_analysis_owner_created", "owner_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("spike_users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_video_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisRun(Base):
    __tablename__ = "spike_analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "state in ('queued', 'processing', 'completed', 'failed', 'cancelled', 'stale')",
            name="ck_spike_run_state",
        ),
        CheckConstraint("row_version > 0", name="ck_spike_run_row_version"),
        CheckConstraint("schema_version > 0", name="ck_spike_run_schema_version"),
        CheckConstraint(
            "source_video_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_spike_run_source_checksum",
        ),
        CheckConstraint(
            "configuration_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_spike_run_configuration_fingerprint",
        ),
        Index(
            "uq_spike_run_one_active",
            "analysis_id",
            unique=True,
            postgresql_where=text("state in ('queued', 'processing')"),
        ),
        Index("ix_spike_run_stale_scan", "state", "lease_expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("spike_analyses.id", ondelete="RESTRICT"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("spike_analysis_runs.id", ondelete="RESTRICT")
    )
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    source_video_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AnalysisStateEvent(Base):
    __tablename__ = "spike_analysis_state_events"
    __table_args__ = (
        CheckConstraint(
            "(subject_type = 'analysis' and analysis_run_id is null) or "
            "(subject_type = 'run' and analysis_run_id is not null)",
            name="ck_spike_event_subject",
        ),
        CheckConstraint(
            "actor_type in ('development', 'test', 'system')",
            name="ck_spike_event_actor_type",
        ),
        Index("ix_spike_event_analysis_created", "analysis_id", "created_at"),
        Index("ix_spike_event_run_created", "analysis_run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    analysis_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("spike_analyses.id", ondelete="RESTRICT"), nullable=False
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("spike_analysis_runs.id", ondelete="RESTRICT")
    )
    previous_state: Mapped[str | None] = mapped_column(String(24))
    new_state: Mapped[str] = mapped_column(String(24), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256))
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject_row_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IdempotencyRecord(Base):
    __tablename__ = "spike_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "scope",
            "key_hash",
            name="uq_spike_idempotency_owner_scope_key",
        ),
        CheckConstraint(
            "status in ('in_progress', 'completed', 'failed')",
            name="ck_spike_idempotency_status",
        ),
        CheckConstraint(
            "key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_spike_idempotency_key_hash",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_spike_idempotency_fingerprint",
        ),
        Index("ix_spike_idempotency_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("spike_users.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
