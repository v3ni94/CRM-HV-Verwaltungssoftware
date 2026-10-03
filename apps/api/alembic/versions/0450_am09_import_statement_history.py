"""AM09: historical statements and resolutions of the import (GAJ-501).

Report types historical_statement and resolution of import_report_type; tables
migrated_statement and migrated_resolution with RLS. Filing and checking only, nothing posts.

Revision ID: 0450
Revises: 0449
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0450"
down_revision: str | None = "0449"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_REPORT_TYPES = ("historical_statement", "resolution")


def _uuid() -> postgresql.UUID:  # type: ignore[type-arg]
    return postgresql.UUID(as_uuid=True)


def _common() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "tenant_id", _uuid(), sa.ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("source", sa.String(40), nullable=False, server_default="immoware24"),
        sa.Column(
            "property_id",
            _uuid(),
            sa.ForeignKey("property.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def _tail() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "source_file_id",
            _uuid(),
            sa.ForeignKey("import_source_file.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
    ]


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in NEW_REPORT_TYPES:
            op.execute(f"ALTER TYPE import_report_type ADD VALUE IF NOT EXISTS '{value}'")
    op.create_table(
        "migrated_statement",
        *_common(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_number", sa.String(50), nullable=False, server_default=""),
        sa.Column("unit_id", _uuid(), sa.ForeignKey("unit.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient", sa.String(300), nullable=True),
        sa.Column("result_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("sent_on", sa.Date(), nullable=True),
        sa.Column("resolution_ref", sa.String(200), nullable=True),
        sa.Column("document_ref", sa.String(300), nullable=True),
        *_tail(),
        sa.UniqueConstraint(
            "tenant_id",
            "property_id",
            "kind",
            "period_start",
            "period_end",
            "unit_number",
            "version",
            name="uq_migrated_statement_tenant_id",
        ),
        sa.CheckConstraint("period_end >= period_start", name="ck_migrated_statement_period"),
        sa.CheckConstraint("version >= 1", name="ck_migrated_statement_version"),
        sa.CheckConstraint(
            "kind IN ('hoa_annual', 'hoa_budget', 'operating_costs', 'heating_costs', 'other')",
            name="ck_migrated_statement_kind",
        ),
    )
    op.create_index(
        "ix_migrated_statement_property",
        "migrated_statement",
        ["tenant_id", "property_id", "period_end"],
    )
    op.create_table(
        "migrated_resolution",
        *_common(),
        sa.Column("resolved_on", sa.Date(), nullable=False),
        sa.Column("item_number", sa.String(50), nullable=False),
        sa.Column("reference", sa.String(200), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("wording", sa.Text(), nullable=True),
        sa.Column("result", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("form", sa.String(16), nullable=False, server_default="unknown"),
        *_tail(),
        sa.UniqueConstraint(
            "tenant_id",
            "property_id",
            "resolved_on",
            "item_number",
            name="uq_migrated_resolution_tenant_id",
        ),
        sa.CheckConstraint(
            "result IN ('accepted', 'rejected', 'postponed', 'unknown')",
            name="ck_migrated_resolution_result",
        ),
        sa.CheckConstraint(
            "form IN ('meeting', 'circular', 'unknown')", name="ck_migrated_resolution_form"
        ),
    )
    op.create_index(
        "ix_migrated_resolution_property",
        "migrated_resolution",
        ["tenant_id", "property_id", "resolved_on"],
    )
    for table in ("migrated_statement", "migrated_resolution"):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    # Filed history has no financial effect (nothing posted); the drop is a development tool,
    # production restores from backup (runbook). Enum values stay (PostgreSQL cannot drop).
    op.drop_index("ix_migrated_resolution_property", table_name="migrated_resolution")
    op.drop_table("migrated_resolution")
    op.drop_index("ix_migrated_statement_property", table_name="migrated_statement")
    op.drop_table("migrated_statement")
