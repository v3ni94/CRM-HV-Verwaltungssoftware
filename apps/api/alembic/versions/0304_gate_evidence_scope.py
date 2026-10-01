"""Release gate evidence, revocation and structured scope (GA14-02, GA14-03, GA14-04).

* ``release_gate_request.opened_by`` / ``opened_at``: approval that opened the gate.
* ``revoked_by`` / ``revoked_at`` / ``revoke_comment``: revocation, never overwrites the
  approval.
* ``evidence_document_id``: linked evidence document (FK ``document``, RESTRICT).
* ``scope_property_ids`` / ``scope_legal_entity_ids`` / ``scope_functions``: structured scope,
  NULL means all.
* ``checklist``: confirmed prerequisites of 18.0 (code -> note).

Existing approvals are backfilled: opened_* from decided_* for approved requests.

Revision ID: 0304
Revises: 0303
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0304"
down_revision: str | None = "0303"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

T = "release_gate_request"


def upgrade() -> None:
    uuid_t = postgresql.UUID(as_uuid=True)
    op.add_column(T, sa.Column("opened_by", uuid_t, nullable=True))
    op.add_column(T, sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(T, sa.Column("revoked_by", uuid_t, nullable=True))
    op.add_column(T, sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(T, sa.Column("revoke_comment", sa.Text(), nullable=True))
    op.add_column(T, sa.Column("evidence_document_id", uuid_t, nullable=True))
    op.create_foreign_key(
        "fk_release_gate_request_evidence_doc",
        T,
        "document",
        ["evidence_document_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(T, sa.Column("scope_property_ids", postgresql.ARRAY(uuid_t), nullable=True))
    op.add_column(T, sa.Column("scope_legal_entity_ids", postgresql.ARRAY(uuid_t), nullable=True))
    op.add_column(T, sa.Column("scope_functions", postgresql.ARRAY(sa.String(64)), nullable=True))
    op.add_column(T, sa.Column("checklist", postgresql.JSONB(), nullable=True))
    op.execute(
        "UPDATE release_gate_request SET opened_by = decided_by, opened_at = decided_at "
        "WHERE status = 'approved'"
    )


def downgrade() -> None:
    op.drop_constraint("fk_release_gate_request_evidence_doc", T, type_="foreignkey")
    for column in (
        "checklist",
        "scope_functions",
        "scope_legal_entity_ids",
        "scope_property_ids",
        "evidence_document_id",
        "revoke_comment",
        "revoked_at",
        "revoked_by",
        "opened_at",
        "opened_by",
    ):
        op.drop_column(T, column)
