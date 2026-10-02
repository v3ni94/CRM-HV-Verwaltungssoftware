"""Deterministic verifiers of the automation classes (plan M12 S6, rule M12-05): fixed
expectations per class, refusal reasons, chronology, account lock criteria, period lock,
evidence chain (B05) and the stability of the fingerprint (rule 0.1.8)."""

from __future__ import annotations

from datetime import date
from typing import Any

from mhvp.banking import posting_proposal as pp
from mhvp.banking import verifiers as v

RULE: dict[str, Any] = {
    "id": "r1",
    "name": "Hausgeld",
    "match": {"purpose_regex": "hausgeld"},
    "action": {"kind": "debtor_payment", "account_number": None},
    "approval_state": "active",
    "max_amount": "500.00",
    "contract_end": None,
}
ACCOUNTS = {
    "100001": v.AccountFlags("100001", "debtor"),
    "100002": v.AccountFlags("100002", "debtor"),
    "001210": v.AccountFlags("001210", "bank"),
    "001220": v.AccountFlags("001220", "bank"),
    "040100": v.AccountFlags("040100", "expense"),
    "040200": v.AccountFlags("040200", "expense", vat_option="opted"),
    "070001": v.AccountFlags("070001", "creditor"),
}


def _ctx(rule: dict[str, Any] | None = None, **kw: Any) -> v.Context:
    return v.Context(
        rule=rule or RULE,
        accounts=ACCOUNTS,
        engine_version="e1",
        rule_version="r1",
        features_hash=kw.pop("features_hash", "h" * 64),
        **kw,
    )


def _item(
    n: int, remaining: str, due: str, debtor: str = "d-1", account: str = "100001"
) -> dict[str, Any]:
    return {
        "id": f"oi-{n}",
        "kind": "receivable",
        "remaining": remaining,
        "due_date": due,
        "account_number": account,
        "debtor_key": debtor,
        "is_deposit": False,
    }


def _tx(amount: str, purpose: str = "Hausgeld März", **kw: Any) -> dict[str, Any]:
    return {
        "amount": amount,
        "purpose": purpose,
        "booking_date": kw.get("booking_date", "2026-03-05"),
        "counterpart_name": "Eigentümer",
        "counterpart_iban_fingerprint": "fp-1",
        "transaction_code": kw.get("code"),
        **{k: v_ for k, v_ in kw.items() if k not in ("booking_date", "code")},
    }


def _full(item: str, amount: str, reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "source": pp.SOURCE_MATCH,
        "kind": pp.KIND_FULL,
        "unambiguous": True,
        "splits": [{"open_item_id": item, "amount": amount}],
        "confidence": 0.85,
        "reasoning": reasons
        if reasons is not None
        else ["Vertragsnummer im Verwendungszweck", "Betrag entspricht dem offenen Betrag"],
    }


def test_debtor_full_happy_path_and_stable_fingerprint() -> None:
    items = [_item(1, "250.00", "2026-03-01")]
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=items,
        payables=[],
        ctx=_ctx(),
    )
    assert out.ok is True
    assert out.settlements == [{"open_item_id": "oi-1", "amount": "250.00"}]
    assert out.rule_id == "r1"
    assert len(out.fingerprint or "") == 64
    again = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=items,
        payables=[],
        ctx=_ctx(),
    )
    assert again.fingerprint == out.fingerprint
    other = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=items,
        payables=[],
        ctx=_ctx(features_hash="x" * 64),
    )
    assert other.fingerprint != out.fingerprint


def test_debtor_full_refuses_chronology_cap_rule_and_deposit() -> None:
    items = [_item(1, "250.00", "2026-02-01"), _item(2, "250.00", "2026-03-01")]
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-2", "250.00")],
        open_items=items,
        payables=[],
        ctx=_ctx(),
    )
    assert out.ok is False
    assert out.reasons == [
        "Chronologie: ein älterer offener Posten desselben Schuldners ist noch offen"
    ]
    out = v.verify(
        "debtor_full",
        _tx("600.00"),
        [_full("oi-1", "600.00")],
        open_items=[_item(1, "600.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(),
    )
    assert "Betrag über der Betragsgrenze der Regel" in out.reasons
    out = v.verify(
        "debtor_full",
        _tx("250.00", "Miete"),
        [_full("oi-1", "250.00")],
        open_items=[items[0]],
        payables=[],
        ctx=_ctx(),
    )
    assert "Regel trifft nicht zu" in out.reasons
    approved = {**RULE, "approval_state": "approved"}
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[items[0]],
        payables=[],
        ctx=_ctx(approved),
    )
    assert "Regel ist nicht aktiv" in out.reasons
    deposit = {**_item(1, "250.00", "2026-03-01"), "is_deposit": True}
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[deposit],
        payables=[],
        ctx=_ctx(),
    )
    assert "Kautionsposten sind ausgeschlossen" in out.reasons
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[_item(1, "250.00", "2026-04-01")],
        payables=[],
        ctx=_ctx(),
    )
    assert "Chronologie: der Posten ist am Buchungstag noch nicht fällig" in out.reasons


def test_debtor_full_no_confidence_without_unambiguous_match_and_return_excluded() -> None:
    weak = {**_full("oi-1", "250.00"), "unambiguous": False, "confidence": 0.99}
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [weak],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(),
    )
    assert out.ok is False
    assert "Kein eindeutiger Vollausgleich" in out.reasons
    out = v.verify(
        "debtor_full",
        _tx("250.00", "Rücklastschrift Hausgeld"),
        [_full("oi-1", "250.00")],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(),
    )
    assert "Rückläufer sind ausgeschlossen" in out.reasons


def test_iban_amount_and_period_hint_alone_stay_manual() -> None:
    weak_reasons = [
        "IBAN des Zahlers beim Vertragspartner hinterlegt",
        "Betrag entspricht dem offenen Betrag",
    ]
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00", weak_reasons)],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(),
    )
    assert out.ok is False
    assert "Ohne Vertragsnummer oder Mandatsreferenz bleibt der Eingang manuell" in out.reasons


def test_period_lock_is_skipped_not_refused() -> None:
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(locked_until=date(2026, 3, 31)),
    )
    assert out.ok is False
    assert out.skipped == "period_locked"


def test_object_lock_is_skipped_not_refused() -> None:
    """GAE-02: an active property lock (object_period) skips the case like the ledger lock."""
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=_ctx(object_locked=True),
    )
    assert out.ok is False
    assert out.skipped == "period_locked"


def test_object_lock_settled_item_ids() -> None:
    import uuid

    from mhvp.banking import object_lock

    one = uuid.uuid4()
    found = object_lock.settled_item_ids(
        [{"splits": [{"open_item_id": str(one)}, {"open_item_id": "kein-uuid"}]}, {}]
    )
    assert found == {one}


def test_account_lock_criteria_block_every_class() -> None:
    locked = {**ACCOUNTS, "100001": v.AccountFlags("100001", "debtor", section_35a_eligible=True)}
    ctx = _ctx()
    ctx.accounts = locked
    out = v.verify(
        "debtor_full",
        _tx("250.00"),
        [_full("oi-1", "250.00")],
        open_items=[_item(1, "250.00", "2026-03-01")],
        payables=[],
        ctx=ctx,
    )
    assert out.reasons == ["Konto 100001 ist § 35a relevant"]
    draft = v.AccountFlags("040100", "expense", review_status="entwurf", deductible_vat_rule="full")
    assert draft.lock_reasons() == [
        "Konto 040100 hat eine Vorsteuerregel",
        "Konto 040100 ist ein Kontenrahmen-Entwurf",
    ]
    assert v.AccountFlags("001300", "asset", name="Kautionskonto").lock_reasons() == [
        "Konto 001300 ist ein Kautionskonto"
    ]


def _invoice_proposal() -> dict[str, Any]:
    return {
        "source": pp.SOURCE_INVOICE,
        "kind": pp.KIND_INVOICE,
        "unambiguous": True,
        "account_number": "070001",
        "splits": [{"open_item_id": "inv-1", "amount": "1190.00"}],
        "evidence": {"lines": [{"account_number": "040100"}]},
        "confidence": 0.9,
    }


CREDITOR_RULE = {
    **RULE,
    "match": {"counterpart_iban_fingerprint": "fp-1"},
    "action": {"kind": "creditor_payment", "account_number": "070001"},
    "max_amount": "2000.00",
}


