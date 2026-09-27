"""E-Mail-Signatur je Nutzer (operator 27.09.2026): ``membership.position`` und
``membership.phone`` (Freitext, Katalog in ``mhvp.communication.signatures``) sowie
``tenant_settings.position_catalogue_extra`` (manuell angelegte Positionen) und
``tenant_settings.signature_template`` (Vorlage mit Platzhaltern, leer = Standard aus den
Firmendaten). Idempotent: every column is checked before it is added.

Revision ID: 0215
Revises: 0214
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0215"
down_revision: str | None = "0214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: dict[str, list[sa.Column[Any]]] = {
    "membership": [
        sa.Column("position", sa.String(120), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
    ],
    "tenant_settings": [
        sa.Column(
            "position_catalogue_extra",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "signature_template",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    ],
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, columns in _COLUMNS.items():
        if not inspector.has_table(table):
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name in existing:
                op.drop_column(table, column.name)
