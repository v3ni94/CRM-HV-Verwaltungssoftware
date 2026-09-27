"""Release workflow and versioning for ai_knowledge_entry (M34-01).

Adds status (draft, in_review, approved, withdrawn), per entry versioning (``group_id`` groups
the versions of one entry, ``version`` counts them, ``superseded_at`` marks a version replaced by
a newer one, the old version stays readable), four eyes approval (``submitted_by/at``,
``approved_by/at`` must differ from the author, ``withdrawn_by/at``), a validity period
(``valid_from``/``valid_until``) and a source document link (``source_document_id``, Quelle
/Beleg). Only ``approved`` and currently valid, non superseded, non deleted entries are read as
AI context (``mhvp.communication.preparation``); everything else stays a draft under review
(rule 0.1.6, Produktschutz M34-01).

Revision ID: 0178
Revises: 0177
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0178"
down_revision: str | None = "0177"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "ai_knowledge_entry"
STATUS_ENUM = postgresql.ENUM(
    "draft", "in_review", "approved", "withdrawn", name="ai_knowledge_status"
)
INDEX_GROUP = "ix_ai_knowledge_entry_group"
INDEX_SOURCE_DOCUMENT = "ix_ai_knowledge_entry_source_document_id"


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE):
        return set()
    return {c["name"] for c in inspector.get_columns(TABLE)}


def upgrade() -> None:
    existing = _existing_columns()
    bind = op.get_bind()
    STATUS_ENUM.create(bind, checkfirst=True)
    if "status" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "status",
                STATUS_ENUM,
                nullable=False,
                server_default="draft",
            ),
        )
    if "group_id" not in existing:
        op.add_column(TABLE, sa.Column("group_id", sa.UUID(), nullable=True))
        # Existing rows each start their own group (version 1).
        op.execute(f"UPDATE {TABLE} SET group_id = id WHERE group_id IS NULL")  # noqa: S608
        op.alter_column(TABLE, "group_id", nullable=False)
    if "version" not in existing:
        op.add_column(TABLE, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    if "superseded_at" not in existing:
        op.add_column(TABLE, sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))
    if "valid_from" not in existing:
        op.add_column(TABLE, sa.Column("valid_from", sa.Date(), nullable=True))
    if "valid_until" not in existing:
        op.add_column(TABLE, sa.Column("valid_until", sa.Date(), nullable=True))
    if "source_document_id" not in existing:
        op.add_column(TABLE, sa.Column("source_document_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            "fk_ai_knowledge_entry_source_document_id_document",
            TABLE,
            "document",
            ["source_document_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "submitted_by" not in existing:
        op.add_column(TABLE, sa.Column("submitted_by", sa.UUID(), nullable=True))
    if "submitted_at" not in existing:
        op.add_column(TABLE, sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    if "approved_by" not in existing:
        op.add_column(TABLE, sa.Column("approved_by", sa.UUID(), nullable=True))
    if "approved_at" not in existing:
        op.add_column(TABLE, sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    if "withdrawn_by" not in existing:
        op.add_column(TABLE, sa.Column("withdrawn_by", sa.UUID(), nullable=True))
    if "withdrawn_at" not in existing:
        op.add_column(TABLE, sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX_GROUP} ON {TABLE} (tenant_id, group_id)")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_SOURCE_DOCUMENT} ON {TABLE} (source_document_id)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_SOURCE_DOCUMENT}")
    op.execute(f"DROP INDEX IF EXISTS {INDEX_GROUP}")
    existing = _existing_columns()
    if "source_document_id" in existing:
        op.drop_constraint(
            "fk_ai_knowledge_entry_source_document_id_document", TABLE, type_="foreignkey"
        )
    for column in (
        "withdrawn_at",
        "withdrawn_by",
        "approved_at",
        "approved_by",
        "submitted_at",
        "submitted_by",
        "source_document_id",
        "valid_until",
        "valid_from",
        "superseded_at",
        "version",
        "group_id",
        "status",
    ):
        if column in existing:
            op.drop_column(TABLE, column)
    STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
