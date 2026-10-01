"""WebAuthn passwordless flag (S16-01/M2-03).

* ``webauthn_credential.passwordless``: boolean, not null, default false. A passkey signs in
  without a password only when this flag was chosen at registration.

Revision ID: 0298
Revises: 0297
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0298"
down_revision: str | None = "0297"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webauthn_credential",
        sa.Column("passwordless", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("webauthn_credential", "passwordless")
