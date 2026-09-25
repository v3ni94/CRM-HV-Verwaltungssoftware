"""sepa_mandate_evidence: mandate evidence either as PDF document or as a recorded
grant (channel and note). document_id becomes optional accordingly.

Revision ID: 0047
Revises: 0046
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("sepa_mandate", "document_id", nullable=True)
    op.add_column("sepa_mandate", sa.Column("evidence_channel", sa.String(length=16)))
    op.add_column("sepa_mandate", sa.Column("evidence_note", sa.String(length=500)))


def downgrade() -> None:
    op.drop_column("sepa_mandate", "evidence_note")
    op.drop_column("sepa_mandate", "evidence_channel")
    # Mandates recorded without a PDF cannot exist in the old schema (document_id NOT NULL);
    # the downgrade removes them explicitly instead of failing on SET NOT NULL. Forced RLS
    # would hide every row from the migrator, so it is lifted for this one statement.
    op.execute("ALTER TABLE sepa_mandate NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM sepa_mandate WHERE document_id IS NULL")
    op.execute("ALTER TABLE sepa_mandate FORCE ROW LEVEL SECURITY")
    op.alter_column("sepa_mandate", "document_id", nullable=False)
