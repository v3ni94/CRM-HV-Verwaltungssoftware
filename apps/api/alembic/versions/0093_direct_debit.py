"""direct_debit: SEPA direct debit runs (pain.008, 7.5 SEPA, M15, rule M15-02). Tables
direct_debit_run, direct_debit_order, direct_debit_approval with tenant RLS; creditor
identifier columns ``sepa_creditor_id`` on legal_entity and tenant_billing_settings (operator
entry only, no format check). The generated file is stored as a document and never sent to a
bank; the download requires release gate G2 (closed by default).

Revision ID: 0093
Revises: 0083
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0093"
down_revision: str | None = "0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = postgresql.ENUM(
    "draft",
    "approved",
    "file_generated",
    "exported",
    "cancelled",
    name="direct_debit_run_status",
)
_SEQ = postgresql.ENUM("FRST", "RCUR", name="direct_debit_sequence_type")
_TABLES = ("direct_debit_run", "direct_debit_order", "direct_debit_approval")


def _audit() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    bind = op.get_bind()
    _STATUS.create(bind, checkfirst=True)
    _SEQ.create(bind, checkfirst=True)
    op.add_column("legal_entity", sa.Column("sepa_creditor_id", sa.String(35), nullable=True))
    op.add_column(
        "tenant_billing_settings", sa.Column("sepa_creditor_id", sa.String(35), nullable=True)
    )
    op.create_table(
        "direct_debit_run",
        *_audit(),
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("creditor_id", sa.String(35), nullable=False),
        sa.Column("creditor_name", sa.String(70), nullable=False),
        sa.Column("collection_date", sa.Date(), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(35), nullable=False, unique=True),
        sa.Column("format", sa.String(32), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="direct_debit_run_status", create_type=False),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("control_sum", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "excluded", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exported_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ledger_id"], ["ledger.id"]),
        sa.ForeignKeyConstraint(["legal_entity_id"], ["legal_entity.id"]),
        sa.ForeignKeyConstraint(["property_bank_account_id"], ["property_bank_account.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
    )
    op.create_table(
        "direct_debit_order",
        *_audit(),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("open_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mandate_reference", sa.String(35), nullable=False),
        sa.Column("mandate_signed_on", sa.Date(), nullable=False),
        sa.Column("mandate_scheme", sa.String(8), nullable=False),
        sa.Column(
            "sequence_type",
            postgresql.ENUM(name="direct_debit_sequence_type", create_type=False),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("debtor_name", sa.String(140), nullable=False),
        sa.Column("debtor_iban", sa.LargeBinary(), nullable=False),
        sa.Column("debtor_iban_fingerprint", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(140), nullable=False),
        sa.Column("end_to_end_id", sa.String(35), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("pre_notification_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pre_notification_dispatch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="direct_debit_order_amount_positive"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["direct_debit_run.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["open_item_id"], ["open_item.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contract.id"]),
        sa.ForeignKeyConstraint(["contact_id"], ["contact.id"]),
        sa.ForeignKeyConstraint(["contact_bank_account_id"], ["contact_bank_account.id"]),
        sa.ForeignKeyConstraint(["pre_notification_document_id"], ["document.id"]),
        sa.ForeignKeyConstraint(["pre_notification_dispatch_id"], ["dispatch.id"]),
    )
    op.create_index("ix_direct_debit_order_run_id", "direct_debit_order", ["run_id"])
    op.create_index(
        "ix_direct_debit_order_contact_bank_account_id",
        "direct_debit_order",
        ["contact_bank_account_id"],
    )
    op.create_table(
        "direct_debit_approval",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["direct_debit_run.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_direct_debit_approval_run_id", "direct_debit_approval", ["run_id"])
    for table in _TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in reversed(_TABLES):
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
        op.drop_table(table)
    op.drop_column("tenant_billing_settings", "sepa_creditor_id")
    op.drop_column("legal_entity", "sepa_creditor_id")
    bind = op.get_bind()
    _SEQ.drop(bind, checkfirst=True)
    _STATUS.drop(bind, checkfirst=True)
