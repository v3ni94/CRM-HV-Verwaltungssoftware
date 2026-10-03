"""AN18 (GAK-202, GAK-203): switches and proposal core of the rent increase process."""

from datetime import date
from decimal import Decimal

from mhvp.letting import increase_proposals as ip
from mhvp.letting import increase_settings as st


def test_parse_defaults_conservative() -> None:
    value = st.parse({})
    assert value.block_months == {}
    assert value.proposals == "off"
    assert st.block_proposal(value, "mietspiegel", date(2026, 1, 1)) is None


def test_parse_ignores_invalid_and_store_roundtrip() -> None:
    pre = "rent_increase_block_months."
    src = {"x": "1", pre + "index": "12", pre + "foo": "3", pre + "graduated": "abc",
           "rent_increase_proposals": "auto"}  # fmt: skip
    value = st.parse(src)
    assert value.block_months == {"index": 12}
    assert value.proposals == "off"
    stored = st.store(src, st.IncreaseSettings({"graduated": 6}, "draft"))
    assert stored["x"] == "1"
    assert pre + "index" not in stored
    assert st.parse(stored) == st.IncreaseSettings({"graduated": 6}, "draft")


def test_block_proposal_clamps_month_end() -> None:
    value = st.IncreaseSettings({"index": 1})
    assert st.block_proposal(value, "index", date(2026, 1, 31)) == date(2026, 2, 28)
    assert st.block_proposal(value, "graduated", date(2026, 1, 31)) is None


def test_due_graduated_steps() -> None:
    steps = [
        ip.GraduatedStep(date(2026, 1, 1), Decimal("550.00")),
        ip.GraduatedStep(date(2026, 11, 1), Decimal("600.00")),
        ip.GraduatedStep(date(2027, 11, 1), Decimal("650.00")),
    ]
    out = ip.due_graduated_steps(steps, set(), date(2026, 10, 3), 60, Decimal("550.00"))
    assert [(p.effective_date, p.current_rent, p.target_rent) for p in out] == [
        (date(2026, 11, 1), Decimal("550.00"), Decimal("600.00"))
    ]
    assert ip.due_graduated_steps(steps, {date(2026, 11, 1)}, date(2026, 10, 3), 60,
                                  Decimal("550.00")) == []  # fmt: skip


def test_index_adjustment_rounds_half_up() -> None:
    p = ip.index_adjustment(
        Decimal("500.00"), Decimal("100.0"), Decimal("103.001"), date(2027, 1, 1)
    )
    assert p is not None
    assert p.target_rent == Decimal("515.01")
    assert p.basis == "index"
    assert (
        ip.index_adjustment(Decimal("500.00"), Decimal("100"), Decimal("99"), date(2027, 1, 1))
        is None
    )
