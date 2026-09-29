"""Case classes and automation levels (ADR 0014 addendum, plan M12 S4, rule M12-05): pure
functions with fixed expectations (rule 0.1.8). Nothing here touches a database."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from mhvp.banking import levels


def _p(source: str, kind: str, **kw: Any) -> dict[str, Any]:
    return {"source": source, "kind": kind, "confidence": 0.5, **kw}


@pytest.mark.parametrize(
    ("tx", "proposals", "expected"),
    [
        ({"amount": "250.00"}, [_p("match", "full", unambiguous=True)], "debtor_full"),
        ({"amount": "250.00"}, [_p("match", "full", unambiguous=False)], "excluded"),
        ({"amount": "500.00"}, [_p("match", "collective")], "debtor_collective"),
        ({"amount": "250.00"}, [_p("match", "partial")], "excluded"),
        (
            {"amount": "250.00"},
            [_p("match", "return"), _p("match", "full", unambiguous=True)],
            "excluded",
        ),
        ({"amount": "250.00"}, [_p("match", "deposit")], "excluded"),
        (
            {"amount": "-1190.00"},
            [_p("invoice", "invoice", unambiguous=True), _p("match", "invoice")],
            "creditor_invoice",
        ),
        ({"amount": "-1190.00"}, [_p("match", "invoice", unambiguous=True)], "creditor_invoice"),
        (
            {"amount": "-80.00"},
            [_p("rule", "posting"), _p("match", "unclear")],
            "recurring_expense",
        ),
        (
            {"amount": "-80.00"},
            [_p("history", "history"), _p("match", "unclear")],
            "recurring_expense",
        ),
        ({"amount": "-80.00"}, [_p("match", "unclear")], "excluded"),
        (
            {"amount": "-500.00", "transfer_pair": {"partner_account_number": "001220"}},
            [_p("match", "transfer")],
            "transfer_pair",
        ),
        (
            {"amount": "500.00"},
            [_p("match", "transfer"), _p("match", "full", unambiguous=True)],
            "transfer_pair",
        ),
    ],
)
def test_classify_fixed_cases(
    tx: dict[str, Any], proposals: list[dict[str, Any]], expected: str
) -> None:
    assert levels.classify(tx, proposals) == expected


def test_effective_levels_default_cap_and_unknown_values() -> None:
    assert levels.effective_levels(None) == dict.fromkeys(levels.CASE_CLASSES, "L0")
    configured = {
        "debtor_full": "L3",
        "debtor_collective": "L3",
        "excluded": "L2",
        "creditor_invoice": "L9",
    }
    out = levels.effective_levels(configured)
    assert out["debtor_full"] == "L3"
    assert out["debtor_collective"] == "L1"  # capped
    assert out["excluded"] == "L0"  # only level of the class
    assert out["creditor_invoice"] == "L0"  # unknown value falls back
    assert out["recurring_expense"] == "L0"


def _metrics(kind: str = "debtor_full", **kw: Any) -> levels.ClassMetrics:
    m = levels.ClassMetrics(kind, None, date(2026, 7, 1), date(2026, 9, 29))
    for key, value in kw.items():
        setattr(m, key, value)
    return m


def test_eligibility_l1_needs_twenty_decisions_and_precision() -> None:
    m = _metrics(n_decided=19, n_accepted_unchanged=19)
    assert levels.missing_for("L1", m, current="L0") == ["n_decided 19 unter 20 in 90 Tagen"]
    m = _metrics(n_decided=20, n_accepted_unchanged=18, n_modified=2)
    assert m.precision_manual == Decimal("0.9000")
    assert levels.missing_for("L1", m, current="L0") == ["precision_manual 0.9000 unter 0.95"]
    m = _metrics(n_decided=20, n_accepted_unchanged=19, n_modified=1)
    assert levels.missing_for("L1", m, current="L0") == []


def test_eligibility_l2_needs_days_at_l1_and_only_one_step() -> None:
    m = _metrics(n_decided=60, n_accepted_unchanged=59, n_modified=1, days_at_level=10)
    assert "Stufe L1 seit 10 Tagen, nötig 30" in levels.missing_for("L2", m, current="L1")
    m.days_at_level = 31
    assert levels.missing_for("L2", m, current="L1") == []
    assert levels.missing_for("L2", m, current="L0")[0].startswith("Nur eine Stufe je Antrag")


def test_eligibility_respects_class_caps_and_l3_automatic_figures() -> None:
    m = _metrics("debtor_collective", n_decided=100, n_accepted_unchanged=100)
    assert levels.missing_for("L2", m, current="L1") == [
        "Klasse debtor_collective ist auf L1 gedeckelt"
    ]
    m = _metrics(
        n_decided=100, n_accepted_unchanged=100, days_at_level=61, n_auto=99, n_auto_reversed=0
    )
    reasons = levels.missing_for("L3", m, current="L2")
    assert reasons == ["n_auto 99 unter 100"]
    m.n_auto = 0
    assert levels.missing_for("L3", m, current="L2") == [
        "n_auto 0 unter 100",
        "error_rate_auto ohne Basis über 0.005",
    ]
    m.n_auto, m.n_auto_reversed = 200, 2
    assert m.error_rate_auto == Decimal("0.0100")
    assert levels.missing_for("L3", m, current="L2") == ["error_rate_auto 0.0100 über 0.005"]
    m.n_auto_reversed = 1
    assert levels.missing_for("L3", m, current="L2") == []


def test_coverage_counts_auto_and_unchanged_only() -> None:
    m = _metrics(n_total=10, n_auto=4, n_accepted_unchanged=3, n_modified=2, n_decided=5, n_open=1)
    assert m.coverage == Decimal("0.7000")
    assert m.as_dict()["case_kind"] == "debtor_full"
    assert (
        levels.ClassMetrics("excluded", uuid.uuid4(), date(2026, 1, 1), date(2026, 1, 2)).coverage
        is None
    )
