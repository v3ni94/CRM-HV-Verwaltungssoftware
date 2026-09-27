"""Owners' meeting: invitation period per tenant, virtual form (M25-03, V13).

``tenant_settings`` gets ``hoa_invitation_weeks`` (draft default 3, source status "to be
verified", no legal assertion) and the per tenant switch ``hoa_virtual_meetings_enabled``
(default off). ``owners_meeting`` gets the validity end of the enabling resolution of a
virtual meeting, the dial-in data (link and access data, encrypted at rest, shown to owners
of the community in the portal only) and the short-notice record of the invitation for the
minutes.

Revision ID: 0187
Revises: 0186
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0187"
down_revision: str | None = "0186"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SETTINGS_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("hoa_invitation_weeks", sa.Integer(), nullable=False, server_default="3"),
    sa.Column(
        "hoa_virtual_meetings_enabled",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    ),
)
MEETING_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column("virtual_basis_valid_until", sa.Date(), nullable=True),
    sa.Column("dial_in_url", sa.LargeBinary(), nullable=True),
    sa.Column("dial_in_access", sa.LargeBinary(), nullable=True),
    sa.Column(
        "invitation_short_notice",
        sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    ),
    sa.Column("invitation_short_notice_reason", sa.Text(), nullable=True),
)


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    for table, columns in (
        ("tenant_settings", SETTINGS_COLUMNS),
        ("owners_meeting", MEETING_COLUMNS),
    ):
        have = _columns(table)
        for column in columns:
            if column.name not in have:
                op.add_column(table, column.copy())


def downgrade() -> None:
    for table, columns in (
        ("owners_meeting", MEETING_COLUMNS),
        ("tenant_settings", SETTINGS_COLUMNS),
    ):
        have = _columns(table)
        for column in columns:
            if column.name in have:
                op.drop_column(table, column.name)
