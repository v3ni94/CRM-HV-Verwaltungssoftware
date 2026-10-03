"""AP25 (AP10-02, AP10-03): partial unique indexes against a second payout or reminder.

* ``uq_deposit_settlement_released``: at most one released settlement per deposit.
* ``uq_dunning_case_sent_level``: at most one sent dunning case per account and level.

Existing rows are checked first; a violation aborts with a clear message (no data change).

Revision ID: 0469
Revises: 0468
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0469"
down_revision: str | None = "0468"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = (
    (
        "SELECT count(*) FROM (SELECT 1 FROM deposit_settlement WHERE status = 'released' "
        "GROUP BY tenant_id, deposit_id HAVING count(*) > 1) d",
        "deposit_settlement: mehrere freigegebene Abrechnungen je Kaution vorhanden",
    ),
    (
        "SELECT count(*) FROM (SELECT 1 FROM dunning_case WHERE status = 'sent' "
        "GROUP BY tenant_id, debtor_account_id, level HAVING count(*) > 1) d",
        "dunning_case: mehrere versendete Mahnfälle gleicher Stufe je Konto vorhanden",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    # The migrator is subject to FORCE ROW LEVEL SECURITY and would see no rows; it is
    # lifted for this transaction only and set again at once (pattern 0398/0411).
    for table in ("deposit_settlement", "dunning_case"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    try:
        for sql, message in CHECKS:
            found = int(bind.execute(sa.text(sql)).scalar() or 0)
            if found:
                raise RuntimeError(
                    f"0469 abgebrochen: {message} ({found} Gruppen). Bitte fachlich klären "
                    "und per Storno bereinigen, dann erneut migrieren."
                )
    finally:
        for table in ("deposit_settlement", "dunning_case"):
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.create_index(
        "uq_deposit_settlement_released",
        "deposit_settlement",
        ["tenant_id", "deposit_id"],
        unique=True,
        postgresql_where=sa.text("status = 'released'"),
    )
    op.create_index(
        "uq_dunning_case_sent_level",
        "dunning_case",
        ["tenant_id", "debtor_account_id", "level"],
        unique=True,
        postgresql_where=sa.text("status = 'sent'"),
    )


def downgrade() -> None:
    op.drop_index("uq_dunning_case_sent_level", table_name="dunning_case")
    op.drop_index("uq_deposit_settlement_released", table_name="deposit_settlement")
