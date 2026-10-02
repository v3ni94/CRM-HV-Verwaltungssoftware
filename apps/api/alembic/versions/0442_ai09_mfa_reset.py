"""AI09 (GAH-301): four eyes reset of the second factor, tenant switch default off.

* ``auth_mfa_reset_setting``: switch ``mfa_admin_reset_enabled`` (no row or false: off).
* ``auth_mfa_reset_request``: request, approval by a second person, rejection.

Revision ID: 0442
Revises: 0441
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0442"
down_revision: str | None = "0441"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTING = "auth_mfa_reset_setting"
REQUEST = "auth_mfa_reset_request"


def _base(table: str) -> list[sa.SchemaItem]:
    return [
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.create_table(
        SETTING,
        *_base(SETTING),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.UniqueConstraint("tenant_id", name=op.f(f"uq_{SETTING}_tenant_id")),
    )
    op.create_table(
        REQUEST,
        *_base(REQUEST),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="requested", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'rejected')",
            name=op.f(f"ck_{REQUEST}_auth_mfa_reset_status"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["membership.id"],
            name=op.f(f"fk_{REQUEST}_membership_id_membership"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_auth_mfa_reset_request_tenant", REQUEST, ["tenant_id", "created_at"])
    for table in (SETTING, REQUEST):
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    # Requests are evidence of a security action; the downgrade only exists for development.
    for table in (REQUEST, SETTING):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_index("ix_auth_mfa_reset_request_tenant", table_name=REQUEST)
    op.drop_table(REQUEST)
    op.drop_table(SETTING)
