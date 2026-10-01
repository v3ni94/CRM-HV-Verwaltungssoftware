"""AE22 (Q01-01): conservative defaults and the source key of payables from statement credits."""

import uuid
from datetime import date
from decimal import Decimal

from mhvp.accounting import credit_payables as cp
from mhvp.accounting.credit_payable_models import MODES, PAYOUT_REASON, SOURCE_TYPES
from mhvp.accounting.models import EntryKind
from mhvp.accounting.services import OPEN_ITEM_KINDS


def test_default_setting_is_off_with_four_eyes() -> None:
    out = cp.setting_out(None)
    assert out["mode"] == "off"
    assert out["four_eyes_required"] is True
    assert out["creditor_account_number"] is None
    assert out["decision_ref"] == "Q01-01"
    assert out["modes"] == ["off", "subledger", "reclass"]
    assert MODES[0] == "off"


def test_every_source_has_a_payout_reason_of_the_payment_run() -> None:
    from mhvp.banking.payment_run import PAYOUT_REASONS

    assert set(PAYOUT_REASON) == set(SOURCE_TYPES)
    assert set(PAYOUT_REASON.values()) <= set(PAYOUT_REASONS)


def test_source_key_and_candidate_json() -> None:
    statement, contract = uuid.uuid4(), uuid.uuid4()
    assert cp.source_key("owner_statement", statement, None) == f"owner_statement:{statement}:-"
    cand = cp.Candidate(
        source_type="rent_statement",
        source_id=statement,
        contract_id=contract,
        ledger_id=uuid.uuid4(),
        amount=Decimal("80.00"),
        label="Guthaben aus Betriebskostenabrechnung 2025",
        reference_date=date(2026, 10, 1),
    )
    assert cand.key == f"rent_statement:{statement}:{contract}"
    data = cand.as_json()
    assert (data["amount"], data["payout_reason"], data["reference_date"]) == (
        "80.00",
        "statement_credit",
        "2026-10-01",
    )


def test_reclass_kind_creates_no_receivable_by_the_generic_rule() -> None:
    # The reclass entry is handled by its own branch in ``_apply_open_items`` (payable only).
    assert EntryKind.CREDIT_RECLASS not in OPEN_ITEM_KINDS
