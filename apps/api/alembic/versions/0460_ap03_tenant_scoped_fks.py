"""AP03 (GAL-103, 5.3, 6.9.1 B01): tenant scoped foreign keys for money and WEG tables.

Plain foreign keys only check id and ignore RLS, so a UUID of another tenant was
accepted. This migration installs mhvp_tenant_fk_guard (referenced row must carry the
same tenant_id) on the accounting, banking, billing, contracts and hoa tables (ADR 0039).
Existing data is checked first; a violation aborts the migration, nothing is deleted.

Revision ID: 0460
Revises: 0459
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from mhvp.core.db.tenant_fk import GUARD_FUNCTION, TRIGGER_NAME, violation_count_sql

revision: str = "0460"
down_revision: str | None = "0459"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of mhvp.core.db.tenant_fk.TENANT_FK_GUARDED at 0460 (do not edit).
GUARDED: dict[str, tuple[tuple[str, str], ...]] = {
    "acceptance_result": (("expected_id", "acceptance_expected"),),
    "admin_fee_invoice": (
        ("corrects_invoice_id", "admin_fee_invoice"),
        ("debtor_legal_entity_id", "legal_entity"),
        ("fee_setting_id", "admin_fee_setting"),
        ("invoice_debtor_party_id", "party"),
        ("manager_entry_id", "journal_entry"),
        ("payer_entry_id", "journal_entry"),
        ("pdf_document_id", "document"),
        ("property_id", "property"),
        ("xml_document_id", "document"),
        ("zugferd_document_id", "document"),
    ),
    "admin_fee_posting_config": (
        ("manager_ledger_id", "ledger"),
        ("manager_receivable_account_id", "ledger_account"),
        ("manager_revenue_account_id", "ledger_account"),
        ("manager_vat_account_id", "ledger_account"),
    ),
    "admin_fee_setting": (
        ("account_id", "ledger_account"),
        ("contract_document_id", "document"),
        ("invoice_debtor_party_id", "party"),
        ("manager_contact_id", "contact"),
        ("property_id", "property"),
    ),
    "allocation_agreement": (
        ("contract_id", "contract"),
        ("document_id", "document"),
    ),
    "audit_engagement": (
        ("legal_entity_id", "legal_entity"),
        ("statement_id", "hoa_statement"),
    ),
    "audit_item": (
        ("document_id", "document"),
        ("engagement_id", "audit_engagement"),
        ("journal_entry_id", "journal_entry"),
    ),
    "audit_item_event": (("item_id", "audit_item"),),
    "audit_report": (("engagement_id", "audit_engagement"),),
    "auto_posting_digest": (("legal_entity_id", "legal_entity"),),
    "auto_posting_review": (
        ("bank_transaction_id", "bank_transaction"),
        ("journal_entry_id", "journal_entry"),
        ("legal_entity_id", "legal_entity"),
        ("posting_decision_id", "posting_decision"),
    ),
    "bank_account_assignment": (
        ("legal_entity_id", "legal_entity"),
        ("property_bank_account_id", "property_bank_account"),
        ("property_id", "property"),
    ),
    "bank_clarification": (
        ("bank_transaction_id", "bank_transaction"),
        ("document_id", "document"),
        ("legal_entity_id", "legal_entity"),
        ("ticket_id", "ticket"),
    ),
    "bank_csv_mapping": (("property_bank_account_id", "property_bank_account"),),
    "bank_fints_session": (
        ("fints_connection_id", "fints_connection"),
        ("sync_run_id", "bank_sync_run"),
    ),
    "bank_rule": (
        ("contract_id", "contract"),
        ("learned_from_proposal_id", "bank_rule_proposal"),
        ("legal_entity_id", "legal_entity"),
        ("property_id", "property"),
        ("test_evidence_document_id", "document"),
    ),
    "bank_rule_proposal": (("legal_entity_id", "legal_entity"),),
    "bank_statement": (
        ("property_bank_account_id", "property_bank_account"),
        ("sync_run_id", "bank_sync_run"),
    ),
    "bank_sync_run": (
        ("connection_id", "bank_connection"),
        ("document_id", "document"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "bank_transaction": (
        ("ai_proposal_id", "ai_proposal"),
        ("journal_entry_id", "journal_entry"),
        ("legal_entity_id", "legal_entity"),
        ("possible_duplicate_of_id", "bank_transaction"),
        ("property_bank_account_id", "property_bank_account"),
        ("statement_id", "bank_statement"),
        ("sync_run_id", "bank_sync_run"),
        ("transfer_pair_id", "bank_transaction"),
    ),
    "chart_of_accounts_template": (
        ("release_document_id", "document"),
        ("supersedes_id", "chart_of_accounts_template"),
    ),
    "consumption_info": (
        ("contract_id", "contract"),
        ("document_id", "document"),
        ("property_id", "property"),
        ("unit_id", "unit"),
    ),
    "contract": (
        ("debtor_account_id", "debtor_account_reservation"),
        ("legal_entity_id", "legal_entity"),
        ("party_id", "party"),
        ("property_id", "property"),
        ("sepa_mandate_id", "sepa_mandate"),
        ("sev_fee_debtor_party_id", "party"),
        ("supersedes_contract_id", "contract"),
        ("unit_id", "unit"),
    ),
    "contract_allocation_value": (
        ("allocation_key_id", "allocation_key"),
        ("contract_id", "contract"),
    ),
    "contract_graduated_step": (("contract_id", "contract"),),
    "contract_payment": (
        ("contract_id", "contract"),
        ("reserve_id", "hoa_reserve"),
        ("revenue_account_id", "ledger_account"),
    ),
    "contract_termination_reading": (
        ("contract_id", "contract"),
        ("meter_id", "meter"),
        ("meter_reading_id", "meter_reading"),
    ),
    "credit_payable": (
        ("contract_id", "contract"),
        ("ledger_id", "ledger"),
        ("open_item_id", "open_item"),
        ("reclass_entry_id", "journal_entry"),
        ("reversal_entry_id", "journal_entry"),
        ("source_entry_id", "journal_entry"),
    ),
    "datev_account_mapping": (("ledger_id", "ledger"),),
    "debtor_account_reservation": (
        ("legal_entity_id", "legal_entity"),
        ("party_id", "party"),
        ("unit_id", "unit"),
    ),
    "deposit": (
        ("contract_id", "contract"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "deposit_interest_draft": (
        ("deposit_id", "deposit"),
        ("movement_id", "deposit_movement"),
    ),
    "deposit_interest_rate": (("deposit_id", "deposit"),),
    "deposit_movement": (("deposit_id", "deposit"),),
    "deposit_settlement": (
        ("deposit_id", "deposit"),
        ("document_id", "document"),
    ),
    "direct_debit_approval": (("run_id", "direct_debit_run"),),
    "direct_debit_order": (
        ("bank_transaction_id", "bank_transaction"),
        ("contact_bank_account_id", "contact_bank_account"),
        ("contact_id", "contact"),
        ("contract_id", "contract"),
        ("open_item_id", "open_item"),
        ("pre_notification_dispatch_id", "dispatch"),
        ("pre_notification_document_id", "document"),
        ("return_fee_document_id", "document"),
        ("return_transaction_id", "bank_transaction"),
        ("run_id", "direct_debit_run"),
    ),
    "direct_debit_run": (
        ("document_id", "document"),
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "dunning_case": (
        ("bank_account_id", "property_bank_account"),
        ("contract_id", "contract"),
        ("debtor_account_id", "ledger_account"),
        ("fee_entry_id", "journal_entry"),
        ("fee_invoice_draft_id", "dunning_fee_invoice_draft"),
        ("interest_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
        ("letter_document_id", "document"),
        ("run_id", "dunning_run"),
    ),
    "dunning_delivery_proof": (
        ("case_id", "dunning_case"),
        ("document_id", "document"),
    ),
    "dunning_fee_invoice_draft": (
        ("case_id", "dunning_case"),
        ("issuer_ledger_id", "ledger"),
        ("recipient_legal_entity_id", "legal_entity"),
    ),
    "dunning_item_block": (("open_item_id", "open_item"),),
    "dunning_mahnbescheid_prep": (
        ("antragsteller_legal_entity_id", "legal_entity"),
        ("case_id", "dunning_case"),
    ),
    "dunning_settings": (("property_id", "property"),),
    "ebics_key": (("subscriber_id", "ebics_subscriber"),),
    "ebics_order": (("subscriber_id", "ebics_subscriber"),),
    "economic_plan": (
        ("basis_plan_id", "economic_plan"),
        ("basis_statement_id", "hoa_statement"),
        ("ledger_id", "ledger"),
        ("resolution_id", "resolution"),
        ("supersedes_id", "economic_plan"),
    ),
    "economic_plan_item": (
        ("account_id", "ledger_account"),
        ("allocation_key_id", "allocation_key"),
        ("plan_id", "economic_plan"),
        ("reserve_id", "hoa_reserve"),
    ),
    "export_run": (
        ("document_id", "document"),
        ("ledger_id", "ledger"),
    ),
    "finapi_account_link": (
        ("finapi_connection_id", "finapi_connection"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "finapi_connection": (("bank_connection_id", "bank_connection"),),
    "fints_account_link": (
        ("fints_connection_id", "fints_connection"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "fints_connection": (("bank_connection_id", "bank_connection"),),
    "g1_acceptance": (("evidence_document_id", "document"),),
    "heating_cost_import": (
        ("applied_item_id", "statement_cost_item"),
        ("document_id", "document"),
        ("property_id", "property"),
        ("provider_contact_id", "contact"),
        ("statement_id", "statement"),
    ),
    "hoa_acquisition_release": (
        ("contract_id", "contract"),
        ("statement_id", "hoa_statement"),
    ),
    "hoa_asset_report": (
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
    ),
    "hoa_asset_report_provision": (
        ("account_id", "portal_account"),
        ("contract_id", "contract"),
        ("report_id", "hoa_asset_report"),
    ),
    "hoa_cost_item": (
        ("account_id", "ledger_account"),
        ("allocation_key_id", "allocation_key"),
        ("basis_document_id", "document"),
        ("basis_resolution_id", "resolution"),
        ("document_id", "document"),
        ("journal_entry_id", "journal_entry"),
        ("statement_id", "hoa_statement"),
    ),
    "hoa_inspection_event": (("request_id", "hoa_inspection_request"),),
    "hoa_inspection_request": (
        ("applicant_contact_id", "contact"),
        ("legal_entity_id", "legal_entity"),
        ("package_document_id", "document"),
        ("property_id", "property"),
    ),
    "hoa_insurance_claim": (
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("measure_id", "hoa_measure"),
        ("resolution_id", "resolution"),
    ),
    "hoa_insurance_claim_item": (
        ("claim_id", "hoa_insurance_claim"),
        ("contract_id", "contract"),
        ("journal_entry_id", "journal_entry"),
    ),
    "hoa_loan": (
        ("account_id", "ledger_account"),
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("measure_id", "hoa_measure"),
        ("resolution_id", "resolution"),
    ),
    "hoa_loan_item": (
        ("journal_entry_id", "journal_entry"),
        ("loan_id", "hoa_loan"),
    ),
    "hoa_majority_rule": (("legal_entity_id", "legal_entity"),),
    "hoa_measure": (
        ("account_id", "ledger_account"),
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("resolution_id", "resolution"),
    ),
    "hoa_measure_financing": (
        ("loan_id", "hoa_loan"),
        ("measure_id", "hoa_measure"),
        ("special_levy_id", "special_levy"),
    ),
    "hoa_plan_difference": (
        ("contract_id", "contract"),
        ("plan_id", "economic_plan"),
        ("unit_id", "unit"),
    ),
    "hoa_reserve": (
        ("account_id", "ledger_account"),
        ("bank_account_id", "property_bank_account"),
        ("ledger_id", "ledger"),
        ("resolution_id", "resolution"),
    ),
    "hoa_reserve_movement": (
        ("document_id", "document"),
        ("journal_entry_id", "journal_entry"),
        ("reserve_id", "hoa_reserve"),
        ("resolution_id", "resolution"),
        ("statement_id", "hoa_statement"),
    ),
    "hoa_reserve_opening_change": (("reserve_id", "hoa_reserve"),),
    "hoa_reserve_plan": (
        ("economic_plan_id", "economic_plan"),
        ("reserve_id", "hoa_reserve"),
        ("resolution_id", "resolution"),
    ),
    "hoa_statement": (
        ("correction_resolution_id", "resolution"),
        ("ledger_id", "ledger"),
        ("resolution_id", "resolution"),
        ("supersedes_id", "hoa_statement"),
    ),
    "interest_tax_withholding": (
        ("bank_account_id", "ledger_account"),
        ("journal_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
    ),
    "invoice": (
        ("creditor_account_id", "ledger_account"),
        ("document_id", "document"),
        ("duplicate_of_id", "invoice"),
        ("journal_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
        ("plan_item_id", "economic_plan_item"),
        ("provider_contact_id", "contact"),
        ("recurring_plan_id", "recurring_invoice_plan"),
        ("reference_invoice_id", "invoice"),
        ("resolution_id", "resolution"),
        ("service_contract_id", "service_contract"),
        ("supersedes_id", "invoice"),
        ("work_order_id", "work_order"),
    ),
    "invoice_bank_transaction_link": (
        ("bank_transaction_id", "bank_transaction"),
        ("invoice_id", "invoice"),
    ),
    "invoice_line": (
        ("account_id", "ledger_account"),
        ("invoice_id", "invoice"),
        ("unit_id", "unit"),
    ),
    "invoice_line_section35a": (
        ("invoice_id", "invoice"),
        ("invoice_line_id", "invoice_line"),
    ),
    "invoice_review": (("invoice_id", "invoice"),),
    "invoice_second_approval": (("invoice_id", "invoice"),),
    "invoice_tax_data": (("invoice_id", "invoice"),),
    "journal_entry": (
        ("ai_proposal_id", "ai_proposal"),
        ("contract_id", "contract"),
        ("document_id", "document"),
        ("ledger_id", "ledger"),
        ("reversed_by_id", "journal_entry"),
        ("reverses_id", "journal_entry"),
    ),
    "journal_entry_note": (
        ("journal_entry_id", "journal_entry"),
        ("supersedes_id", "journal_entry_note"),
    ),
    "journal_line": (
        ("account_id", "ledger_account"),
        ("allocation_key_override_id", "allocation_key"),
        ("journal_entry_id", "journal_entry"),
        ("property_id", "property"),
        ("unit_id", "unit"),
    ),
    "journal_number_counter": (("ledger_id", "ledger"),),
    "ledger": (
        ("legal_entity_id", "legal_entity"),
        ("property_id", "property"),
        ("template_id", "chart_of_accounts_template"),
    ),
    "ledger_account": (
        ("contact_id", "contact"),
        ("contract_id", "contract"),
        ("ledger_id", "ledger"),
        ("party_id", "party"),
        ("property_bank_account_id", "property_bank_account"),
        ("unit_id", "unit"),
    ),
    "ledger_account_allocation": (
        ("allocation_key_id", "allocation_key"),
        ("ledger_account_id", "ledger_account"),
    ),
    "ledger_interest_tax_config": (
        ("capital_gains_tax_account_id", "ledger_account"),
        ("church_tax_account_id", "ledger_account"),
        ("ledger_id", "ledger"),
        ("solidarity_tax_account_id", "ledger_account"),
    ),
    "ledger_leading_switch": (
        ("ledger_id", "ledger"),
        ("property_id", "property"),
    ),
    "majority_rule": (("legal_entity_id", "legal_entity"),),
    "meeting_agenda_item": (
        ("meeting_id", "owners_meeting"),
        ("rule_id", "majority_rule"),
    ),
    "meeting_attendance": (
        ("contract_id", "contract"),
        ("meeting_id", "owners_meeting"),
        ("proxy_contact_id", "contact"),
        ("proxy_document_id", "document"),
    ),
    "meeting_proxy": (
        ("document_id", "document"),
        ("grantor_contract_id", "contract"),
        ("legal_entity_id", "legal_entity"),
        ("meeting_id", "owners_meeting"),
        ("proxy_contract_id", "contract"),
    ),
    "meeting_speaker_request": (
        ("agenda_item_id", "meeting_agenda_item"),
        ("contract_id", "contract"),
        ("meeting_id", "owners_meeting"),
    ),
    "meeting_vote": (
        ("agenda_item_id", "meeting_agenda_item"),
        ("contract_id", "contract"),
        ("proxy_id", "meeting_proxy"),
    ),
    "meeting_vote_conflict": (
        ("agenda_item_id", "meeting_agenda_item"),
        ("contract_id", "contract"),
        ("meeting_id", "owners_meeting"),
        ("second_proxy_id", "meeting_proxy"),
        ("vote_id", "meeting_vote"),
    ),
    "open_item": (
        ("account_id", "ledger_account"),
        ("contract_id", "contract"),
        ("journal_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
    ),
    "open_item_balance": (
        ("account_id", "ledger_account"),
        ("ledger_id", "ledger"),
        ("open_item_id", "open_item"),
    ),
    "open_item_settlement": (
        ("journal_entry_id", "journal_entry"),
        ("open_item_id", "open_item"),
    ),
    "open_item_write_off": (
        ("document_id", "document"),
        ("open_item_id", "open_item"),
    ),
    "owner_statement": (
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("property_id", "property"),
    ),
    "owners_meeting": (
        ("ballot_template_id", "document_template"),
        ("invitation_template_id", "document_template"),
        ("legal_entity_id", "legal_entity"),
        ("minutes_document_id", "document"),
        ("minutes_draft_document_id", "document"),
        ("origin_meeting_id", "owners_meeting"),
        ("proxy_template_id", "document_template"),
        ("virtual_basis_resolution_id", "resolution"),
    ),
    "payment_approval": (("order_id", "payment_order"),),
    "payment_bank_config": (("property_bank_account_id", "property_bank_account"),),
    "payment_batch": (
        ("document_id", "document"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "payment_file_download": (("batch_id", "payment_batch"),),
    "payment_order": (
        ("bank_transaction_id", "bank_transaction"),
        ("batch_id", "payment_batch"),
        ("contact_bank_account_id", "contact_bank_account"),
        ("invoice_id", "invoice"),
        ("journal_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
        ("open_item_id", "open_item"),
        ("property_bank_account_id", "property_bank_account"),
    ),
    "payment_schedule": (("contract_id", "contract"),),
    "payment_type_account": (
        ("account_id", "ledger_account"),
        ("ledger_id", "ledger"),
    ),
    "period_lock": (
        ("ledger_id", "ledger"),
        ("property_id", "property"),
    ),
    "posting_decision": (
        ("ai_proposal_id", "ai_proposal"),
        ("bank_transaction_id", "bank_transaction"),
        ("journal_entry_id", "journal_entry"),
        ("legal_entity_id", "legal_entity"),
        ("supersedes_id", "posting_decision"),
        ("sync_run_id", "bank_sync_run"),
    ),
    "property_tax_profile": (("property_id", "property"),),
    "receivable_item": (
        ("contract_id", "contract"),
        ("contract_payment_id", "contract_payment"),
        ("difference_of_item_id", "receivable_item"),
        ("journal_entry_id", "journal_entry"),
        ("ledger_id", "ledger"),
        ("payment_schedule_id", "payment_schedule"),
        ("reserve_id", "hoa_reserve"),
        ("run_id", "receivable_run"),
    ),
    "recurring_invoice_plan": (
        ("account_id", "ledger_account"),
        ("ledger_id", "ledger"),
        ("provider_contact_id", "contact"),
        ("service_contract_id", "service_contract"),
    ),
    "rent_invoice": (
        ("cancelled_by_invoice_id", "rent_invoice"),
        ("cancels_invoice_id", "rent_invoice"),
        ("contact_id", "contact"),
        ("contract_id", "contract"),
        ("document_id", "document"),
        ("legal_entity_id", "legal_entity"),
    ),
    "rent_invoice_number_counter": (("legal_entity_id", "legal_entity"),),
    "reserve_statement": (
        ("hoa_statement_id", "hoa_statement"),
        ("ledger_id", "ledger"),
        ("resolution_id", "resolution"),
    ),
    "resolution": (
        ("document_id", "document"),
        ("enabling_resolution_id", "resolution"),
        ("legal_entity_id", "legal_entity"),
    ),
    "section35a_certificate_log": (
        ("contract_id", "contract"),
        ("document_id", "document"),
    ),
    "sepa_mandate": (
        ("contact_bank_account_id", "contact_bank_account"),
        ("legal_entity_id", "legal_entity"),
        ("party_id", "party"),
    ),
    "service_contract": (
        ("property_id", "property"),
        ("provider_contact_id", "contact"),
    ),
    "special_levy": (
        ("account_id", "ledger_account"),
        ("allocation_key_id", "allocation_key"),
        ("ledger_id", "ledger"),
        ("legal_entity_id", "legal_entity"),
        ("resolution_id", "resolution"),
        ("revenue_account_id", "ledger_account"),
        ("supersedes_id", "special_levy"),
    ),
    "statement": (
        ("deadline_exception_document_id", "document"),
        ("ledger_id", "ledger"),
        ("property_id", "property"),
        ("supersedes_id", "statement"),
    ),
    "statement_advance_proposal": (("statement_id", "statement"),),
    "statement_cost_item": (
        ("account_id", "ledger_account"),
        ("allocation_key_id", "allocation_key"),
        ("statement_id", "statement"),
    ),
    "statement_event": (("statement_id", "statement"),),
    "statement_heating": (
        ("applied_item_id", "statement_cost_item"),
        ("statement_id", "statement"),
    ),
    "statement_inspection": (
        ("contract_id", "contract"),
        ("statement_id", "statement"),
    ),
    "statement_result": (
        ("contract_id", "contract"),
        ("document_id", "document"),
        ("evidence_document_id", "document"),
        ("statement_id", "statement"),
    ),
    "statement_snapshot": (("statement_id", "statement"),),
    "supplier_tax_profile": (
        ("contact_id", "contact"),
        ("exemption_document_id", "document"),
    ),
}

GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION mhvp_tenant_fk_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  i integer := 0;
  col text;
  parent text;
  ref uuid;
  ref_tenant uuid;
BEGIN
  WHILE i < TG_NARGS LOOP
    col := TG_ARGV[i];
    parent := TG_ARGV[i + 1];
    i := i + 2;
    ref := (to_jsonb(NEW) ->> col)::uuid;
    CONTINUE WHEN ref IS NULL;
    IF TG_OP = 'UPDATE' AND ref IS NOT DISTINCT FROM (to_jsonb(OLD) ->> col)::uuid
       AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id THEN
      CONTINUE;
    END IF;
    EXECUTE format('SELECT tenant_id FROM public.%I WHERE id = $1', parent)
      INTO ref_tenant USING ref;
    IF ref_tenant IS DISTINCT FROM NEW.tenant_id THEN
      RAISE EXCEPTION 'tenant foreign key violation: %.% references % of another tenant',
        TG_TABLE_NAME, col, parent
        USING ERRCODE = '23503', CONSTRAINT = 'mhvp_tenant_fk';
    END IF;
  END LOOP;
  RETURN NEW;
END $$
"""


