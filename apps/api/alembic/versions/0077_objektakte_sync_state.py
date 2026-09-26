"""objektakte_sync_state, objektakte_source_deletion: M35 Stufe 5 (paralleler Betrieb,
täglicher Differenzimport, docs/plans/M35-objektakte-uebernahme.md section 4). Per tenant
water mark, switch, export path and last report of the differential import, plus markers for
source rows a complete export no longer contains (never a physical delete, rule 0.1.7).

Revision ID: 0077
Revises: 0076
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0077"
down_revision: str | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_TENANT_TABLES = ("objektakte_sync_state", "objektakte_source_deletion")

_SYNC_STATUS = postgresql.ENUM("never", "ok", "failed", name="objektakte_sync_status")


def _base_columns() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
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
    ]


def upgrade() -> None:
    _SYNC_STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "objektakte_sync_state",
        *_base_columns(),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dump_path", sa.String(length=500)),
        sa.Column("last_source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_status",
            postgresql.ENUM(
                "never", "ok", "failed", name="objektakte_sync_status", create_type=False
            ),
            nullable=False,
            server_default="never",
        ),
        sa.Column("last_report", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("last_error", sa.String(length=1000)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_table(
        "objektakte_source_deletion",
        *_base_columns(),
        sa.Column("source_table", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("target_table", sa.String(length=64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "source_table", "source_id"),
    )

    for table in _NEW_TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_NEW_TENANT_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)

    op.drop_table("objektakte_source_deletion")
    op.drop_table("objektakte_sync_state")
    _SYNC_STATUS.drop(op.get_bind(), checkfirst=True)
