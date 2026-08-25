"""Add durable sport identity and immutable run sport provenance.

Revision ID: 0008_sport_architecture
Revises: 0007_stage_evidence
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_sport_architecture"
down_revision: str | None = "0007_stage_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Court4 supported only Pickleball before this revision, so every pre-existing
    # analysis and run has known Pickleball provenance.
    op.add_column(
        "analyses",
        sa.Column("sport", sa.String(24), nullable=False, server_default="pickleball"),
    )
    op.create_check_constraint("ck_analysis_sport", "analyses", "sport in ('pickleball','padel')")
    op.execute(
        "UPDATE analyses SET sport = job_payload->>'sport' "
        "WHERE job_payload->>'sport' IN ('pickleball','padel')"
    )
    op.execute(
        "UPDATE analyses SET job_payload = jsonb_set(job_payload, '{sport}', "
        "'\"pickleball\"'::jsonb, true) WHERE NOT (job_payload ? 'sport')"
    )

    op.add_column(
        "analysis_runs",
        sa.Column("sport", sa.String(24), nullable=False, server_default="pickleball"),
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "sport_config_version",
            sa.String(64),
            nullable=False,
            server_default="pickleball-analysis-v1",
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "court_definition_version",
            sa.String(64),
            nullable=False,
            server_default="pickleball-court-v1",
        ),
    )
    op.create_check_constraint("ck_run_sport", "analysis_runs", "sport in ('pickleball','padel')")
    op.execute(
        "UPDATE analysis_runs AS runs SET "
        "sport = analyses.sport, "
        "sport_config_version = CASE analyses.sport "
        "WHEN 'padel' THEN 'padel-experimental-v1' ELSE 'pickleball-analysis-v1' END, "
        "court_definition_version = CASE analyses.sport "
        "WHEN 'padel' THEN 'padel-court-v1' ELSE 'pickleball-court-v1' END "
        "FROM analyses WHERE runs.analysis_id = analyses.id"
    )

    op.alter_column("analyses", "sport", server_default=None)
    op.alter_column("analysis_runs", "sport", server_default=None)
    op.alter_column("analysis_runs", "sport_config_version", server_default=None)
    op.alter_column("analysis_runs", "court_definition_version", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_run_sport", "analysis_runs", type_="check")
    op.drop_column("analysis_runs", "court_definition_version")
    op.drop_column("analysis_runs", "sport_config_version")
    op.drop_column("analysis_runs", "sport")
    # Preserve the compatibility payload so a later re-upgrade can restore Padel
    # identity instead of relabelling it as historical Pickleball.
    op.drop_constraint("ck_analysis_sport", "analyses", type_="check")
    op.drop_column("analyses", "sport")
