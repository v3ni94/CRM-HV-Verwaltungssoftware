"""AI18 (GAH-101, GAH-111): technical preparation behind switches, conservative defaults.

* ``accounting_tax_settings.section_35a_basis``: invoice_date (default) or payment_date.
* ``section35a_certificate_log``: record per generated § 35a certificate, no lock.
* ``deposit_hint_setting``: non blocking deposit hint, default off.

Revision ID: 0443
Revises: 0442
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0443"
down_revision: str | None = "0442"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TAX = "accounting_tax_settings"
LOG = "section35a_certificate_log"
HINT = "deposit_hint_setting"


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]


def upgrade() -> None:
    op.add_column(
        TAX,
        sa.Column(
            "section_35a_basis",
            sa.String(16),
            server_default="invoice_date",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f(f"ck_{TAX}_section_35a_basis"),
        TAX,
        "section_35a_basis IN ('invoice_date', 'payment_date')",
    )
    op.create_table(
        LOG,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("output", sa.String(16), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("labor_total", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("output IN ('pdf', 'document')", name=op.f(f"ck_{LOG}_output")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{LOG}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f(f"fk_{LOG}_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name=op.f(f"fk_{LOG}_document_id_document")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{LOG}")),
    )
    op.create_index(
        "ix_section35a_certificate_log_contract_year", LOG, ["tenant_id", "contract_id", "year"]
    )
    for statement in tenant_rls_statements(LOG):
        op.execute(statement)
    op.create_table(
        HINT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        *_audit_columns(),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("factor_months", sa.Numeric(20, 8), server_default="3", nullable=False),
        sa.Column("max_installments", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "rent_payment_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("""'["rent"]'::jsonb"""),
            nullable=False,
        ),
        sa.CheckConstraint(
            "factor_months > 0 AND factor_months <= 24", name=op.f(f"ck_{HINT}_factor_months")
        ),
        sa.CheckConstraint(
            "max_installments BETWEEN 1 AND 12", name=op.f(f"ck_{HINT}_max_installments")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{HINT}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{HINT}")),
        sa.UniqueConstraint("tenant_id", name=op.f(f"uq_{HINT}_tenant_id")),
    )
    for statement in tenant_rls_statements(HINT):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(HINT):
        op.execute(statement)
    op.drop_table(HINT)
    for statement in drop_tenant_rls_statements(LOG):
        op.execute(statement)
    op.drop_index("ix_section35a_certificate_log_contract_year", table_name=LOG)
    op.drop_table(LOG)
    op.drop_constraint(op.f(f"ck_{TAX}_section_35a_basis"), TAX, type_="check")
    op.drop_column(TAX, "section_35a_basis")
