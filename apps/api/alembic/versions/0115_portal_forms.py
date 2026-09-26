"""portal_form_template and portal_form_submission (14, M21-01, A56): configurable portal forms
per tenant; a submission creates a ticket and keeps the raw values for traceability.

Revision ID: 0115
Revises: 0112
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0115"
down_revision: str | None = "0112"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATE = "portal_form_template"
SUBMISSION = "portal_form_submission"


def _audit_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
    ]


def upgrade() -> None:
    op.create_table(
        TEMPLATE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000)),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("audience", sa.String(length=16), server_default="all", nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_portal_form_template_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_form_template")),
    )
    op.create_index("ix_portal_form_template_tenant", TEMPLATE, ["tenant_id", "active"])
    op.create_table(
        SUBMISSION,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_portal_form_submission_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["portal_form_template.id"],
            name=op.f("fk_portal_form_submission_template_id_portal_form_template"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["portal_account.id"],
            name=op.f("fk_portal_form_submission_account_id_portal_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["ticket.id"],
            name=op.f("fk_portal_form_submission_ticket_id_ticket"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portal_form_submission")),
    )
    op.create_index("ix_portal_form_submission_account", SUBMISSION, ["tenant_id", "account_id"])
    for table in (TEMPLATE, SUBMISSION):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in (SUBMISSION, TEMPLATE):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_portal_form_submission_account", table_name=SUBMISSION)
    op.drop_table(SUBMISSION)
    op.drop_index("ix_portal_form_template_tenant", table_name=TEMPLATE)
    op.drop_table(TEMPLATE)
