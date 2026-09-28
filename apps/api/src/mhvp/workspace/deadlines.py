"""Deadline type catalogue, user created deadline entries, the notice period orientation and
property checklists (rule WS-01; handbook gaps Verwalterwechsel row 1, Mieterwechsel row 3,
Mieterhöhung rows 2 and 3).

Nothing here is a legal deadline calculation (rule 0.1.3, M1-09): every duration is entered
by the operator per tenant without a default, every computed date is returned with
``verify=True`` and labelled "zu verifizieren" in the CRM, and no computation blocks a
business action. Money and gates are not touched.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.models import ComplianceDeadline, DeadlineEntry, DeadlineType

# Events a deadline type starts from. The trigger only names the event; the date is always
# entered by the user (or taken from the record the deadline is created from).
TRIGGERS: tuple[str, ...] = (
    "termination_received",
    "handover_done",
    "rent_increase_access",
    "management_start",
    "management_end",
    "contract_end",
    "manual",
)
# Records a deadline can be created from (``DeadlineEntry.source_type``).
SOURCE_TYPES: tuple[str, ...] = ("ticket", "contract", "unit", "property", "rent_increase_case")
# Kind of the mirrored ``compliance_deadline`` row and the generated calendar entry.
CUSTOM_KIND = "custom_deadline"
CUSTOM_SOURCE_TYPE = "deadline_entry"
# Seeded per tenant without a duration (the operator enters it, "zu verifizieren").
SYSTEM_TYPES: tuple[tuple[str, str, str], ...] = (
    ("verwalterwechsel", "Verwalterwechsel", "management_start"),
    ("kautionsabrechnung", "Kautionsabrechnung", "handover_done"),
    ("mieterhoehung", "Mieterhöhung", "rent_increase_access"),
)
# Checklist templates per kind; ``manager_change`` mirrors the checklist of the handbook page
# docs/handbuch/anleitung-verwalterwechsel.md (order kept).
CHECKLIST_TEMPLATES: dict[str, tuple[tuple[str, str], ...]] = {
    "manager_change": (
        ("management_type", "Verwaltungsart vor Anlage geklärt"),
        ("property_created", "Objekt angelegt, Verwaltungsbeginn eingetragen"),
        ("units_imported", "Gebäude, Einheiten und Schlüsselwerte per Import angelegt und geprüft"),
        ("contacts", "Kontakte angelegt, Dubletten geprüft, Rollen gesetzt"),
        ("contracts", "Verträge angelegt; Importverträge durch die Geschäftsführung freigegeben"),
        ("bank_accounts", "Bankkonten zugeordnet, Standardkonto gesetzt; neue IBAN freigegeben"),
        ("documents", "Unterlagen der Vorverwaltung hochgeladen und im richtigen Ordner abgelegt"),
        (
            "completeness",
            "Vollständigkeit geprüft, Nachforderungsschreiben freigegeben und versandt, "
            "Kopie abgelegt",
        ),
        ("deadline", "Frist Verwalterwechsel mit Fälligkeit und Verantwortlichem angelegt"),
        ("legal_review", "Rechtliche Punkte durch Rechtsanwalt geprüft"),
    ),
}


# Date arithmetic (pure, tested with fixed values) ---------------------------------------


def add_months(day: date, months: int) -> date:
    """Calendar month shift; a day beyond the target month's length is clamped to its last
    day (31.01. + 1 month = 28.02. or 29.02.)."""
    index = day.month - 1 + months
    year = day.year + index // 12
    month = index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last))


def end_of_month(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def compute_due(trigger_on: date, months: int | None, days: int | None) -> date | None:
    """Trigger date plus the entered duration; None when the type carries no duration at all
    (then the due date must be entered)."""
    if months is None and days is None:
        return None
    return add_months(trigger_on, months or 0) + timedelta(days=days or 0)


def notice_period_end(termination_on: date, months: int, days: int, *, to_month_end: bool) -> date:
    """Orientation for the end of a tenancy after a termination received on
    ``termination_on``: the entered notice period (months and days) is added; with
    ``to_month_end`` the result is moved to the last day of its month. The values come from
    the contract or the user, never from a legal rule; the result is marked "zu verifizieren"
    and never blocks the termination."""
    end = add_months(termination_on, months) + timedelta(days=days)
    return end_of_month(end) if to_month_end else end


# Catalogue ------------------------------------------------------------------------------


async def ensure_system_types(
    session: AsyncSession, tenant_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> None:
    """Seed the three system types of the tenant once (idempotent, no duration)."""
    existing = set(
        (await session.scalars(select(DeadlineType.code).where(DeadlineType.is_system))).all()
    )
    for code, name, trigger in SYSTEM_TYPES:
        if code in existing:
            continue
        session.add(
            DeadlineType(
                tenant_id=tenant_id,
                code=code,
                name=name,
                trigger=trigger,
                is_system=True,
                is_active=True,
                created_by=actor_user_id,
            )
        )
    await session.flush()


# Sources --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceInfo:
    reference: str
    property_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    ticket_id: uuid.UUID | None


async def resolve_source(
    session: AsyncSession, source_type: str, source_id: uuid.UUID
) -> SourceInfo:
    """Record the deadline is created from; raises 404 when it does not exist in the tenant.
    The links (property, unit, contract, ticket) are copied so the deadline list and the
    calendar can show the context without joining the source later."""
    if source_type == "ticket":
        from mhvp.tickets.models import Ticket

        ticket = await session.get(Ticket, source_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return SourceInfo(
            reference=f"Ticket #{ticket.number} {ticket.title}",
            property_id=ticket.property_id,
            unit_id=ticket.unit_id,
            contract_id=None,
            ticket_id=ticket.id,
        )
    if source_type == "contract":
        from mhvp.contracts.models import Contract

        contract = await session.get(Contract, source_id)
        if contract is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return SourceInfo(
            reference=f"Vertrag {contract.number}",
            property_id=contract.property_id,
            unit_id=contract.unit_id,
            contract_id=contract.id,
            ticket_id=None,
        )
    if source_type == "unit":
        from mhvp.properties.models import Unit

        unit = await session.get(Unit, source_id)
        if unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return SourceInfo(
            reference=f"Einheit {unit.number}",
            property_id=unit.property_id,
            unit_id=unit.id,
            contract_id=None,
            ticket_id=None,
        )
    if source_type == "property":
        from mhvp.properties.models import Property

        prop = await session.get(Property, source_id)
        if prop is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return SourceInfo(
            reference=f"Objekt {prop.number} {prop.name}",
            property_id=prop.id,
            unit_id=None,
            contract_id=None,
            ticket_id=None,
        )
    if source_type == "rent_increase_case":
        from mhvp.contracts.models import Contract
        from mhvp.letting.models import RentIncreaseCase

        case = await session.get(RentIncreaseCase, source_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        contract = await session.get(Contract, case.contract_id)
        return SourceInfo(
            reference=f"Mieterhöhung Vertrag {contract.number if contract else ''}".strip(),
            property_id=contract.property_id if contract else None,
            unit_id=contract.unit_id if contract else None,
            contract_id=case.contract_id,
            ticket_id=None,
        )
    raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Quelle.")


# Mirror into the deadline list (compliance_deadline) ------------------------------------


def entry_candidate(entry: DeadlineEntry, type_name: str) -> dict[str, Any]:
    """Candidate of the deadline job for one open entry (same shape as ``jobs._candidate``)."""
    return {
        "kind": CUSTOM_KIND,
        "source_type": CUSTOM_SOURCE_TYPE,
        "source_id": entry.id,
        "reference": f"{type_name}: {entry.title}"[:300],
        "due_on": entry.due_on,
        "property_id": entry.property_id,
    }


async def read_entries(session: AsyncSession, since: date, today: date) -> list[dict[str, Any]]:
    """Source reader of ``jobs.calendar_sources``: open entries due from ``since`` on."""
    rows = (
        await session.execute(
            select(DeadlineEntry, DeadlineType.name)
            .join(DeadlineType, DeadlineType.id == DeadlineEntry.type_id)
            .where(DeadlineEntry.status == "open", DeadlineEntry.due_on >= since)
        )
    ).all()
    return [entry_candidate(entry, name) for entry, name in rows]


async def materialize(
    session: AsyncSession, entry: DeadlineEntry, type_name: str, lead_days: int
) -> ComplianceDeadline:
    """Write the compliance row of a new entry at once so the list, the calendar and the
    lead time notification do not wait for the nightly job (which keeps it in sync)."""
    cand = entry_candidate(entry, type_name)
    row = await session.scalar(
        select(ComplianceDeadline).where(
            ComplianceDeadline.kind == CUSTOM_KIND,
            ComplianceDeadline.source_id == entry.id,
            ComplianceDeadline.due_on == entry.due_on,
        )
    )
    if row is None:
        row = ComplianceDeadline(
            tenant_id=entry.tenant_id, lead_days=lead_days, status="open", **cand
        )
        session.add(row)
    else:
        row.status, row.done_at, row.reference = "open", None, cand["reference"]
    await session.flush()
    return row


async def close_mirror(session: AsyncSession, entry: DeadlineEntry) -> None:
    rows = (
        await session.scalars(
            select(ComplianceDeadline).where(
                ComplianceDeadline.kind == CUSTOM_KIND,
                ComplianceDeadline.source_id == entry.id,
                ComplianceDeadline.status == "open",
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.status, row.done_at = "done", now
    await session.flush()


async def responsible_for_deadlines(
    session: AsyncSession, entry_ids: set[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Responsible user per entry id, for the lead time notification of the job."""
    if not entry_ids:
        return {}
    rows = (
        await session.execute(
            select(DeadlineEntry.id, DeadlineEntry.responsible_user_id).where(
                DeadlineEntry.id.in_(entry_ids), DeadlineEntry.responsible_user_id.is_not(None)
            )
        )
    ).all()
    return {entry_id: user_id for entry_id, user_id in rows if user_id is not None}


def checklist_items(kind: str) -> list[dict[str, Any]]:
    return [
        {"code": code, "label": label, "done_at": None, "done_by": None, "done_by_name": None}
        for code, label in CHECKLIST_TEMPLATES[kind]
    ]
