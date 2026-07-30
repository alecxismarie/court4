"""Align uploaded-video metadata with its non-null mapping contract.

Revision ID: 0003_metadata_payload_contract
Revises: 0002_exact_duplicate_video
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_metadata_payload_contract"
down_revision = "0002_exact_duplicate_video"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE uploaded_videos
        SET metadata_payload = '{}'::jsonb
        WHERE metadata_payload IS NULL
        """
    )
    op.alter_column(
        "uploaded_videos",
        "metadata_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def downgrade() -> None:
    op.alter_column(
        "uploaded_videos",
        "metadata_payload",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )
