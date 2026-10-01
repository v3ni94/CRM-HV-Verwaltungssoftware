"""Object of a journal line (Q15-01, AE21, migration 0377).

``journal_line.property_id`` names the object (property) a line belongs to. It is set once when
the draft line is written and never changed after posting (B02); a wrong object on a posted line
is corrected by reversal and a new posting. Derivation, in this order:

1. ``explicit``: the property given with the line (API ``lines[].property_id``);
2. ``unit``: ``unit.property_id`` of the line's unit; an explicit property must match it;
3. ``contract``: ``contract.property_id`` of the entry's contract (``journal_entry.contract_id``).

Nothing else is derived: no object from the ledger, the cost center or the text. Lines without
any of the three sources stay without object ("ohne Objekt"). The database enforces the unit
rule for every writer (check ``ck_journal_line_property_with_unit`` and trigger
``journal_line_property``).

The drift report compares every stored object with its sources: a line with unit whose object
differs from the unit's object is a hard finding (also in ``GET /ledgers/{id}/checks``); a
different contract or ledger object is a hint for review, never an automatic change.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import JournalEntry, JournalLine, Ledger
from mhvp.core.problems import ErrorCodes, ProblemError

if TYPE_CHECKING:
    from mhvp.accounting.services import LineIn

DRIFT_ROW_LIMIT = 500

# Drift kinds: ``unit_mismatch`` is a hard finding (the database refuses it for new lines);
# the others are hints for review.
HARD_KINDS = ("unit_mismatch",)
HINT_KINDS = ("contract_mismatch", "contract_unfilled", "ledger_mismatch")


async def resolve(
    session: AsyncSession, entry: JournalEntry, lines: Sequence[LineIn]
) -> list[uuid.UUID | None]:
    """Object per line in input order (explicit, unit, contract); refuses unknown units and
    properties and an explicit object that differs from the unit's object (422)."""
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Property, Unit

    unit_ids = {line.unit_id for line in lines if line.unit_id is not None}
    units: dict[uuid.UUID, uuid.UUID] = {}
    if unit_ids:
        rows = await session.execute(select(Unit.id, Unit.property_id).where(Unit.id.in_(unit_ids)))
        units = dict(rows.tuples().all())
        missing = unit_ids - set(units)
        if missing:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Einheit der Buchungszeile unbekannt.")
    explicit = {line.property_id for line in lines if line.property_id is not None}
    if explicit:
        found = set(await session.scalars(select(Property.id).where(Property.id.in_(explicit))))
        if explicit - found:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Objekt der Buchungszeile unbekannt.")
    contract_property: uuid.UUID | None = None
    if entry.contract_id is not None:
        contract_property = await session.scalar(
            select(Contract.property_id).where(Contract.id == entry.contract_id)
        )
    out: list[uuid.UUID | None] = []
    for no, line in enumerate(lines, start=1):
        unit_property = units.get(line.unit_id) if line.unit_id is not None else None
        if line.property_id is not None:
            if unit_property is not None and line.property_id != unit_property:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=f"Zeile {no}: Das Objekt passt nicht zum Objekt der Einheit.",
                )
            out.append(line.property_id)
        elif unit_property is not None:
            out.append(unit_property)
        else:
            out.append(contract_property)
    return out


def _drift_kind(ledger: Ledger) -> Any:
    """SQL drift kind per line (``NULL`` when consistent), same order as the derivation."""
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit

    stored = JournalLine.property_id
    branches: list[tuple[Any, str | None]] = [
        (
            JournalLine.unit_id.is_not(None) & stored.is_distinct_from(Unit.property_id),
            "unit_mismatch",
        ),
        (JournalLine.unit_id.is_not(None), None),
        (Contract.property_id.is_not(None) & stored.is_(None), "contract_unfilled"),
        (Contract.property_id.is_not(None) & (stored != Contract.property_id), "contract_mismatch"),
    ]
    if ledger.property_id is not None:
        branches.append((stored.is_not(None) & (stored != ledger.property_id), "ledger_mismatch"))
    return case(*branches, else_=None)


