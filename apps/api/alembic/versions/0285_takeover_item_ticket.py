"""Property takeover checklist: ticket per open point (R03, M7-01).

Revision ID: 0285
Revises: 0284
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0285"
down_revision: str | None = "0284"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "property_takeover_item",
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_property_takeover_item_ticket_id_ticket"),
        "property_takeover_item",
        "ticket",
        ["ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_property_takeover_item_ticket_id_ticket"),
        "property_takeover_item",
        type_="foreignkey",
    )
    op.drop_column("property_takeover_item", "ticket_id")
