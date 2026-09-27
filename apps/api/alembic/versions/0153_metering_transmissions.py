"""Messdienstleister, controlled write workflows (master prompt Messdienstleister section 12,
cases 11 and 12): ``metering_transmission`` keeps every checked data set of the user and role
submission (On-Site Roles 2.0) and of the billing input workflow with its payload fingerprint,
validation result, diff against the last order, release and order protocol (user, time, data
version, provider answer). Tenant table with RLS (ADR 0002).

Revision ID: 0153
Revises: 0152
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0153"
down_revision: str | None = "0152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "metering_transmission"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("property_assignment_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("assignment_version", sa.Integer(), nullable=False),
        sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diff", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("released_by", sa.UUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warnings_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("ordered_by", sa.UUID(), nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=128), nullable=True),
        sa.Column("provider_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("log", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
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
        sa.CheckConstraint(
            "kind IN ('roles', 'billing_input')", name=op.f("ck_metering_transmission_kind")
        ),
        sa.CheckConstraint(
            "status IN ('checked', 'invalid', 'released', 'superseded', 'ordered', 'rejected', "
            "'unclear', 'failed')",
            name=op.f("ck_metering_transmission_status"),
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["metering_connection.id"],
            name=op.f("fk_metering_transmission_connection_id_metering_connection"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["property_assignment_id"],
            ["metering_property_assignment.id"],
            name=op.f(
                "fk_metering_transmission_property_assignment_id_metering_property_assignment"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_metering_transmission_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metering_transmission")),
    )
    op.create_index(
        "ix_metering_transmission_tenant_id_property_assignment_id",
        TABLE,
        ["tenant_id", "property_assignment_id"],
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_index("ix_metering_transmission_tenant_id_property_assignment_id", table_name=TABLE)
    op.drop_table(TABLE)
