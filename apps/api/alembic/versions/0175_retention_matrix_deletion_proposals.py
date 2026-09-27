"""Retention matrix productive (M6-04, V17, 6.9.5): category to profile mapping
(``document_category.retention_profile_id``), start date of the period per document
(``document.retention_base_on``), hold per ticket (``ticket.retention_hold_reason``) and the
deletion proposal run with four eyes approval and deletion log (``deletion_proposal``,
``deletion_proposal_item``). Idempotent: every column, type and table is checked first.

Revision ID: 0175
Revises: 0174
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0175"
down_revision: str | None = "0174"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROPOSAL = "deletion_proposal"
ITEM = "deletion_proposal_item"
_PROPOSAL_STATUS = ("open", "approved", "executed", "rejected")
_ITEM_STATUS = ("proposed", "deleted", "skipped")


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)
    # create_type=False: the type exists already, create_table must not create it again.
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    if "retention_profile_id" not in _columns("document_category"):
        op.add_column(
            "document_category",
            sa.Column(
                "retention_profile_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "retention_profile.id",
                    name="fk_document_category_retention_profile_id_retention_profile",
                    ondelete="RESTRICT",
                ),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_document_category_retention_profile_id",
            "document_category",
            ["retention_profile_id"],
        )
    if "retention_base_on" not in _columns("document"):
        op.add_column("document", sa.Column("retention_base_on", sa.Date(), nullable=True))
    if "retention_hold_reason" not in _columns("ticket"):
        op.add_column("ticket", sa.Column("retention_hold_reason", sa.Text(), nullable=True))

    proposal_status = _enum("deletion_proposal_status", _PROPOSAL_STATUS)
    item_status = _enum("deletion_item_status", _ITEM_STATUS)
    tables = _tables()
    if PROPOSAL not in tables:
        op.create_table(
            PROPOSAL,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", proposal_status, nullable=False),
            sa.Column("reference_date", sa.Date(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejected_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("executed_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f(f"fk_{PROPOSAL}_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{PROPOSAL}")),
        )
        op.create_index(f"ix_{PROPOSAL}_tenant_id", PROPOSAL, ["tenant_id"])
        op.create_index(f"ix_{PROPOSAL}_status", PROPOSAL, ["tenant_id", "status"])
        for statement in tenant_rls_statements(PROPOSAL):
            op.execute(statement)
    if ITEM not in tables:
        op.create_table(
            ITEM,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("category_code", sa.String(length=63), nullable=True),
            sa.Column("document_class", sa.String(length=63), nullable=False),
            sa.Column("retention_until", sa.Date(), nullable=False),
            sa.Column("status", item_status, nullable=False),
            sa.Column("skip_reason", sa.Text(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("mirror_deletions", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name=op.f(f"fk_{ITEM}_tenant_id_tenant"),
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["proposal_id"],
                [f"{PROPOSAL}.id"],
                name=op.f(f"fk_{ITEM}_proposal_id_{PROPOSAL}"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{ITEM}")),
            sa.UniqueConstraint(
                "tenant_id",
                "proposal_id",
                "document_id",
                name=op.f(f"uq_{ITEM}_tenant_id_proposal_id_document_id"),
            ),
        )
        op.create_index(f"ix_{ITEM}_tenant_id", ITEM, ["tenant_id"])
        op.create_index(f"ix_{ITEM}_proposal_id", ITEM, ["proposal_id"])
        op.create_index(f"ix_{ITEM}_document", ITEM, ["tenant_id", "document_id"])
        for statement in tenant_rls_statements(ITEM):
            op.execute(statement)


def downgrade() -> None:
    tables = _tables()
    for table in (ITEM, PROPOSAL):
        if table in tables:
            for statement in drop_tenant_rls_statements(table):
                op.execute(statement)
            op.drop_table(table)
    postgresql.ENUM(name="deletion_item_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="deletion_proposal_status").drop(op.get_bind(), checkfirst=True)
    if "retention_hold_reason" in _columns("ticket"):
        op.drop_column("ticket", "retention_hold_reason")
    if "retention_base_on" in _columns("document"):
        op.drop_column("document", "retention_base_on")
    if "retention_profile_id" in _columns("document_category"):
        op.drop_index("ix_document_category_retention_profile_id", table_name="document_category")
        op.drop_column("document_category", "retention_profile_id")
