"""Leading tenant_id index per tenant table (section 5.3, GAH-308, migration 0440).

Every table with ``tenant_id`` needs an index or a unique/primary key constraint whose first
column is ``tenant_id``. Migration 0440 created the missing single column indexes for the
tables in ``TENANT_INDEXED_TABLES``; ``apply_tenant_indexes`` declares the identical indexes on
the ORM metadata so autogenerate stays drift free. New tables declare their own index.
"""

from __future__ import annotations

from sqlalchemy import Connection, Index, MetaData, text

# Small per tenant configuration tables (few rows per tenant): no index needed.
TENANT_INDEX_ALLOWLIST: dict[str, str] = {
    "admin_fee_setting": "configuration, a handful of rows per tenant",
    "ledger_interest_tax_config": "configuration, a handful of rows per tenant",
    "payment_bank_config": "configuration, one row per bank account at most",
}

# Frozen list of migration 0440 (keep identical to alembic/versions/0440_*.py).
TENANT_INDEXED_TABLES: tuple[str, ...] = (
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

_MISSING = text(
    """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
    WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')
      AND NOT EXISTS (
        SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indkey[0] = a.attnum
      )
    ORDER BY c.relname
    """
)


def tenant_tables_without_leading_index(conn: Connection) -> list[str]:
    """Tenant tables without an index (or unique/PK) led by tenant_id, allowlist excluded."""
    names = conn.execute(_MISSING).scalars()
    return [name for name in names if name not in TENANT_INDEX_ALLOWLIST]


def apply_tenant_indexes(metadata: MetaData) -> None:
    """Declare the 0440 indexes on the mapped tables (idempotent)."""
    for name in TENANT_INDEXED_TABLES:
        table = metadata.tables.get(name)
        if table is None:
            continue
        index_name = f"ix_{name}_tenant_id"
        if any(index.name == index_name for index in table.indexes):
            continue
        Index(index_name, table.c.tenant_id)
