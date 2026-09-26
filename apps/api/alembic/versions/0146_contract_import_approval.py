"""contract: source and approval of imported contracts (Betreiberauftrag 26.09.2026).

Contracts created by the Immoware24 Zuordnung import (``mhvp.imports.zuordnung``) carry an
assumed start date and amounts. They must be approved by management before the first
receivable run (Sollstellung) reads their payment schedules. Adds ``source`` (text, e.g.
``immoware24:zuordnung``, NULL for manually created contracts), ``approval_status``
(``pending``, ``approved``, ``rejected``; server default ``approved`` so existing and manually
created contracts are unaffected), ``approved_by`` and ``approved_at`` (the decision, also for a
rejection). Existing rows created by the import (event source ``import.zuordnung``, recognisable
by their notes) stay ``approved``: they may already be posted, a retroactive block would change
running receivables. The table already carries tenant RLS; the new columns inherit it.

Revision ID: 0146
Revises: 0145
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0146"
down_revision: str | None = "0145"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "contract"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("source", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "approval_status", sa.String(length=20), nullable=False, server_default="approved"
        ),
    )
    op.add_column(TABLE, sa.Column("approved_by", UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_contract_approval_status_values",
        TABLE,
        "approval_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_index("ix_contract_tenant_approval_status", TABLE, ["tenant_id", "approval_status"])


def downgrade() -> None:
    op.drop_index("ix_contract_tenant_approval_status", table_name=TABLE)
    op.drop_constraint("ck_contract_approval_status_values", TABLE, type_="check")
    for column in ("approved_at", "approved_by", "approval_status", "source"):
        op.drop_column(TABLE, column)
