"""Objektakte export for the successor manager (M12 gaps, 29.09.2026).

* ``objektakte_export``: one run per export of a property's Objektakte (status queued,
  running, done, failed), who requested it and confirmed the personal data note, the filed
  ZIP document, counts, error and download counter. Tenant table with RLS via
  ``tenant_rls_statements`` (ADR 0002).

Idempotent: every step checks the catalogue first, a re-run changes nothing.

Revision ID: 0246
Revises: 0241
Create Date: 2026-09-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0246"
down_revision: str | None = "0241"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "objektakte_export"
ENUM_NAME = "objektakte_export_status"
STATUSES = ("queued", "running", "done", "failed")


def _has_table(name: str) -> bool:
    return bool(sa.inspect(op.get_bind()).has_table(name))


def upgrade() -> None:
    if _has_table(TABLE):
        return
    postgresql.ENUM(*STATUSES, name=ENUM_NAME).create(op.get_bind(), checkfirst=True)
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
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("property.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*STATUSES, name=ENUM_NAME, create_type=False),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "personal_data_acknowledged", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "counts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(f"ix_{TABLE}_property", TABLE, ["tenant_id", "property_id"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if _has_table(TABLE):
        for statement in drop_tenant_rls_statements(TABLE):
            op.execute(statement)
        op.drop_table(TABLE)
    postgresql.ENUM(*STATUSES, name=ENUM_NAME).drop(op.get_bind(), checkfirst=True)
