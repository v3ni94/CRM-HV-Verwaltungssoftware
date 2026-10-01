"""Access grant scope document_class (GA03-05, 6.9.6).

* ``access_grant.document_class``: class of the released documents; with ``scope_type``
  ``document_class`` the ``scope_id`` is the legal entity the documents are linked to.
* Check ``ck_access_grant_document_class_scope``: a document_class grant names its class.
* ``provider_availability`` (GA11-04): availability windows of service providers.

Revision ID: 0316
Revises: 0315
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0316"
down_revision: str | None = "0315"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE = "provider_availability"


def upgrade() -> None:
    op.add_column("access_grant", sa.Column("document_class", sa.String(63), nullable=True))
    op.create_check_constraint(
        "document_class_scope",
        "access_grant",
        "scope_type <> 'document_class' OR document_class IS NOT NULL",
    )
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_contact_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_provider_availability_window")),
        sa.CheckConstraint(
            "kind IN ('available', 'unavailable')", name=op.f("ck_provider_availability_kind")
        ),
        sa.ForeignKeyConstraint(
            ["provider_contact_id"],
            ["contact.id"],
            name=op.f("fk_provider_availability_provider_contact_id_contact"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_provider_availability_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_availability")),
    )
    op.create_index(
        "ix_provider_availability_provider",
        TABLE,
        ["tenant_id", "provider_contact_id", "starts_at"],
    )
    for statement in tenant_rls_statements(TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(TABLE):
        op.execute(statement)
    op.drop_table(TABLE)
    # Grants of the new scope cannot be represented without the column; the migrator is bound by
    # FORCE ROW LEVEL SECURITY and would not see them, so it is lifted for this one statement.
    op.execute('ALTER TABLE "public"."access_grant" NO FORCE ROW LEVEL SECURITY')
    op.execute("DELETE FROM access_grant WHERE scope_type = 'document_class'")
    op.execute('ALTER TABLE "public"."access_grant" FORCE ROW LEVEL SECURITY')
    op.drop_constraint(op.f("ck_access_grant_document_class_scope"), "access_grant", type_="check")
    op.drop_column("access_grant", "document_class")
