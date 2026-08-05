"""Persist the focused first-time player onboarding state.

Revision ID: 0006_auth_onboarding
Revises: 0005_account_security
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_auth_onboarding"
down_revision: str | None = "0005_account_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(36), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
