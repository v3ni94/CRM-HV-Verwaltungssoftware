"""Pure decision helpers of the learning bookkeeper (ADR 0014, plan M12 3.3): which proposal a
booking refers to and how the booked ``BookIn`` differs from it. No database, no side effects,
so the expected results of ``tests/unit/test_posting_decision_diff.py`` are fixed in advance
(rule 0.1.8).

Semantics:

* ``reference_index`` picks the proposal a decision is compared against: the explicit
  ``chosen`` index of the person, else the proposal with the highest confidence. Choosing the
  second proposal is therefore not a modification (plan 3.3).
* ``expected_of`` turns a proposal into the shape of a booking: settled open items with
  amounts, the counter account (only a proposal without splits names one; the ``account_number``
  of a match proposal is the debtor account that the settlement implies, never a counter
  account) and the discount (proposals never carry one).
* ``diff`` compares that expectation with the normalised final booking; ``{}`` means the
  proposal was accepted unchanged. Free text is not compared: wording is no decision.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

ZERO = "0.00"


def _amount(value: Any) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _settlements(rows: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out = [
        {"open_item_id": str(r["open_item_id"]), "amount": _amount(r["amount"])}
        for r in rows or []
        if r.get("open_item_id") is not None
    ]
    return sorted(out, key=lambda r: (r["open_item_id"], r["amount"]))


def normalise_final(
    *,
    settlements: list[dict[str, Any]] | None,
    counter_account_number: str | None,
    discount: Any = ZERO,
    text: str | None = None,
) -> dict[str, Any]:
    """Snapshot of what was booked (``posting_decision.final``)."""
    return {
        "settlements": _settlements(settlements),
        "counter_account_number": counter_account_number,
        "discount": _amount(discount or ZERO),
        "text": text,
    }


def expected_of(proposal: dict[str, Any] | None) -> dict[str, Any]:
    """The booking a proposal implies (see module docstring)."""
    if proposal is None:
        return {"settlements": [], "counter_account_number": None, "discount": ZERO}
    splits = _settlements(proposal.get("splits"))
    return {
        "settlements": splits,
        "counter_account_number": None if splits else proposal.get("account_number"),
        "discount": ZERO,
    }


def reference_index(proposals: list[dict[str, Any]], chosen: int | None) -> int | None:
    """Index of the proposal a decision refers to; ``None`` without proposals."""
    if not proposals:
        return None
    if chosen is not None:
        if chosen < 0 or chosen >= len(proposals):
            raise ValueError("chosen proposal index out of range")
        return chosen
    best = max(range(len(proposals)), key=lambda i: float(proposals[i].get("confidence") or 0))
    return best


def diff(proposal: dict[str, Any] | None, final: dict[str, Any]) -> dict[str, Any]:
    """Changed keys between the expectation of ``proposal`` and ``final``; ``{}`` when equal."""
    expected = expected_of(proposal)
    out: dict[str, Any] = {}
    exp_set = {(s["open_item_id"], s["amount"]) for s in expected["settlements"]}
    fin_set = {(s["open_item_id"], s["amount"]) for s in final.get("settlements", [])}
    if exp_set != fin_set:
        out["settlements"] = {
            "added": [{"open_item_id": i, "amount": a} for i, a in sorted(fin_set - exp_set)],
            "removed": [{"open_item_id": i, "amount": a} for i, a in sorted(exp_set - fin_set)],
        }
    if expected["counter_account_number"] != final.get("counter_account_number"):
        out["counter_account_number"] = {
            "proposed": expected["counter_account_number"],
            "final": final.get("counter_account_number"),
        }
    if _amount(expected["discount"]) != _amount(final.get("discount") or ZERO):
        out["discount"] = {
            "proposed": _amount(expected["discount"]),
            "final": _amount(final.get("discount") or ZERO),
        }
    return out


def outcome(changes: dict[str, Any]) -> str:
    """``accepted_unchanged`` or ``modified`` (values of ``PostingDecisionStatus``)."""
    return "accepted_unchanged" if not changes else "modified"
