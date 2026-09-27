"""calendar_entry: source, category, reminders and recurrence of generated appointments
(P1 AP7, spec 4.10 and B.30).

Appointments are generated deterministically from date fields of the master data (meter
calibration, energy certificate, contract end, move in and out, maintenance, follow up,
owners' meeting, ticket deadline) by the deadline job. Such entries have no owner
(``owner_user_id`` becomes nullable), carry ``source_type``/``source_id`` (the row they were
derived from) and ``category`` (the deadline kind), ``reminders`` (codes of B.30) and an
optional ``recurrence``. A partial unique index keeps one generated entry per source and
category; manual entries (owner set) are not restricted. The table keeps its tenant RLS;
the new columns inherit it. The Google Calendar link table ``calendar_event`` is unchanged.

Revision ID: 0151
Revises: 0150
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0151"
down_revision: str | None = "0150"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "calendar_entry"


def upgrade() -> None:
    op.alter_column(TABLE, "owner_user_id", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        TABLE,
        sa.Column(
            "source_type", sa.String(length=64), nullable=False, server_default=sa.text("'manual'")
        ),
    )
    op.add_column(TABLE, sa.Column("source_id", sa.UUID(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "category",
            sa.String(length=48),
            nullable=False,
            server_default=sa.text("'appointment'"),
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "reminders",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        TABLE, sa.Column("recurrence", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_index(
        "ix_calendar_entry_source", TABLE, ["tenant_id", "source_type", "source_id"], unique=False
    )
    op.create_index(
        "uq_calendar_entry_generated",
        TABLE,
        ["tenant_id", "source_type", "source_id", "category"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_calendar_entry_generated", table_name=TABLE)
    op.drop_index("ix_calendar_entry_source", table_name=TABLE)
    # Generated entries have no owner and cannot survive the NOT NULL constraint. The table
    # forces row level security (ADR 0002); without a tenant context the owner would delete
    # no rows, so the force is lifted for the fix and restored afterwards.
    op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM calendar_entry WHERE owner_user_id IS NULL")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    op.drop_column(TABLE, "recurrence")
    op.drop_column(TABLE, "reminders")
    op.drop_column(TABLE, "category")
    op.drop_column(TABLE, "source_id")
    op.drop_column(TABLE, "source_type")
    op.alter_column(TABLE, "owner_user_id", existing_type=sa.UUID(), nullable=False)