def _drift_base(ledger: Ledger, start: date | None, end: date | None, *columns: Any) -> Any:
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit

    query = (
        select(*columns)
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .outerjoin(Unit, Unit.id == JournalLine.unit_id)
        .outerjoin(Contract, Contract.id == JournalEntry.contract_id)
        .where(JournalEntry.ledger_id == ledger.id)
    )
    if start is not None:
        query = query.where(JournalEntry.booking_date >= start)
    if end is not None:
        query = query.where(JournalEntry.booking_date <= end)
    return query


async def drift(
    session: AsyncSession, ledger: Ledger, start: date | None = None, end: date | None = None
) -> dict[str, Any]:
    """Stored object of each line against unit, contract and ledger (drift report)."""
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit

    kind = _drift_kind(ledger).label("kind")
    counts = dict.fromkeys((*HARD_KINDS, *HINT_KINDS), 0)
    # Grouped over a subquery: the CASE carries bound parameters, which PostgreSQL would not
    # match between the select list and a repeated GROUP BY expression.
    inner = _drift_base(ledger, start, end, kind).subquery()
    grouped = await session.execute(
        select(inner.c.kind, func.count()).where(inner.c.kind.is_not(None)).group_by(inner.c.kind)
    )
    for name, n in grouped.tuples().all():
        counts[str(name)] = int(n)
    without = await session.scalar(
        _drift_base(ledger, start, end, func.count(JournalLine.id)).where(
            JournalLine.property_id.is_(None)
        )
    )
    listed = await session.execute(
        _drift_base(
            ledger,
            start,
            end,
            JournalEntry.id,
            JournalEntry.fiscal_year,
            JournalEntry.number,
            JournalEntry.status,
            JournalEntry.booking_date,
            JournalLine.line_no,
            JournalLine.unit_id,
            JournalLine.property_id,
            Unit.property_id,
            Contract.property_id,
            kind,
        )
        .where(kind.is_not(None))
        .order_by(JournalEntry.booking_date, JournalEntry.id, JournalLine.line_no)
        .limit(DRIFT_ROW_LIMIT)
    )
    expected_of = {"unit": 0, "contract": 1, "ledger": 2}
    rows: list[dict[str, Any]] = []
    for (
        entry_id,
        year,
        number,
        status,
        booking_date,
        line_no,
        unit_id,
        stored,
        unit_property,
        contract_property,
        name,
    ) in listed.tuples().all():
        source = "unit" if name == "unit_mismatch" else name.split("_")[0]
        expected = (unit_property, contract_property, ledger.property_id)[expected_of[source]]
        rows.append(
            {
                "entry_id": entry_id,
                "number": f"{year}-{number}" if number is not None else None,
                "status": status.value,
                "booking_date": booking_date,
                "line_no": line_no,
                "unit_id": unit_id,
                "property_id": stored,
                "expected_property_id": expected,
                "source": source,
                "kind": name,
                "severity": "finding" if name in HARD_KINDS else "hint",
            }
        )
    total = sum(counts.values())
    return {
        "counts": counts,
        "without_property": int(without or 0),
        "findings": sum(counts[k] for k in HARD_KINDS),
        "hints": sum(counts[k] for k in HINT_KINDS),
        "rows": rows,
        "rows_truncated": total > len(rows),
        "note": (
            "Das Objekt einer Buchungszeile stammt aus der Angabe der Zeile, der Einheit oder "
            "dem Vertrag des Buchungssatzes. Abweichungen gebuchter Zeilen werden nicht "
            "geändert, sondern per Storno und neuer Buchung berichtigt."
        ),
    }


async def findings(session: AsyncSession, ledger: Ledger) -> list[str]:
    """Hard findings for ``services.checks``: lines with unit whose object is missing or
    differs from the unit's object."""
    from mhvp.properties.models import Unit

    rows = await session.execute(
        select(JournalEntry.id, JournalEntry.fiscal_year, JournalEntry.number, JournalLine.line_no)
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .join(Unit, Unit.id == JournalLine.unit_id)
        .where(
            JournalEntry.ledger_id == ledger.id,
            JournalLine.property_id.is_distinct_from(Unit.property_id),
        )
        .order_by(JournalEntry.booking_date, JournalLine.line_no)
        .limit(DRIFT_ROW_LIMIT)
    )
    return [
        f"Satz {f'{y}-{n}' if n is not None else entry_id} Zeile {no}: "
        "Objekt passt nicht zur Einheit"
        for entry_id, y, n, no in rows.all()
    ]
