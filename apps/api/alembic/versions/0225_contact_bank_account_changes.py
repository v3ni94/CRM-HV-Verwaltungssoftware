"""contact_bank_account_changes: IBAN change as new row (``replaces_account_id``) and four
eyes change requests on existing contact bank accounts (``contact_bank_account_change``),
CRM screen Bankverbindungen am Kontakt (docs/rules/M3-02-sepa-mandate.md, M5-01 addendum).

The new table is a tenant table with RLS via mhvp.core.db.rls.tenant_rls_statements()
(ADR 0002). ``status`` reuses the existing enum ``bank_account_approval_status``.

Revision ID: 0225
Revises: 0224
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0225"
down_revision: str | None = "0224"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "contact_bank_account_change"


def upgrade() -> None:
    op.add_column(
        "contact_bank_account", sa.Column("replaces_account_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_contact_bank_account_replaces_account_id_contact_bank_account"),
        "contact_bank_account",
        "contact_bank_account",
        ["replaces_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    change_kind = postgresql.ENUM("end", name="contact_bank_account_change_kind")
    change_kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("bank_account_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM("end", name="contact_bank_account_change_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "approved",
                "rejected",
                name="bank_account_approval_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contact.id"],
            name=op.f(f"fk_{TABLE}_contact_id_contact"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_id"],
            ["contact_bank_account.id"],
            name=op.f(f"fk_{TABLE}_bank_account_id_contact_bank_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{TABLE}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(op.f(f"ix_{TABLE}_contact_id"), TABLE, ["contact_id"], unique=False)
    op.create_index(op.f(f"ix_{TABLE}_bank_account_id"), TABLE, ["bank_account_id"], unique=False)
    op.create_index(
        "ux_contact_bank_account_change_pending",
        TABLE,
        ["bank_account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    for stmt in tenant_rls_statements(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in drop_tenant_rls_statements(TABLE):
        op.execute(stmt)
    op.drop_index("ux_contact_bank_account_change_pending", table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_bank_account_id"), table_name=TABLE)
    op.drop_index(op.f(f"ix_{TABLE}_contact_id"), table_name=TABLE)
    op.drop_table(TABLE)
    op.execute("DROP TYPE IF EXISTS contact_bank_account_change_kind")
    op.drop_constraint(
        op.f("fk_contact_bank_account_replaces_account_id_contact_bank_account"),
        "contact_bank_account",
        type_="foreignkey",
    )
    op.drop_column("contact_bank_account", "replaces_account_id")
