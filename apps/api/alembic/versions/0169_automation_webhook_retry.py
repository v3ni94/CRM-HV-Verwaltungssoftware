"""M9-08 (A82, Masterprompt 15.2, module mhvp.automation): retry plan for failed rule webhook
deliveries. ``automation_webhook_delivery`` gets ``last_duration_ms`` (attempt duration),
``idempotency_key`` (stable ``Idempotency-Key`` header value across retries) and
``owner_notified`` (the rule owner is notified once a row goes ``dead`` after the retry plan
of 1, 5, 15, 60 minutes and 5 attempts is exhausted; status values are stored as free text in
the existing ``status`` column and need no schema change). Feature is on by default: it has no
money effect (docs/OPEN_QUESTIONS.md M9-08).

Revision ID: 0169
Revises: 0168
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0169"
down_revision: str | None = "0168"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "automation_webhook_delivery"


def _existing_columns(name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(name)}


def upgrade() -> None:
    existing = _existing_columns(TABLE)
    if "last_duration_ms" not in existing:
        op.add_column(TABLE, sa.Column("last_duration_ms", sa.Integer(), nullable=True))
    if "idempotency_key" not in existing:
        op.add_column(TABLE, sa.Column("idempotency_key", sa.String(length=64), nullable=True))
    if "owner_notified" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "owner_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )
    # Backfill: existing rows get a stable idempotency key derived from their id.
    op.execute(
        "UPDATE automation_webhook_delivery SET idempotency_key = id::text "
        "WHERE idempotency_key IS NULL"
    )


def downgrade() -> None:
    existing = _existing_columns(TABLE)
    if "owner_notified" in existing:
        op.drop_column(TABLE, "owner_notified")
    if "idempotency_key" in existing:
        op.drop_column(TABLE, "idempotency_key")
    if "last_duration_ms" in existing:
        op.drop_column(TABLE, "last_duration_ms")
