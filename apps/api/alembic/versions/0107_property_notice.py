"""property_notice: Schwarzes Brett je Objekt (14, M21-01, A54): notices of the management
with validity period, audience (tenant, owner, all), optional attachment document and end
marker. Tenant table with RLS (ADR 0002).

Revision ID: 0107
Revises: 0106
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0107"
down_revision: str | None = "0106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "property_notice"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("audience", sa.String(length=16), nullable=False, server_default="all"),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_property_notice_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_notice_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_property_notice_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "audience IN ('tenant', 'owner', 'all')", name="ck_property_notice_audience"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_property_notice_period"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_notice")),
    )
    op.create_index("ix_property_notice_property", TABLE, ["tenant_id", "property_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_property_notice_property", table_name=TABLE)
    op.drop_table(TABLE)
