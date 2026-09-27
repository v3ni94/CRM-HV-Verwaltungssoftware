"""Circular resolution with a lowered majority (M25-02, docs/rules/M25-02-umlaufbeschluss.md).

``resolution`` gets ``allowed_majority`` (unanimous, simple), ``enabling_resolution_id`` (the
prior resolution of the owners that admitted the lower majority for this one subject) and
``vote_deadline_at`` (end of the text form voting period). ``tenant_settings`` gets the per
tenant switch ``hoa_circular_lower_majority_enabled`` (default off): without it a circular
resolution is only recorded as unanimous in text form, as before.

Revision ID: 0166
Revises: 0165
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0166"
down_revision: str | None = "0165"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    have = _columns("resolution")
    if "allowed_majority" not in have:
        op.add_column(
            "resolution",
            sa.Column(
                "allowed_majority",
                sa.String(16),
                nullable=False,
                server_default="unanimous",
            ),
        )
    if "enabling_resolution_id" not in have:
        op.add_column(
            "resolution",
            sa.Column(
                "enabling_resolution_id",
                UUID(as_uuid=True),
                sa.ForeignKey("resolution.id", ondelete="RESTRICT"),
                nullable=True,
            ),
        )
    if "vote_deadline_at" not in have:
        op.add_column(
            "resolution", sa.Column("vote_deadline_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "hoa_circular_lower_majority_enabled" not in _columns("tenant_settings"):
        op.add_column(
            "tenant_settings",
            sa.Column(
                "hoa_circular_lower_majority_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    if "hoa_circular_lower_majority_enabled" in _columns("tenant_settings"):
        op.drop_column("tenant_settings", "hoa_circular_lower_majority_enabled")
    have = _columns("resolution")
    for name in ("vote_deadline_at", "enabling_resolution_id", "allowed_majority"):
        if name in have:
            op.drop_column("resolution", name)
