"""AP02 (GAL-201, GAL-207): idempotent lexoffice export and live mode per integration.

lexoffice_export_link gets ``status`` (exported/unknown), ``idempotency_key`` and
``voucher_number``; ``lexoffice_id`` becomes nullable for the ``unknown`` state (a POST that
timed out). New tenant table integration_live_mode (RLS): one switch row per integration; no
row keeps today's behaviour (live allowed, no gate bound).

Revision ID: 0459
Revises: 0458
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0459"
down_revision: str | None = "0458"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:  # type: ignore[type-arg]
    return postgresql.UUID(as_uuid=True)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.add_column(
        "lexoffice_export_link",
        sa.Column("status", sa.String(16), nullable=False, server_default="exported"),
    )
    op.add_column(
        "lexoffice_export_link", sa.Column("idempotency_key", sa.String(64), nullable=True)
    )
    op.add_column(
        "lexoffice_export_link", sa.Column("voucher_number", sa.String(64), nullable=True)
    )
    op.alter_column("lexoffice_export_link", "lexoffice_id", nullable=True)
    op.create_check_constraint(
        "ck_lexoffice_export_link_status",
        "lexoffice_export_link",
        "status IN ('exported', 'unknown') AND (status = 'unknown' OR lexoffice_id IS NOT NULL)",
    )
    op.create_table(
        "integration_live_mode",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        sa.Column("integration", sa.String(32), nullable=False),
        sa.Column("live_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("required_gate", sa.String(4), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
        sa.CheckConstraint(
            "integration IN ('lexoffice', 'letterxpress', 'finapi')",
            name="ck_integration_live_mode_integration",
        ),
        sa.CheckConstraint(
            "required_gate IS NULL OR required_gate IN ('G1', 'G2', 'G3', 'G4', 'G5')",
            name="ck_integration_live_mode_gate",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_integration_live_mode"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_integration_live_mode_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "uq_integration_live_mode",
        "integration_live_mode",
        ["tenant_id", "integration"],
        unique=True,
    )
    for statement in tenant_rls_statements("integration_live_mode"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("integration_live_mode")
    op.drop_constraint("ck_lexoffice_export_link_status", "lexoffice_export_link", type_="check")
    # Rows without a Lexware id (unknown outcome) cannot survive the NOT NULL of 0458.
    op.execute("DELETE FROM lexoffice_export_link WHERE lexoffice_id IS NULL")
    op.alter_column("lexoffice_export_link", "lexoffice_id", nullable=False)
    op.drop_column("lexoffice_export_link", "voucher_number")
    op.drop_column("lexoffice_export_link", "idempotency_key")
    op.drop_column("lexoffice_export_link", "status")
