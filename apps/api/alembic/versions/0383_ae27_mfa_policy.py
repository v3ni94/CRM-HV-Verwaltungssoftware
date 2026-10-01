"""AE27 (M2-04, M21-09): second factor policy per tenant (``auth_mfa_policy``).

One row per tenant (no row means the default policy ``voluntary`` without portal obligation,
the operator decision M2-01, ``mhvp.core.auth.mfa_policy``): ``crm_mode`` ``voluntary`` (column
default), ``all_staff`` or ``roles``, the role codes for ``roles`` and ``portal_required`` for the
portal role. RLS. Opens no gate.

Revision ID: 0383
Revises: 0382
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0383"
down_revision: str | None = "0382"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "auth_mfa_policy"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crm_mode", sa.String(length=16), nullable=False, server_default="voluntary"),
        sa.Column(
            "crm_role_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("portal_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.CheckConstraint(
            "crm_mode IN ('all_staff', 'roles', 'voluntary')",
            name=op.f("ck_auth_mfa_policy_crm_mode_values"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_auth_mfa_policy_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_mfa_policy")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_auth_mfa_policy_tenant_id")),
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
