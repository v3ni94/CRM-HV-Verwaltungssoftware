"""Pure date arithmetic of ``mhvp.workspace.deadlines`` with predefined expected values (rule
0.1.8). The functions add operator entered durations; they carry no legal rule."""

from datetime import date

from mhvp.workspace.deadlines import (
    CHECKLIST_TEMPLATES,
    SYSTEM_TYPES,
    TRIGGERS,
    add_months,
    checklist_items,
    compute_due,
    end_of_month,
    notice_period_end,
)


def test_add_months_clamps_to_month_length() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), 2) == date(2027, 1, 15)
    assert add_months(date(2026, 3, 31), 0) == date(2026, 3, 31)
    assert add_months(date(2026, 12, 31), 12) == date(2027, 12, 31)


def test_end_of_month() -> None:
    assert end_of_month(date(2026, 2, 3)) == date(2026, 2, 28)
    assert end_of_month(date(2026, 12, 31)) == date(2026, 12, 31)


def test_compute_due_needs_a_duration() -> None:
    assert compute_due(date(2026, 9, 28), None, None) is None
    assert compute_due(date(2026, 9, 28), 0, 0) == date(2026, 9, 28)
    assert compute_due(date(2026, 9, 28), None, 14) == date(2026, 10, 12)
    assert compute_due(date(2026, 9, 28), 6, None) == date(2027, 3, 28)
    assert compute_due(date(2026, 1, 31), 1, 3) == date(2026, 3, 3)


def test_notice_period_end_orientation() -> None:
    # Received 05.09.2026, three months: 05.12.2026, to the month end 31.12.2026.
    assert notice_period_end(date(2026, 9, 5), 3, 0, to_month_end=False) == date(2026, 12, 5)
    assert notice_period_end(date(2026, 9, 5), 3, 0, to_month_end=True) == date(2026, 12, 31)
    # Days are added after the months; the month end applies to the result.
    assert notice_period_end(date(2026, 9, 29), 3, 3, to_month_end=True) == date(2027, 1, 31)
    assert notice_period_end(date(2026, 9, 29), 0, 0, to_month_end=False) == date(2026, 9, 29)


def test_catalogue_constants() -> None:
    assert {t[2] for t in SYSTEM_TYPES} <= set(TRIGGERS)
    assert [t[0] for t in SYSTEM_TYPES] == [
        "verwalterwechsel",
        "kautionsabrechnung",
        "mieterhoehung",
    ]
    items = checklist_items("manager_change")
    assert len(items) == len(CHECKLIST_TEMPLATES["manager_change"]) == 10
    assert items[0] == {
        "code": "management_type",
        "label": "Verwaltungsart vor Anlage geklärt",
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
    }
    assert len({i["code"] for i in items}) == 10
