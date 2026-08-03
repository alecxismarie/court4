"""Create the isolated Phase 1.8B0 persistence spike schema.

Revision ID: 0001_phase_1_8b0
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase_1_8b0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spike_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_label", sa.String(length=120), nullable=False),
        sa.Column("account_status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_status in ('active', 'disabled')",
            name="ck_spike_users_account_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_label"),
    )
    op.create_table(
        "spike_uploaded_videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_version > 0", name="ck_spike_video_row_version"),
        sa.CheckConstraint(
            "source_checksum is null or source_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_spike_video_checksum",
        ),
        sa.CheckConstraint(
            "state in ('pending', 'available', 'failed')",
            name="ck_spike_video_state",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["spike_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_spike_video_id_owner"),
    )
    op.create_index(
        "ix_spike_video_owner_created",
        "spike_uploaded_videos",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "spike_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_video_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("row_version > 0", name="ck_spike_analysis_row_version"),
        sa.CheckConstraint(
            "state in ('created', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_spike_analysis_state",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["spike_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["uploaded_video_id", "owner_user_id"],
            ["spike_uploaded_videos.id", "spike_uploaded_videos.owner_user_id"],
            name="fk_spike_analysis_video_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_spike_analysis_owner_created",
        "spike_analyses",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "spike_analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column(
            "attempt_number",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("previous_run_id", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("source_video_checksum", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("configuration_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("software_commit_identifier", sa.String(length=64), nullable=False),
        sa.Column("deployment_build_identifier", sa.String(length=128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_version > 0", name="ck_spike_run_row_version"),
        sa.CheckConstraint("schema_version > 0", name="ck_spike_run_schema_version"),
        sa.CheckConstraint(
            "configuration_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_spike_run_configuration_fingerprint",
        ),
        sa.CheckConstraint(
            "source_video_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_spike_run_source_checksum",
        ),
        sa.CheckConstraint(
            "state in ('queued', 'processing', 'completed', 'failed', 'cancelled', 'stale')",
            name="ck_spike_run_state",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["spike_analyses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["previous_run_id"], ["spike_analysis_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_number"),
    )
    op.create_index(
        "ix_spike_run_stale_scan",
        "spike_analysis_runs",
        ["state", "lease_expires_at"],
    )
    op.create_index(
        "uq_spike_run_one_active",
        "spike_analysis_runs",
        ["analysis_id"],
        unique=True,
        postgresql_where=sa.text("state in ('queued', 'processing')"),
    )
    op.create_table(
        "spike_analysis_state_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("previous_state", sa.String(length=24), nullable=True),
        sa.Column("new_state", sa.String(length=24), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("subject_row_version", sa.BigInteger(), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type in ('development', 'test', 'system')",
            name="ck_spike_event_actor_type",
        ),
        sa.CheckConstraint(
            "(subject_type = 'analysis' and analysis_run_id is null) or "
            "(subject_type = 'run' and analysis_run_id is not null)",
            name="ck_spike_event_subject",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["spike_analyses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"], ["spike_analysis_runs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_spike_event_analysis_created",
        "spike_analysis_state_events",
        ["analysis_id", "created_at"],
    )
    op.create_index(
        "ix_spike_event_run_created",
        "spike_analysis_state_events",
        ["analysis_run_id", "created_at"],
    )
    op.create_table(
        "spike_idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "key_hash ~ '^[a-f0-9]{64}$'",
            name="ck_spike_idempotency_key_hash",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_spike_idempotency_fingerprint",
        ),
        sa.CheckConstraint(
            "status in ('in_progress', 'completed', 'failed')",
            name="ck_spike_idempotency_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["spike_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "scope",
            "key_hash",
            name="uq_spike_idempotency_owner_scope_key",
        ),
    )
    op.create_index(
        "ix_spike_idempotency_expiry",
        "spike_idempotency_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_spike_idempotency_expiry", table_name="spike_idempotency_records")
    op.drop_table("spike_idempotency_records")
    op.drop_index("ix_spike_event_run_created", table_name="spike_analysis_state_events")
    op.drop_index("ix_spike_event_analysis_created", table_name="spike_analysis_state_events")
    op.drop_table("spike_analysis_state_events")
    op.drop_index("uq_spike_run_one_active", table_name="spike_analysis_runs")
    op.drop_index("ix_spike_run_stale_scan", table_name="spike_analysis_runs")
    op.drop_table("spike_analysis_runs")
    op.drop_index("ix_spike_analysis_owner_created", table_name="spike_analyses")
    op.drop_table("spike_analyses")
    op.drop_index("ix_spike_video_owner_created", table_name="spike_uploaded_videos")
    op.drop_table("spike_uploaded_videos")
    op.drop_table("spike_users")
