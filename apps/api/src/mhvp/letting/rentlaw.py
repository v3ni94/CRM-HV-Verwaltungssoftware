"""Rent law rule set for rent increases (M26-01, decided 24.09.2026).

Parameters are platform wide (the law is the same for every tenant) and take effect only after
a platform administrator released them. Pre-filled values come from domain knowledge and are
marked unverified until checked against the official text (sources register M26). Capping
areas with a reduced cap are maintained per federal state and municipality; only entries with
a documented source are allowed. The check never states that an increase is lawful."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Date, DateTime, Numeric, String, Text, or_, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import (
    Principal,
    TenantPrincipal,
    require_permission,
    require_platform_admin,
    sessions,
    tenant_tx,
)
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.problems import ErrorCodes, ProblemError

RATE = Numeric(20, 8)
CENT = Decimal("0.01")


class RentLawRule(TimestampMixin, Base):
    __tablename__ = "rent_law_rule"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    norm: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(RATE)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    source_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CapArea(IdMixin, TimestampMixin, Base):
    """Municipality with a reduced capping limit by state ordinance, with validity and source."""

    __tablename__ = "rent_cap_area"

    state: Mapped[str] = mapped_column(String(2), nullable=False)  # e.g. NW
    municipality: Mapped[str] = mapped_column(String(200), nullable=False)
    municipality_code: Mapped[str | None] = mapped_column(String(20))
    cap_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text, nullable=False)


NRW_ORDINANCE = (
    "MietSchVO NRW vom 28.01.2025 (GV. NRW. S. 111), geändert 28.10.2025 (GV. NRW. S. 848), "
    "§ 1 Abs. 2 mit Anlage; abgerufen von recht.nrw.de am 24.09.2026"
)
NRW_ORDINANCE_URL = (
    "https://recht.nrw.de/system/files/BA/54532-52830-sgv_238_20250128_1_anlage1.pdf"
)
# Anlage zu § 1 MietSchVO NRW, names as printed; valid 01.03.2025 to 28.02.2030 (§ 3).
NRW_CAP_TOWNS = (
    "Aachen", "Alfter", "Bad Lippspringe", "Bergheim", "Bergisch Gladbach", "Bielefeld", "Bonn",
    "Bornheim", "Brühl", "Dormagen", "Dortmund", "Düren, Stadt", "Düsseldorf", "Elsdorf",
    "Erftstadt", "Erkrath", "Frechen", "Greven", "Grevenbroich", "Harsewinkel", "Hennef",
    "Hilden", "Hürth", "Kaarst", "Kempen", "Kerpen", "Korschenbroich", "Köln", "Königswinter",
    "Krefeld", "Langenfeld", "Leichlingen", "Leverkusen", "Lohmar", "Lotte", "Meckenheim",
    "Meerbusch", "Monheim", "Münster", "Neuss", "Niederkassel", "Ostbevern", "Overath",
    "Paderborn", "Pulheim", "Ratingen", "Rheinbach", "Rösrath", "Rommerskirchen",
    "Sankt Augustin", "Siegburg", "Swisttal", "Telgte", "Troisdorf", "Wachtberg", "Weilerswist",
    "Wesseling",
)  # fmt: skip

BGB = "https://www.gesetze-im-internet.de/bgb/"
# Seed rows (migration 0030). Unverified until checked against the official text.
_SEED = (
    (
        "waiting_months",
        "Miete seit mindestens so vielen Monaten unverändert, wenn die Erhöhung eintreten soll",
        "§ 558 Abs. 1 BGB",
        15,
        "Monate",
        "__558.html",
    ),
    ("cap_percent", "Kappungsgrenze im Zeitraum", "§ 558 Abs. 3 BGB", 20, "Prozent", "__558.html"),
    (
        "cap_window_years",
        "Zeitraum der Kappungsgrenze",
        "§ 558 Abs. 3 BGB",
        3,
        "Jahre",
        "__558.html",
    ),
    (
        "comparison_flats_min",
        "Mindestanzahl benannter Vergleichswohnungen",
        "§ 558a Abs. 2 Nr. 4 BGB",
        3,
        "Wohnungen",
        "__558a.html",
    ),
    (
        "consent_months",
        "Zustimmungsfrist bis Ende des so vielten Kalendermonats nach Zugang",
        "§ 558b Abs. 2 BGB",
        2,
        "Monate",
        "__558b.html",
    ),
    (
        "effective_month",
        "Erhöhte Miete ab Beginn des so vielten Kalendermonats nach Zugang",
        "§ 558b Abs. 1 BGB",
        3,
        "Monate",
        "__558b.html",
    ),
)
SEED: list[dict[str, Any]] = [
    {
        "code": c,
        "label": label,
        "norm": norm,
        "value": Decimal(v),
        "unit": unit,
        "source_url": BGB + page,
    }
    for c, label, norm, v, unit, page in _SEED
]
NEEDED = ("waiting_months", "cap_percent", "cap_window_years", "comparison_flats_min")


def _add_months(first_of_month: date, months: int) -> date:
    y, m = divmod(first_of_month.month - 1 + months, 12)
    return date(first_of_month.year + y, m + 1, 1)


def deadlines(received: date, consent_months: int, effective_month: int) -> dict[str, date]:
    """Consent deadline = last day of the n-th calendar month after receipt; increased rent from
    the first day of the m-th calendar month after receipt (values from the released rules)."""
    base = received.replace(day=1)
    return {
        "consent_until": _add_months(base, consent_months + 1) - timedelta(days=1),
        "effective_from": _add_months(base, effective_month),
    }


async def released_rules(session: AsyncSession) -> dict[str, Decimal]:
    rows = (
        await session.scalars(select(RentLawRule).where(RentLawRule.status == "released"))
    ).all()
    return {r.code: r.value for r in rows if r.value is not None}


STATES = {
    "baden-württemberg": "BW", "bayern": "BY", "berlin": "BE", "brandenburg": "BB",
    "bremen": "HB", "hamburg": "HH", "hessen": "HE", "mecklenburg-vorpommern": "MV",
    "niedersachsen": "NI", "nordrhein-westfalen": "NW", "rheinland-pfalz": "RP",
    "saarland": "SL", "sachsen": "SN", "sachsen-anhalt": "ST", "schleswig-holstein": "SH",
    "thüringen": "TH",
}  # fmt: skip


def state_code(value: str | None) -> str | None:
    """ISO 3166-2 suffix of a German state from a code or name, else None."""
    if not value:
        return None
    text = value.strip()
    if text.upper() in STATES.values():
        return text.upper()
    return STATES.get(text.lower())


def _name(value: str) -> str:
    # Ordinance lists name towns like "Düren, Stadt"; the property city may add a suffix
    # such as "Monheim am Rhein" for "Monheim".
    return value.split(",")[0].strip().lower()


async def cap_for(session: AsyncSession, prop: Any, day: date, default: Decimal) -> dict[str, Any]:
    """Reduced cap of the property's municipality on the day, else the general cap. Matching by
    municipality code first; by name only within the property's state, else flagged."""
    general = {"percent": default, "source": "allgemeine Kappungsgrenze", "flag": None}
    query = select(CapArea).where(
        CapArea.valid_from <= day,
        or_(CapArea.valid_to.is_(None), CapArea.valid_to >= day),
    )
    code = getattr(prop, "municipality_code", None)
    if code:
        area = await session.scalar(query.where(CapArea.municipality_code == code))
        if area is not None:
            return {
                "percent": area.cap_percent,
                "source": f"{area.municipality}: {area.source}",
                "flag": None,
            }
    city = (getattr(prop, "city", None) or "").strip().lower()
    if not city:
        return general
    state = state_code(getattr(prop, "state", None))
    if state:
        query = query.where(CapArea.state == state)
    matches = [
        a
        for a in (await session.scalars(query)).all()
        if city == _name(a.municipality) or city.startswith(_name(a.municipality) + " ")
    ]
    if not matches:
        return general
    area = max(matches, key=lambda a: len(_name(a.municipality)))
    flag = None
    if state is None:
        flag = (
            "Bundesland der Liegenschaft fehlt: Kappungsgebiet nur nach Gemeindename "
            "zugeordnet, prüfen."
        )
    elif city != _name(area.municipality):
        flag = f"Gemeinde nach Namensanfang zugeordnet ({area.municipality}), prüfen."
    return {
        "percent": area.cap_percent,
        "source": f"{area.municipality}: {area.source}",
        "flag": flag,
    }


