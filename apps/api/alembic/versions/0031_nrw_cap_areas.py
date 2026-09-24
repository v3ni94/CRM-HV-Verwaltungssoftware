"""NRW cap areas from the MietSchVO NRW annex (M26-01) and rule notes after text check.

Revision ID: 0031
Revises: 0030
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTE = (
    "Wortlaut am 24.09.2026 auf gesetze-im-internet.de abgeglichen; Wert stimmt. "
    "Freigabe durch den Betreiber im Backend."
)


def upgrade() -> None:
    from mhvp.core.ids import uuid7
    from mhvp.letting.rentlaw import NRW_CAP_TOWNS, NRW_ORDINANCE, NRW_ORDINANCE_URL

    table = sa.table(
        "rent_cap_area",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("state", sa.String),
        sa.column("municipality", sa.String),
        sa.column("municipality_code", sa.String),
        sa.column("cap_percent", sa.Numeric),
        sa.column("valid_from", sa.Date),
        sa.column("valid_to", sa.Date),
        sa.column("source", sa.Text),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid7(),
                "state": "NW",
                "municipality": town,
                "municipality_code": None,
                "cap_percent": Decimal("15"),
                "valid_from": date(2025, 3, 1),
                "valid_to": date(2030, 2, 28),
                "source": f"{NRW_ORDINANCE}; {NRW_ORDINANCE_URL}",
            }
            for town in NRW_CAP_TOWNS
        ],
    )
    op.execute(
        sa.text("UPDATE rent_law_rule SET note = :note WHERE status = 'draft'").bindparams(
            note=NOTE
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM rent_cap_area WHERE source LIKE 'MietSchVO NRW vom 28.01.2025%'")
