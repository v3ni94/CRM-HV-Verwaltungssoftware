"""Übergabeprotokoll: Änderung nach Unterschrift (M30-09, operator decision 28.09.2026).

* ``handover_change``: history of explicit content unlocks after a signature (reason,
  timestamp, user, number of signatures set aside), tenant table with RLS via
  ``tenant_rls_statements`` (ADR 0002); existing policies stay untouched.
* ``handover_signature.invalidated_at`` and ``invalidated_change_id``: the signature was given
  before a content change and has to be repeated; the row stays as evidence.

Idempotent: every step checks the catalogue first, a re-run changes nothing.

Revision ID: 0239
Revises: 0238
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0239"
down_revision: str | None = "0238"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "handover_change"


def _has_table(name: str) -> bool:
    return bool(sa.inspect(op.get_bind()).has_table(name))


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "protocol_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("handover_protocol.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("changed_by_name", sa.String(200), nullable=True),
            sa.Column("signatures_invalidated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(f"ix_{TABLE}_protocol_id", TABLE, ["protocol_id"])
        op.create_index(f"ix_{TABLE}_tenant_id", TABLE, ["tenant_id"])
        for statement in tenant_rls_statements(TABLE):
            op.execute(statement)
    if not _has_column("handover_signature", "invalidated_at"):
        op.add_column(
            "handover_signature",
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("handover_signature", "invalidated_change_id"):
        op.add_column(
            "handover_signature",
            sa.Column(
                "invalidated_change_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    f"{TABLE}.id",
                    ondelete="SET NULL",
                    name="fk_handover_signature_invalidated_change_id",
                ),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _has_column("handover_signature", "invalidated_change_id"):
        op.drop_column("handover_signature", "invalidated_change_id")
    if _has_column("handover_signature", "invalidated_at"):
        op.drop_column("handover_signature", "invalidated_at")
    if _has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
