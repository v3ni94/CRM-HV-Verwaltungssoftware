"""contact_bank_account: four eyes release of new or changed IBANs (M5-01).

Adds approval_status (pending, approved, rejected), requested_by, decided_by and decided_at.
Existing rows start as pending as well: no IBAN entered before M5-01 has been released by a
second person, so none may feed mandates or payment runs until it is (rule 0.1.3). The table
already carries tenant RLS (migration 0003); new columns inherit it.

Revision ID: 0109
Revises: 0108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0109"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "contact_bank_account"
_STATUSES = ("pending", "approved", "rejected")


def upgrade() -> None:
    status = postgresql.ENUM(*_STATUSES, name="bank_account_approval_status")
    status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        TABLE,
        sa.Column("approval_status", status, nullable=False, server_default="pending"),
    )
    op.add_column(TABLE, sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(TABLE, sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    # Bestandskonten vor Einführung der Vier-Augen-Regel gelten als freigegeben, sonst würde
    # nach dem Deploy kein Lastschriftlauf mehr laufen; neue oder geänderte IBANs starten
    # als "zur Freigabe" (Ereignis bank_account.pending im Kontaktmodul).
    op.execute(
        "UPDATE contact_bank_account SET approval_status = 'approved', decided_at = now() "
        "WHERE approval_status = 'pending'"
    )


def downgrade() -> None:
    op.drop_column(TABLE, "decided_at")
    op.drop_column(TABLE, "decided_by")
    op.drop_column(TABLE, "requested_by")
    op.drop_column(TABLE, "approval_status")
    postgresql.ENUM(name="bank_account_approval_status").drop(op.get_bind(), checkfirst=True)
