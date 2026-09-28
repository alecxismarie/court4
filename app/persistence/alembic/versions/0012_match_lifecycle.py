"""Owner-scoped, durable whole-match deletion; existing analyses remain live."""

import sqlalchemy as sa
from alembic import op

revision = "0012_match_lifecycle"
down_revision = "0011_source_media"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("lifecycle_state", sa.String(24), nullable=False, server_default="live"),
    )
    op.add_column("analyses", sa.Column("deletion_requested_at", sa.DateTime(timezone=True)))
    op.add_column("analyses", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_analysis_lifecycle",
        "analyses",
        "lifecycle_state in ('live','deletion_pending','deleted')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM analyses WHERE lifecycle_state <> 'live')")
    ):
        raise RuntimeError("Cannot downgrade while match deletion records exist.")
    op.drop_constraint("ck_analysis_lifecycle", "analyses", type_="check")
    op.drop_column("analyses", "deleted_at")
    op.drop_column("analyses", "deletion_requested_at")
    op.drop_column("analyses", "lifecycle_state")
