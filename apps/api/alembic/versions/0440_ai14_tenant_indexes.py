"""AI14 (GAH-308, section 5.3): leading tenant_id index for tenant tables without one.

Plain CREATE INDEX inside the migration transaction (no CONCURRENTLY); IF NOT EXISTS keeps a
rerun after a partial manual fix safe. Downgrade drops exactly these indexes.

Revision ID: 0440
Revises: 0439
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0440"
down_revision: str | None = "0439"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of mhvp.core.db.tenant_index.TENANT_INDEXED_TABLES at revision 0440.
TABLES: tuple[str, ...] = (
    "acceptance_result",
    "ai_conversation",
    "ai_example",
    "ai_message",
    "allocation_agreement",
    "api_key",
    "audit_engagement",
    "audit_item",
    "audit_report",
    "bank_connection",
    "bank_rule",
    "bank_sync_run",
    "building",
    "consent",
    "contact_address",
    "contact_bank_account_change",
    "contact_identifier",
    "contact_note",
    "contact_phone",
    "contact_relation",
    "contract_allocation_value",
    "contract_payment",
    "contract_termination_reading",
    "deposit",
    "deposit_interest_draft",
    "deposit_interest_rate",
    "deposit_movement",
    "deposit_settlement",
    "direct_debit_approval",
    "direct_debit_order",
    "dunning_case",
    "dunning_fee_invoice_draft",
    "dunning_run",
    "economic_plan",
    "economic_plan_item",
    "export_run",
    "finapi_connection",
    "fints_connection",
    "flow_import_run",
    "handover_defect",
    "handover_item",
    "handover_key",
    "handover_meter",
    "handover_note",
    "handover_participant",
    "handover_room",
    "handover_signature",
    "hoa_cost_item",
    "hoa_insurance_claim",
    "hoa_insurance_claim_item",
    "hoa_loan",
    "hoa_loan_item",
    "hoa_majority_rule",
    "hoa_measure",
    "hoa_measure_financing",
    "hoa_statement",
    "immoware_learning_run",
    "immoware_sync_run",
    "import_run",
    "import_run_item",
    "import_source_file",
    "interest_tax_withholding",
    "invoice_line",
    "invoice_line_section35a",
    "invoice_review",
    "invoice_second_approval",
    "invoice_tax_data",
    "journal_line",
    "journal_number_counter",
    "license",
    "mailbox",
    "mailbox_sync_retry",
    "majority_rule",
    "meeting_agenda_item",
    "meeting_attendance",
    "meter",
    "meter_change",
    "meter_reading",
    "migration_opening_balance_line",
    "notice_board_read",
    "objektakte_person_proposal",
    "oidc_authorization_code",
    "open_item",
    "open_item_settlement",
    "openimmo_import_run",
    "owners_meeting",
    "party",
    "payment_approval",
    "payment_batch",
    "payment_order",
    "payment_schedule",
    "portal_change_request",
    "property_billing_period",
    "property_contact",
    "property_owner",
    "property_tax_profile",
    "prospect",
    "receivable_run",
    "recurring_invoice_plan",
    "refresh_token",
    "release_gate_request",
    "rent_increase_case",
    "resolution",
    "self_disclosure_link",
    "service_provider_relation",
    "sla_clock",
    "sla_clock_log",
    "sla_emergency_alert",
    "sla_escalation_step",
    "sla_on_call_schedule",
    "sla_whatsapp_delivery",
    "special_levy",
    "statement",
    "statement_cost_item",
    "statement_event",
    "statement_inspection",
    "statement_result",
    "statement_snapshot",
    "supplier_tax_profile",
    "tenant_domain",
    "ticket_assignee",
    "trusted_device",
    "unit_allocation_value",
    "unit_vacancy_allocation_value",
    "unit_vat_option",
    "webhook_delivery",
    "webhook_subscription",
    "work_order_event",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
