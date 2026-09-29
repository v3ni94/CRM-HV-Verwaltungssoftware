"""Handover protocol: link a protocol meter row to the meter reading it was taken over into.

``handover_meter.meter_reading_id`` records which ``meter_reading`` was created from the
protocol row by the action "Zählerstände übernehmen" (Package F, handbook Mieterwechsel).
The link makes the takeover idempotent (a row with a reading is never taken over again) and
keeps the source reference from the reading back to the protocol. No new table, so no new RLS
statements; ``handover_meter`` keeps its tenant policy.

Revision ID: 0231
Revises: 0230
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0231"
down_revision: str | None = "0230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "handover_meter",
        sa.Column(
            "meter_reading_id",
            sa.UUID(),
            sa.ForeignKey("meter_reading.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_handover_meter_meter_reading_id", "handover_meter", ["meter_reading_id"])


def downgrade() -> None:
    op.drop_index("ix_handover_meter_meter_reading_id", table_name="handover_meter")
    op.drop_column("handover_meter", "meter_reading_id")
