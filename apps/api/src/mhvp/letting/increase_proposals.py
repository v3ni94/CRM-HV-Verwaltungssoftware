"""Rent increase proposals (AN18, AO03, GAK-203).

Pure functions plus the daily job that prepares due graduated steps (``contract_graduated_step``)
and index adjustments (``contract.index_agreement`` against released ``consumer_price_index``
values) as draft ``rent_increase_case`` rows. Nothing is applied, sent or posted; the job runs
only for tenants with the switch ``rent_increase_proposals = draft`` (default ``off``). No waiting
period, effective date rule, index source or notice form is fixed here (question AN18-01,
Rechtsanwalt, G1): the proposed effective date is only a placeholder that the user must check.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.money import round_cents


@dataclass(frozen=True)
class GraduatedStep:
    valid_from: date
    net: Decimal


@dataclass(frozen=True)
class IncreaseProposal:
    basis: str
    effective_date: date
    current_rent: Decimal
    target_rent: Decimal
    reason: str


def due_graduated_steps(
    steps: list[GraduatedStep],
    existing_starts: set[date],
    today: date,
    horizon_days: int,
    current_rent: Decimal,
) -> list[IncreaseProposal]:
    """Steps starting within ``horizon_days`` from ``today`` without a rent line yet."""
    until = today + timedelta(days=horizon_days)
    out: list[IncreaseProposal] = []
    previous = current_rent
    for step in sorted(steps, key=lambda s: s.valid_from):
        if step.valid_from in existing_starts or not today <= step.valid_from <= until:
            previous = step.net if step.valid_from <= today else previous
            continue
        out.append(
            IncreaseProposal(
                "graduated",
                step.valid_from,
                previous,
                step.net,
                f"Staffelstufe ab {step.valid_from.strftime('%d.%m.%Y')} laut Vertrag.",
            )
        )
        previous = step.net
    return out


def index_adjustment(
    current_rent: Decimal,
    base_index: Decimal,
    current_index: Decimal,
    effective_date: date,
) -> IncreaseProposal | None:
    """Rent changed in the ratio of the index values (rounded half up); None without a rise.

    Whether and when an adjustment may be declared is not decided here (AN18-01)."""
    if base_index <= 0 or current_index <= base_index:
        return None
    target = round_cents(current_rent * current_index / base_index)
    change = round_cents((current_index / base_index - 1) * 100)
    return IncreaseProposal(
        "index",
        effective_date,
        current_rent,
        target,
        f"Indexänderung {base_index} auf {current_index} ({change} Prozent), nur Vorschlag.",
    )


# Product safeguard, not a legal rule: graduated steps are proposed this many days ahead.
HORIZON_DAYS = 60
SERIES_PATTERN = r"^[A-Za-z0-9_.-]{1,40}$"
_MONTH_ISO = re.compile(r"^(\d{4})-(\d{2})(?:-01)?$")
_MONTH_DE = re.compile(r"^(\d{2})[./](\d{4})$")


def parse_month(raw: str) -> date:
    """``2026-08``, ``2026-08-01``, ``08.2026`` or ``08/2026`` to the first day of the month."""
    text_ = raw.strip()
    if m := _MONTH_ISO.match(text_):
        year, month = int(m.group(1)), int(m.group(2))
    elif m := _MONTH_DE.match(text_):
        month, year = int(m.group(1)), int(m.group(2))
    else:
        raise ValueError(f"Monat nicht lesbar: {raw!r}")
    if not 1 <= month <= 12 or year < 1900:
        raise ValueError(f"Monat nicht lesbar: {raw!r}")
    return date(year, month, 1)


def parse_index_value(raw: str) -> Decimal:
    """Index value with decimal comma or point, positive, at most 8 decimals."""
    text_ = raw.strip().replace(" ", "")
    if "," in text_:
        text_ = text_.replace(".", "").replace(",", ".")
    try:
        value = Decimal(text_)
    except InvalidOperation:
        raise ValueError(f"Indexwert nicht lesbar: {raw!r}") from None
    exponent = value.as_tuple().exponent
    if not value.is_finite() or value <= 0 or (isinstance(exponent, int) and exponent < -8):
        raise ValueError(f"Indexwert ungültig: {raw!r}")
    return value


def parse_cpi_csv(content: str) -> list[tuple[date, Decimal]]:
    """Rows ``month;value`` (separator ``;``, ``,`` with point decimals, or tab). A first line
    without a readable month is taken as header. Duplicate months are refused."""
    rows: list[tuple[date, Decimal]] = []
    seen: set[date] = set()
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        sep = ";" if ";" in line else "\t" if "\t" in line else ","
        parts = [p.strip().strip('"') for p in line.split(sep)]
        if len(parts) != 2:
            raise ValueError(f"Zeile {number}: zwei Spalten Monat und Wert erwartet.")
        try:
            month = parse_month(parts[0])
        except ValueError:
            if not rows and number == 1:
                continue  # header
            raise ValueError(f"Zeile {number}: Monat nicht lesbar.") from None
        try:
            value = parse_index_value(parts[1])
        except ValueError as exc:
            raise ValueError(f"Zeile {number}: {exc}") from None
        if month in seen:
            raise ValueError(f"Zeile {number}: Monat doppelt.")
        seen.add(month)
        rows.append((month, value))
    if not rows:
        raise ValueError("Keine Indexwerte gefunden.")
    return rows


def first_of_next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


async def latest_released_index(session: AsyncSession, series: str) -> tuple[date, Decimal] | None:
    from mhvp.platform.models import ConsumerPriceIndex as Cpi

    row = (
        await session.execute(
            select(Cpi.month, Cpi.value)
            .where(Cpi.series == series, Cpi.released.is_(True))
            .order_by(Cpi.month.desc())
            .limit(1)
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def _rent_net(session: AsyncSession, contract_id: uuid.UUID, day: date) -> Decimal | None:
    from mhvp.contracts.models import ContractPayment

    net: Decimal | None = await session.scalar(
        select(ContractPayment.net)
        .where(
            ContractPayment.contract_id == contract_id,
            ContractPayment.payment_type_code == "rent",
            ContractPayment.valid_from <= day,
            or_(ContractPayment.valid_to.is_(None), ContractPayment.valid_to >= day),
        )
        .order_by(ContractPayment.valid_from.desc())
        .limit(1)
    )
    return net


def _case(
    tenant_id: uuid.UUID, contract_id: uuid.UUID, p: IncreaseProposal, basis_data: dict[str, Any]
) -> Any:
    from mhvp.letting.models import RentIncreaseCase

    increase = p.target_rent - p.current_rent
    return RentIncreaseCase(
        tenant_id=tenant_id,
        contract_id=contract_id,
        basis=p.basis,
        current_rent=p.current_rent,
        target_rent=p.target_rent,
        effective_date=p.effective_date,
        status="draft",
        source_note=p.reason,
        basis_data=basis_data,
        check={
            "proposal": True,
            "origin": "job",
            "increase": str(increase),
            "ok": False,
            "flags": ["proposal_unchecked"],
            "note": (
                "Vorschlag des Tagesjobs. Wirksamkeitszeitpunkt, Wartefrist und Form sind nicht "
                "geprüft (AN18-01); nichts wird angewendet oder versendet."
            ),
        },
    )


async def propose_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, today: date, *, horizon_days: int = HORIZON_DAYS
) -> dict[str, int]:
    """Draft cases for due graduated steps and index rises of active tenancies (RLS scoped).

    Idempotent: a step already present as rent line or case and an index value already
    proposed for the contract are skipped. Returns counters."""
    from mhvp.contracts.models import (
        Contract,
        ContractGraduatedStep,
        ContractKind,
        ContractPayment,
    )
    from mhvp.letting.models import RentIncreaseCase

    counts = {"graduated": 0, "index": 0, "skipped": 0}
    contracts = (
        await session.scalars(
            select(Contract).where(
                Contract.kind == ContractKind.TENANCY,
                Contract.start_date <= today,
                or_(Contract.end_date.is_(None), Contract.end_date >= today),
            )
        )
    ).all()
    for contract in contracts:
        steps = (
            await session.scalars(
                select(ContractGraduatedStep).where(
                    ContractGraduatedStep.contract_id == contract.id
                )
            )
        ).all()
        if not steps and not contract.index_agreement:
            continue
        current = await _rent_net(session, contract.id, today)
        if current is None:
            counts["skipped"] += 1
            continue
        cases = (
            await session.scalars(
                select(RentIncreaseCase).where(RentIncreaseCase.contract_id == contract.id)
            )
        ).all()
        if steps:
            starts = set(
                (
                    await session.scalars(
                        select(ContractPayment.valid_from).where(
                            ContractPayment.contract_id == contract.id,
                            ContractPayment.payment_type_code == "rent",
                        )
                    )
                ).all()
            )
            starts |= {c.effective_date for c in cases if c.basis == "graduated"}
            due = due_graduated_steps(
                [GraduatedStep(s.valid_from, s.net) for s in steps],
                starts,
                today,
                horizon_days,
                current,
            )
            for p in due:
                data: dict[str, Any] = {
                    "steps": [
                        {"valid_from": p.effective_date.isoformat(), "rent": str(p.target_rent)}
                    ]
                }
                session.add(_case(tenant_id, contract.id, p, data))
                counts["graduated"] += 1
        agreement = contract.index_agreement or {}
        series, base = agreement.get("index_name"), agreement.get("base_index")
        if series and base:
            latest = await latest_released_index(session, str(series))
            base_month = agreement.get("base_month")
            if latest is None or (base_month and latest[0].isoformat() <= str(base_month)):
                continue
            proposed = {c.basis_data.get("index_current") for c in cases if c.basis == "index"}
            if str(latest[1]) in proposed:
                counts["skipped"] += 1
                continue
            p_index = index_adjustment(
                current, Decimal(str(base)), latest[1], first_of_next_month(today)
            )
            if p_index is None:
                continue
            index_data: dict[str, Any] = {
                "index_base": str(base),
                "index_current": str(latest[1]),
                "index_name": str(series),
                "index_month": latest[0].isoformat(),
            }
            session.add(_case(tenant_id, contract.id, p_index, index_data))
            counts["index"] += 1
    await session.flush()
    return counts
