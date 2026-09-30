"""Acceptance record of the migration per property (13.1, M8-09).

``migration_acceptance``: scope of the check, responsible persons, non migratable data,
fallback plan and archive concept; signed records are never changed. RLS.

Revision ID: 0268
Revises: 0267
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0268"
down_revision: str | None = "0267"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "migration_acceptance"


def _stamp(name: str) -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _text(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.Text(), nullable=False, server_default=sa.text("''"))


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uid, nullable=False),
        sa.Column("tenant_id", uid, nullable=False),
        _stamp("created_at"),
        _stamp("updated_at"),
        sa.Column("created_by", uid, nullable=True),
        sa.Column("updated_by", uid, nullable=True),
        sa.Column("property_id", uid, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        _text("review_scope"),
        sa.Column(
            "responsible_persons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        _text("non_migratable_data"),
        _text("fallback_plan"),
        _text("archive_concept"),
        sa.Column("reconciliation_report_id", uid, nullable=True),
        sa.Column("signed_by", uid, nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_migration_acceptance_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_migration_acceptance_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_report_id"],
            ["migration_reconciliation_report.id"],
            name=op.f(
                "fk_migration_acceptance_reconciliation_report_id_migration_reconciliation_report"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_migration_acceptance")),
    )
    op.create_index("ix_migration_acceptance_property", TABLE, ["tenant_id", "property_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
