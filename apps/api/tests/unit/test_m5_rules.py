"""M5 pure rules: statement status model (6.9.3, D13, D14), amounts, SEPA identifiers."""

import itertools
from decimal import Decimal

import pytest

from mhvp.billing.status import StatementStatus as S
from mhvp.billing.status import TransitionError, check_transition
from mhvp.contracts.services import check_amounts
from mhvp.contracts.validation import (
    InvalidSepaValueError,
    check_mandate_reference,
    normalise_creditor_id,
)
from mhvp.core.problems import ProblemError


def test_rental_statement_path() -> None:
    path = [S.DRAFT, S.CALCULATED, S.INTERNALLY_APPROVED, S.ISSUED, S.DUE, S.POSTED, S.LOCKED]
    for current, target in itertools.pairwise(path):
        check_transition(current, target, is_hoa=False)
    with pytest.raises(TransitionError):
        check_transition(S.INTERNALLY_APPROVED, S.RESOLVED, is_hoa=False)
    with pytest.raises(TransitionError):
        check_transition(S.CALCULATED, S.DRAFT, is_hoa=False)
    with pytest.raises(TransitionError):
        check_transition(S.ISSUED, S.POSTED, is_hoa=False)


def test_hoa_statement_needs_resolution_on_this_snapshot() -> None:
    with pytest.raises(TransitionError):
        check_transition(S.INTERNALLY_APPROVED, S.ISSUED, is_hoa=True)
    with pytest.raises(TransitionError, match="D14"):
        check_transition(S.BOARD_REVIEWED, S.RESOLVED, is_hoa=True)
    check_transition(S.BOARD_REVIEWED, S.RESOLVED, is_hoa=True, resolution_snapshot_matches=True)
    check_transition(S.RESOLVED, S.ISSUED, is_hoa=True)
    with pytest.raises(TransitionError, match="D13"):
        check_transition(S.DUE, S.POSTED, is_hoa=True, resolution_status="contested")
    check_transition(S.DUE, S.POSTED, is_hoa=True, resolution_status="final")


def test_amount_plausibility() -> None:
    check_amounts("rent", Decimal("100.00"), Decimal("19"), Decimal("119.00"))
    check_amounts("rent", Decimal("100.00"), Decimal("19"), Decimal("119.01"))
    with pytest.raises(ProblemError):
        check_amounts("rent", Decimal("100.00"), Decimal("19"), Decimal("119.02"))
    with pytest.raises(ProblemError):
        check_amounts("rent", Decimal("-10.00"), Decimal("0"), Decimal("-10.00"))
    check_amounts("rent_reduction", Decimal("-10.00"), Decimal("0"), Decimal("-10.00"))
    with pytest.raises(ProblemError):
        check_amounts("rent_reduction", Decimal("-10.00"), Decimal("0"), Decimal("10.00"))


def test_sepa_identifiers() -> None:
    assert normalise_creditor_id("de98 zzz0 9999 9999 99") == "DE98ZZZ09999999999"
    with pytest.raises(InvalidSepaValueError):
        normalise_creditor_id("DE97ZZZ09999999999")
    assert check_mandate_reference("MANDAT-2026/001") == "MANDAT-2026/001"
    with pytest.raises(InvalidSepaValueError):
        check_mandate_reference("Mandat mit Ümlaut")
