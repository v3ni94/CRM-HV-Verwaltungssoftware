"""performance_indexes: indexes for frequent list filters (tenant with status, date and foreign
key) found in the performance review of 26.09.2026. Indexes only, no data change.

Revision ID: 0127
Revises: 0126
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0127"
down_revision: str | None = "0126"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index name, table, columns), declared identically in the models' __table_args__.
INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("ix_contract_tenant_end_date", "contract", ["tenant_id", "end_date"]),
    ("ix_contract_tenant_termination_date", "contract", ["tenant_id", "termination_date"]),
    ("ix_contract_tenant_kind", "contract", ["tenant_id", "kind"]),
    ("ix_sepa_mandate_tenant_status", "sepa_mandate", ["tenant_id", "status"]),
    ("ix_journal_entry_ledger_status", "journal_entry", ["tenant_id", "ledger_id", "status"]),
    (
        "ix_journal_entry_ledger_booking_date",
        "journal_entry",
        ["tenant_id", "ledger_id", "booking_date"],
    ),
    ("ix_journal_line_journal_entry_id", "journal_line", ["journal_entry_id"]),
    ("ix_journal_line_account_id", "journal_line", ["account_id"]),
    ("ix_invoice_tenant_ledger_id", "invoice", ["tenant_id", "ledger_id"]),
    (
        "ix_invoice_tenant_review_status_date",
        "invoice",
        ["tenant_id", "review_status", "invoice_date"],
    ),
    ("ix_invoice_line_invoice_id", "invoice_line", ["invoice_id"]),
    ("ix_invoice_review_invoice_id", "invoice_review", ["invoice_id"]),
    (
        "ix_direct_debit_run_tenant_status_date",
        "direct_debit_run",
        ["tenant_id", "status", "collection_date"],
    ),
    ("ix_document_tenant_created_at", "document", ["tenant_id", "created_at"]),
    (
        "ix_ai_proposal_tenant_entity_decision",
        "ai_proposal",
        ["tenant_id", "entity_type", "decision", "created_at"],
    ),
    (
        "ix_maintenance_item_tenant_status_due",
        "maintenance_item",
        ["tenant_id", "status", "due_date"],
    ),
    ("ix_property_tenant_status", "property", ["tenant_id", "status", "management_type"]),
    ("ix_contact_tenant_display_name", "contact", ["tenant_id", "display_name"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