def _check_existing_data() -> None:
    """Abort on cross tenant references in existing rows (never delete or repair data)."""
    tables = sorted(set(GUARDED) | {p for refs in GUARDED.values() for _, p in refs})
    # The migrator is subject to FORCE RLS and would see no rows: lift it inside this
    # transaction for the check only and restore it right after (pattern 0398).
    for table in tables:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    bind = op.get_bind()
    violations = []
    for table, refs in GUARDED.items():
        for col, parent in refs:
            count = bind.execute(sa.text(violation_count_sql(table, col, parent))).scalar()
            if count:
                violations.append(f"{table}.{col} -> {parent}: {count}")
    for table in tables:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    if violations:
        raise RuntimeError(
            "0460 aborted: existing rows reference rows of another tenant; clarify and correct "
            "them by reversal or status, never by deletion: " + "; ".join(violations)
        )


def upgrade() -> None:
    _check_existing_data()
    op.execute(GUARD_FUNCTION_SQL)
    for table, refs in GUARDED.items():
        cols = ", ".join(c for c, _ in refs)
        args = ", ".join(f"'{c}', '{p}'" for c, p in refs)
        op.execute(
            f"CREATE TRIGGER {TRIGGER_NAME} BEFORE INSERT OR UPDATE OF tenant_id, {cols} "
            f"ON public.{table} FOR EACH ROW EXECUTE FUNCTION {GUARD_FUNCTION}({args})"
        )


def downgrade() -> None:
    for table in GUARDED:
        op.execute(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON public.{table}")
    op.execute(f"DROP FUNCTION IF EXISTS {GUARD_FUNCTION}()")
