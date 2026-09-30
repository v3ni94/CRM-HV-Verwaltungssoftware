"""Welle 2, Paket P16: Kontakte, Objekte, Verträge (M4-05, M4-06, M5-01, M5-02, M5-06).

* ``property_bank_account.bank_connection_id``: link to the bank access (reference only).
* ``property.images``: image gallery as document references (JSONB list, default empty).
* ``contract.custom_fields``: user defined fields (JSONB object, default empty).
* ``contract_payment.revenue_account_id``: revenue account of the component (reference).
* ``deposit.documents``: document references of a deposit (JSONB list, default empty).

Only additive columns with defaults; existing rows stay valid and no RLS change is needed
(the tables already carry their policies).

Revision ID: 0265
Revises: 0264
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0265"
down_revision: str | None = "0264"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("property_bank_account", sa.Column("bank_connection_id", UUID, nullable=True))
    op.create_foreign_key(
        op.f("fk_property_bank_account_bank_connection_id_bank_connection"),
        "property_bank_account",
        "bank_connection",
        ["bank_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_property_bank_account_bank_connection_id"),
        "property_bank_account",
        ["bank_connection_id"],
    )
    op.add_column(
        "property",
        sa.Column("images", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "contract",
        sa.Column("custom_fields", _jsonb(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("contract_payment", sa.Column("revenue_account_id", UUID, nullable=True))
    op.create_foreign_key(
        op.f("fk_contract_payment_revenue_account_id_ledger_account"),
        "contract_payment",
        "ledger_account",
        ["revenue_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_contract_payment_revenue_account_id"),
        "contract_payment",
        ["revenue_account_id"],
    )
    op.add_column(
        "deposit",
        sa.Column("documents", _jsonb(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("deposit", "documents")
    op.drop_index(op.f("ix_contract_payment_revenue_account_id"), table_name="contract_payment")
    op.drop_constraint(
        op.f("fk_contract_payment_revenue_account_id_ledger_account"),
        "contract_payment",
        type_="foreignkey",
    )
    op.drop_column("contract_payment", "revenue_account_id")
    op.drop_column("contract", "custom_fields")
    op.drop_column("property", "images")
    op.drop_index(
        op.f("ix_property_bank_account_bank_connection_id"), table_name="property_bank_account"
    )
    op.drop_constraint(
        op.f("fk_property_bank_account_bank_connection_id_bank_connection"),
        "property_bank_account",
        type_="foreignkey",
    )
    op.drop_column("property_bank_account", "bank_connection_id")
