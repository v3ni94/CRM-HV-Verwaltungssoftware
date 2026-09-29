"""M12-01 stage 1 (deterministic posting proposal) and M12-02 independent test set: the
240 synthetic cases in ``tests/ai_eval/posting_stage1/cases.json`` run through
``mhvp.banking.posting_proposal.propose``; the hit rate per class is reported and must not
drop below ``evaluate.STAGE1_THRESHOLD``. Hand written edge cases cover what the generator
does not: rule below and above its limit, approved but inactive rule, two combinations that
add up (unclear), purpose determination (D39), AI stage never postable.

Stage 1d (plan M12 S3, ADR 0014): the cases of the classes ``history``,
``recurring_expense``, ``linked_invoice`` and ``transfer_pair`` additionally fix the expected
confidence, account number, periodicity label and the absence of a source
(``test_stage1d_expectations_are_met_exactly``); the hand written cases below pin the
confidence table of the history (0,4 plus 0,1 per case, cap 0,85, halved per contradiction,
bulk 0,05, minimum two), the exclusion of ended contracts for rules and history, the
end-to-end id against an own payment order, the booking text hint and that a history
proposal is never unambiguous and never postable."""

from pathlib import Path
from typing import Any

import pytest

from mhvp.ai import evaluate
from mhvp.banking import allocation
from mhvp.banking import posting_proposal as pp

FOLDER = Path(__file__).parents[1] / "ai_eval"


def _tx(
    amount: str, purpose: str | None = None, fp: str | None = "fp-1", **kw: Any
) -> dict[str, Any]:
    return {
        "amount": amount,
        "purpose": purpose,
        "counterpart_name": kw.get("name", "Zahler"),
        "counterpart_iban_fingerprint": fp,
        "mandate_reference": kw.get("mandate"),
        "end_to_end_id": None,
        "transaction_code": kw.get("code"),
    }


def _item(n: int, remaining: str, contract: str, fp: str = "fp-1", **kw: Any) -> dict[str, Any]:
    return {
        "id": f"oi-{n}",
        "kind": "receivable",
        "remaining": remaining,
        "due_date": kw.get("due", "2026-03-01"),
        "reference": kw.get("reference"),
        "contract_number": contract,
        "mandate_reference": kw.get("mandate"),
        "party_iban_fingerprints": [fp],
        "account_number": f"1{n:04d}",
        "debtor_key": kw.get("debtor", f"d-{n}"),
        "is_deposit": kw.get("deposit", False),
    }


RULE = {
    "id": "r1",
    "name": "Hausgeld",
    "match": {"purpose_regex": "hausgeld"},
    "action": {"kind": "debtor_payment", "account_number": "1400"},
    "priority": 10,
    "approval_state": "active",
    "max_amount": "500.00",
}


def test_independent_set_has_240_cases_with_unique_ids_and_all_classes() -> None:
    cases = evaluate.load_stage1_cases(FOLDER)
    assert len(cases) == 240
    assert len({c["id"] for c in cases}) == 240
    assert {c["class"] for c in cases} == {
        "rent_with_purpose",
        "rent_without_purpose",
        "partial",
        "collective",
        "return",
        "invoice",
        "deposit",
        "unclear",
        "rule",
        "history",
        "recurring_expense",
        "linked_invoice",
        "transfer_pair",
    }


def test_stage1_hit_rate_per_class_is_reported_and_above_threshold() -> None:
    report = evaluate.evaluate_stage1(FOLDER)
    lines = [
        f"{name}: {b['hits']}/{b['cases']} ({b['hit_rate']:.0%})"
        for name, b in report["classes"].items()
    ]
    print("Trefferquote Stufe 1: " + ", ".join(lines) + f"; gesamt {report['hit_rate']:.1%}")  # noqa: T201
    assert report["cases"] == 240
    assert report["hit_rate"] >= evaluate.STAGE1_THRESHOLD, report["misses"]
    for name, bucket in report["classes"].items():
        assert bucket["hit_rate"] >= 0.8, (name, report["misses"])


def test_nothing_is_ever_postable() -> None:
    cases = evaluate.load_stage1_cases(FOLDER)
    for case in cases:
        for p in pp.propose(case["tx"], case["rules"], case["open_items"], case["payables"]):
            assert p.postable is False
            assert 0.0 <= p.confidence <= 1.0
            assert p.reasoning
            if p.source == pp.SOURCE_HISTORY:
                assert p.unambiguous is False, case["id"]


