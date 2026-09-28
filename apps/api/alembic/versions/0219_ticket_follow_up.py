"""Folgevorgang statt Wiedereröffnung (Betreiberentscheidung 28.09.2026, Regel M19-10).

``tenant_settings.ticket_reopen_window_days`` (Standard 30, 0 bis 3650): eine neue Mail zu
einem abgeschlossenen Ticket öffnet es nur wieder, wenn der Abschluss höchstens so viele
Kalendertage zurückliegt; sonst entsteht ein Folgeticket. ``ticket.follow_up_of_ticket_id``
verweist vom Folgeticket auf den Vorgänger; der partielle eindeutige Index lässt je Vorgänger
höchstens ein Folgeticket zu (Nachfolgekette statt Verzweigung, Schutz gegen doppelte
Folgetickets bei parallelem Eingang). Idempotent: Spalten und Index werden nur angelegt, wenn
sie fehlen.

Revision ID: 0219
Revises: 0217
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0219"
down_revision: str | None = "0217"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WINDOW = "ticket_reopen_window_days"
WINDOW_CHECK = "ck_tenant_settings_ticket_reopen_window_days_range"
FOLLOW_UP = "follow_up_of_ticket_id"
FOLLOW_UP_FK = "fk_ticket_follow_up_of_ticket_id_ticket"
FOLLOW_UP_INDEX = "uq_ticket_follow_up_of"


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if WINDOW not in _columns("tenant_settings"):
        op.add_column(
            "tenant_settings",
            sa.Column(WINDOW, sa.Integer(), nullable=False, server_default="30"),
        )
        op.create_check_constraint(WINDOW_CHECK, "tenant_settings", f"{WINDOW} BETWEEN 0 AND 3650")
    if FOLLOW_UP not in _columns("ticket"):
        op.add_column("ticket", sa.Column(FOLLOW_UP, sa.UUID(), nullable=True))
        op.create_foreign_key(FOLLOW_UP_FK, "ticket", "ticket", [FOLLOW_UP], ["id"])
        op.create_index(
            FOLLOW_UP_INDEX,
            "ticket",
            ["tenant_id", FOLLOW_UP],
            unique=True,
            postgresql_where=sa.text(f"{FOLLOW_UP} IS NOT NULL"),
        )


def downgrade() -> None:
    if FOLLOW_UP in _columns("ticket"):
        op.drop_index(FOLLOW_UP_INDEX, table_name="ticket")
        op.drop_constraint(FOLLOW_UP_FK, "ticket", type_="foreignkey")
        op.drop_column("ticket", FOLLOW_UP)
    if WINDOW in _columns("tenant_settings"):
        op.drop_constraint(WINDOW_CHECK, "tenant_settings", type_="check")
        op.drop_column("tenant_settings", WINDOW)
