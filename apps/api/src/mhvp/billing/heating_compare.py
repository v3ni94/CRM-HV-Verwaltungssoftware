"""Comparison of external heating amounts with the own HeizkostenV calculation (M17-02,
AB10-01 area). Read only: nothing is booked, the draft stays unchanged. The tolerance is a
parameter of the caller (default 0,50 EUR and 1,0 percent, a working value and no legal
figure). Missing figures give a status with a reason, nothing is estimated."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
DEFAULT_TOLERANCE_ABS = Decimal("0.50")
DEFAULT_TOLERANCE_PERCENT = Decimal("1.0")


@dataclass(frozen=True)
class ExternalItem:
    label: str
    amounts: dict[str, str]  # occupancy key or unit id -> amount


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def compare(
    *,
    result: dict[str, Any] | None,
    key_to_unit: dict[str, str],
    external: list[ExternalItem],
    tolerance_abs: Decimal = DEFAULT_TOLERANCE_ABS,
    tolerance_percent: Decimal = DEFAULT_TOLERANCE_PERCENT,
) -> dict[str, Any]:
    """Per user: external amount, own amount, difference. A row deviates when the absolute
    difference exceeds both tolerances (cent amount and percent of the external amount)."""
    if tolerance_abs < 0 or tolerance_percent < 0:
        raise ValueError("Toleranzen dürfen nicht negativ sein.")
    if result is None:
        return {
            "status": "nicht_berechenbar",
            "reason": "Eigene Heizkostenberechnung fehlt; erst berechnen.",
            "rows": [],
            "summary": _summary([], tolerance_abs, tolerance_percent),
        }
    own: dict[str, Decimal] = {
        k: Decimal(v["total"]) for k, v in result.get("per_occupant", {}).items()
    }
    unit_label = {k: v.get("unit_number", "") for k, v in result.get("per_occupant", {}).items()}
    ext: dict[str, Decimal] = {}
    unmatched: list[str] = []
    for item in external:
        for key, raw in item.amounts.items():
            amount = _dec(raw)
            if amount is None:
                unmatched.append(f"{item.label}: {key}")
                continue
            target = [key] if key in own else [k for k in own if key_to_unit.get(k) == key]
            if not target:
                unmatched.append(f"{item.label}: {key}")
                continue
            # a unit id covers all occupancies of the unit: spread by own share, remainder
            # to the last; a single key takes the amount unchanged
            if len(target) == 1:
                ext[target[0]] = ext.get(target[0], Decimal(0)) + amount
            else:
                base = sum((own[k] for k in target), Decimal(0))
                left = amount
                for i, k in enumerate(target):
                    part = (
                        left
                        if i == len(target) - 1
                        else (_q(amount * own[k] / base) if base else Decimal(0))
                    )
                    left -= part
                    ext[k] = ext.get(k, Decimal(0)) + part
    rows: list[dict[str, Any]] = []
    for key in sorted(own, key=lambda k: (unit_label.get(k, ""), k)):
        mine = own[key]
        theirs = ext.get(key)
        row: dict[str, Any] = {
            "key": key,
            "unit_number": unit_label.get(key, ""),
            "unit_id": key_to_unit.get(key),
            "vacancy": result["per_occupant"][key].get("vacancy") == "true",
            "own": str(mine),
            "external": None if theirs is None else str(theirs),
        }
        if theirs is None:
            row |= {"difference": None, "percent": None, "status": "extern_fehlt"}
        else:
            diff = _q(mine - theirs)
            pct = _q(abs(diff) / abs(theirs) * 100) if theirs != 0 else None
            over_abs = abs(diff) > tolerance_abs
            over_pct = pct is None or pct > tolerance_percent
            row |= {
                "difference": str(diff),
                "percent": None if pct is None else str(pct),
                "status": "abweichung" if over_abs and over_pct else "ok",
            }
        rows.append(row)
    return {
        "status": "berechnet",
        "reason": None,
        "rows": rows,
        "unmatched_external": unmatched,
        "summary": _summary(rows, tolerance_abs, tolerance_percent),
    }


def _summary(rows: list[dict[str, Any]], tol_abs: Decimal, tol_pct: Decimal) -> dict[str, Any]:
    own = sum((Decimal(r["own"]) for r in rows), Decimal(0))
    ext_rows = [r for r in rows if r["external"] is not None]
    ext = sum((Decimal(r["external"]) for r in ext_rows), Decimal(0))
    return {
        "own_total": str(_q(own)),
        "external_total": str(_q(ext)),
        "difference_total": str(_q(sum((Decimal(r["difference"]) for r in ext_rows), Decimal(0)))),
        "deviations": sum(1 for r in rows if r["status"] == "abweichung"),
        "missing_external": sum(1 for r in rows if r["status"] == "extern_fehlt"),
        "tolerance_abs": str(tol_abs),
        "tolerance_percent": str(tol_pct),
        "method": (
            "Differenz = eigen minus extern je Nutzer; Abweichung, wenn der Betrag der Differenz "
            "die absolute Toleranz und die prozentuale Toleranz (bezogen auf extern) übersteigt."
        ),
    }


def report_csv(data: dict[str, Any]) -> str:
    """Deviation report as CSV (semicolon, decimal comma), deviations and gaps only."""

    def n(v: str | None) -> str:
        return "" if v is None else v.replace(".", ",")

    lines = ["Einheit;Schlüssel;Extern;Eigen;Differenz;Prozent;Status"]
    for r in data["rows"]:
        if r["status"] == "ok":
            continue
        lines.append(
            ";".join(
                [
                    r["unit_number"],
                    r["key"],
                    n(r["external"]),
                    n(r["own"]),
                    n(r["difference"]),
                    n(r["percent"]),
                    r["status"],
                ]
            )
        )
    return "\n".join(lines) + "\n"
