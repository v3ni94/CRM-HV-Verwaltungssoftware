"""Portal language choice stored at the portal account (GA11-01, AB12).

* ``portal_account.locale``: language code chosen by the person (nullable; empty means the
  browser decides). The allowed codes are checked in the API, a further language is added by
  file in the portal, so no CHECK constraint.

Revision ID: 0331
Revises: 0330
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0331"
down_revision: str | None = "0330"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("portal_account", sa.Column("locale", sa.String(8)))


def downgrade() -> None:
    op.drop_column("portal_account", "locale")
