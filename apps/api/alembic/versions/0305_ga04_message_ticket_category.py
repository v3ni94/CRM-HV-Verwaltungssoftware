"""Message delivery fields and ticket category catalog link (GA04-08, GA04-09).

* ``message.delivered_at`` / ``read_at`` / ``provider_message_id`` (spec 6.6 message);
  ``provider_message_id`` is backfilled from ``gmail_message_id``.
* ``ticket.category_id`` references ``ticket_template.id`` (the category catalog), set by a
  trigger from the free text ``category``; the text stays as fallback.

Revision ID: 0305
Revises: 0304
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0305"
down_revision: str | None = "0304"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("provider_message_id", sa.String(255), nullable=True))
    op.execute(
        "UPDATE message SET provider_message_id = gmail_message_id "
        "WHERE gmail_message_id IS NOT NULL"
    )
    op.add_column(
        "ticket",
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ticket_template.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE ticket t SET category_id = tt.id FROM ticket_template tt "
        "WHERE tt.tenant_id = t.tenant_id AND tt.category = t.category"
    )
    op.execute(
        """
        CREATE FUNCTION ticket_set_category_id() RETURNS trigger AS $$
        BEGIN
            IF NEW.category IS NULL THEN
                NEW.category_id := NULL;
            ELSIF TG_OP = 'INSERT' AND NEW.category_id IS NOT NULL THEN
                RETURN NEW;
            ELSIF TG_OP = 'INSERT' OR NEW.category IS DISTINCT FROM OLD.category THEN
                NEW.category_id := (
                    SELECT tt.id FROM ticket_template tt
                    WHERE tt.tenant_id = NEW.tenant_id AND tt.category = NEW.category
                );
            END IF;
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_ticket_category_id BEFORE INSERT OR UPDATE OF category ON ticket "
        "FOR EACH ROW EXECUTE FUNCTION ticket_set_category_id()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ticket_category_id ON ticket")
    op.execute("DROP FUNCTION IF EXISTS ticket_set_category_id()")
    op.drop_column("ticket", "category_id")
    op.drop_column("message", "provider_message_id")
    op.drop_column("message", "read_at")
    op.drop_column("message", "delivered_at")
