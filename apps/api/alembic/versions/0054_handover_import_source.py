"""handover_import_source: traceability and idempotency for the U-Protokoll data takeover
(M30 stage 4, operator request 25.09.2026). Each handover_* row gets an optional
``import_source`` ("uprotokoll:<source id>"), unique per tenant and table, so re-running the
same dump changes nothing (rule 0.1.7 domain tests, rule 0.1.12 idempotent imports).

Revision ID: 0054
Revises: 0053
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "handover_protocol",
    "handover_participant",
    "handover_meter",
    "handover_room",
    "handover_defect",
    "handover_key",
    "handover_item",
    "handover_note",
    "handover_signature",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("import_source", sa.String(length=100)))
        op.create_index(f"ix_{table}_import_source", table, ["import_source"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_import_source", table_name=table)
        op.drop_column(table, "import_source")
