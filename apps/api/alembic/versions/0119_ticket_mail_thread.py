"""Ticket-Mailverlauf und Ticketnummer im Betreff (operator 26.09.2026, M19/M20):
``message`` erhält Kopie-Empfänger, bereinigtes HTML, die Kopfzeile ``References`` und den
letzten Versandfehler; ``ticket.number`` wird je Mandant eindeutig (Grundlage der Kennung
``TNR#<nummer>``, ``mhvp.tickets.tnr``). Keine neue Mandantentabelle, RLS bleibt unverändert.

Revision ID: 0119
Revises: 0118
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0119"
down_revision: str | None = "0118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message",
        sa.Column(
            "cc_addresses",
            postgresql.ARRAY(sa.String(length=320)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column("message", sa.Column("body_html", sa.Text(), nullable=True))
    op.add_column("message", sa.Column("references_header", sa.Text(), nullable=True))
    op.add_column("message", sa.Column("send_error", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_ticket_tenant_number", "ticket", ["tenant_id", "number"])


def downgrade() -> None:
    op.drop_constraint("uq_ticket_tenant_number", "ticket", type_="unique")
    op.drop_column("message", "send_error")
    op.drop_column("message", "references_header")
    op.drop_column("message", "body_html")
    op.drop_column("message", "cc_addresses")
