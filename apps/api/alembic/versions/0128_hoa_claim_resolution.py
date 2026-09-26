"""hoa_insurance_claim: structured resolution link (A79, W10). The resolution must belong to
the same community; checked in mhvp.hoa.finance._check_resolution. Column only; the table
keeps its RLS policies of migration 0116.

Revision ID: 0128
Revises: 0127
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0128"
down_revision: str | None = "0127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hoa_insurance_claim",
        sa.Column(
            "resolution_id",
            UUID(as_uuid=True),
            sa.ForeignKey("resolution.id", name="fk_hoa_insurance_claim_resolution_id_resolution"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("hoa_insurance_claim", "resolution_id")
