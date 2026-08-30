"""Add provider-neutral logical artifact locators.

Revision ID: 0009_object_storage
Revises: 0008_sport_architecture
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_object_storage"
down_revision: str | None = "0008_sport_architecture"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_artifacts", sa.Column("logical_key", sa.String(1024)))
    # Every legacy storage key is already the owner-scoped path exposed by the API.
    # Copy it verbatim; never reinterpret a local path as an S3 provider key.
    op.execute("UPDATE analysis_artifacts SET logical_key = storage_key")
    op.alter_column("analysis_artifacts", "logical_key", nullable=False)
    op.create_index(
        "uq_artifact_current_logical",
        "analysis_artifacts",
        ["analysis_id", "logical_key"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM analysis_artifacts WHERE storage_provider <> 'local'
            ) THEN
                RAISE EXCEPTION
                    'refusing object-storage downgrade while non-local artifact locators exist';
            END IF;
        END
        $$
        """
    )
    op.drop_index("uq_artifact_current_logical", table_name="analysis_artifacts")
    op.drop_column("analysis_artifacts", "logical_key")
