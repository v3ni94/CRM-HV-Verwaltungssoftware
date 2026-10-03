"""AO03 (GAK-203): index clause, graduated steps and consumer price index.

contract.index_agreement JSONB (nullable), tenant table contract_graduated_step with RLS and
platform table consumer_price_index (no tenant, written only by platform administrators).
Nothing changes a rent; the daily job only drafts proposals with the switch on.

Revision ID: 0456
Revises: 0455
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import tenant_rls_statements

revision: str = "0456"
down_revision: str | None = "0455"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:  # type: ignore[type-arg]
    return postgresql.UUID(as_uuid=True)


def _ts(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.add_column("contract", sa.Column("index_agreement", postgresql.JSONB(), nullable=True))
    op.create_table(
        "contract_graduated_step",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        sa.Column("contract_id", _uuid(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("net", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("created_by", _uuid(), nullable=True),
        sa.Column("updated_by", _uuid(), nullable=True),
        sa.CheckConstraint("net > 0", name="ck_contract_graduated_step_net_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_contract_graduated_step"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_contract_graduated_step_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contract.id"],
            name="fk_contract_graduated_step_contract_id_contract",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_contract_graduated_step_contract_from",
        "contract_graduated_step",
        ["tenant_id", "contract_id", "valid_from"],
        unique=True,
    )
    for statement in tenant_rls_statements("contract_graduated_step"):
        op.execute(statement)
    op.create_table(
        "consumer_price_index",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("series", sa.String(40), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(20, 8), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("data_as_of", sa.Date(), nullable=False),
        sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("imported_by", _uuid(), nullable=True),
        _ts("imported_at"),
        sa.CheckConstraint("value > 0", name="ck_consumer_price_index_value_positive"),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month) = 1", name="ck_consumer_price_index_month_first_day"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consumer_price_index"),
        sa.UniqueConstraint("series", "month", name="uq_consumer_price_index_series_month"),
    )


def downgrade() -> None:
    # Development tool only: production restores from backup (runbook).
    op.drop_table("consumer_price_index")
    op.drop_index("uq_contract_graduated_step_contract_from", table_name="contract_graduated_step")
    op.drop_table("contract_graduated_step")
    op.drop_column("contract", "index_agreement")
