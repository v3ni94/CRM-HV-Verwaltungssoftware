"""Structured record links on chat answers (assistant platform lookup).

``ai_message.links`` keeps the links the platform lookup produced for an assistant answer
(type, id, label, CRM href, short detail). The links come from deterministic, permission checked
queries in the caller's session, never from the model, and stay with the message as part of the
conversation log (audit). Existing rows get an empty list.

Revision ID: 0223
Revises: 0222
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0223"
down_revision: str | None = "0222"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_message",
        sa.Column(
            "links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_message", "links")
