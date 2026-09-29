"""Prozessflows für Tickets (Regel M19-11, Betreiberauftrag 29.09.2026).

``ticket_template`` gets the flow definition of a process catalogue entry (``process_code``,
``responsible_role``, ``required_links``, ``deadline_type_codes``, ``document_kinds``);
``ticket`` gets the applied process (``process_code``, ``flow``). Existing tables only, RLS
of both tables stays as it is. At most one template per tenant and process code.

Revision ID: 0235
Revises: 0223
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0235"
down_revision: str | None = "0223"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb_list(name: str) -> sa.Column[object]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )


def upgrade() -> None:
    op.add_column("ticket_template", sa.Column("process_code", sa.String(32), nullable=True))
    op.add_column("ticket_template", sa.Column("responsible_role", sa.String(63), nullable=True))
    op.add_column("ticket_template", _jsonb_list("required_links"))
    op.add_column("ticket_template", _jsonb_list("deadline_type_codes"))
    op.add_column("ticket_template", _jsonb_list("document_kinds"))
    op.create_index(
        "uq_ticket_template_process_code",
        "ticket_template",
        ["tenant_id", "process_code"],
        unique=True,
        postgresql_where=sa.text("process_code IS NOT NULL"),
    )
    op.add_column("ticket", sa.Column("process_code", sa.String(32), nullable=True))
    op.add_column(
        "ticket",
        sa.Column(
            "flow",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_ticket_process_code", "ticket", ["tenant_id", "process_code"])


def downgrade() -> None:
    op.drop_index("ix_ticket_process_code", table_name="ticket")
    op.drop_column("ticket", "flow")
    op.drop_column("ticket", "process_code")
    op.drop_index("uq_ticket_template_process_code", table_name="ticket_template")
    for column in (
        "document_kinds",
        "deadline_type_codes",
        "required_links",
        "responsible_role",
        "process_code",
    ):
        op.drop_column("ticket_template", column)
