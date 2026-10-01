"""AE37 / Q08-01 (M8): stored column assignments per tenant and report type.

* ``import_column_assignment``: a file header (normalised key and original spelling) confirmed
  for a target field of a report type; ``target_field`` NULL means the header is deliberately
  not imported. The header heuristic of the import assistant proposes it first for the next
  file. Nothing is imported by an assignment itself.

Revision ID: 0393
Revises: 0392
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0393"
down_revision: str | None = "0392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "import_column_assignment"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "report_type",
            postgresql.ENUM(name="import_report_type", create_type=False),
            nullable=False,
        ),
        sa.Column("header_key", sa.String(200), nullable=False),
        sa.Column("header", sa.String(200), nullable=False),
        sa.Column("target_field", sa.String(63), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.UniqueConstraint(
            "tenant_id",
            "report_type",
            "header_key",
            name=op.f("uq_import_column_assignment_header"),
        ),
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
