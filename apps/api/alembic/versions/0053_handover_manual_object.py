"""handover_manual_object: free text fields for an Übergabeprotokoll on an object that is not
in the managed portfolio (M30, operator request 25.09.2026). property_id/unit_id were already
nullable; this adds the external object number and the landlord/owner name so a protocol can be
fully created and printed without any link into the master data.

Revision ID: 0053
Revises: 0052
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "handover_protocol", sa.Column("external_object_number", sa.String(length=100))
    )
    op.add_column("handover_protocol", sa.Column("owner_name", sa.String(length=200)))


def downgrade() -> None:
    op.drop_column("handover_protocol", "owner_name")
    op.drop_column("handover_protocol", "external_object_number")
