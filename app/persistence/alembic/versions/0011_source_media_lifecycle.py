"""Extend the existing video lifecycle for media-only deletion.

Revision ID: 0011_source_media
Revises: 0010_direct_multipart
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_source_media"
down_revision = "0010_direct_multipart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_video_state", "uploaded_videos", type_="check")
    op.create_check_constraint(
        "ck_video_state",
        "uploaded_videos",
        "state in ('pending','available','failed','deleting','deleted')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM uploaded_videos WHERE state IN ('deleting','deleted'))"
        )
    ):
        raise RuntimeError("Cannot downgrade while media deletion records exist.")
    op.drop_constraint("ck_video_state", "uploaded_videos", type_="check")
    op.create_check_constraint(
        "ck_video_state", "uploaded_videos", "state in ('pending','available','failed')"
    )
