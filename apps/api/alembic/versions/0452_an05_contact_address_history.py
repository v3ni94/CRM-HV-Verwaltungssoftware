"""AN05: address history of contacts (GAJ-610, OPEN_QUESTIONS AM14-01).

contact_address gets valid_to and superseded_at, a range check and an index
(tenant_id, contact_id, valid_from). Used only with the tenant switch
contacts.address_history (default off).

Revision ID: 0452
Revises: 0451
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0452"
down_revision: str | None = "0451"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contact_address", sa.Column("valid_to", sa.Date(), nullable=True))
    op.add_column(
        "contact_address",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_contact_address_valid_range"),
        "contact_address",
        "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
    )
    op.create_index(
        "ix_contact_address_tenant_contact_from",
        "contact_address",
        ["tenant_id", "contact_id", "valid_from"],
    )


def downgrade() -> None:
    # Without the columns closed rows would reappear as current addresses. They are removed;
    # the migrator is subject to FORCE ROW LEVEL SECURITY, so FORCE is lifted for this
    # transaction only and restored right after (pattern 0398). No financial data.
    op.execute("ALTER TABLE contact_address NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM contact_address WHERE superseded_at IS NOT NULL")
    op.execute("ALTER TABLE contact_address FORCE ROW LEVEL SECURITY")
    op.drop_index("ix_contact_address_tenant_contact_from", table_name="contact_address")
    op.drop_constraint(op.f("ck_contact_address_valid_range"), "contact_address", type_="check")
    op.drop_column("contact_address", "superseded_at")
    op.drop_column("contact_address", "valid_to")
