"""AF07 (GAE-21, GAA-05): budget assigned total and B2B refusal.

Expected values by hand: invoices 1.000,00, credit note 150,00, journal lines on the plan
account without invoice: debit 300,00 and credit 50,00 = 250,00 net.
booked_before = 1.000,00 - 150,00 + 250,00 = 1.100,00. With an invoice of 400,00 the total
is 1.500,00; plan 1.400,00 at 5 % tolerance gives a limit of 1.470,00, so exceeded.
"""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.accounting.invoice_factual import budget_booked_before
from mhvp.contacts.models import MandateScheme
from mhvp.contacts.schemas import BankAccountIn
from mhvp.contacts.services import reject_b2b_mandates
from mhvp.core.problems import ProblemError


def test_booked_before_counts_credit_notes_negative_and_journal_lines() -> None:
    journal_net = Decimal("300.00") - Decimal("50.00")
    before = budget_booked_before(Decimal("1000.00"), Decimal("150.00"), journal_net)
    assert before == Decimal("1100.00")
    total = before + Decimal("400.00")
    limit = Decimal("1400.00") + Decimal("1400.00") * Decimal("5") / 100
    assert total == Decimal("1500.00")
    assert limit == Decimal("1470.00")
    assert total > limit


def test_booked_before_credit_journal_reduces() -> None:
    assert budget_booked_before(Decimal("0"), Decimal("0"), Decimal("-80.00")) == Decimal("-80.00")


def _account(scheme: MandateScheme) -> BankAccountIn:
    return BankAccountIn(
        iban="DE89370400440532013000",
        valid_from=date(2026, 1, 1),
        mandate_scheme=scheme,
    )


def test_b2b_mandate_refused_with_code() -> None:
    with pytest.raises(ProblemError) as exc:
        reject_b2b_mandates([_account(MandateScheme.CORE), _account(MandateScheme.B2B)])
    assert exc.value.error.code == "MHVP-CONT-0033"
    assert exc.value.error.status == 422


def test_core_mandate_accepted() -> None:
    reject_b2b_mandates([_account(MandateScheme.CORE)])
