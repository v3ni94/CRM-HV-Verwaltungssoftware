"""M10-03: settlement proposal in the statutory order (7.4 Nr. 5, D39). Expected results are
computed by hand in the comments (rule 0.1.8); the function is pure and deterministic."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from mhvp.accounting.settlement import (
    CLASS_COSTS,
    CLASS_INTEREST,
    CLASS_PRINCIPAL,
    PROPOSAL_NOTE,
    REASON_DETERMINED,
    REASON_STATUTORY,
    Determination,
    ProposalItem,
    determination_from_purpose,
    propose,
    verify_fingerprint,
)
from mhvp.core.problems import ProblemError

AS_OF = date(2026, 9, 26)
D = Decimal


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(f"0192abcd-0000-7000-8000-{n:012d}")


def _item(n: int, remaining: str, due: date, **extra: object) -> ProposalItem:
    return ProposalItem(
        open_item_id=_id(n),
        remaining=D(remaining),
        booking_date=due,
        due_date=due,
        **extra,  # type: ignore[arg-type]
    )


def _lines(proposal: object) -> list[tuple[int, str]]:
    return [(int(a.open_item_id.hex[-4:]), str(a.amount)) for a in proposal.allocations]  # type: ignore[attr-defined]


def test_due_before_not_yet_due_then_older_first() -> None:
    # Items: 1 due 01.08. 300,00; 2 due 01.10. (future) 200,00; 3 due 01.09. 250,00.
    # Payment 500,00: due items in age order -> 1: 300,00, 3: 200,00 (partial); 2 stays open.
    items = [
        _item(1, "300.00", date(2026, 8, 1)),
        _item(2, "200.00", date(2026, 10, 1)),
        _item(3, "250.00", date(2026, 9, 1)),
    ]
    p = propose(items, D("500.00"), AS_OF)
    assert _lines(p) == [(1, "300.00"), (3, "200.00")]
    assert p.unallocated == D("0.00")
    assert p.basis == "statutory_order"
    assert all(a.reason == REASON_STATUTORY for a in p.allocations)
    assert [a.rank for a in p.allocations] == [1, 2]
    assert p.to_dict()["note"] == PROPOSAL_NOTE
    assert p.to_dict()["requires_confirmation"] is True


def test_not_yet_due_items_are_used_only_after_all_due_items() -> None:
    # 1 due 01.08. 100,00; 2 due 01.12. (future) 400,00. Payment 300,00 -> 1: 100,00, 2: 200,00.
    items = [_item(1, "100.00", date(2026, 8, 1)), _item(2, "400.00", date(2026, 12, 1))]
    p = propose(items, D("300.00"), AS_OF)
    assert _lines(p) == [(1, "100.00"), (2, "200.00")]


def test_more_burdensome_before_older() -> None:
    # 1 due 01.06. 100,00 (not dunned); 2 due 01.08. 100,00 in a sent dunning case.
    # Payment 150,00 -> 2 first (more burdensome): 100,00, then 1: 50,00.
    items = [
        _item(1, "100.00", date(2026, 6, 1)),
        _item(2, "100.00", date(2026, 8, 1), burdensome=True),
    ]
    p = propose(items, D("150.00"), AS_OF)
    assert _lines(p) == [(2, "100.00"), (1, "50.00")]


def test_less_security_before_burden() -> None:
    # 1 security 1, burdensome; 2 security 0, not burdensome. Same due date -> 2 first.
    items = [
        _item(1, "100.00", date(2026, 8, 1), burdensome=True, security=1),
        _item(2, "100.00", date(2026, 8, 1)),
    ]
    p = propose(items, D("120.00"), AS_OF)
    assert _lines(p) == [(2, "100.00"), (1, "20.00")]


def test_costs_before_interest_before_principal_at_equal_rank() -> None:
    # Same due date 01.08.: 1 principal 500,00; 2 interest 12,50; 3 costs 5,00.
    # Payment 100,00 -> 3: 5,00, 2: 12,50, 1: 82,50. Sum 100,00.
    items = [
        _item(1, "500.00", date(2026, 8, 1), claim_class=CLASS_PRINCIPAL),
        _item(2, "12.50", date(2026, 8, 1), claim_class=CLASS_INTEREST),
        _item(3, "5.00", date(2026, 8, 1), claim_class=CLASS_COSTS),
    ]
    p = propose(items, D("100.00"), AS_OF)
    assert _lines(p) == [(3, "5.00"), (2, "12.50"), (1, "82.50")]
    assert sum(a.amount for a in p.allocations) == D("100.00")


def test_tie_broken_by_id_is_deterministic() -> None:
    items = [_item(2, "10.00", date(2026, 8, 1)), _item(1, "10.00", date(2026, 8, 1))]
    a = propose(items, D("10.00"), AS_OF)
    b = propose(list(reversed(items)), D("10.00"), AS_OF)
    assert _lines(a) == _lines(b) == [(1, "10.00")]
    assert a.fingerprint == b.fingerprint


def test_overpayment_stays_unallocated_never_income() -> None:
    # 1 due 01.08. 100,00. Payment 130,00 -> 1: 100,00, unallocated 30,00 (credit, D07).
    p = propose([_item(1, "100.00", date(2026, 8, 1))], D("130.00"), AS_OF)
    assert _lines(p) == [(1, "100.00")]
    assert p.unallocated == D("30.00")


def test_explicit_determination_wins_over_statutory_order() -> None:
    # 1 due 01.06. 100,00 (oldest); 2 due 01.09. 100,00. Payer determines item 2.
    # Payment 100,00 -> only 2: 100,00 with reason "Bestimmung des Zahlers"; item 1 untouched.
    items = [_item(1, "100.00", date(2026, 6, 1)), _item(2, "100.00", date(2026, 9, 1))]
    p = propose(items, D("100.00"), AS_OF, [Determination(_id(2))])
    assert _lines(p) == [(2, "100.00")]
    assert p.allocations[0].reason == REASON_DETERMINED
    assert p.basis == "determination"
    # Payment 150,00 with the same determination: 2 first, then the rest in statutory order.
    q = propose(items, D("150.00"), AS_OF, [Determination(_id(2))])
    assert _lines(q) == [(2, "100.00"), (1, "50.00")]
    assert q.basis == "mixed"
    assert q.allocations[1].reason == REASON_STATUTORY


def test_determination_with_amount_is_capped_by_remaining() -> None:
    # Payer determines 40,00 on item 2 (rest 100,00). Payment 60,00 -> 2: 40,00, then 1: 20,00.
    items = [_item(1, "100.00", date(2026, 6, 1)), _item(2, "100.00", date(2026, 9, 1))]
    p = propose(items, D("60.00"), AS_OF, [Determination(_id(2), D("40.00"))])
    assert _lines(p) == [(2, "40.00"), (1, "20.00")]
    # Determined amount above the remaining amount is capped: 2 has 100,00 open.
    q = propose(items, D("150.00"), AS_OF, [Determination(_id(2), D("500.00"))])
    assert _lines(q) == [(2, "100.00"), (1, "50.00")]


def test_unknown_determination_and_invalid_amounts_are_refused() -> None:
    items = [_item(1, "100.00", date(2026, 6, 1))]
    with pytest.raises(ProblemError):
        propose(items, D("10.00"), AS_OF, [Determination(_id(9))])
    with pytest.raises(ProblemError):
        propose(items, D("0.00"), AS_OF)
    with pytest.raises(ProblemError):
        propose(items, D("10.00"), AS_OF, [Determination(_id(1), D("0"))])


def test_fingerprint_changes_with_facts() -> None:
    items = [_item(1, "100.00", date(2026, 6, 1)), _item(2, "100.00", date(2026, 9, 1))]
    p = propose(items, D("100.00"), AS_OF)
    verify_fingerprint(p, p.fingerprint)
    changed = propose([_item(1, "50.00", date(2026, 6, 1)), items[1]], D("100.00"), AS_OF)
    assert changed.fingerprint != p.fingerprint
    with pytest.raises(ProblemError):
        verify_fingerprint(changed, p.fingerprint)


def test_determination_from_purpose_names_items_by_reference_or_period() -> None:
    items = [
        ProposalItem(_id(1), D("100.00"), date(2026, 6, 1), date(2026, 6, 1), reference="SO-1"),
        ProposalItem(_id(2), D("100.00"), date(2026, 9, 1), date(2026, 9, 1), reference="SO-2"),
    ]
    assert determination_from_purpose(items, None) == []
    assert determination_from_purpose(items, "Miete") == []
    assert [d.open_item_id for d in determination_from_purpose(items, "Miete 09/2026")] == [_id(2)]
    assert [d.open_item_id for d in determination_from_purpose(items, "Sollstellung Nr. SO-1")] == [
        _id(1)
    ]