def test_stage1d_expectations_are_met_exactly() -> None:
    """The stage 1d classes fix more than the hit: confidence, account number, periodicity
    label (explanation only) and the absence of a source (rule 0.1.8)."""
    cases = [
        c
        for c in evaluate.load_stage1_cases(FOLDER)
        if c["class"] in {"history", "recurring_expense", "linked_invoice", "transfer_pair"}
    ]
    assert len(cases) == 40
    for case in cases:
        proposals = pp.propose(case["tx"], case["rules"], case["open_items"], case["payables"])
        expected = case["expected"]
        if expected.get("no_source"):
            assert all(p.source != expected["no_source"] for p in proposals), case["id"]
            continue
        got = next(p for p in proposals if p.source == expected["source"])
        assert got.kind == expected["kind"], case["id"]
        if "account_number" in expected:
            assert got.account_number == expected["account_number"], case["id"]
        if "confidence" in expected:
            assert got.confidence == expected["confidence"], (case["id"], got.reasoning)
        if "periodic" in expected:
            periodicity = (got.evidence or {}).get("periodicity")
            if expected["periodic"] is None:
                assert periodicity is None, case["id"]
                assert not any("Regelmäßig" in r for r in got.reasoning)
            else:
                assert periodicity is not None, case["id"]
                assert periodicity["interval"] == expected["periodic"], case["id"]
                assert any("Regelmäßig" in r for r in got.reasoning), case["id"]
        if got.source == pp.SOURCE_HISTORY:
            assert got.evidence is not None
            assert got.evidence["count"] >= 2
            assert all("journal_entry_id" in e for e in got.evidence["entries"])
            assert got.reasoning[0].startswith("Zuletzt ")


def _history_entry(n: int, day: str, amount: str, accounts: list[str], **kw: Any) -> dict[str, Any]:
    return {
        "decision_id": f"d-{n}",
        "journal_entry_id": f"je-{n}",
        "label": f"2026-{n}",
        "booking_date": day,
        "decided_at": f"{day}T09:00:00+00:00",
        "amount": amount,
        "accounts": accounts,
        "text": None,
        "reversed": kw.get("reversed", False),
        "bulk": kw.get("bulk", False),
        "key": kw.get("key", "iban"),
        "contract_end": kw.get("contract_end"),
    }


