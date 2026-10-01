"""AE33 / AC07-01, AC07-03: document trash and access export scope (tenant switches).

* ``document.deleted_at`` / ``deleted_by`` / ``purge_at``: a document in the trash; both
  timestamps are set together (``ck_document_trash_pair``). Existing rows are not in the trash.
* ``document_trash_setting``: one row per tenant, off by default; the 30 day period is a
  proposal (OPEN_QUESTIONS AE33-01).
* ``contact_access_export_setting``: one row per tenant, other persons by role only and internal
  notes withheld by default (OPEN_QUESTIONS AC07-01).

Revision ID: 0389
Revises: 0388
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0389"
down_revision: str | None = "0388"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("document_trash_setting", "contact_access_export_setting")


def _common(table: str) -> list[sa.SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f(f"fk_{table}_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.add_column("document", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document", sa.Column("deleted_by", sa.Uuid(), nullable=True))
    op.add_column("document", sa.Column("purge_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f("ck_document_trash_pair"), "document", "(deleted_at IS NULL) = (purge_at IS NULL)"
    )
    op.create_index(
        "ix_document_trash_purge_at",
        "document",
        ["tenant_id", "purge_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )
    op.create_table(
        "document_trash_setting",
        *_common("document_trash_setting"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.CheckConstraint(
            "retention_days BETWEEN 1 AND 365",
            name=op.f("ck_document_trash_setting_retention_days_range"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_document_trash_setting_tenant_id")),
    )
    op.create_table(
        "contact_access_export_setting",
        *_common("contact_access_export_setting"),
        sa.Column("third_party_scope", sa.String(16), nullable=False, server_default="none"),
        sa.Column(
            "include_internal_notes", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.CheckConstraint(
            "third_party_scope IN ('none', 'names')",
            name=op.f("ck_contact_access_export_setting_third_party_scope_values"),
        ),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_contact_access_export_setting_tenant_id")),
    )
    for table in TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    op.drop_index("ix_document_trash_purge_at", table_name="document")
    op.drop_constraint(op.f("ck_document_trash_pair"), "document", type_="check")
    op.drop_column("document", "purge_at")
    op.drop_column("document", "deleted_by")
    op.drop_column("document", "deleted_at")