def _active(rows: Any, day: date) -> Any:
    return next(
        (r for r in rows if r.valid_from <= day and (r.valid_to is None or r.valid_to >= day)),
        None,
    )


async def statutory_check(
    session: AsyncSession, case: Any, contract: Any, prop: Any
) -> dict[str, Any]:
    """Checks with released rules only. Returns flags and computed values; nothing is released
    unless all needed parameters are released."""
    from mhvp.contracts.models import ContractPayment

    rules = await released_rules(session)
    missing = [c for c in NEEDED if c not in rules]
    if missing:
        return {"active": False, "missing_rules": missing, "flags": []}
    flags: list[str] = []
    out: dict[str, Any] = {"active": True, "flags": flags}
    rents = (
        await session.scalars(
            select(ContractPayment)
            .where(
                ContractPayment.contract_id == contract.id,
                ContractPayment.payment_type_code == "rent",
            )
            .order_by(ContractPayment.valid_from)
        )
    ).all()
    current = next(
        (
            r
            for r in rents
            if r.valid_from <= case.effective_date
            and (r.valid_to is None or r.valid_to >= case.effective_date)
        ),
        None,
    )
    if current is not None:
        waiting = int(rules["waiting_months"])
        unchanged_until = _add_months(current.valid_from.replace(day=1), waiting)
        if current.valid_from.day != 1:
            unchanged_until = _add_months(unchanged_until, 1)
        out["earliest_by_waiting_period"] = unchanged_until.isoformat()
        if case.effective_date < unchanged_until:
            flags.append(
                f"Wartefrist: Miete wäre bei Wirksamkeit noch keine {waiting} Monate unverändert "
                f"(frühestens {unchanged_until:%d.%m.%Y})."
            )
    years = int(rules["cap_window_years"])
    ref_day = case.effective_date.replace(year=case.effective_date.year - years)
    reference = next(
        (
            r
            for r in rents
            if r.valid_from <= ref_day and (r.valid_to is None or r.valid_to >= ref_day)
        ),
        None,
    )
    cap = await cap_for(session, prop, case.effective_date, rules["cap_percent"])
    out["cap_percent"] = str(cap["percent"])
    out["cap_source"] = cap["source"]
    if cap["flag"]:
        flags.append(cap["flag"])
    if reference is None:
        flags.append(f"Keine Miete zum {ref_day:%d.%m.%Y} erfasst: Kappungsgrenze nicht prüfbar.")
    else:
        maximum = (reference.net * (1 + cap["percent"] / 100)).quantize(CENT)
        out["cap_reference_rent"] = str(reference.net)
        out["cap_max_rent"] = str(maximum)
        if case.target_rent > maximum:
            flags.append(f"Kappungsgrenze überschritten: höchstens {maximum} EUR.")
    justification = getattr(case, "justification", None)
    if justification == "vergleichswohnungen":
        needed = int(rules["comparison_flats_min"])
        if len(case.comparison_flats or []) < needed:
            flags.append(f"Mindestens {needed} Vergleichswohnungen benennen.")
    elif justification == "gutachten" and not case.expert_document_id:
        flags.append("Gutachten als Dokument hinterlegen.")
    elif justification == "mietspiegel" and not case.rent_index_name:
        flags.append("Mietspiegel mit Bezeichnung und Stand angeben.")
    elif justification is None:
        flags.append("Begründungsmittel wählen (Mietspiegel, Gutachten, Vergleichswohnungen).")
    return out


