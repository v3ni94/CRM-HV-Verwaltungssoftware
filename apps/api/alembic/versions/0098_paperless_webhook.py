"""paperless_webhook: per tenant secret for the Paperless post-consume webhook and the switch
"Belegeingang aus Paperless automatisch" (task A30, master prompt 11.2/11.4, M14-05; default
off).

Revision ID: 0098
Revises: 0097
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0098"
down_revision: str | None = "0097"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Field encrypted like `secret` (mhvp.core.crypto.EncryptedText, LargeBinary).
    op.add_column("dms_connection", sa.Column("webhook_secret", sa.LargeBinary(), nullable=True))
    op.add_column(
        "dms_connection",
        sa.Column(
            "auto_receipt_intake",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("dms_connection", "auto_receipt_intake")
    op.drop_column("dms_connection", "webhook_secret")