def test_creditor_invoice_takes_accounts_from_the_invoice() -> None:
    payables = [{"id": "inv-1", "remaining": "1190.00", "payee_iban_fingerprint": "fp-1"}]
    out = v.verify(
        "creditor_invoice",
        _tx("-1190.00", "RE 1"),
        [_invoice_proposal()],
        open_items=[],
        payables=payables,
        ctx=_ctx(CREDITOR_RULE),
    )
    assert out.ok is True
    assert out.settlements == [{"open_item_id": "inv-1", "amount": "1190.00"}]
    wrong = [{"id": "inv-1", "remaining": "1000.00", "payee_iban_fingerprint": "fp-1"}]
    out = v.verify(
        "creditor_invoice",
        _tx("-1190.00", "RE 1"),
        [_invoice_proposal()],
        open_items=[],
        payables=wrong,
        ctx=_ctx(CREDITOR_RULE),
    )
    assert "Offene Verbindlichkeit nicht mehr in Höhe des Zahlbetrags" in out.reasons
    other_iban = [{"id": "inv-1", "remaining": "1190.00", "payee_iban_fingerprint": "fp-9"}]
    out = v.verify(
        "creditor_invoice",
        _tx("-1190.00", "RE 1"),
        [_invoice_proposal()],
        open_items=[],
        payables=other_iban,
        ctx=_ctx(CREDITOR_RULE),
    )
    assert "Empfänger-IBAN weicht von der Rechnung ab" in out.reasons
    vat_line = _invoice_proposal()
    vat_line["evidence"]["lines"] = [{"account_number": "040200"}]
    out = v.verify(
        "creditor_invoice",
        _tx("-1190.00", "RE 1"),
        [vat_line],
        open_items=[],
        payables=payables,
        ctx=_ctx(CREDITOR_RULE),
    )
    assert "Konto 040200 hat eine USt-Option" in out.reasons


EXPENSE_RULE = {
    **RULE,
    "match": {"counterpart_iban_fingerprint": "fp-1"},
    "action": {"kind": "posting", "account_number": "040100"},
    "max_amount": "200.00",
}


def _history(n: int, amount: str = "-80.00") -> list[dict[str, Any]]:
    return [{"accounts": ["040100"], "amount": amount, "reversed": False} for _ in range(n)]


def test_recurring_expense_needs_switch_history_band_and_evidence_chain() -> None:
    tx = _tx("-80.00", "Wartung", history=_history(3), linked_invoices=[{"invoice_id": "i1"}])
    out = v.verify("recurring_expense", tx, [], open_items=[], payables=[], ctx=_ctx(EXPENSE_RULE))
    assert out.reasons == ["Ausgangsautomatik ist nicht eingeschaltet"]
    out = v.verify(
        "recurring_expense",
        tx,
        [],
        open_items=[],
        payables=[],
        ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
    )
    assert out.ok is True
    assert out.counter_account_number == "040100"
    unbelegt = _tx("-80.00", "Wartung", history=_history(3))
    out = v.verify(
        "recurring_expense",
        unbelegt,
        [],
        open_items=[],
        payables=[],
        ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
    )
    assert out.ok is False
    assert out.clarification is True
    flagged = {**EXPENSE_RULE, "match": {**EXPENSE_RULE["match"], "no_receipt_required": True}}
    out = v.verify(
        "recurring_expense",
        unbelegt,
        [],
        open_items=[],
        payables=[],
        ctx=_ctx(flagged, outgoing_enabled=True),
    )
    assert out.ok is True
    # B05 clarification row of the movement: resolved with a document or decided by a
    # person as "kein Beleg erforderlich" completes the chain; open or undecided does not.
    for clarification, expected in [
        ({"status": "resolved", "document_id": "doc-1", "decided_by_person": True}, True),
        ({"status": "resolved", "document_id": None, "decided_by_person": True}, False),
        ({"status": "no_document_required", "document_id": None, "decided_by_person": True}, True),
        (
            {"status": "no_document_required", "document_id": None, "decided_by_person": False},
            False,
        ),
        ({"status": "in_clarification", "document_id": None, "decided_by_person": False}, False),
        ({"status": "open", "document_id": None, "decided_by_person": False}, False),
        (None, False),
    ]:
        out = v.verify(
            "recurring_expense",
            _tx("-80.00", "Wartung", history=_history(3), clarification=clarification),
            [],
            open_items=[],
            payables=[],
            ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
        )
        assert out.ok is expected, clarification
        assert out.clarification is (not expected), clarification
    off_band = _tx(
        "-150.00", "Wartung", history=_history(3), linked_invoices=[{"invoice_id": "i1"}]
    )
    out = v.verify(
        "recurring_expense",
        off_band,
        [],
        open_items=[],
        payables=[],
        ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
    )
    assert "Betrag außerhalb der beobachteten Spanne" in out.reasons
    payable = [{"id": "inv-2", "remaining": "300.00", "payee_iban_fingerprint": "fp-1"}]
    out = v.verify(
        "recurring_expense",
        tx,
        [],
        open_items=[],
        payables=payable,
        ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
    )
    assert "Offene Verbindlichkeit des Kreditors mit abweichendem Betrag" in out.reasons
    mixed = _tx(
        "-80.00",
        "Wartung",
        history=[*_history(2), {"accounts": ["040200"], "amount": "-80.00", "reversed": False}],
        linked_invoices=[{"invoice_id": "i1"}],
    )
    out = v.verify(
        "recurring_expense",
        mixed,
        [],
        open_items=[],
        payables=[],
        ctx=_ctx(EXPENSE_RULE, outgoing_enabled=True),
    )
    assert "Historie stimmt nicht mit dem Regelkonto überein" in out.reasons


