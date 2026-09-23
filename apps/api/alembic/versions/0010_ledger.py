"""accounting

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23 15:12:25.039811+00:00

Tenant tables must call mhvp.core.db.rls.tenant_rls_statements() (ADR 0002).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = (
    "chart_of_accounts_template",
    "ledger",
    "journal_number_counter",
    "journal_entry",
    "ledger_account",
    "journal_line",
    "ledger_account_allocation",
    "open_item",
    "open_item_settlement",
)
ENUMS = (
    "account_category",
    "account_type",
    "account_vat_option",
    "allocation_category",
    "deductible_vat_rule",
    "journal_entry_kind",
    "journal_entry_source",
    "journal_entry_status",
    "ledger_leading_system",
    "ledger_vat_mode",
    "open_item_kind",
    "statement_kind",
)

# Database guards (B02, B03): posted entries and their lines are immutable, lines use accounts of
# the entry's ledger, a posted entry is balanced at commit, settlements are insert only.
TRIGGERS = [
    """
    CREATE FUNCTION mhvp_journal_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        IF OLD.status = 'posted' THEN
          RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
        END IF;
        RETURN OLD;
      END IF;
      IF OLD.status = 'posted' THEN
        IF (to_jsonb(NEW) - 'reversed_by_id' - 'updated_at' - 'updated_by')
           IS DISTINCT FROM (to_jsonb(OLD) - 'reversed_by_id' - 'updated_at' - 'updated_by')
           OR (OLD.reversed_by_id IS NOT NULL
               AND NEW.reversed_by_id IS DISTINCT FROM OLD.reversed_by_id)
        THEN
          RAISE EXCEPTION 'posted journal entry % is immutable', OLD.id USING ERRCODE = 'P0001';
        END IF;
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER journal_entry_guard BEFORE UPDATE OR DELETE ON journal_entry
    FOR EACH ROW EXECUTE FUNCTION mhvp_journal_entry_guard()
    """,
    """
    CREATE FUNCTION mhvp_journal_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      entry_row journal_entry%ROWTYPE;
      account_ledger uuid;
    BEGIN
      SELECT * INTO entry_row FROM journal_entry
        WHERE id = COALESCE(NEW.journal_entry_id, OLD.journal_entry_id);
      IF entry_row.status = 'posted' THEN
        RAISE EXCEPTION 'lines of posted journal entry % are immutable', entry_row.id
          USING ERRCODE = 'P0001';
      END IF;
      IF TG_OP = 'DELETE' THEN
        RETURN OLD;
      END IF;
      SELECT ledger_id INTO account_ledger FROM ledger_account WHERE id = NEW.account_id;
      IF account_ledger IS DISTINCT FROM entry_row.ledger_id THEN
        RAISE EXCEPTION 'account % belongs to another ledger', NEW.account_id
          USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER journal_line_guard BEFORE INSERT OR UPDATE OR DELETE ON journal_line
    FOR EACH ROW EXECUTE FUNCTION mhvp_journal_line_guard()
    """,
    """
    CREATE FUNCTION mhvp_journal_entry_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      d numeric; c numeric; n integer;
    BEGIN
      IF NEW.status = 'posted' THEN
        SELECT coalesce(sum(debit), 0), coalesce(sum(credit), 0), count(*) INTO d, c, n
          FROM journal_line WHERE journal_entry_id = NEW.id;
        IF n < 2 OR d <> c THEN
          RAISE EXCEPTION 'journal entry % is not balanced (debit %, credit %, lines %)',
            NEW.id, d, c, n USING ERRCODE = 'P0001';
        END IF;
      END IF;
      RETURN NULL;
    END $$
    """,
    """
    CREATE CONSTRAINT TRIGGER journal_entry_balanced AFTER INSERT OR UPDATE ON journal_entry
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mhvp_journal_entry_balanced()
    """,
    """
    CREATE FUNCTION mhvp_insert_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION '% is insert only', TG_TABLE_NAME USING ERRCODE = 'P0001';
    END $$
    """,
    """
    CREATE TRIGGER open_item_settlement_insert_only BEFORE UPDATE OR DELETE
    ON open_item_settlement FOR EACH ROW EXECUTE FUNCTION mhvp_insert_only()
    """,
    """
    CREATE FUNCTION mhvp_open_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' OR NEW.amount <> OLD.amount OR NEW.account_id <> OLD.account_id
         OR NEW.journal_entry_id <> OLD.journal_entry_id OR NEW.ledger_id <> OLD.ledger_id THEN
        RAISE EXCEPTION 'open item % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER open_item_guard BEFORE UPDATE OR DELETE ON open_item
    FOR EACH ROW EXECUTE FUNCTION mhvp_open_item_guard()
    """,
]
FUNCTIONS = (
    "mhvp_journal_entry_guard",
    "mhvp_journal_line_guard",
    "mhvp_journal_entry_balanced",
    "mhvp_insert_only",
    "mhvp_open_item_guard",
)


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "chart_of_accounts_template",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("released", sa.Boolean(), nullable=False),
        sa.Column("released_by", sa.UUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_chart_of_accounts_template_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chart_of_accounts_template")),
        sa.UniqueConstraint(
            "tenant_id",
            "code",
            "version",
            name=op.f("uq_chart_of_accounts_template_tenant_id_code_version"),
        ),
    )
    op.create_table(
        "ledger",
        sa.Column("legal_entity_id", sa.UUID(), nullable=False),
        sa.Column("property_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=400), nullable=False),
        sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False),
        sa.Column("vat_mode", sa.Enum("none", "option", name="ledger_vat_mode"), nullable=False),
        sa.Column("locked_until", sa.Date(), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column(
            "leading_system",
            sa.Enum("immoware24", "mhvp", name="ledger_leading_system"),
            nullable=False,
        ),
        sa.Column("migration_cutoff", sa.Date(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "fiscal_year_start_month BETWEEN 1 AND 12",
            name=op.f("ck_ledger_fiscal_year_start_month_range"),
        ),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entity.id"],
            name=op.f("fk_ledger_legal_entity_id_legal_entity"),
        ),
        sa.ForeignKeyConstraint(
            ["property_id"], ["property.id"], name=op.f("fk_ledger_property_id_property")
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["chart_of_accounts_template.id"],
            name=op.f("fk_ledger_template_id_chart_of_accounts_template"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_ledger_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger")),
        sa.UniqueConstraint(
            "tenant_id", "legal_entity_id", name=op.f("uq_ledger_tenant_id_legal_entity_id")
        ),
    )
    op.create_table(
        "journal_number_counter",
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledger.id"],
            name=op.f("fk_journal_number_counter_ledger_id_ledger"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_journal_number_counter_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ledger_id", "fiscal_year", name=op.f("pk_journal_number_counter")),
    )
    op.create_table(
        "journal_entry",
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column(
            "status", sa.Enum("draft", "posted", name="journal_entry_status"), nullable=False
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("accrual_date", sa.Date(), nullable=True),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "receivable",
                "invoice",
                "custom",
                "bank_transfer",
                "cost_transfer",
                "opening_balance",
                "debtor_payment",
                "creditor_payment",
                "reversal",
                "statement_result",
                "dunning_fee",
                "interest",
                name="journal_entry_kind",
            ),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("bank_transaction_id", sa.UUID(), nullable=True),
        sa.Column("invoice_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("reverses_id", sa.UUID(), nullable=True),
        sa.Column("reversed_by_id", sa.UUID(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "auto_receivable",
                "bank_import",
                "ai",
                "statement",
                "migration",
                name="journal_entry_source",
            ),
            nullable=False,
        ),
        sa.Column("ai_proposal_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("settlement_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by", sa.UUID(), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(status = 'draft' AND number IS NULL) OR (status = 'posted' AND number IS NOT NULL)",
            name=op.f("ck_journal_entry_number_when_posted"),
        ),
        sa.CheckConstraint(
            "kind <> 'reversal' OR reverses_id IS NOT NULL",
            name=op.f("ck_journal_entry_reversal_ref"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_proposal_id"],
            ["ai_proposal.id"],
            name=op.f("fk_journal_entry_ai_proposal_id_ai_proposal"),
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f("fk_journal_entry_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document.id"], name=op.f("fk_journal_entry_document_id_document")
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"], ["ledger.id"], name=op.f("fk_journal_entry_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["reversed_by_id"],
            ["journal_entry.id"],
            name=op.f("fk_journal_entry_reversed_by_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            ["journal_entry.id"],
            name=op.f("fk_journal_entry_reverses_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_journal_entry_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry")),
        sa.UniqueConstraint("ledger_id", "id", name="uq_journal_entry_ledger_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "ledger_id",
            "fiscal_year",
            "number",
            name=op.f("uq_journal_entry_tenant_id_ledger_id_fiscal_year_number"),
        ),
    )
    op.create_index(
        "uq_journal_entry_idempotency",
        "journal_entry",
        ["tenant_id", "ledger_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_journal_entry_reverses",
        "journal_entry",
        ["reverses_id"],
        unique=True,
        postgresql_where=sa.text("reverses_id IS NOT NULL"),
    )
    op.create_table(
        "ledger_account",
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(length=6), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "bank",
                "cash",
                "reserve",
                "loan",
                "technical",
                "revenue",
                "cost",
                "debtor",
                "creditor",
                "transit",
                "tax",
                "opening_balance",
                name="account_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum("asset", "liability", "income", "expense", name="account_type"),
            nullable=False,
        ),
        sa.Column(
            "vat_option",
            sa.Enum("none", "full", "reduced", name="account_vat_option"),
            nullable=False,
        ),
        sa.Column(
            "deductible_vat_rule",
            sa.Enum("none", "fixed_percent", "commercial_share", name="deductible_vat_rule"),
            nullable=False,
        ),
        sa.Column("deductible_vat_percent", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("relevant_for_cash_report", sa.Boolean(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("booking_texts", postgresql.ARRAY(sa.String(length=200)), nullable=False),
        sa.Column(
            "allocation_category",
            sa.Enum(
                "allocable_heating",
                "allocable_water",
                "allocable_other",
                "non_allocable_heating",
                "non_allocable_water",
                "non_allocable_other",
                "none",
                name="allocation_category",
            ),
            nullable=False,
        ),
        sa.Column(
            "statement_kind",
            sa.Enum("hoa_fee", "reserve", "operating_costs", "none", name="statement_kind"),
            nullable=False,
        ),
        sa.Column("section_35a_eligible", sa.Boolean(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("party_id", sa.UUID(), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("property_bank_account_id", sa.UUID(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "number ~ '^[0-9]{6}$'", name=op.f("ck_ledger_account_number_six_digits")
        ),
        sa.CheckConstraint(
            "deductible_vat_percent IS NULL OR deductible_vat_percent BETWEEN 0 AND 100",
            name=op.f("ck_ledger_account_deductible_vat_percent_range"),
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contact.id"], name=op.f("fk_ledger_account_contact_id_contact")
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f("fk_ledger_account_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"],
            ["ledger.id"],
            name=op.f("fk_ledger_account_ledger_id_ledger"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"], ["party.id"], name=op.f("fk_ledger_account_party_id_party")
        ),
        sa.ForeignKeyConstraint(
            ["property_bank_account_id"],
            ["property_bank_account.id"],
            name=op.f("fk_ledger_account_property_bank_account_id_property_bank_account"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_ledger_account_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["unit.id"], name=op.f("fk_ledger_account_unit_id_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_account")),
        sa.UniqueConstraint("ledger_id", "id", name="uq_ledger_account_ledger_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "ledger_id",
            "number",
            name=op.f("uq_ledger_account_tenant_id_ledger_id_number"),
        ),
    )
    op.create_table(
        "journal_line",
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("debit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("credit", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("vat_percent", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("vat_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("net_amount", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("cost_center", sa.String(length=50), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("allocation_key_override_id", sa.UUID(), nullable=True),
        sa.Column("text", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name=op.f("ck_journal_line_one_side_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_account.id"],
            name=op.f("fk_journal_line_account_id_ledger_account"),
        ),
        sa.ForeignKeyConstraint(
            ["allocation_key_override_id"],
            ["allocation_key.id"],
            name=op.f("fk_journal_line_allocation_key_override_id_allocation_key"),
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_journal_line_journal_entry_id_journal_entry"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_journal_line_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"], ["unit.id"], name=op.f("fk_journal_line_unit_id_unit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_line")),
    )
    op.create_table(
        "ledger_account_allocation",
        sa.Column("ledger_account_id", sa.UUID(), nullable=False),
        sa.Column("allocation_key_id", sa.UUID(), nullable=False),
        sa.Column("share_percent", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "share_percent > 0 AND share_percent <= 100",
            name=op.f("ck_ledger_account_allocation_share_range"),
        ),
        sa.ForeignKeyConstraint(
            ["allocation_key_id"],
            ["allocation_key.id"],
            name=op.f("fk_ledger_account_allocation_allocation_key_id_allocation_key"),
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_account.id"],
            name=op.f("fk_ledger_account_allocation_ledger_account_id_ledger_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_ledger_account_allocation_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_account_allocation")),
        sa.UniqueConstraint(
            "tenant_id",
            "ledger_account_id",
            "allocation_key_id",
            name=op.f("uq_ledger_account_allocation_tenant_id_ledger_account_id_allocation_key_id"),
        ),
    )
    op.create_table(
        "open_item",
        sa.Column("ledger_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Enum("receivable", "payable", name="open_item_kind"), nullable=False),
        sa.Column("booking_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("component", sa.String(length=63), nullable=True),
        sa.Column("written_off", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_open_item_amount_positive")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_account.id"],
            name=op.f("fk_open_item_account_id_ledger_account"),
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contract.id"], name=op.f("fk_open_item_contract_id_contract")
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_open_item_journal_entry_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["ledger_id"], ["ledger.id"], name=op.f("fk_open_item_ledger_id_ledger")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_open_item_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_open_item")),
        sa.UniqueConstraint(
            "journal_entry_id", "account_id", name=op.f("uq_open_item_journal_entry_id_account_id")
        ),
    )
    op.create_table(
        "open_item_settlement",
        sa.Column("open_item_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_open_item_settlement_amount_non_zero")),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_open_item_settlement_journal_entry_id_journal_entry"),
        ),
        sa.ForeignKeyConstraint(
            ["open_item_id"],
            ["open_item.id"],
            name=op.f("fk_open_item_settlement_open_item_id_open_item"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name=op.f("fk_open_item_settlement_tenant_id_tenant"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_open_item_settlement")),
    )
    # ### end Alembic commands ###
    for table in TENANT_TABLES:
        for statement in tenant_rls_statements(table):
            op.execute(statement)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    for table, trigger in (
        ("journal_entry", "journal_entry_guard"),
        ("journal_entry", "journal_entry_balanced"),
        ("journal_line", "journal_line_guard"),
        ("open_item_settlement", "open_item_settlement_insert_only"),
        ("open_item", "open_item_guard"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    for table in TENANT_TABLES:
        for statement in drop_tenant_rls_statements(table):
            op.execute(statement)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("open_item_settlement")
    op.drop_table("open_item")
    op.drop_table("ledger_account_allocation")
    op.drop_table("journal_line")
    op.drop_table("ledger_account")
    op.drop_index(
        "uq_journal_entry_reverses",
        table_name="journal_entry",
        postgresql_where=sa.text("reverses_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_journal_entry_idempotency",
        table_name="journal_entry",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_table("journal_entry")
    op.drop_table("journal_number_counter")
    op.drop_table("ledger")
    op.drop_table("chart_of_accounts_template")
    # ### end Alembic commands ###
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
