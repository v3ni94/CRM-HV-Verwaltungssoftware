"""M12-01 stage 1 (deterministic posting proposal) and M12-02 independent test set: the
200 synthetic cases in ``tests/ai_eval/posting_stage1/cases.json`` run through
``mhvp.banking.posting_proposal.propose``; the hit rate per class is reported and must not
drop below ``evaluate.STAGE1_THRESHOLD``. Hand written edge cases cover what the generator
does not: rule below and above its limit, approved but inactive rule, two combinations that
add up (unclear), purpose determination (D39), AI stage never postable."""

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


def test_independent_set_has_200_cases_with_unique_ids_and_all_classes() -> None:
    cases = evaluate.load_stage1_cases(FOLDER)
    assert len(cases) == 200
    assert len({c["id"] for c in cases}) == 200
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
    }


def test_stage1_hit_rate_per_class_is_reported_and_above_threshold() -> None:
    report = evaluate.evaluate_stage1(FOLDER)
    lines = [
        f"{name}: {b['hits']}/{b['cases']} ({b['hit_rate']:.0%})"
        for name, b in report["classes"].items()
    ]
    print("Trefferquote Stufe 1: " + ", ".join(lines) + f"; gesamt {report['hit_rate']:.1%}")  # noqa: T201
    assert report["cases"] == 200
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
