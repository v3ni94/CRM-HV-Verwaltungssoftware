"""Correction report of a statement version (P02, D09): per owner before/after/difference and
the heating bridge as its own block. Display only: nothing is posted, claimed or sent; the legal
consequence of a correction stays an open decision (docs/OPEN_QUESTIONS.md P02, gate G4)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

CORRECTION_REASONS = ("resolution_changed", "court_invalid", "calculation_error", "other")
LEGAL_NOTE = (
    "Rechtsfolge der Korrektur offen (P02), keine Nachforderung und keine Erstattung "
    "ohne Freigabe der Geschäftsführung und vor G4."
)
_FIELDS = ("cost_share", "advances_resolved", "result")


def _d(value: Any) -> Decimal:
    return Decimal(str(value if value not in (None, "") else "0"))


def _triple(a: Decimal, b: Decimal) -> dict[str, str]:
    return {"old": str(a), "new": str(b), "difference": str(b - a)}


def _owner_of(unit: dict[str, Any]) -> str:
    periods = unit.get("ownership_periods") or []
    return str(periods[-1]["party_id"]) if periods else f"unit:{unit['unit_number']}"


def owner_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Sums the unit results per owner (party of the latest ownership period in the year)."""
    totals: dict[str, dict[str, Any]] = {}  # values: Any-typed accumulators
    for side, snap in (("old", old), ("new", new)):
        for unit in snap.get("units", []):
            row = totals.setdefault(
                _owner_of(unit),
                {
                    "units": set(),
                    **{f"{side_}{f}": Decimal(0) for side_ in ("old", "new") for f in _FIELDS},
                },
            )
            row["units"].add(unit["unit_number"])
            for f in _FIELDS:
                row[f"{side}{f}"] += _d(unit.get(f))
    owners: list[dict[str, Any]] = []
    for key in sorted(totals):
        r = totals[key]
        owners.append(
            {
                "owner": key,
                "units": sorted(r["units"]),
                **{f: _triple(r[f"old{f}"], r[f"new{f}"]) for f in _FIELDS},
            }
        )
    check = {f: str(sum((_d(o[f]["difference"]) for o in owners), Decimal(0))) for f in _FIELDS}
    return {"owners": owners, "sum_differences": check}


def heating_block(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Heating bridge (D09) of both versions: paid, distributed, explained, unexplained.
    No universal formula: the difference is shown and explained, never netted away."""

    def side(snap: dict[str, Any]) -> dict[str, str]:
        recon = snap.get("reconciliation") or {}
        explained = sum(
            (
                _d(n.get("amount"))
                for n in recon.get("explained_manual", [])
                if n.get("code") == "heating_accrual"
            ),
            Decimal(0),
        )
        return {
            "cash_outflows": str(_d((recon.get("cash") or {}).get("outflows"))),
            "cost_booked": str(_d(recon.get("cost_booked"))),
            "cost_distributed": str(_d(recon.get("cost_distributed"))),
            "heating_accrual": str(explained),
            "unexplained": str(_d(recon.get("unexplained"))),
        }

    o, n = side(old), side(new)
    return {
        "old": o,
        "new": n,
        "difference": {k: str(_d(n[k]) - _d(o[k])) for k in o},
    }