# API -------------------------------------------------------------------------------------

tenant_router = APIRouter(prefix="/letting/rent-law", tags=["letting"])
platform_router = APIRouter(prefix="/platform/rent-law", tags=["platform"])
READ = require_permission("contracts:read")


class RentLawRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Decimal | None = Field(default=None, ge=0)
    source_verified: bool | None = None
    source_url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, pattern="^(draft|released)$")


class CapAreaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(pattern="^[A-Z]{2}$")
    municipality: str = Field(min_length=2, max_length=200)
    municipality_code: str | None = Field(default=None, max_length=20)
    cap_percent: Decimal = Field(gt=0, lt=100)
    valid_from: date
    valid_to: date | None = None
    source: str = Field(min_length=5, max_length=4000)


def _rule_out(r: RentLawRule) -> dict[str, Any]:
    return {
        "code": r.code,
        "label": r.label,
        "norm": r.norm,
        "value": r.value,
        "unit": r.unit,
        "status": r.status,
        "source_verified": r.source_verified,
        "source_url": r.source_url,
        "note": r.note,
        "released_at": r.released_at,
    }


def _area_out(a: CapArea) -> dict[str, Any]:
    return {
        "id": a.id,
        "state": a.state,
        "municipality": a.municipality,
        "municipality_code": a.municipality_code,
        "cap_percent": a.cap_percent,
        "valid_from": a.valid_from,
        "valid_to": a.valid_to,
        "source": a.source,
    }


