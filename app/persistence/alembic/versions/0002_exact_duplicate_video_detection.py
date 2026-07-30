"""Add the owner-scoped uploaded-video checksum lookup index.

Revision ID: 0002_exact_duplicate_video
Revises: 0001_phase_1_8b
Create Date: 2026-07-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_exact_duplicate_video"
down_revision: str | None = "0001_phase_1_8b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_video_owner_checksum",
        "uploaded_videos",
        ["owner_user_id", "source_checksum"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_owner_checksum", table_name="uploaded_videos")
