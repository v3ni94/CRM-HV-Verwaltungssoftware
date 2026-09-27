"""contracts: P1 additions (Ergänzung CRM section 4.5, AP3).

Adds ``contract.move_in_on`` and ``contract.move_out_on`` (calendar dates of the physical
move), ``sepa_mandate.payment_type_codes`` (JSON list of payment types the mandate covers,
empty = all) and ``sepa_mandate.exclude_special_levy``, the table
``contract_allocation_value`` (contract related allocation key values with period, periods per
contract and key never overlap) and the table ``contract_termination_reading`` (meter readings
recorded with a termination, linked to the ``meter_reading`` row they created). New tables get
tenant RLS (ADR 0002). Recording only: no postings, no collection, G1 to G3 stay closed.

Revision ID: 0150
Revises: 0149
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0150"
down_revision: str | None = "0149"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("contract_allocation_value", "contract_termination_reading")


def _audit_columns() -> list[sa.Column[Any]]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column("contract", sa.Column("move_in_on", sa.Date(), nullable=True))
    op.add_column("contract", sa.Column("move_out_on", sa.Date(), nullable=True))
    op.add_column(
        "sepa_mandate",
        sa.Column(
            "payment_type_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "sepa_mandate",
        sa.Column(
            "exclude_special_levy",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_table(
        "contract_allocation_value",
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("allocation_key_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_audit_columns(),
        postgresql.ExcludeConstraint(
            (sa.column("contract_id"), "="),
            (sa.column("allocation_key_id"), "="),
            (sa.text("daterange(valid_from, valid_to, '[]')"), "&&"),
            using="gist",
            name="ex_contract_allocation_value_period",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_contract_allocation_value_period_order"),
        ),
        sa.ForeignKeyConstraint(
            ["allocation_key_id"],
            ["allocation_key.id"],
            name=op.f("fk_contract_allocation_value_allocation_key_id_allocation_key"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_contract_allocation_value_contract_id_contract"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_contract_allocation_value_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_allocation_value")),
    )
    op.create_index(
        op.f("ix_contract_allocation_value_allocation_key_id"),
        "contract_allocation_value",
        ["allocation_key_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contract_allocation_value_contract_id"),
        "contract_allocation_value",
        ["contract_id"],
        unique=False,
    )
    op.create_table(
        "contract_termination_reading",
        sa.Column("contract_id", sa.UUID(), nullable=False),
        sa.Column("meter_id", sa.UUID(), nullable=False),
        sa.Column("meter_reading_id", sa.UUID(), nullable=True),
        sa.Column("value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("read_at", sa.Date(), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name=op.f("fk_contract_termination_reading_contract_id_contract"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["meter_id"],
            ["meter.id"],
            name=op.f("fk_contract_termination_reading_meter_id_meter"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["meter_reading_id"],
            ["meter_reading.id"],
            name=op.f("fk_contract_termination_reading_meter_reading_id_meter_reading"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_contract_termination_reading_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contract_termination_reading")),
        sa.UniqueConstraint(
            "contract_id",
            "meter_id",
            name=op.f("uq_contract_termination_reading_contract_id_meter_id"),
        ),
    )
    op.create_index(
        op.f("ix_contract_termination_reading_contract_id"),
        "contract_termination_reading",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contract_termination_reading_meter_id"),
        "contract_termination_reading",
        ["meter_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_contract_termination_reading_meter_reading_id"),
        "contract_termination_reading",
        ["meter_reading_id"],
        unique=False,
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    op.drop_table("contract_termination_reading")
    op.drop_table("contract_allocation_value")
    op.drop_column("sepa_mandate", "exclude_special_levy")
    op.drop_column("sepa_mandate", "payment_type_codes")
    op.drop_column("contract", "move_out_on")
    op.drop_column("contract", "move_in_on")