@tenant_router.get("/rules", summary="Mietrechtliche Parameter (lesend)")
async def list_rules(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(select(RentLawRule).order_by(RentLawRule.code))
        return [_rule_out(r) for r in rows.all()]


@tenant_router.get("/cap-areas", summary="Gebiete mit abgesenkter Kappungsgrenze (lesend)")
async def list_areas(
    request: Request, state: str | None = None, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(CapArea).order_by(CapArea.state, CapArea.municipality)
        if state:
            query = query.where(CapArea.state == state.upper())
        return [_area_out(a) for a in (await session.scalars(query)).all()]


@platform_router.put("/rules/{code}", summary="Parameter pflegen oder freigeben")
async def update_rule(
    code: str,
    body: RentLawRuleIn,
    request: Request,
    principal: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(RentLawRule, code, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_none=True)
        for key, value in data.items():
            setattr(row, key, value)
        if body.status == "released":
            if row.value is None or not row.source_verified:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Freigabe nur mit Wert und am Originaltext geprüfter Quelle.",
                )
            row.released_by, row.released_at = principal.user_id, datetime.now(UTC)
        elif data:
            row.status, row.released_by, row.released_at = "draft", None, None
        await session.flush()
        return _rule_out(row)


@platform_router.post("/cap-areas", status_code=201, summary="Kappungsgebiet anlegen")
async def create_area(
    body: CapAreaIn, request: Request, _: Principal = Depends(require_platform_admin)
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        row = CapArea(**body.model_dump())
        session.add(row)
        await session.flush()
        return _area_out(row)


@platform_router.put("/cap-areas/{area_id}", summary="Kappungsgebiet ändern")
async def update_area(
    area_id: uuid.UUID,
    body: CapAreaIn,
    request: Request,
    _: Principal = Depends(require_platform_admin),
) -> dict[str, Any]:
    async with platform_transaction(sessions(request)) as session:
        row = await session.get(CapArea, area_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        await session.flush()
        return _area_out(row)


def _eur(value: Any) -> str:
    q = Decimal(str(value)).quantize(CENT)
    whole, frac = f"{q:.2f}".split(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{'.'.join(groups)},{frac} EUR"


def _date(value: Any) -> str:
    d = value if isinstance(value, date) else date.fromisoformat(str(value))
    return f"{d:%d.%m.%Y}"


def letter_text(case: Any, unit_label: str, address: str) -> dict[str, Any]:
    """Draft of the tenant letter (§ 558 BGB) from the case data. Draft only; the operator
    checks it legally before use. Unknown facts stay as visible placeholders."""
    check = case.check or {}
    stat = check.get("statutory") or {}
    placeholders: list[str] = []

    def ph(label: str) -> str:
        placeholders.append(label)
        return f"[{label}]"

    lines = [
        "ENTWURF, vor Versand rechtlich zu prüfen",
        "",
        ph("Vermieter mit Anschrift"),
        "",
        ph("Mieter mit Anschrift"),
        "",
        f"Mieterhöhungsverlangen nach § 558 BGB für die Wohnung {unit_label}, {address}",
        "",
        "Sehr geehrte Damen und Herren,",
        "",
        f"die Nettokaltmiete für die von Ihnen gemietete Wohnung beträgt derzeit "
        f"{_eur(case.current_rent)} monatlich. Wir bitten Sie, einer Erhöhung der Nettokaltmiete "
        f"auf {_eur(case.target_rent)} monatlich ab dem {_date(case.effective_date)} "
        f"zuzustimmen. Die Erhöhung beträgt {_eur(case.target_rent - case.current_rent)}.",
        "",
        "Begründung:",
    ]
    if case.justification == "mietspiegel":
        lines.append(
            f"Die verlangte Miete ist die ortsübliche Vergleichsmiete nach dem Mietspiegel "
            f"{case.rent_index_name or ph('Bezeichnung des Mietspiegels')}"
            f"{', Stand ' + _date(case.rent_index_date) if case.rent_index_date else ''}. "
            f"Die Einordnung der Wohnung ist in der Anlage erläutert."
        )
    elif case.justification == "gutachten":
        lines.append(
            "Zur Begründung fügen wir das mit Gründen versehene Gutachten eines öffentlich "
            "bestellten und vereidigten Sachverständigen bei."
        )
    elif case.justification == "vergleichswohnungen":
        lines.append("Zur Begründung benennen wir folgende vergleichbare Wohnungen:")
        for flat in case.comparison_flats or []:
            rate = str(flat.get("rent_per_sqm")).replace(".", ",")
            lines.append(f"{flat.get('address')}: {rate} EUR je m²")
    else:
        lines.append(ph("Begründungsmittel: Mietspiegel, Gutachten oder Vergleichswohnungen"))
    lines.append("")
    if stat.get("active") and stat.get("cap_max_rent"):
        lines.append(
            f"Die Kappungsgrenze von {Decimal(stat['cap_percent']).normalize():f} % ist "
            f"eingehalten; ausgehend von {_eur(stat['cap_reference_rent'])} beträgt die "
            f"zulässige Höchstmiete {_eur(stat['cap_max_rent'])}."
        )
    else:
        lines.append(ph("Angaben zur Kappungsgrenze und zur Wartefrist prüfen"))
    lines.append("")
    if check.get("consent_until"):
        lines.append(
            f"Wir bitten Sie, Ihre Zustimmung bis zum {_date(check['consent_until'])} zu erklären."
        )
    else:
        until = ph("Frist nach Zugang")
        lines.append(f"Wir bitten Sie, Ihre Zustimmung bis zum {until} zu erklären.")
    lines += [
        "Die Erhöhung wird nur mit Ihrer Zustimmung wirksam.",
        "",
        "Mit freundlichen Grüßen",
        "",
        ph("Name und Funktion"),
        "",
        "Anlagen: "
        + ("Mietspiegelauszug" if case.justification == "mietspiegel" else ph("Anlagen")),
    ]
    return {"status": "draft", "text": "\n".join(lines), "placeholders": placeholders}
