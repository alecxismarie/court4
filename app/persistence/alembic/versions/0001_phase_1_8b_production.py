"""Create the Phase 1.8B production persistence schema.

Revision ID: 0001_phase_1_8b
Revises:
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase_1_8b"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("identity_label", sa.String(320), nullable=False),
        sa.Column("account_status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_status in ('active','disabled')", name="ck_user_account_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_label"),
    )
    op.create_table(
        "uploaded_videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("storage_provider", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(1024)),
        sa.Column("content_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("source_checksum", sa.String(64)),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_checksum is null or source_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_video_checksum",
        ),
        sa.CheckConstraint("row_version > 0", name="ck_video_row_version"),
        sa.CheckConstraint("state in ('pending','available','failed')", name="ck_video_state"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_uploaded_video_id_owner"),
    )
    op.create_index(
        "ix_video_owner_created",
        "uploaded_videos",
        ["owner_user_id", "created_at"],
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_video_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("current_stage", sa.String(32), nullable=False),
        sa.Column("job_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("promoted_run_id", sa.Uuid()),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "current_stage in "
            "('uploaded','inspected','calibrated','tracked','player_selected','analyzed')",
            name="ck_analysis_stage",
        ),
        sa.CheckConstraint("row_version > 0", name="ck_analysis_row_version"),
        sa.CheckConstraint(
            "state in ('pending','processing','completed','failed','cancelled')",
            name="ck_analysis_state",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["uploaded_video_id", "owner_user_id"],
            ["uploaded_videos.id", "uploaded_videos.owner_user_id"],
            name="fk_analysis_video_owner",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "owner_user_id", name="uq_analysis_id_owner"),
    )
    op.create_index("ix_analysis_owner_created", "analyses", ["owner_user_id", "created_at"])
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("previous_run_id", sa.Uuid()),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("source_video_checksum", sa.String(64)),
        sa.Column("pipeline_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("configuration_fingerprint", sa.String(64), nullable=False),
        sa.Column("software_commit_identifier", sa.String(64), nullable=False),
        sa.Column("deployment_build_identifier", sa.String(128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "configuration_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_run_configuration_fingerprint",
        ),
        sa.CheckConstraint("row_version > 0", name="ck_run_row_version"),
        sa.CheckConstraint("schema_version > 0", name="ck_run_schema_version"),
        sa.CheckConstraint(
            "source_video_checksum is null or source_video_checksum ~ '^[a-f0-9]{64}$'",
            name="ck_run_source_checksum",
        ),
        sa.CheckConstraint(
            "state in ('queued','processing','completed','failed','cancelled','stale')",
            name="ck_run_state",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["previous_run_id"], ["analysis_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "attempt_number", name="uq_run_analysis_attempt"),
        sa.UniqueConstraint("id", "analysis_id", name="uq_run_id_analysis"),
    )
    op.create_index("ix_run_stale_scan", "analysis_runs", ["state", "lease_expires_at"])
    op.create_index(
        "uq_run_one_active",
        "analysis_runs",
        ["analysis_id"],
        unique=True,
        postgresql_where=sa.text("state in ('queued','processing')"),
    )
    op.create_foreign_key(
        "fk_analysis_promoted_run",
        "analyses",
        "analysis_runs",
        ["promoted_run_id", "id"],
        ["id", "analysis_id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "analysis_state_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid()),
        sa.Column("previous_state", sa.String(24)),
        sa.Column("new_state", sa.String(24), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(256)),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("subject_row_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(subject_type='analysis' and analysis_run_id is null) or "
            "(subject_type='run' and analysis_run_id is not null)",
            name="ck_state_event_subject",
        ),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_state_event_analysis_created",
        "analysis_state_events",
        ["analysis_id", "created_at"],
    )
    op.create_index(
        "ix_state_event_run_created",
        "analysis_state_events",
        ["analysis_run_id", "created_at"],
    )
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("key_hash ~ '^[a-f0-9]{64}$'", name="ck_idempotency_key_hash"),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_idempotency_request_fingerprint",
        ),
        sa.CheckConstraint(
            "status in ('in_progress','completed','failed')",
            name="ck_idempotency_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "scope",
            "key_hash",
            name="uq_idempotency_owner_scope_key",
        ),
    )
    op.create_index("ix_idempotency_expiry", "idempotency_records", ["expires_at"])
    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid()),
        sa.Column("artifact_kind", sa.String(64), nullable=False),
        sa.Column("storage_provider", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer()),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("checksum_sha256 ~ '^[a-f0-9]{64}$'", name="ck_artifact_checksum"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_artifact_size"),
        sa.CheckConstraint(
            "state in ('pending','available','quarantined','deleted')",
            name="ck_artifact_state",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_artifact_analysis_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "analysis_id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_artifact_run_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "storage_provider",
            "storage_key",
            name="uq_artifact_storage_key",
        ),
    )
    op.create_index(
        "ix_artifact_owner_analysis",
        "analysis_artifacts",
        ["owner_user_id", "analysis_id"],
    )
    op.create_table(
        "player_selections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.String(128)),
        sa.Column("track_id", sa.BigInteger()),
        sa.Column(
            "source_track_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_player_selection_analysis_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "analysis_id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_player_selection_run_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_player_selection_current",
        "player_selections",
        ["analysis_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index("uq_player_selection_current", table_name="player_selections")
    op.drop_table("player_selections")
    op.drop_index("ix_artifact_owner_analysis", table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")
    op.drop_index("ix_idempotency_expiry", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_state_event_run_created", table_name="analysis_state_events")
    op.drop_index("ix_state_event_analysis_created", table_name="analysis_state_events")
    op.drop_table("analysis_state_events")
    op.drop_constraint("fk_analysis_promoted_run", "analyses", type_="foreignkey")
    op.drop_index("uq_run_one_active", table_name="analysis_runs")
    op.drop_index("ix_run_stale_scan", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_analysis_owner_created", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index("ix_video_owner_created", table_name="uploaded_videos")
    op.drop_table("uploaded_videos")
    op.drop_table("users")
