"""Cap area matching (M26-01). Expected values from the MietSchVO NRW annex: Monheim is
listed as "Monheim", Düren as "Düren, Stadt"; both carry the 15 % cap from 01.03.2025."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from mhvp.letting.rentlaw import NRW_CAP_TOWNS, CapArea, cap_for, state_code

AREAS = [
    CapArea(
        state="NW",
        municipality=name,
        cap_percent=Decimal("15"),
        valid_from=date(2025, 3, 1),
        valid_to=date(2030, 2, 28),
        source="MietSchVO NRW",
    )
    for name in ("Monheim", "Düren, Stadt", "Brühl")
]


class FakeSession:
    """Returns all areas; the state filter is covered by the integration database."""

    def __init__(self, areas: list[CapArea]) -> None:
        self.areas = areas

    async def scalar(self, _: Any) -> None:
        return None

    async def scalars(self, _: Any) -> Any:
        return SimpleNamespace(all=lambda: self.areas)


def _cap(city: str, state: str | None) -> dict[str, Any]:
    prop = SimpleNamespace(city=city, state=state, municipality_code=None)
    return asyncio.run(cap_for(FakeSession(AREAS), prop, date(2026, 1, 1), Decimal("20")))  # type: ignore[arg-type]


def test_state_code() -> None:
    assert state_code("Nordrhein-Westfalen") == "NW"
    assert state_code("nw") == "NW"
    assert state_code("Westfalen") is None
    assert state_code(None) is None


def test_prefix_and_suffix_names() -> None:
    monheim = _cap("Monheim am Rhein", "NRW")
    assert monheim["percent"] == Decimal("15")
    assert "fehlt" in monheim["flag"]  # "NRW" is no state code: flagged for review
    duren = _cap("Düren", "Nordrhein-Westfalen")
    assert (duren["percent"], duren["flag"]) == (Decimal("15"), None)
    named = _cap("Monheim am Rhein", "Nordrhein-Westfalen")
    assert "Namensanfang" in named["flag"]


def test_no_match_uses_general_cap() -> None:
    other = _cap("Erkelenz", "Nordrhein-Westfalen")
    assert (other["percent"], other["source"], other["flag"]) == (
        Decimal("20"),
        "allgemeine Kappungsgrenze",
        None,
    )
    assert _cap("Brühler Straße", "NW")["percent"] == Decimal("20")


def test_annex_list() -> None:
    assert len(NRW_CAP_TOWNS) == 57
    assert len(set(NRW_CAP_TOWNS)) == 57
