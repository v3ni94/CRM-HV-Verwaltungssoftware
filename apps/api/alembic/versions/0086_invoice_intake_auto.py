"""invoice_intake_auto: M14-05 automatischer Belegeingang. Mandantenschalter
``tenant_settings.invoice_intake_auto`` (Standard aus) und die Markierungstabelle
``invoice_intake_auto_run`` (je Anhang höchstens ein extract_invoice-Lauf), Mandantentabelle mit
RLS (ADR 0002).

Revision ID: 0086
Revises: 0083
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0086"
down_revision: str | None = "0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("invoice_intake_auto_run",)


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column("invoice_intake_auto", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "invoice_intake_auto_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["message.id"]),
        sa.ForeignKeyConstraint(["task_run_id"], ["ai_task_run.id"]),
        sa.UniqueConstraint("tenant_id", "document_id"),
    )
    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("invoice_intake_auto_run")
    op.drop_column("tenant_settings", "invoice_intake_auto")
