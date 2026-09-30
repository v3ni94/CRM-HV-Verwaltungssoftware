"""Arithmetic checks for the rent increase bases modernization, index and graduated (M26-02).

Like the comparative rent check, these checks only recompute values that were entered with
their source. The platform contains no statutory percentages or limits for these bases and
never states that an increase is lawful (rule M26-02a, source register annex C holds no rent
law norms). Every check returns hints that block the approval until they are resolved."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CENT = Decimal("0.01")


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndexData(_Data):
    """Indexed rent: base index at the agreement, current index, both with the source."""

    index_base: Decimal = Field(gt=0)
    index_current: Decimal = Field(gt=0)
    index_name: str | None = Field(default=None, max_length=200)


class ModernizationData(_Data):
    """Modernization: costs, share to allocate in percent per year (entered with the source),
    deduction for maintenance work."""

    costs: Decimal = Field(gt=0)
    umlage_percent: Decimal = Field(gt=0, le=100)
    deducted_maintenance: Decimal = Field(default=Decimal(0), ge=0)


class GraduatedStep(_Data):
    valid_from: date
    rent: Decimal = Field(gt=0, decimal_places=2)


class GraduatedData(_Data):
    """Graduated rent: the steps agreed in the contract."""

    steps: list[GraduatedStep] = Field(min_length=1, max_length=60)


MODELS: dict[str, type[_Data]] = {
    "index": IndexData,
    "modernization": ModernizationData,
    "graduated": GraduatedData,
}


def validate(basis: str, data: dict[str, Any]) -> dict[str, Any]:
    """Normalised ``basis_data`` (strings for numbers) or ``ValueError`` with the reason."""
    model = MODELS.get(basis)
    if model is None:
        if data:
            raise ValueError("Für diese Begründung gibt es keine Zusatzangaben.")
        return {}
    try:
        return model.model_validate(data).model_dump(mode="json")
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise ValueError(f"Zusatzangaben ungültig ({where}): {first['msg']}") from None


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def check(
    basis: str,
    data: dict[str, Any],
    *,
    current_rent: Decimal,
    target_rent: Decimal,
    effective_date: date,
    has_agreement_document: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Computed values and hints for one basis; empty hints mean the arithmetic is consistent."""
    out: dict[str, Any] = {}
    flags: list[str] = []
    if basis not in MODELS:
        return out, flags
    if not data:
        return out, [f"Zusatzangaben für die Begründung {basis} fehlen."]
    if basis == "index":
        base, now = _dec(data.get("index_base")), _dec(data.get("index_current"))
        if base is None or now is None or base <= 0:
            return out, ["Indexwerte unvollständig."]
        maximum = (current_rent * now / base).quantize(CENT, rounding=ROUND_HALF_UP)
        out.update(index_max_rent=str(maximum), index_change=str((now / base - 1) * 100))
        if target_rent > maximum:
            flags.append(f"Zielmiete über der Indexanpassung ({maximum} EUR).")
        if not has_agreement_document:
            flags.append("Vertragliche Indexvereinbarung als Quelldokument hinterlegen.")
    elif basis == "modernization":
        costs = _dec(data.get("costs"))
        percent = _dec(data.get("umlage_percent"))
        deducted = _dec(data.get("deducted_maintenance")) or Decimal(0)
        if costs is None or percent is None or deducted >= costs:
            return out, ["Modernisierungskosten oder Umlagesatz unvollständig."]
        monthly = ((costs - deducted) * percent / 100 / 12).quantize(CENT, rounding=ROUND_HALF_UP)
        maximum = current_rent + monthly
        out.update(umlage_monthly=str(monthly), modernization_max_rent=str(maximum))
        if target_rent > maximum:
            flags.append(f"Zielmiete über Miete plus Modernisierungsumlage ({maximum} EUR).")
        if not has_agreement_document:
            flags.append("Kostennachweis oder Ankündigung als Quelldokument hinterlegen.")
    else:
        steps = [
            (_dec(s.get("rent")), s.get("valid_from"))
            for s in data.get("steps", [])
            if isinstance(s, dict)
        ]
        match = [r for r, d in steps if d == effective_date.isoformat()]
        out["steps"] = len(steps)
        if not match:
            flags.append("Keine Mietstaffel zum Wirksamkeitsdatum erfasst.")
        elif match[0] != target_rent:
            flags.append(f"Zielmiete weicht von der vereinbarten Staffel ab ({match[0]} EUR).")
        if not has_agreement_document:
            flags.append("Staffelmietvereinbarung als Quelldokument hinterlegen.")
    return out, flags
