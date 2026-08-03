"""Add password authentication and rotating refresh sessions.

Revision ID: 0004_authentication_foundation
Revises: 0003_metadata_payload_contract
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_authentication_foundation"
down_revision: str | None = "0003_metadata_payload_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "identity_label",
        existing_type=sa.String(320),
        new_column_name="email",
        existing_nullable=False,
    )
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.Text(),
            nullable=False,
            server_default="!legacy-account-without-password",
        ),
    )
    op.alter_column("users", "password_hash", server_default=None)
    op.add_column(
        "users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE users
        SET email = lower(btrim(email)),
            account_status = 'disabled'
        """
    )

    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_family_id", sa.Uuid(), nullable=False),
        sa.Column("replaced_by_session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"], ["refresh_sessions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_refresh_session_user", "refresh_sessions", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_refresh_session_family", "refresh_sessions", ["token_family_id"]
    )
    op.create_index("ix_refresh_session_expiry", "refresh_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_session_expiry", table_name="refresh_sessions")
    op.drop_index("ix_refresh_session_family", table_name="refresh_sessions")
    op.drop_index("ix_refresh_session_user", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_hash")
    op.alter_column(
        "users",
        "email",
        existing_type=sa.String(320),
        new_column_name="identity_label",
        existing_nullable=False,
    )
