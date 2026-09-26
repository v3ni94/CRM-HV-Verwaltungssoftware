"""bank_account_assignment: selectable link between a bank account and a property or a
legal entity with default markers (Bankkontenauswahl). Organisation only: no money moves,
no posting, no payment (G2 stays closed). The account's home property and owning legal
entity on property_bank_account stay untouched.

Revision ID: 0079
Revises: 0078
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0079"
down_revision: str | None = "0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "bank_account_assignment"
_PURPOSE = postgresql.ENUM("hausgeld", "miete", "general", name="bank_account_purpose")


def upgrade() -> None:
    _PURPOSE.create(op.get_bind(), checkfirst=True)
    op.create_table(
        _TABLE,
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
        sa.Column("property_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "purpose",
            postgresql.ENUM(name="bank_account_purpose", create_type=False),
            nullable=False,
            server_default="general",
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint(
            "(property_id IS NOT NULL) <> (legal_entity_id IS NOT NULL)",
            name="exactly_one_scope",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["property_bank_account_id"], ["property_bank_account.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entity.id"]),
    )
    op.create_index(
        "uq_bank_account_assignment_property",
        _TABLE,
        ["tenant_id", "property_bank_account_id", "property_id"],
        unique=True,
        postgresql_where=sa.text("property_id IS NOT NULL"),
    )
    op.create_index(
        "uq_bank_account_assignment_legal_entity",
        _TABLE,
        ["tenant_id", "property_bank_account_id", "legal_entity_id"],
        unique=True,
        postgresql_where=sa.text("legal_entity_id IS NOT NULL"),
    )
    op.create_index(
        "uq_bank_account_assignment_property_default",
        _TABLE,
        ["tenant_id", "property_id", "purpose"],
        unique=True,
        postgresql_where=sa.text("is_default AND property_id IS NOT NULL"),
    )
    op.create_index(
        "uq_bank_account_assignment_legal_entity_default",
        _TABLE,
        ["tenant_id", "legal_entity_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND legal_entity_id IS NOT NULL"),
    )
    for statement in tenant_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(_TABLE):
        op.execute(statement)
    op.drop_table(_TABLE)
    _PURPOSE.drop(op.get_bind(), checkfirst=True)
