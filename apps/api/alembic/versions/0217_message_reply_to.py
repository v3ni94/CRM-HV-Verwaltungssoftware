"""``message.reply_to`` (operator 27.09.2026, Antworten mit An/Cc): Kopfzeile ``Reply-To`` der
eingehenden Mail, getrennt von ``from_address``, damit der Antwortentwurf bei abweichender
Reply-To-Adresse dorthin adressiert statt an den Absender. Idempotent: die Spalte wird nur
angelegt, wenn sie fehlt.

Revision ID: 0217
Revises: 0216
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0217"
down_revision: str | None = "0216"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "message"
COLUMN = "reply_to"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN not in existing:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(320), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN in existing:
        op.drop_column(TABLE, COLUMN)
