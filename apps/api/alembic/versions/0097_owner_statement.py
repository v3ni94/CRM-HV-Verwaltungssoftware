"""owner_statement: owner statements for rental management and SEV (7.6 A06, M17, task A25).
Table owner_statement with tenant RLS; the snapshot (inputs, results, findings) is stored as
JSONB with rule version and hash. Drafts only; the PDF output needs release gate G3.

Revision ID: 0097
Revises: 0096
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0097"
down_revision: str | None = "0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND = postgresql.ENUM("rental_owner", "sev_owner", name="owner_statement_kind")
_STATUS = postgresql.ENUM(
    "draft", "calculated", "internally_approved", name="owner_statement_status"
)
_TABLE = "owner_statement"


def upgrade() -> None:
    bind = op.get_bind()
    _KIND.create(bind, checkfirst=True)
    _STATUS.create(bind, checkfirst=True)
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
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind", postgresql.ENUM(name="owner_statement_kind", create_type=False), nullable=False
        ),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="owner_statement_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ledger_id"], ["ledger.id"]),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entity.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.CheckConstraint("period_to >= period_from", name="ck_owner_statement_period"),
    )
    op.create_index("ix_owner_statement_tenant_id", _TABLE, ["tenant_id"])
    op.create_index("ix_owner_statement_ledger_id", _TABLE, ["ledger_id"])
    for statement in tenant_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in drop_tenant_rls_statements(_TABLE):
        op.execute(statement)
    op.drop_table(_TABLE)
    bind = op.get_bind()
    _STATUS.drop(bind, checkfirst=True)
    _KIND.drop(bind, checkfirst=True)
