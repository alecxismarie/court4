"""Add verification, recovery, and account-security state.

Revision ID: 0005_account_security
Revises: 0004_authentication_foundation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_account_security"
down_revision: str | None = "0004_authentication_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "account_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_user_agent", sa.String(512), nullable=True),
        sa.CheckConstraint(
            "purpose in ('email_verification','password_reset')",
            name="ck_account_token_purpose",
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_account_token_expiry"),
        sa.CheckConstraint(
            "consumed_at is null or invalidated_at is null",
            name="ck_account_token_terminal_state",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_token_hash", "account_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_account_token_user_purpose",
        "account_tokens",
        ["user_id", "purpose", "created_at"],
    )
    op.create_index("ix_account_token_expiry", "account_tokens", ["expires_at"])
    op.create_index(
        "uq_account_token_active_purpose",
        "account_tokens",
        ["user_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("consumed_at is null and invalidated_at is null"),
    )


def downgrade() -> None:
    op.drop_index("uq_account_token_active_purpose", table_name="account_tokens")
    op.drop_index("ix_account_token_expiry", table_name="account_tokens")
    op.drop_index("ix_account_token_user_purpose", table_name="account_tokens")
    op.drop_index("ix_account_token_hash", table_name="account_tokens")
    op.drop_table("account_tokens")
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "email_verified_at")
