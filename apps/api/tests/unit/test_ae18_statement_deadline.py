"""M17-04 statement deadline: expected values by hand (§ 556 Abs. 3 BGB, orientation only).

Period end 31.12.2025 -> deadline 31.12.2026; period end 31.12.2023 -> 31.12.2024 (leap year);
period end 28.02.2025 -> 28.02.2026; period end 29.02.2024 -> 28.02.2025.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from mhvp.billing import calc, deadline, services
from mhvp.core.problems import ProblemError


def test_deadline_orientation_month_ends() -> None:
    assert calc.deadline(date(2025, 12, 31)) == date(2026, 12, 31)
    assert calc.deadline(date(2023, 12, 31)) == date(2024, 12, 31)
    assert calc.deadline(date(2025, 2, 28)) == date(2026, 2, 28)
    assert calc.deadline(date(2024, 2, 29)) == date(2025, 2, 28)


def test_state_of() -> None:
    end = date(2026, 12, 31)
    assert deadline.state_of(end, None, date(2026, 6, 1), 60) == "open"
    assert deadline.state_of(end, None, date(2026, 11, 1), 60) == "warning"  # 60 days left
    assert deadline.state_of(end, None, date(2027, 1, 1), 60) == "expired"
    assert deadline.state_of(end, date(2026, 12, 31), date(2027, 1, 1), 60) == "delivered_in_time"
    assert deadline.state_of(end, date(2027, 1, 2), date(2027, 1, 3), 60) == "delivered_late"


def _statement() -> SimpleNamespace:
    return SimpleNamespace(period_to=date(2025, 12, 31), deadline_exception_effective=False)


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        created_at=datetime(2027, 1, 5, 10, tzinfo=UTC),
        results={"results": [{"unit_number": "1", "balance": "50.00", "late_claim_blocked": True}]},
    )


def test_policy_block_claims_is_default_and_blocks() -> None:
    with pytest.raises(ProblemError):
        services.check_issue(_statement(), _snapshot(), date(2027, 1, 10))  # type: ignore[arg-type]
    with pytest.raises(ProblemError):
        services.check_issue(_statement(), _snapshot(), date(2027, 1, 10), "block_claims")  # type: ignore[arg-type]


def test_policy_notice_does_not_block() -> None:
    services.check_issue(_statement(), _snapshot(), date(2027, 1, 10), "notice")  # type: ignore[arg-type]
