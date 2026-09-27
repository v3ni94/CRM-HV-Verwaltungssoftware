"""Fristberechnung der Aufbewahrungsmatrix (M6-04): Beginn am Jahresende des Entstehungsjahres,
am Jahresende des Vertragsendes oder tagesgenau am Zweckende; dauerhaft ergibt kein Datum."""

from datetime import date

import pytest

from mhvp.documents.models import RetentionProfile, RetentionStart
from mhvp.documents.retention import add_period, compute_retention_until, needs_base_date


def _profile(
    years: int, months: int = 0, *, rule: RetentionStart, permanent: bool = False
) -> RetentionProfile:
    return RetentionProfile(
        document_class="x",
        legal_basis="Test",
        retention_years=years,
        retention_months=months,
        permanent=permanent,
        start_rule=rule,
    )


def test_add_period_clamps_day_to_month_length() -> None:
    assert add_period(date(2024, 12, 31), 0, 6) == date(2025, 6, 30)
    assert add_period(date(2024, 1, 31), 0, 1) == date(2024, 2, 29)
    assert add_period(date(2024, 12, 31), 10, 0) == date(2034, 12, 31)


def test_end_of_year_created_ten_years() -> None:
    profile = _profile(10, rule=RetentionStart.END_OF_YEAR_CREATED)
    assert compute_retention_until(profile, created_on=date(2026, 3, 15), base_on=None) == date(
        2036, 12, 31
    )
    assert not needs_base_date(profile)


def test_contract_end_and_last_entry_use_year_end_of_base_date() -> None:
    contracts = _profile(10, rule=RetentionStart.CONTRACT_END)
    assert needs_base_date(contracts)
    assert compute_retention_until(contracts, created_on=date(2015, 1, 1), base_on=None) is None
    assert compute_retention_until(
        contracts, created_on=date(2015, 1, 1), base_on=date(2026, 4, 30)
    ) == date(2036, 12, 31)
    journals = _profile(10, rule=RetentionStart.END_OF_YEAR_LAST_ENTRY)
    assert compute_retention_until(
        journals, created_on=date(2020, 1, 1), base_on=date(2021, 2, 2)
    ) == date(2031, 12, 31)
    statements = _profile(10, rule=RetentionStart.STATEMENT_ISSUED)
    assert compute_retention_until(
        statements, created_on=date(2020, 1, 1), base_on=date(2021, 6, 1)
    ) == date(2031, 12, 31)


def test_purpose_end_is_day_exact() -> None:
    profile = _profile(0, 6, rule=RetentionStart.PURPOSE_END)
    assert compute_retention_until(
        profile, created_on=date(2026, 1, 1), base_on=date(2026, 8, 31)
    ) == date(2027, 2, 28)
    assert compute_retention_until(profile, created_on=date(2026, 1, 1), base_on=None) is None


@pytest.mark.parametrize("rule", list(RetentionStart))
def test_permanent_never_yields_a_date(rule: RetentionStart) -> None:
    profile = _profile(0, rule=rule, permanent=True)
    assert (
        compute_retention_until(profile, created_on=date(2000, 1, 1), base_on=date(2000, 1, 1))
        is None
    )
    assert not needs_base_date(profile)
