"""AE34 / AC06-01 to AC06-03, AD03-01: evidence of consents and objections.

* ``consent.record_type`` (``consent`` or ``objection``): an objection to a processing based
  on legitimate interest is stored beside the consents with the same lifecycle.
* ``consent.text_version`` and ``consent.ip_hash``: accepted version of the portal terms and a
  keyed hash of the client address (never the clear address) as evidence of the acceptance
  in text form.

Revision ID: 0390
Revises: 0389
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0390"
down_revision: str | None = "0389"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "consent",
        sa.Column("record_type", sa.String(16), nullable=False, server_default="consent"),
    )
    op.add_column("consent", sa.Column("text_version", sa.String(60), nullable=True))
    op.add_column("consent", sa.Column("ip_hash", sa.String(64), nullable=True))
    op.create_check_constraint("record_type", "consent", "record_type IN ('consent', 'objection')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_consent_record_type"), "consent", type_="check")
    op.drop_column("consent", "ip_hash")
    op.drop_column("consent", "text_version")
    op.drop_column("consent", "record_type")
