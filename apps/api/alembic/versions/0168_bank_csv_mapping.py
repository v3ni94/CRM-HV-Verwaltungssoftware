"""Bank specific CSV import (M11-02): ``bank_csv_mapping`` stores a user defined column
mapping per account for the generic CSV import path (recognised bank formats need none).

Revision ID: 0168
Revises: 0167
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0168"
down_revision: str | None = "0167"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "bank_csv_mapping"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in inspector.get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("property_bank_account_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["property_bank_account_id"],
            ["property_bank_account.id"],
            name=op.f("fk_bank_csv_mapping_property_bank_account_id_property_bank_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_bank_csv_mapping_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bank_csv_mapping")),
    )
    op.create_index(
        op.f("ix_bank_csv_mapping_property_bank_account_id"),
        TABLE,
        ["property_bank_account_id"],
    )
    op.create_index(
        "uq_bank_csv_mapping_account_label",
        TABLE,
        ["tenant_id", "property_bank_account_id", "label"],
        unique=True,
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
