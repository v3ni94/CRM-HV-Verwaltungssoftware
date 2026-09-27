"""market_readiness: pricing structure without amounts (M27-01), G5 evidence list per tenant
(M27-02), tenant export requests with four eyes (M27-03). ``pricing_plan_item`` is a platform
table without RLS (5.3); ``g5_evidence`` and ``tenant_export_request`` carry ``tenant_id`` and
are tenant tables with RLS (ADR 0002).

Revision ID: 0199
Revises: 0198
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0199"
down_revision: str | None = "0198"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("pricing_plan_item", "g5_evidence", "tenant_export_request")
TENANT_TABLES = ("g5_evidence", "tenant_export_request")


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _base_columns() -> list[sa.Column[Any]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
    ]


def _has_rls(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = :name"), {"name": name}
        )
        .scalar()
    )


def upgrade() -> None:
    if not _has_table("pricing_plan_item"):
        op.create_table(
            "pricing_plan_item",
            *_base_columns(),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("code", sa.String(32), nullable=False, unique=True),
            sa.Column("label", sa.String(200), nullable=False),
            sa.Column("min_units", sa.Integer()),
            sa.Column("max_units", sa.Integer()),
            sa.Column("amount", sa.Numeric(14, 2)),
            sa.Column("unit", sa.String(16), nullable=False, server_default="unit_month"),
            sa.Column("trial_days", sa.Integer()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if not _has_table("g5_evidence"):
        op.create_table(
            "g5_evidence",
            *_base_columns(),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("code", sa.String(48), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="open"),
            sa.Column("document_id", postgresql.UUID(as_uuid=True)),
            sa.Column("note", sa.Text()),
            sa.Column("decided_by", postgresql.UUID(as_uuid=True)),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("tenant_id", "code", name="uq_g5_evidence_tenant_code"),
        )
    if not _has_table("tenant_export_request"):
        op.create_table(
            "tenant_export_request",
            *_base_columns(),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("purpose", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="requested"),
            sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("decided_by", postgresql.UUID(as_uuid=True)),
            sa.Column("decided_at", sa.DateTime(timezone=True)),
            sa.Column("comment", sa.Text()),
            sa.Column("downloads", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        )
        op.create_index(
            "ix_tenant_export_request_tenant", "tenant_export_request", ["tenant_id", "created_at"]
        )
    for table in TENANT_TABLES:
        if not _has_rls(table):
            for statement in tenant_rls_statements(table):
                op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        if _has_table(table):
            if table in TENANT_TABLES:
                for statement in drop_tenant_rls_statements(table):
                    op.execute(statement)
            op.drop_table(table)
