"""Ticket: Gebäudebezug, Beginn, Wiedervorlage, Sichtbarkeit externer Beiträge, archivierte
Kommentare.

Spec 6.6 (M19-03, M19-04, M19-07). Keine Daten werden verändert; Bestandstickets erhalten die
Sichtbarkeit "none" (keine externe Kommentierung), das bisherige Verhalten des Portals bleibt.

Revision ID: 0260
Revises: 0259
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0260"
down_revision: str | None = "0259"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ticket", sa.Column("building_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_ticket_building_id_building"), "ticket", "building", ["building_id"], ["id"]
    )
    op.add_column("ticket", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("ticket", sa.Column("follow_up_date", sa.Date(), nullable=True))
    op.add_column(
        "ticket",
        sa.Column(
            "external_comments", sa.String(16), nullable=False, server_default=sa.text("'none'")
        ),
    )
    op.add_column(
        "ticket",
        sa.Column(
            "external_attachments", sa.String(16), nullable=False, server_default=sa.text("'none'")
        ),
    )
    op.create_check_constraint(
        op.f("ck_ticket_external_comments"),
        "ticket",
        "external_comments IN ('none','to_manager','open')",
    )
    op.create_check_constraint(
        op.f("ck_ticket_external_attachments"),
        "ticket",
        "external_attachments IN ('none','initiator_only','open')",
    )
    op.create_index("ix_ticket_follow_up_date", "ticket", ["tenant_id", "follow_up_date"])
    op.add_column("ticket_comment", sa.Column("removed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "ticket_comment", sa.Column("removed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ticket_comment", "removed_by")
    op.drop_column("ticket_comment", "removed_at")
    op.drop_index("ix_ticket_follow_up_date", table_name="ticket")
    op.drop_constraint(op.f("ck_ticket_external_attachments"), "ticket", type_="check")
    op.drop_constraint(op.f("ck_ticket_external_comments"), "ticket", type_="check")
    op.drop_column("ticket", "external_attachments")
    op.drop_column("ticket", "external_comments")
    op.drop_column("ticket", "follow_up_date")
    op.drop_column("ticket", "start_date")
    op.drop_constraint(op.f("fk_ticket_building_id_building"), "ticket", type_="foreignkey")
    op.drop_column("ticket", "building_id")
