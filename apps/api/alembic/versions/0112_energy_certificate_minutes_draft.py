"""A63 and A62: energy certificate data on the property (type, value, energy source,
construction year, issue date, validity, efficiency class), issue date and building year on
the listing, listing.energy_status widened to 24 characters ("nicht_erforderlich" has 18,
the column was String(16)), and the generated minutes draft document of an owners' meeting.

Revision ID: 0112
Revises: 0111
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112"
down_revision: str | None = "0111"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROPERTY_COLUMNS = (
    sa.Column("energy_certificate_type", sa.String(length=16), nullable=True),
    sa.Column("energy_certificate_value", sa.Numeric(8, 2), nullable=True),
    sa.Column("energy_certificate_source", sa.String(length=32), nullable=True),
    sa.Column("energy_certificate_construction_year", sa.Integer(), nullable=True),
    sa.Column("energy_certificate_issued_on", sa.Date(), nullable=True),
    sa.Column("energy_certificate_valid_until", sa.Date(), nullable=True),
    sa.Column("energy_certificate_class", sa.String(length=4), nullable=True),
)
LISTING_COLUMNS = (
    sa.Column("energy_issued_on", sa.Date(), nullable=True),
    sa.Column("energy_building_year", sa.Integer(), nullable=True),
)
MEETING_FK = "fk_owners_meeting_minutes_draft_document_id_document"


def upgrade() -> None:
    for column in PROPERTY_COLUMNS:
        op.add_column("property", column)
    for column in LISTING_COLUMNS:
        op.add_column("listing", column)
    op.alter_column(
        "listing",
        "energy_status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        existing_nullable=False,
        existing_server_default="in_erstellung",
    )
    op.add_column(
        "owners_meeting", sa.Column("minutes_draft_document_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        MEETING_FK, "owners_meeting", "document", ["minutes_draft_document_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(MEETING_FK, "owners_meeting", type_="foreignkey")
    op.drop_column("owners_meeting", "minutes_draft_document_id")
    # Values longer than 16 characters could not exist before 0112; they fall back to the
    # previous default so the narrower column accepts them (RLS is forced, ADR 0002).
    op.execute("ALTER TABLE listing NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE listing SET energy_status = 'in_erstellung' WHERE length(energy_status) > 16")
    op.execute("ALTER TABLE listing FORCE ROW LEVEL SECURITY")
    op.alter_column(
        "listing",
        "energy_status",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="in_erstellung",
    )
    for column in reversed(LISTING_COLUMNS):
        op.drop_column("listing", column.name)
    for column in reversed(PROPERTY_COLUMNS):
        op.drop_column("property", column.name)
