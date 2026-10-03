"""AO04 / GAK-205: special_levy.revenue_account_id and reference_date as columns.

Values are taken over from snapshot.terms (AN19); snapshot.terms stays for the resolution
hash. FORCE RLS (special_levy, ledger_account) is lifted for the takeover only (0411).
Rows with an unknown account or a reference date after first_due keep NULL (logged).

Revision ID: 0457
Revises: 0456
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0457"
down_revision: str | None = "0456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOG = logging.getLogger("alembic.runtime.migration")
CK = "ck_special_levy_reference_date_order"
FK = "fk_special_levy_revenue_account_id_ledger_account"


def upgrade() -> None:
    op.add_column(
        "special_levy",
        sa.Column("revenue_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("special_levy", sa.Column("reference_date", sa.Date(), nullable=True))
    op.create_foreign_key(FK, "special_levy", "ledger_account", ["revenue_account_id"], ["id"])
    op.create_check_constraint(
        "reference_date_order",
        "special_levy",
        "reference_date IS NULL OR reference_date <= first_due",
    )
    bind = op.get_bind()
    op.execute("ALTER TABLE special_levy NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ledger_account NO FORCE ROW LEVEL SECURITY")
    accounts = bind.execute(
        sa.text(
            "UPDATE special_levy s SET revenue_account_id = a.id FROM ledger_account a "
            "WHERE s.revenue_account_id IS NULL "
            "AND (s.snapshot->'terms'->>'revenue_account_id') IS NOT NULL "
            "AND a.id::text = s.snapshot->'terms'->>'revenue_account_id' "
            "AND a.tenant_id = s.tenant_id"
        )
    ).rowcount
    dates = bind.execute(
        sa.text(
            "UPDATE special_levy SET reference_date = (snapshot->'terms'->>'reference_date')::date "
            "WHERE reference_date IS NULL "
            "AND (snapshot->'terms'->>'reference_date') ~ '^\\d{4}-\\d{2}-\\d{2}$' "
            "AND (snapshot->'terms'->>'reference_date')::date <= first_due"
        )
    ).rowcount
    skipped = bind.execute(
        sa.text(
            "SELECT count(*) FROM special_levy WHERE "
            "((snapshot->'terms'->>'revenue_account_id') IS NOT NULL "
            "AND revenue_account_id IS NULL) OR "
            "((snapshot->'terms'->>'reference_date') IS NOT NULL AND reference_date IS NULL)"
        )
    ).scalar_one()
    op.execute("ALTER TABLE ledger_account FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE special_levy FORCE ROW LEVEL SECURITY")
    LOG.warning("0457 special_levy: accounts=%s dates=%s skipped=%s", accounts, dates, skipped)


def downgrade() -> None:
    # The values stay in snapshot.terms, so dropping the columns loses nothing.
    op.drop_constraint(op.f(CK), "special_levy", type_="check")
    op.drop_constraint(op.f(FK), "special_levy", type_="foreignkey")
    op.drop_column("special_levy", "reference_date")
    op.drop_column("special_levy", "revenue_account_id")