def _with_history(tx: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    return {**tx, "booking_date": "2026-06-05", "history": history}


def _history_of(proposals: list[pp.Proposal]) -> pp.Proposal | None:
    return next((p for p in proposals if p.source == pp.SOURCE_HISTORY), None)


@pytest.mark.parametrize(
    ("consistent", "contradictions", "expected"),
    [
        (1, 0, None),
        (2, 0, 0.6),
        (3, 0, 0.7),
        (4, 0, 0.8),
        (5, 0, 0.85),
        (9, 0, 0.85),
        (2, 1, 0.3),
        (3, 1, 0.35),
        (4, 2, 0.2),
        (2, 3, 0.08),
    ],
)
def test_history_confidence_table(
    consistent: int, contradictions: int, expected: float | None
) -> None:
    days = [f"2026-0{1 + k % 9}-{1 + k // 9:02d}" for k in range(consistent)]
    history = [_history_entry(k, days[k], "-100.00", ["4210"]) for k in range(consistent)]
    history += [
        _history_entry(90 + k, "2025-12-01", "-100.00", ["4300"]) for k in range(contradictions)
    ]
    got = _history_of(pp.propose(_with_history(_tx("-100.00", "Abschlag", "cred"), history)))
    if expected is None:
        assert got is None
    else:
        assert got is not None
        assert got.confidence == expected
        assert got.account_number == "4210"
        assert got.unambiguous is False
        assert got.evidence is not None
        assert got.evidence == {
            **got.evidence,
            "count": consistent,
            "contradictions": contradictions,
        }


def test_history_reversal_is_a_counter_example_and_last_pattern_wins() -> None:
    history = [
        _history_entry(1, "2026-01-05", "-100.00", ["4210"]),
        _history_entry(2, "2026-02-05", "-100.00", ["4210"]),
        _history_entry(3, "2026-03-05", "-100.00", ["4210"], reversed=True),
    ]
    got = _history_of(pp.propose(_with_history(_tx("-100.00", None, "cred"), history)))
    assert got is not None
    assert got.confidence == 0.3  # 0.6 halved by the reversal of the same pattern
    assert any("storniert" in r for r in got.reasoning)
    assert [e["reversed"] for e in (got.evidence or {})["entries"]] == [False, False, True]
    # The last confirmed pattern is proposed even when older bookings differ.
    history = [
        _history_entry(1, "2026-01-05", "-100.00", ["4210"]),
        _history_entry(2, "2026-02-05", "-100.00", ["4300"]),
        _history_entry(3, "2026-03-05", "-100.00", ["4300"]),
    ]
    got = _history_of(pp.propose(_with_history(_tx("-100.00", None, "cred"), history)))
    assert got is not None
    assert got.account_number == "4300"
    assert got.confidence == 0.3  # two consistent, one contradiction
    # A reversed booking of another pattern is neither evidence nor contradiction.
    history[0]["reversed"] = True
    got = _history_of(pp.propose(_with_history(_tx("-100.00", None, "cred"), history)))
    assert got is not None
    assert got.confidence == 0.6


def test_history_bulk_weight_split_pattern_and_creditor_id_reason() -> None:
    history = [
        _history_entry(1, "2026-01-05", "-100.00", ["4210", "4300"], bulk=True),
        _history_entry(2, "2026-02-05", "-100.00", ["4300", "4210"], bulk=True),
        _history_entry(3, "2026-03-05", "-100.00", ["4210", "4300"], key="creditor_id"),
    ]
    got = _history_of(pp.propose(_with_history(_tx("-100.00", None, "cred"), history)))
    assert got is not None
    assert got.confidence == 0.6  # 0.4 + 0.1 * (0.5 + 0.5 + 1)
    assert got.account_number == "4210"
    assert (got.evidence or {})["accounts"] == ["4210", "4300"]
    assert any("Aufteilung auf 2 Konten" in r for r in got.reasoning)
    assert any("Gläubiger-ID" in r for r in got.reasoning)
    assert any("geringerem Gewicht" in r for r in got.reasoning)


def test_history_incoming_names_the_open_item_only_when_exactly_one_fits() -> None:
    history = [_history_entry(k, f"2026-0{k + 1}-05", "500.00", ["10001"]) for k in range(3)]
    items = [
        _item(1, "500.00", "MV-1", fp="fp-x"),
        _item(2, "500.00", "MV-2", fp="fp-y"),
    ]
    items[0]["account_number"] = "10001"
    got = _history_of(pp.propose(_with_history(_tx("500.00", None, "fp-z"), history), [], items))
    assert got is not None
    assert got.splits == [{"open_item_id": "oi-1", "amount": "500.00"}]
    items[1]["account_number"] = "10001"
    got = _history_of(pp.propose(_with_history(_tx("500.00", None, "fp-z"), history), [], items))
    assert got is not None
    assert got.splits == []


def test_ended_contract_excludes_history_and_rules() -> None:
    history = [
        _history_entry(k, f"2026-0{k + 1}-05", "500.00", ["10001"], contract_end="2026-04-30")
        for k in range(3)
    ]
    assert _history_of(pp.propose(_with_history(_tx("500.00", None, "fp"), history))) is None
    history[0]["contract_end"] = None
    history[1]["contract_end"] = "2026-06-05"  # ends on the booking date: still valid
    got = _history_of(pp.propose(_with_history(_tx("500.00", None, "fp"), history)))
    assert got is not None
    assert (got.evidence or {})["count"] == 2
    rule = {**RULE, "contract_end": "2026-05-31"}
    tx = {**_tx("300.00", "Hausgeld WE-7"), "booking_date": "2026-06-05"}
    assert all(p.source != "rule" for p in pp.propose(tx, [rule], [_item(1, "300.00", "WE-7")]))
    rule["contract_end"] = "2026-06-05"
    assert pp.propose(tx, [rule], [_item(1, "300.00", "WE-7")])[0].source == "rule"


def test_periodicity_is_explanation_only() -> None:
    history = [
        _history_entry(k, day, "-90.00", ["4210"])
        for k, day in enumerate(["2026-01-03", "2026-04-02", "2026-07-01", "2026-10-01"])
    ]
    got = _history_of(pp.propose(_with_history(_tx("-90.00", None, "cred"), history)))
    assert got is not None
    assert got.confidence == 0.8  # four cases, the regularity adds nothing
    assert (got.evidence or {})["periodicity"] == {
        "interval": "vierteljährlich",
        "median_days": 90,
        "count": 4,
        "first_booking_date": "2026-01-03",
        "last_booking_date": "2026-10-01",
        "amount_min": "90.00",
        "amount_max": "90.00",
    }
    assert any(r.startswith("Regelmäßig etwa vierteljährlich") for r in got.reasoning)


def test_linked_invoice_carries_creditor_account_and_lines() -> None:
    linked = {
        "invoice_id": "inv-9",
        "number": "RE-9",
        "gross": "119.00",
        "posted": True,
        "match_basis": "amount_and_number",
        "creditor_account_number": "70001",
        "open_item_id": "oi-9",
        "remaining": "119.00",
        "lines": [{"account_number": "4210", "name": "Reinigung", "net": "100.00", "text": None}],
    }
    tx = {**_tx("-119.00", "RE-9", "c1"), "linked_invoices": [linked]}
    got = next(p for p in pp.propose(tx) if p.source == pp.SOURCE_INVOICE)
    assert (got.kind, got.confidence, got.unambiguous, got.account_number) == (
        "invoice",
        0.9,
        True,
        "70001",
    )
    assert got.splits == [{"open_item_id": "oi-9", "amount": "119.00"}]
    assert (got.evidence or {})["lines"][0]["account_number"] == "4210"
    assert any("Kontierung der Rechnung: 4210 100,00 EUR" in r for r in got.reasoning)
    # IBAN based link: review, never unambiguous; partial remaining: split limited.
    tx["linked_invoices"] = [{**linked, "match_basis": "amount_and_iban", "remaining": "50.00"}]
    got = next(p for p in pp.propose(tx) if p.source == pp.SOURCE_INVOICE)
    assert (got.confidence, got.unambiguous) == (0.7, False)
    assert got.splits == [{"open_item_id": "oi-9", "amount": "50.00"}]
    # Two linked invoices: unclear.
    tx["linked_invoices"] = [linked, {**linked, "invoice_id": "inv-10"}]
    got = next(p for p in pp.propose(tx) if p.source == pp.SOURCE_INVOICE)
    assert got.kind == "unclear"
    # Unposted invoices are ignored (never a learning source).
    tx["linked_invoices"] = [{**linked, "posted": False}]
    assert all(p.source != pp.SOURCE_INVOICE for p in pp.propose(tx))


def test_end_to_end_id_of_own_payment_order_identifies_the_payable() -> None:
    payables = [
        {
            "id": "inv-1",
            "invoice_id": "i-1",
            "remaining": "119.00",
            "number": "RE-1",
            "payee_iban_fingerprint": "c1",
            "account_number": "70001",
        },
        {
            "id": "inv-2",
            "invoice_id": "i-2",
            "remaining": "119.00",
            "number": "RE-2",
            "payee_iban_fingerprint": "c1",
            "account_number": "70001",
        },
    ]
    tx = {**_tx("-119.00", "Zahlung", "c1"), "end_to_end_id": "E2E-7"}
    (p,) = pp.propose(tx, [], [], payables)
    assert p.kind == "unclear"
    tx["payment_order"] = {"id": "po", "end_to_end_id": "E2E-7", "invoice_id": "i-2"}
    (p,) = pp.propose(tx, [], [], payables)
    assert (p.kind, p.unambiguous, p.splits[0]["open_item_id"]) == ("invoice", True, "inv-2")
    assert "End-to-End-Referenz des eigenen Zahlungsauftrags" in p.reasoning
    tx["payment_order"] = {"id": "po", "end_to_end_id": "OTHER", "invoice_id": "i-2"}
    (p,) = pp.propose(tx, [], [], payables)
    assert p.kind == "unclear"


def test_booking_text_hint_only_for_exactly_one_account() -> None:
    texts = [
        {"account_number": "4210", "name": "Reinigung", "booking_texts": ["Reinigung"]},
        {"account_number": "4220", "name": "Winterdienst", "booking_texts": ["Winterdienst"]},
    ]
    tx = {**_tx("-80.00", "Gebäudereinigung März", "c9"), "account_texts": texts}
    hint = next(p for p in pp.propose(tx) if p.kind == pp.KIND_ACCOUNT_TEXT)
    assert (hint.confidence, hint.account_number, hint.unambiguous) == (0.3, "4210", False)
    tx["purpose"] = "Reinigung und Winterdienst"
    assert all(p.kind != pp.KIND_ACCOUNT_TEXT for p in pp.propose(tx))
    tx["purpose"] = "Abschlag"
    assert all(p.kind != pp.KIND_ACCOUNT_TEXT for p in pp.propose(tx))


def test_transfer_pair_proposes_the_partner_bank_account() -> None:
    tx = {
        **_tx("2500.00", "Umbuchung", "own"),
        "transfer_pair": {"partner_transaction_id": "tx-2", "partner_account_number": "1210"},
    }
    first, *_rest = pp.propose(tx, [], [_item(1, "2500.00", "MV-1", fp="own")])
    assert (first.kind, first.account_number, first.confidence, first.unambiguous) == (
        "transfer",
        "1210",
        0.9,
        False,
    )
    assert first.splits == []
    top = pp.best(pp.propose(tx))
    assert top is not None
    assert top.kind == "transfer"


def test_active_rule_carries_account_and_split_and_limit_lowers_confidence() -> None:
    items = [_item(1, "300.00", "WE-7")]
    rule, match = pp.propose(_tx("300.00", "Hausgeld WE-7"), [RULE], items)
    assert (rule.source, rule.kind, rule.account_number, rule.rule_id) == (
        "rule",
        "debtor_payment",
        "1400",
        "r1",
    )
    assert rule.confidence == 0.9
    assert rule.splits == [{"open_item_id": "oi-1", "amount": "300.00"}]
    assert match.unambiguous
    assert match.kind == "full"
    over = pp.propose(_tx("800.00", "Hausgeld WE-7"), [RULE], [_item(1, "800.00", "WE-7")])[0]
    assert over.confidence == 0.5
    assert any("Betragsgrenze" in r for r in over.reasoning)
    inactive = pp.propose(
        _tx("300.00", "Hausgeld WE-7"), [{**RULE, "approval_state": "approved"}], items
    )[0]
    assert inactive.confidence == 0.6
    assert (
        pp.propose(_tx("300.00", "Hausgeld WE-7"), [{**RULE, "approval_state": "proposed"}], items)[
            0
        ].source
        == "match"
    )


def test_iban_and_amount_alone_is_weak_and_never_unambiguous() -> None:
    (p,) = pp.propose(
        _tx("500.00", None), [], [_item(1, "500.00", "MV-1"), _item(2, "600.00", "MV-2", fp="fp-9")]
    )
    assert (p.kind, p.unambiguous, p.confidence) == ("weak", False, 0.3)
    assert p.splits == [{"open_item_id": "oi-1", "amount": "500.00"}]


def test_two_combinations_adding_up_are_unclear() -> None:
    items = [
        _item(1, "200.00", "MV-1", debtor="a"),
        _item(2, "300.00", "MV-1", debtor="a"),
        _item(3, "500.00", "MV-1", debtor="a"),
        _item(4, "250.00", "MV-1", debtor="a"),
        _item(5, "250.00", "MV-1", debtor="a"),
    ]
    (p,) = pp.propose(_tx("500.00", "Miete MV-1 Nachzahlung"), [], items)
    assert p.kind == "full"  # one strong item settles in full: preferred over any combination
    (p,) = pp.propose(_tx("500.00", "Miete MV-1 Nachzahlung"), [], items[:2] + items[3:])
    assert p.kind == "unclear"


def test_purpose_determination_prefers_the_named_month() -> None:
    items = [
        _item(1, "700.00", "MV-3", due="2026-01-01", debtor="a"),
        _item(2, "700.00", "MV-3", due="2026-02-01", debtor="a"),
    ]
    (p,) = pp.propose(_tx("700.00", "Miete Februar MV-3"), [], items)
    assert p.kind == "full"
    assert p.splits[0]["open_item_id"] == "oi-2"
    assert allocation.REASON_DETERMINED in p.reasoning


def test_return_and_deposit_stay_review_cases() -> None:
    (p,) = pp.propose(_tx("-500.00", "Miete MV-1", code="RTRN"), [], [_item(1, "500.00", "MV-1")])
    assert p.kind == "return"
    assert not p.splits
    assert not p.unambiguous
    (p,) = pp.propose(
        _tx("1500.00", "Kaution MV-1"),
        [],
        [_item(1, "500.00", "MV-1"), _item(2, "1500.00", "MV-1", deposit=True)],
    )
    assert p.kind == "deposit"
    assert p.splits[0]["open_item_id"] == "oi-2"
    assert not p.unambiguous


@pytest.mark.parametrize("purpose", ["RE-2026-7 Wartung", "Rechnung RE-2026-7"])
def test_invoice_number_and_amount_identify_the_payable(purpose: str) -> None:
    payables = [
        {
            "id": "inv-1",
            "remaining": "119.00",
            "number": "RE-2026-7",
            "payee_iban_fingerprint": "c1",
            "account_number": "6000",
        },
        {
            "id": "inv-2",
            "remaining": "119.00",
            "number": "RE-2026-8",
            "payee_iban_fingerprint": "c1",
            "account_number": "6000",
        },
    ]
    (p,) = pp.propose(_tx("-119.00", purpose, fp="c1"), [], [], payables)
    assert p.kind == "invoice"
    assert p.unambiguous
    assert p.splits[0]["open_item_id"] == "inv-1"
    (p,) = pp.propose(_tx("-119.00", "Abschlag", fp="c1"), [], [], payables)
    assert p.kind == "unclear"  # two invoices with the same IBAN and amount
