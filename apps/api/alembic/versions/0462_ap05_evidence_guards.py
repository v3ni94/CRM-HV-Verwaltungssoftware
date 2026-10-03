"""AP05 (GAL-104 to GAL-107): evidence guards, author columns and CHECKs.

* GAL-104: insert-only triggers (pattern 0444) for ``approval_decision`` (only a first
  invalidation: status, time and reason), ``migrated_journal_line``, ``statement_event``,
  ``hoa_reserve_movement`` (changeable only while its statement is a draft) and
  ``bank_transaction`` (amount, date and reference fields frozen, no delete).
  ``open_item_settlement`` and ``audit_log`` already carry insert-only triggers.
* GAL-105: ``created_at/updated_at/created_by/updated_by`` on ``hoa_reserve_movement``,
  ``economic_plan_item``, ``hoa_cost_item``, ``invoice_line``, ``role_permission`` and
  ``membership_role``.
* GAL-106: period CHECK and value lists on ``access_grant``; period CHECK on ``license`` and
  ``property_notice``.
* GAL-107: from ``resolved`` on ``resolution_id`` is mandatory (``economic_plan``,
  ``hoa_statement``, ``reserve_statement``); an ``active`` ``bank_rule`` needs approval, limit
  and test evidence.

CHECKs are added NOT VALID and validated only when no existing row violates them; the
violation count is logged (pattern 0449). FORCE RLS is lifted per table for the count only.

Revision ID: 0462
Revises: 0461
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0462"
down_revision: str | None = "0461"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOG = logging.getLogger("alembic.runtime.migration")
_META = "'updated_at', 'updated_by'"

# Keep in sync with mhvp.portal.models.GRANT_* (value lists of access_grant).
_SCOPES = (
    "'unit', 'contract', 'property', 'legal_entity', 'document_class', 'tenant', "
    "'audit_engagement', 'handover'"
)
_RIGHTS = "'read', 'download', 'comment', 'edit'"
_ROLES = "'tenant', 'owner', 'board', 'provider', 'staff', 'participant', 'helper'"
_BASES = (
    "'contract', 'hoa_member_right', 'representation', 'staff_access', 'rental_owner_right', "
    "'board_audit', 'document_class_grant', 'handover_helper', 'handover_participant'"
)
_RESOLVED = (
    "status NOT IN ('resolved', 'issued', 'due', 'posted', 'locked') OR resolution_id IS NOT NULL"
)

# (table, constraint name, condition)
CHECKS: tuple[tuple[str, str, str], ...] = (
    ("access_grant", "ck_access_grant_period_order", "valid_to IS NULL OR valid_to >= valid_from"),
    ("access_grant", "ck_access_grant_scope_type_values", f"scope_type IN ({_SCOPES})"),
    ("access_grant", "ck_access_grant_right_values", f'"right" IN ({_RIGHTS})'),
    ("access_grant", "ck_access_grant_role_values", f"role IN ({_ROLES})"),
    ("access_grant", "ck_access_grant_legal_basis_values", f"legal_basis IN ({_BASES})"),
    ("license", "ck_license_period_order", "valid_until IS NULL OR valid_until >= valid_from"),
    (
        "property_notice",
        "ck_property_notice_period_order",
        "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
    ),
    ("economic_plan", "ck_economic_plan_resolved_needs_resolution", _RESOLVED),
    ("hoa_statement", "ck_hoa_statement_resolved_needs_resolution", _RESOLVED),
    ("reserve_statement", "ck_reserve_statement_resolved_needs_resolution", _RESOLVED),
    (
        "bank_rule",
        "ck_bank_rule_active_needs_release",
        "approval_state <> 'active' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL "
        "AND max_amount > 0 AND test_evidence_document_id IS NOT NULL)",
    ),
)

AUTHOR_TABLES = (
    "hoa_reserve_movement",
    "economic_plan_item",
    "hoa_cost_item",
    "invoice_line",
    "role_permission",
    "membership_role",
)

GUARDS = [
    f"""
    CREATE FUNCTION mhvp_approval_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE'
         OR OLD.invalidated_at IS NOT NULL
         OR NEW.status NOT IN (OLD.status, 'invalidated')
         OR (to_jsonb(NEW) - ARRAY['status', 'invalidated_at', 'invalidation_reason', {_META}])
            IS DISTINCT FROM
            (to_jsonb(OLD) - ARRAY['status', 'invalidated_at', 'invalidation_reason', {_META}])
      THEN
        RAISE EXCEPTION 'approval decision % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER approval_decision_guard BEFORE UPDATE OR DELETE ON approval_decision
    FOR EACH ROW EXECUTE FUNCTION mhvp_approval_decision_guard()
    """,
    """
    CREATE FUNCTION mhvp_insert_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION '% row % is immutable', TG_TABLE_NAME, OLD.id USING ERRCODE = 'P0001';
    END $$
    """,
    """
    CREATE TRIGGER migrated_journal_line_guard BEFORE UPDATE OR DELETE ON migrated_journal_line
    FOR EACH ROW EXECUTE FUNCTION mhvp_insert_only_guard()
    """,
    """
    CREATE TRIGGER statement_event_guard BEFORE UPDATE OR DELETE ON statement_event
    FOR EACH ROW EXECUTE FUNCTION mhvp_insert_only_guard()
    """,
    """
    CREATE FUNCTION mhvp_hoa_reserve_movement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      parent_status text;
    BEGIN
      -- A missing parent means the draft statement is being deleted (cascade).
      SELECT status::text INTO parent_status FROM hoa_statement WHERE id = OLD.statement_id;
      IF parent_status IS NOT NULL AND parent_status <> 'draft' THEN
        RAISE EXCEPTION 'reserve movement % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      IF TG_OP = 'DELETE' THEN
        RETURN OLD;
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER hoa_reserve_movement_guard BEFORE UPDATE OR DELETE ON hoa_reserve_movement
    FOR EACH ROW EXECUTE FUNCTION mhvp_hoa_reserve_movement_guard()
    """,
    """
    CREATE FUNCTION mhvp_bank_transaction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' OR (
           NEW.tenant_id, NEW.property_bank_account_id, NEW.booking_date, NEW.value_date,
           NEW.amount, NEW.currency, NEW.bank_reference, NEW.end_to_end_id,
           NEW.mandate_reference, NEW.hash
         ) IS DISTINCT FROM (
           OLD.tenant_id, OLD.property_bank_account_id, OLD.booking_date, OLD.value_date,
           OLD.amount, OLD.currency, OLD.bank_reference, OLD.end_to_end_id,
           OLD.mandate_reference, OLD.hash
         ) THEN
        RAISE EXCEPTION 'bank transaction % is immutable', OLD.id USING ERRCODE = 'P0001';
      END IF;
      RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER bank_transaction_guard BEFORE UPDATE OR DELETE ON bank_transaction
    FOR EACH ROW EXECUTE FUNCTION mhvp_bank_transaction_guard()
    """,
]

DROPPED = (
    ("approval_decision_guard", "approval_decision"),
    ("migrated_journal_line_guard", "migrated_journal_line"),
    ("statement_event_guard", "statement_event"),
    ("hoa_reserve_movement_guard", "hoa_reserve_movement"),
    ("bank_transaction_guard", "bank_transaction"),
)
FUNCTIONS = (
    "mhvp_approval_decision_guard",
    "mhvp_insert_only_guard",
    "mhvp_hoa_reserve_movement_guard",
    "mhvp_bank_transaction_guard",
)


def _force(table: str, on: bool) -> None:
    op.execute(f"ALTER TABLE {table} {'' if on else 'NO '}FORCE ROW LEVEL SECURITY")


def _forced(bind: sa.Connection, table: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:t)"),
            {"t": table},
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    for table in AUTHOR_TABLES:
        op.add_column(
            table,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.add_column(table, sa.Column("created_by", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("updated_by", sa.UUID(), nullable=True))
    for table, name, condition in CHECKS:
        forced = _forced(bind, table)
        if forced:
            _force(table, False)
        violations = bind.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE NOT ({condition})")  # noqa: S608
        ).scalar_one()
        if forced:
            _force(table, True)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
        if violations == 0:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
        LOG.warning("0462 %s: %s violations, validated=%s", name, violations, violations == 0)
    for statement in GUARDS:
        op.execute(statement)


def downgrade() -> None:
    # Schema only: no rows are changed, so FORCE ROW LEVEL SECURITY stays untouched.
    for trigger, table in DROPPED:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {function}()")
    for table, name, _ in reversed(CHECKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    for table in reversed(AUTHOR_TABLES):
        for column in ("updated_by", "created_by", "updated_at", "created_at"):
            op.drop_column(table, column)
