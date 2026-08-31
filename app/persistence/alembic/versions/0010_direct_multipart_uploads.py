"""Add durable direct multipart upload sessions.

Revision ID: 0010_direct_multipart
Revises: 0009_object_storage
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_direct_multipart"
down_revision: str | None = "0009_object_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("sport", sa.String(24), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("declared_size", sa.BigInteger(), nullable=False),
        sa.Column("logical_key", sa.String(1024), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_upload_id", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("part_size", sa.BigInteger(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(64)),
        sa.Column("verified_sha256", sa.String(64)),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("reanalyze", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "client_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result_payload", postgresql.JSONB()),
        sa.Column("failure_reason", sa.String(256)),
        sa.Column("row_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("aborted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status in ('initiated','uploading','completing','verifying','analyzing',"
            "'completed','aborted','failed','expired')",
            name="ck_upload_session_status",
        ),
        sa.CheckConstraint("declared_size > 0", name="ck_upload_session_declared_size"),
        sa.CheckConstraint("part_size > 0", name="ck_upload_session_part_size"),
        sa.CheckConstraint("part_count > 0", name="ck_upload_session_part_count"),
        sa.CheckConstraint("row_version > 0", name="ck_upload_session_row_version"),
        sa.CheckConstraint("sport in ('pickleball','padel')", name="ck_upload_session_sport"),
        sa.CheckConstraint(
            "expected_sha256 is null or expected_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_upload_session_expected_checksum",
        ),
        sa.CheckConstraint(
            "verified_sha256 is null or verified_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_upload_session_verified_checksum",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint(
            "owner_user_id", "idempotency_key_hash", name="uq_upload_session_owner_idempotency"
        ),
    )
    op.create_index(
        "ix_upload_session_owner_created",
        "upload_sessions",
        ["owner_user_id", "created_at"],
    )
    op.create_index("ix_upload_session_status_expiry", "upload_sessions", ["status", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_upload_session_status_expiry", table_name="upload_sessions")
    op.drop_index("ix_upload_session_owner_created", table_name="upload_sessions")
    op.drop_table("upload_sessions")
