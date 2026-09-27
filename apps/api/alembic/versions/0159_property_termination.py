"""Property termination (operator 27.09.2026): ``property_termination`` records the end of
the management relationship (who gave notice, notice date, end of management, successor
manager and owner contacts, notice letter, note) and the reactivation by the superadmin.
Tenant table with RLS (ADR 0002); one open termination per property.

Revision ID: 0159
Revises: 0156
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0159"
down_revision: str | None = "0158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "property_termination"
TERMINATED_BY = postgresql.ENUM(
    "manager", "owner", "hoa", "other", name="property_terminated_by", create_type=False
)


def upgrade() -> None:
    TERMINATED_BY.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
        sa.Column("property_id", sa.UUID(), nullable=False),
        sa.Column("terminated_by", TERMINATED_BY, nullable=False),
        sa.Column("notice_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column(
            "previous_status",
            postgresql.ENUM(name="property_status", create_type=False),
            nullable=False,
        ),
        sa.Column("successor_manager_contact_id", sa.UUID(), nullable=True),
        sa.Column("successor_owner_contact_id", sa.UUID(), nullable=True),
        sa.Column("notice_document_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactivated_by_user_id", sa.UUID(), nullable=True),
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
            "effective_date >= notice_date", name=op.f("ck_property_termination_dates_ordered")
        ),
        sa.ForeignKeyConstraint(
            ["property_id"],
            ["property.id"],
            name=op.f("fk_property_termination_property_id_property"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["successor_manager_contact_id"],
            ["contact.id"],
            name=op.f("fk_property_termination_successor_manager_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["successor_owner_contact_id"],
            ["contact.id"],
            name=op.f("fk_property_termination_successor_owner_contact_id_contact"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["notice_document_id"],
            ["document.id"],
            name=op.f("fk_property_termination_notice_document_id_document"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_property_termination_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_property_termination")),
    )
    op.create_index(op.f("ix_property_termination_property_id"), TABLE, ["property_id"])
    op.create_index(
        op.f("ix_property_termination_successor_manager_contact_id"),
        TABLE,
        ["successor_manager_contact_id"],
    )
    op.create_index(
        op.f("ix_property_termination_successor_owner_contact_id"),
        TABLE,
        ["successor_owner_contact_id"],
    )
    op.create_index(
        op.f("ix_property_termination_notice_document_id"), TABLE, ["notice_document_id"]
    )
    op.create_index(
        "uq_property_termination_open",
        TABLE,
        ["tenant_id", "property_id"],
        unique=True,
        postgresql_where=sa.text("reactivated_at IS NULL"),
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    TERMINATED_BY.drop(op.get_bind(), checkfirst=True)
