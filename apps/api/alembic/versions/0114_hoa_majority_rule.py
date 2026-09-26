"""hoa_majority_rule: majority rules per subject kind with optional community override, subject
kind and stored majority check on resolutions (M25-01).

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).

Revision ID: 0114
Revises: 0108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0114"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("hoa_majority_rule",)


def upgrade() -> None:
    op.create_table(
        "hoa_majority_rule",
        sa.Column("legal_entity_id", sa.UUID(), nullable=True),
        sa.Column("subject_kind", sa.String(length=32), nullable=False),
        sa.Column("majority_type", sa.String(length=16), nullable=False),
        sa.Column("custom_numerator", sa.Integer(), nullable=True),
        sa.Column("custom_denominator", sa.Integer(), nullable=True),
        sa.Column("counting_basis", sa.String(length=8), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
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
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_hoa_majority_rule_legal_entity_id_legal_entity"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_hoa_majority_rule_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hoa_majority_rule")),
    )
    op.add_column("resolution", sa.Column("subject_kind", sa.String(length=32), nullable=True))
    op.add_column(
        "resolution",
        sa.Column("majority_check", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_column("resolution", "majority_check")
    op.drop_column("resolution", "subject_kind")
    op.drop_table("hoa_majority_rule")
