"""objektakte_preview_import_run: M35 technical preparation of the preview image takeover
(docs/plans/M35-objektakte-uebernahme.md section 3.2, open question M35-02). One row per run
of `mhvp.objektakte.previews.import_previews` with counters and a resume cursor; the preview
files themselves go to the object store, the document keeps a pointer in `source_meta`.

Revision ID: 0176
Revises: 0175
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0176"
down_revision: str | None = "0175"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "objektakte_preview_import_run"
ENUM_NAME = "objektakte_preview_import_status"
_STATUS = postgresql.ENUM("running", "done", "failed", name=ENUM_NAME)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table(TABLE):
        return
    _STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "status",
            postgresql.ENUM("running", "done", "failed", name=ENUM_NAME, create_type=False),
            nullable=False,
            server_default="running",
        ),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("previews_dir", sa.String(length=500)),
        sa.Column("render_missing", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rendered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_document_id", postgresql.UUID(as_uuid=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.String(length=1000)),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
    )
    op.create_index(f"ix_{TABLE}_tenant", TABLE, ["tenant_id", "started_at"])
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    _STATUS.drop(op.get_bind(), checkfirst=True)
