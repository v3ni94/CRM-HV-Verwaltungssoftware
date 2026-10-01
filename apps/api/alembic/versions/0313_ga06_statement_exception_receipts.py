"""Deadline exception evidence and owner statement receipts option (GA06-04, GA03-08).

* ``statement.deadline_exception_document_id`` (FK document, RESTRICT), ``..._set_by``,
  ``..._set_at``: evidence document and author of the exception to the statement deadline
  (7.6 A04); a late claim is released only with reason and document.
* ``owner_statement.attach_receipts``: option to append the linked receipts to the PDF
  output of the owner statement (6.5 owner_statement).

Revision ID: 0313
Revises: 0312
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0313"
down_revision: str | None = "0312"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "statement",
        sa.Column("deadline_exception_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_statement_deadline_exc_document",
        "statement",
        "document",
        ["deadline_exception_document_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "statement",
        sa.Column("deadline_exception_set_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "statement",
        sa.Column("deadline_exception_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "owner_statement",
        sa.Column("attach_receipts", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("owner_statement", "attach_receipts")
    op.drop_column("statement", "deadline_exception_set_at")
    op.drop_column("statement", "deadline_exception_set_by")
    op.drop_constraint("fk_statement_deadline_exc_document", "statement", type_="foreignkey")
    op.drop_column("statement", "deadline_exception_document_id")