TRANSFER_RULE = {
    **RULE,
    "match": {},
    "action": {"kind": "posting", "account_number": None},
    "max_amount": "10000.00",
}


def test_transfer_pair_books_against_partner_bank_account() -> None:
    tx = _tx(
        "-500.00",
        "Umbuchung Rücklage",
        transfer_pair={"partner_account_number": "001220", "partner_transaction_id": "t2"},
    )
    proposals = [
        {
            "source": pp.SOURCE_MATCH,
            "kind": pp.KIND_TRANSFER,
            "account_number": "001220",
            "confidence": 0.9,
        }
    ]
    out = v.verify(
        "transfer_pair", tx, proposals, open_items=[], payables=[], ctx=_ctx(TRANSFER_RULE)
    )
    assert out.ok is True
    assert out.counter_account_number == "001220"
    no_pair = _tx("-500.00", "Umbuchung")
    out = v.verify(
        "transfer_pair", no_pair, proposals, open_items=[], payables=[], ctx=_ctx(TRANSFER_RULE)
    )
    assert "Kein erkanntes Transferpaar" in out.reasons


def test_collective_and_excluded_are_never_automatic() -> None:
    assert v.verify(
        "debtor_collective", _tx("500.00"), [], open_items=[], payables=[], ctx=_ctx()
    ).reasons == ["Klasse debtor_collective wird nie automatisch gebucht"]
    assert v.verify("excluded", _tx("1.00"), [], open_items=[], payables=[], ctx=_ctx()).ok is False


def test_l1_verified_never_takes_history_or_ai() -> None:
    history = {
        "source": pp.SOURCE_HISTORY,
        "kind": "history",
        "confidence": 0.99,
        "splits": [{"open_item_id": "oi-1", "amount": "250.00"}],
    }
    ai = {
        "source": pp.SOURCE_AI,
        "kind": "full",
        "confidence": 0.99,
        "splits": [{"open_item_id": "oi-1", "amount": "250.00"}],
    }
    assert v.l1_verified("debtor_full", [history, ai], "250.00") is None
    full = _full("oi-1", "250.00")
    assert v.l1_verified("debtor_full", [history, full], "250.00") is full
    partial = {**full, "splits": [{"open_item_id": "oi-1", "amount": "100.00"}]}
    assert v.l1_verified("debtor_full", [partial], "250.00") is None
    collective = {
        "source": pp.SOURCE_MATCH,
        "kind": pp.KIND_COLLECTIVE,
        "splits": [
            {"open_item_id": "a", "amount": "100.00"},
            {"open_item_id": "b", "amount": "150.00"},
        ],
    }
    assert v.l1_verified("debtor_collective", [collective], "250.00") is collective
    transfer = {"source": pp.SOURCE_MATCH, "kind": pp.KIND_TRANSFER, "account_number": "001220"}
    assert v.l1_verified("transfer_pair", [transfer], "-500.00") is transfer
