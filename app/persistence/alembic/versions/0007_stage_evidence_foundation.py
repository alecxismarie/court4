"""Add independent stage execution and immutable evidence metadata.

Revision ID: 0007_stage_evidence
Revises: 0006_auth_onboarding
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_stage_evidence"
down_revision: str | None = "0006_auth_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_stage_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=False),
        sa.Column("stage_type", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("is_optional", sa.Boolean(), nullable=False),
        sa.Column("shadow_mode", sa.Boolean(), nullable=False),
        sa.Column("configuration_fingerprint", sa.String(64), nullable=False),
        sa.Column("provenance_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "input_artifact_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "output_artifact_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("failure_category", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("unavailable_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempt_number > 0", name="ck_stage_execution_attempt"),
        sa.CheckConstraint(
            "configuration_fingerprint ~ '^[a-f0-9]{64}$'",
            name="ck_stage_execution_configuration_fingerprint",
        ),
        sa.CheckConstraint("row_version > 0", name="ck_stage_execution_row_version"),
        sa.CheckConstraint(
            "state in "
            "('queued','processing','completed','failed','cancelled','stale','unavailable')",
            name="ck_stage_execution_state",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_stage_execution_analysis_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_run_id", "analysis_id"],
            ["analysis_runs.id", "analysis_runs.analysis_id"],
            name="fk_stage_execution_run_analysis",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "analysis_id", name="uq_stage_execution_id_analysis"),
        sa.UniqueConstraint(
            "analysis_id",
            "stage_type",
            "attempt_number",
            name="uq_stage_execution_attempt",
        ),
    )
    op.create_index(
        "ix_stage_execution_owner_analysis",
        "analysis_stage_executions",
        ["owner_user_id", "analysis_id", "stage_type"],
    )
    op.create_index(
        "uq_stage_execution_one_active",
        "analysis_stage_executions",
        ["analysis_id", "stage_type"],
        unique=True,
        postgresql_where=sa.text("state in ('queued','processing')"),
    )

    op.create_table(
        "calibration_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.String(64), nullable=False),
        sa.Column("calibration_id", sa.String(128), nullable=False),
        sa.Column("calibration_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("verification_state", sa.String(24), nullable=False),
        sa.Column("verification_method", sa.String(64), nullable=False),
        sa.Column("reviewer_context", sa.String(256)),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "calibration_checksum_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_calibration_verification_checksum",
        ),
        sa.CheckConstraint("schema_version > 0", name="ck_calibration_verification_schema"),
        sa.CheckConstraint(
            "verification_state in ('verified','rejected')",
            name="ck_calibration_verification_state",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_calibration_verification_analysis_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_id",
            "calibration_id",
            "calibration_checksum_sha256",
            name="uq_calibration_verification_evidence",
        ),
    )
    op.create_index(
        "ix_calibration_verification_owner_analysis",
        "calibration_verifications",
        ["owner_user_id", "analysis_id"],
    )

    op.drop_constraint("uq_artifact_storage_key", "analysis_artifacts", type_="unique")
    op.add_column("analysis_artifacts", sa.Column("stage_execution_id", sa.Uuid()))
    op.add_column(
        "analysis_artifacts",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_foreign_key(
        "fk_artifact_stage_execution_analysis",
        "analysis_artifacts",
        "analysis_stage_executions",
        ["stage_execution_id", "analysis_id"],
        ["id", "analysis_id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_artifact_stage_execution",
        "analysis_artifacts",
        ["stage_execution_id", "created_at"],
    )
    op.create_index(
        "uq_artifact_current_storage",
        "analysis_artifacts",
        ["analysis_id", "storage_provider", "storage_key"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.alter_column("analysis_artifacts", "is_current", server_default=None)


def downgrade() -> None:
    # A downgrade is refused by PostgreSQL if multiple historical rows now share a
    # storage key. Operators must reconcile that evidence explicitly before rollback.
    op.drop_index("uq_artifact_current_storage", table_name="analysis_artifacts")
    op.drop_index("ix_artifact_stage_execution", table_name="analysis_artifacts")
    op.drop_constraint(
        "fk_artifact_stage_execution_analysis", "analysis_artifacts", type_="foreignkey"
    )
    op.drop_column("analysis_artifacts", "is_current")
    op.drop_column("analysis_artifacts", "stage_execution_id")
    op.create_unique_constraint(
        "uq_artifact_storage_key",
        "analysis_artifacts",
        ["analysis_id", "storage_provider", "storage_key"],
    )
    op.drop_index(
        "ix_calibration_verification_owner_analysis",
        table_name="calibration_verifications",
    )
    op.drop_table("calibration_verifications")
    op.drop_index("uq_stage_execution_one_active", table_name="analysis_stage_executions")
    op.drop_index("ix_stage_execution_owner_analysis", table_name="analysis_stage_executions")
    op.drop_table("analysis_stage_executions")
