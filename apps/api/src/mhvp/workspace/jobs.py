"""Daily jobs of section 15.1: ``tasks.digest`` (A40) and ``compliance.deadlines`` (A41).

Both jobs read data, write only their own tables (``digest_run``, ``compliance_deadline``)
and in-app notifications (``notify`` pattern), and never touch money or legally relevant
records. Dates are orientation only: the lead time comes from the tenant settings with a
documented default; the legal deadline calculation (time zone, receipt, end of period) is an
open operator decision (M1-09) and is neither computed nor claimed here.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.config import Settings
from mhvp.core.ids import uuid7
from mhvp.workspace.models import (
    CalendarEntry,
    ComplianceDeadline,
    DigestRun,
    WorkspaceJobSettings,
)
from mhvp.workspace.services import local_date, notify

DEFAULT_LEAD_DAYS = 30
DEADLINE_KINDS: tuple[str, ...] = (
    "contract_end",
    "contract_termination",
    "meter_calibration",
    "bank_consent",
    "document_retention_end",
    "service_contract_notice",
    "meeting_resolution_deadline",
    # P1 AP7 (spec 4.10): further date fields with a calendar entry.
    "energy_certificate",
    "move_in",
    "move_out",
    "maintenance",
    "note_follow_up",
    "meeting",
    "ticket_due",
    # M19-06: scheduled appointment of a work order (internal entry only, no invitation).
    "work_order_appointment",
    # Rule WS-01: user created deadlines from the tenant's deadline type catalogue
    # (``mhvp.workspace.deadlines``), mirrored from ``deadline_entry``.
    "custom_deadline",
)
# Fixed lead time per kind; overrides the tenant setting (M9-06: 14 days for the notice date
# of service provider contracts).
DEADLINE_LEAD_DAYS: dict[str, int] = {
    "service_contract_notice": 14,
    "meeting_resolution_deadline": 7,
}
# Read permission needed to see a kind (endpoint) and update permission of the recipients of
# the "lead time reached" notification (job). Bank consents are additionally covered by the
# ten day reminder of A29 (``mhvp.banking.tasks``); this list is the long range view.
DEADLINE_PERMISSIONS: dict[str, tuple[str, str]] = {
    "contract_end": ("contracts:read", "contracts:update"),
    "contract_termination": ("contracts:read", "contracts:update"),
    "meter_calibration": ("properties:read", "properties:update"),
    "bank_consent": ("accounting:read", "accounting:update"),
    "document_retention_end": ("documents:read", "documents:update"),
    "service_contract_notice": ("contracts:read", "contracts:update"),
    # Same permissions as the owners' meeting endpoints of the HOA module (M9-07).
    "meeting_resolution_deadline": ("accounting:read", "accounting:update"),
    "energy_certificate": ("properties:read", "properties:update"),
    "move_in": ("contracts:read", "contracts:update"),
    "move_out": ("contracts:read", "contracts:update"),
    "maintenance": ("properties:read", "properties:update"),
    "note_follow_up": ("contacts:read", "contacts:update"),
    "meeting": ("accounting:read", "accounting:update"),
    "ticket_due": ("tickets:read", "tickets:update"),
    "work_order_appointment": ("tickets:read", "tickets:update"),
    # The responsible person of the entry is notified instead when one is set (WS-01).
    "custom_deadline": ("tickets:read", "tickets:update"),
}
DEADLINE_NOTIFICATION_KIND = "compliance_deadline"
DIGEST_NOTIFICATION_KIND = "daily_digest"
DIGEST_LIST_LIMIT = 10
OPEN_TICKET_STATUSES = ("new", "in_progress", "waiting")


# Settings -----------------------------------------------------------------------------


async def job_settings(session: AsyncSession, tenant_id: uuid.UUID) -> WorkspaceJobSettings:
    """Row of the tenant; a missing row is returned as transient defaults (not inserted)."""
    row = await session.scalar(
        select(WorkspaceJobSettings).where(WorkspaceJobSettings.tenant_id == tenant_id)
    )
    if row is None:
        row = WorkspaceJobSettings(
            tenant_id=tenant_id, digest_mail_enabled=False, deadline_lead_days=DEFAULT_LEAD_DAYS
        )
    return row


async def save_job_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    digest_mail_enabled: bool | None,
    deadline_lead_days: int | None,
    actor_user_id: uuid.UUID | None,
) -> WorkspaceJobSettings:
    row = await session.scalar(
        select(WorkspaceJobSettings).where(WorkspaceJobSettings.tenant_id == tenant_id)
    )
    if row is None:
        row = WorkspaceJobSettings(tenant_id=tenant_id, created_by=actor_user_id)
        session.add(row)
    if digest_mail_enabled is not None:
        row.digest_mail_enabled = digest_mail_enabled
    if deadline_lead_days is not None:
        row.deadline_lead_days = deadline_lead_days
    row.updated_by = actor_user_id
    await session.flush()
    return row


# Deadlines (A41) -----------------------------------------------------------------------


# Source readers (P1 AP7, spec 4.10) ---------------------------------------------------
#
# Every dated obligation of the data model is read by one reader function that appends
# candidates ``{kind, source_type, source_id, reference, due_on, property_id}``. The
# candidates feed both the deadline list (``refresh_deadlines``, only future dates) and the
# generated calendar entries (``calendar_sync``, dates from ``CALENDAR_PAST_DAYS`` back).
# Readers of fields that other work packages add in parallel are registered only when the
# model carries the field (``hasattr``), see ``CALENDAR_SOURCES``.

Candidate = dict[str, Any]
SourceReader = Callable[[AsyncSession, date, date], Awaitable[list[Candidate]]]
# How far back generated calendar entries reach (historic move outs and meetings stay
# visible for a year); the deadline list itself starts at today.
CALENDAR_PAST_DAYS = 365
# Reminder codes (B.30) per kind before the date; maintenance uses its own ``remind_before``.
CALENDAR_REMINDERS: dict[str, list[str]] = {
    "contract_end": ["1m", "1d"],
    "contract_termination": ["1m", "1d"],
    "meter_calibration": ["1m"],
    "energy_certificate": ["3m", "1m"],
    "move_in": ["1d"],
    "move_out": ["1d"],
    "maintenance": ["14d"],
    "note_follow_up": ["0"],
    "meeting": ["14d", "1d"],
    "ticket_due": ["1d"],
    "work_order_appointment": ["1d"],
    "meeting_resolution_deadline": ["7d"],
    "service_contract_notice": ["14d"],
    "bank_consent": ["14d"],
    "document_retention_end": ["1m"],
    "custom_deadline": ["14d", "1d"],
}
DEFAULT_REMINDERS = ["1d"]


def _candidate(
    kind: str,
    source_type: str,
    source_id: uuid.UUID,
    reference: str,
    due_on: date | None,
    property_id: uuid.UUID | None = None,
) -> Candidate | None:
    if due_on is None:
        return None
    return {
        "kind": kind,
        "source_type": source_type,
        "source_id": source_id,
        "reference": reference[:300],
        "due_on": due_on,
        "property_id": property_id,
    }


async def _read_contracts(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    """Contract end, termination and, when the model carries them (AP3, 0150), the move
    in and move out dates (spec 4.5)."""
    from mhvp.contracts.models import Contract

    move_in = getattr(Contract, "move_in_on", None)
    move_out = getattr(Contract, "move_out_on", None)
    dated = [Contract.end_date >= since, Contract.termination_date >= since]
    if move_in is not None:
        dated.append(move_in >= since)
    if move_out is not None:
        dated.append(move_out >= since)
    out: list[Candidate] = []
    for c in (await session.scalars(select(Contract).where(or_(*dated)))).all():
        label = "Mietvertrag" if c.kind.value == "tenancy" else "Eigentumsverhältnis"
        ref = f"{label} {c.number}"
        fields = [
            ("contract_end", c.end_date),
            ("contract_termination", c.termination_date),
            ("move_in", getattr(c, "move_in_on", None)),
            ("move_out", getattr(c, "move_out_on", None)),
        ]
        for kind, value in fields:
            cand = _candidate(kind, "contract", c.id, ref, value, c.property_id)
            if cand is not None and cand["due_on"] >= since:
                out.append(cand)
    return out


async def _read_meters(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    from mhvp.properties.models import Meter, Property

    rows = (
        await session.execute(
            select(Meter, Property.number, Property.name)
            .join(Property, Property.id == Meter.property_id)
            .where(Meter.calibration_due_date >= since)
        )
    ).all()
    out: list[Candidate] = []
    for meter, number, name in rows:
        cand = _candidate(
            "meter_calibration",
            "meter",
            meter.id,
            f"Zähler {meter.number} ({number} {name})",
            meter.calibration_due_date,
            meter.property_id,
        )
        if cand is not None:
            out.append(cand)
    return out


async def _read_bank_consents(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    from mhvp.banking.models import BankConnection, ConnectionStatus, FinApiConnection

    out: list[Candidate] = []
    connections = (
        await session.scalars(
            select(BankConnection).where(BankConnection.status != ConnectionStatus.DISABLED)
        )
    ).all()
    for conn in connections:
        fa = await session.scalar(
            select(FinApiConnection).where(FinApiConnection.bank_connection_id == conn.id)
        )
        valid_until = (fa.consent_valid_until if fa is not None else None) or (
            conn.consent_valid_until
        )
        cand = _candidate(
            "bank_consent",
            "bank_connection",
            conn.id,
            f"Bankzustimmung {conn.bank_name}",
            valid_until,
        )
        if cand is not None and cand["due_on"] >= since:
            out.append(cand)
    return out


async def _read_documents(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    from mhvp.documents.models import Document

    rows = (
        await session.execute(
            select(Document.id, Document.title, Document.retention_until).where(
                Document.retention_until >= since
            )
        )
    ).all()
    out: list[Candidate] = []
    for doc_id, title, until in rows:
        cand = _candidate(
            "document_retention_end", "document", doc_id, f"Aufbewahrung {title}", until
        )
        if cand is not None:
            out.append(cand)
    return out


async def _read_service_contracts(
    session: AsyncSession, since: date, today: date
) -> list[Candidate]:
    from mhvp.contracts.service_contracts import ServiceContract, terms_of

    out: list[Candidate] = []
    rows = (
        await session.scalars(select(ServiceContract).where(ServiceContract.cancelled_at.is_(None)))
    ).all()
    for sc in rows:
        cand = _candidate(
            "service_contract_notice",
            "service_contract",
            sc.id,
            f"Kündigungsfrist Dienstleistervertrag {sc.title}",
            terms_of(sc, today).notice_deadline,
            sc.property_id,
        )
        if cand is not None and cand["due_on"] >= since:
            out.append(cand)
    return out


async def _read_meetings(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    """Meeting date of every owners' meeting (spec 4.8) and the entered resolution
    deadline of virtual meetings (M9-07), never a computed one."""
    from mhvp.hoa.models import Meeting
    from mhvp.properties.models import LegalEntity

    out: list[Candidate] = []
    # The meeting belongs to a legal entity (the HOA); its property is the route of the
    # entry (/weg/{property_id}/versammlung/{meeting_id}, ``links.target_href``).
    rows = (
        await session.execute(
            select(Meeting, LegalEntity.property_id)
            .join(LegalEntity, LegalEntity.id == Meeting.legal_entity_id)
            .where(or_(Meeting.scheduled_at >= since, Meeting.resolution_deadline_at >= since))
        )
    ).all()
    for m, property_id in rows:
        held_on = local_date(m.scheduled_at)
        if held_on >= since:
            cand = _candidate(
                "meeting",
                "owners_meeting",
                m.id,
                f"Eigentümerversammlung am {held_on:%d.%m.%Y}",
                held_on,
                property_id,
            )
            if cand is not None:
                out.append(cand)
        if m.mode == "virtual" and m.resolution_deadline_at is not None:
            cand = _candidate(
                MEETING_RESOLUTION_KIND,
                "owners_meeting",
                m.id,
                meeting_deadline_reference(held_on, m.resolution_deadline_source),
                m.resolution_deadline_at,
                property_id,
            )
            if cand is not None and m.resolution_deadline_at >= since:
                out.append(cand)
    return out


async def _read_maintenance(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    from mhvp.properties.models import MaintenanceItem, Property

    rows = (
        await session.execute(
            select(MaintenanceItem, Property.number, Property.name)
            .join(Property, Property.id == MaintenanceItem.property_id)
            .where(MaintenanceItem.status == "open", MaintenanceItem.due_date >= since)
        )
    ).all()
    out: list[Candidate] = []
    for item, number, name in rows:
        cand = _candidate(
            "maintenance",
            "maintenance_item",
            item.id,
            f"{item.title} ({number} {name})",
            item.due_date,
            item.property_id,
        )
        if cand is not None:
            cand["reminders"] = [item.remind_before] if item.remind_before else None
            out.append(cand)
    return out


async def _read_energy_certificates(
    session: AsyncSession, since: date, today: date
) -> list[Candidate]:
    """Expiry of the energy certificate per building (spec 4.3); the property level field
    is read as long as it exists (open question 1 of the P1 plan)."""
    from mhvp.properties.models import Building, Property

    out: list[Candidate] = []
    rows = (
        await session.execute(
            select(Building, Property.number, Property.name)
            .join(Property, Property.id == Building.property_id)
            .where(Building.energy_certificate_valid_until >= since)
        )
    ).all()
    for b, number, name in rows:
        cand = _candidate(
            "energy_certificate",
            "building",
            b.id,
            f"Energieausweis {b.name} ({number} {name})",
            b.energy_certificate_valid_until,
            b.property_id,
        )
        if cand is not None:
            out.append(cand)
    property_column = getattr(Property, "energy_certificate_valid_until", None)
    if property_column is not None:
        props = (await session.scalars(select(Property).where(property_column >= since))).all()
        for p in props:
            cand = _candidate(
                "energy_certificate",
                "property",
                p.id,
                f"Energieausweis Objekt {p.number} {p.name}",
                getattr(p, "energy_certificate_valid_until", None),
                p.id,
            )
            if cand is not None:
                out.append(cand)
    return out


async def _read_note_follow_ups(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    """Follow up dates of contact notes (spec 4.1 Notizen)."""
    from mhvp.contacts.models import Contact, ContactNote

    rows = (
        await session.execute(
            select(ContactNote, Contact.display_name)
            .join(Contact, Contact.id == ContactNote.contact_id)
            .where(ContactNote.follow_up_on >= since)
        )
    ).all()
    out: list[Candidate] = []
    for note, display_name in rows:
        cand = _candidate(
            "note_follow_up",
            "contact",
            note.contact_id,
            f"Wiedervorlage {display_name}",
            note.follow_up_on,
        )
        if cand is not None:
            cand["source_id"] = note.id
            cand["source_type"] = "contact_note"
            out.append(cand)
    return out


async def _read_ticket_due(session: AsyncSession, since: date, today: date) -> list[Candidate]:
    """Ticket deadlines (spec 4.9): the due date field of open tickets. Registered only when
    the ticket model carries ``due_on`` (P4); the SLA due time is not a deadline here, its
    escalation has its own notifications."""
    from mhvp.tickets.models import Ticket, TicketStatus

    due_column = getattr(Ticket, "due_on", None)
    if due_column is None:
        return []
    open_statuses = [TicketStatus(s) for s in OPEN_TICKET_STATUSES]
    rows = (
        await session.scalars(
            select(Ticket).where(Ticket.status.in_(open_statuses), due_column >= since)
        )
    ).all()
    out: list[Candidate] = []
    for t in rows:
        cand = _candidate(
            "ticket_due",
            "ticket",
            t.id,
            f"Ticket {t.number} {t.title}",
            getattr(t, "due_on", None),
            t.property_id,
        )
        if cand is not None:
            out.append(cand)
    return out


async def _read_work_order_appointments(
    session: AsyncSession, since: date, today: date
) -> list[Candidate]:
    """M19-06: appointment date (``scheduled_at``, local date Europe/Berlin) of work orders
    that are scheduled or in progress. Internal calendar entry only; nothing is sent to the
    service provider or any external calendar here (rule M19-06)."""
    from mhvp.tickets.models import OrderStatus, Ticket, WorkOrder
    from mhvp.workspace.services import _LOCAL

    rows = (
        await session.execute(
            select(WorkOrder, Ticket.number, Ticket.property_id)
            .outerjoin(Ticket, Ticket.id == WorkOrder.ticket_id)
            .where(
                WorkOrder.scheduled_at.is_not(None),
                WorkOrder.status.in_([OrderStatus.SCHEDULED, OrderStatus.IN_PROGRESS]),
            )
        )
    ).all()
    out: list[Candidate] = []
    for order, number, property_id in rows:
        day = order.scheduled_at.astimezone(_LOCAL).date()
        if day < since:
            continue
        label = f"Auftragstermin {order.scheduled_at.astimezone(_LOCAL):%H:%M} Uhr"
        if number:
            label += f" Ticket {number}"
        cand = _candidate("work_order_appointment", "work_order", order.id, label, day, property_id)
        if cand is not None:
            out.append(cand)
    return out


def calendar_sources() -> list[SourceReader]:
    """Fixed registry of all source readers (GAH-312). Every reader is registered
    unconditionally; a renamed model field fails loudly in the reader and in the test
    ``test_calendar_sources_complete`` instead of silently dropping a deadline source."""
    readers: list[SourceReader] = [
        _read_contracts,
        _read_meters,
        _read_bank_consents,
        _read_documents,
        _read_service_contracts,
        _read_meetings,
        _read_maintenance,
        _read_energy_certificates,
    ]
    readers.append(_read_note_follow_ups)
    readers.append(_read_ticket_due)
    readers.append(_read_work_order_appointments)
    readers.append(_read_deadline_entries)
    return readers


async def _read_deadline_entries(
    session: AsyncSession, since: date, today: date
) -> list[Candidate]:
    """Open user created deadlines (rule WS-01, ``mhvp.workspace.deadlines``)."""
    from mhvp.workspace.deadlines import read_entries

    return await read_entries(session, since, today)


async def deadline_candidates(
    session: AsyncSession, tenant_id: uuid.UUID, today: date, *, since: date | None = None
) -> list[dict[str, Any]]:
    """Every dated obligation known to the data model from ``since`` (default: today) on,
    keyed by (kind, source, date). Resolution deadlines of virtual owners' meetings come
    from the entered field with its source (M9-07), never from a computation."""
    lower = today if since is None else since
    out: list[Candidate] = []
    for reader in calendar_sources():
        out.extend(await reader(session, lower, today))
    return out


MEETING_RESOLUTION_KIND = "meeting_resolution_deadline"
# Fixed lead time of the resolution deadline (M9-07, Produktschutz), independent of the
# tenant switch: the entered date is orientation only and must be verified.
MEETING_RESOLUTION_LEAD_DAYS = 7


def meeting_deadline_reference(held_on: date, source: str | None) -> str:
    """Reference text of the deadline list entry, marked as orientation (M1-09)."""
    return (
        f"Beschlussfrist virtuelle Versammlung vom {held_on:%d.%m.%Y} "
        f"(Orientierung, zu prüfen; Quelle: {source or 'fehlt'})"
    )


def lead_days_for(kind: str, tenant_lead_days: int) -> int:
    """Fixed lead time per kind (``DEADLINE_LEAD_DAYS``), otherwise the tenant setting."""
    return DEADLINE_LEAD_DAYS.get(kind, tenant_lead_days)


async def refresh_deadlines(
    session: AsyncSession, tenant_id: uuid.UUID, today: date, lead_days: int
) -> dict[str, int]:
    """Upsert the deadline list from the sources; rows whose date vanished or passed are
    marked done. Idempotent: a second run on the same data changes nothing."""
    candidates = [
        {k: v for k, v in c.items() if k != "reminders"}
        for c in await deadline_candidates(session, tenant_id, today)
    ]
    existing = {
        (row.kind, row.source_id, row.due_on): row
        for row in (
            await session.scalars(
                select(ComplianceDeadline).where(ComplianceDeadline.status == "open")
            )
        ).all()
    }
    counts = {"created": 0, "updated": 0, "closed": 0}
    seen: set[tuple[str, uuid.UUID, date]] = set()
    now = datetime.now(UTC)
    for cand in candidates:
        key = (cand["kind"], cand["source_id"], cand["due_on"])
        seen.add(key)
        row = existing.get(key)
        if row is None:
            # A row closed earlier for the same key (date re-entered) is reopened, not
            # duplicated: the unique constraint covers all statuses.
            row = await session.scalar(
                select(ComplianceDeadline).where(
                    ComplianceDeadline.kind == cand["kind"],
                    ComplianceDeadline.source_id == cand["source_id"],
                    ComplianceDeadline.due_on == cand["due_on"],
                )
            )
            if row is None:
                session.add(
                    ComplianceDeadline(
                        tenant_id=tenant_id,
                        lead_days=lead_days_for(cand["kind"], lead_days),
                        status="open",
                        **cand,
                    )
                )
                counts["created"] += 1
                continue
            row.status, row.done_at = "open", None
            counts["updated"] += 1
        changed = False
        for field in ("reference", "property_id", "source_type"):
            if getattr(row, field) != cand[field]:
                setattr(row, field, cand[field])
                changed = True
        wanted_lead = lead_days_for(cand["kind"], lead_days)
        if row.lead_days != wanted_lead:
            row.lead_days, changed = wanted_lead, True
        counts["updated"] += int(changed)
    for key, row in existing.items():
        if key not in seen:
            row.status, row.done_at = "done", now
            counts["closed"] += 1
    await session.flush()
    return counts


async def notify_deadlines(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> int:
    """One notification per deadline row when the lead time is reached (``notified_at``)."""
    from mhvp.banking.tasks import users_with_permission

    rows = (
        await session.scalars(
            select(ComplianceDeadline).where(
                ComplianceDeadline.status == "open", ComplianceDeadline.notified_at.is_(None)
            )
        )
    ).all()
    due = [r for r in rows if r.due_on - timedelta(days=r.lead_days) <= today]
    if not due:
        return 0
    from mhvp.workspace.deadlines import CUSTOM_KIND, responsible_for_deadlines

    recipients: dict[str, list[uuid.UUID]] = {}
    responsible = await responsible_for_deadlines(
        session, {r.source_id for r in due if r.kind == CUSTOM_KIND}
    )
    created = 0
    for row in due:
        permission = DEADLINE_PERMISSIONS.get(row.kind, ("", "tenant_settings:update"))[1]
        if permission not in recipients:
            recipients[permission] = await users_with_permission(session, tenant_id, permission)
        days = (row.due_on - today).days
        # A user created deadline with a responsible person notifies that person only
        # (ES-10); without one, the holders of the update permission as for every kind.
        targets = recipients[permission]
        if row.kind == CUSTOM_KIND and row.source_id in responsible:
            targets = [responsible[row.source_id]]
        for user_id in targets:
            note = await notify(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                kind=DEADLINE_NOTIFICATION_KIND,
                title=f"Frist in {days} Tagen: {row.reference} ({row.due_on:%d.%m.%Y})",
                body=(
                    "Termin aus den Stammdaten, zu prüfen. Die Vorfrist stammt aus den "
                    f"Einstellungen ({row.lead_days} Tage). Rechtliche Fristen werden nicht "
                    "berechnet (M1-09)."
                ),
                entity_type="compliance_deadline",
                entity_id=row.id,
            )
            created += int(note is not None)
        row.notified_at = datetime.now(UTC)
    await session.flush()
    return created


async def deadlines_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, today: date
) -> dict[str, int]:
    settings_row = await job_settings(session, tenant_id)
    counts = await refresh_deadlines(session, tenant_id, today, settings_row.deadline_lead_days)
    counts["notified"] = await notify_deadlines(session, tenant_id, today)
    calendar = await calendar_sync(session, tenant_id, today)
    for key, value in calendar.items():
        counts[f"calendar_{key}"] = value
    counts["reminders"] = await notify_reminders(session, tenant_id, today)
    return counts


# Generated calendar entries (P1 AP7) ---------------------------------------------------


def reminders_for(kind: str, own: list[str] | None) -> list[str]:
    """Reminder codes (B.30) of a generated entry: the source's own setting wins."""
    return own or CALENDAR_REMINDERS.get(kind, DEFAULT_REMINDERS)


# Reminders and recurrence (spec B.30) --------------------------------------------------

# Days before the (all day) start at which a reminder code fires; codes within the day of
# the appointment ("0", minutes, hours) fire on the day itself, the job runs once a day.
REMINDER_OFFSET_DAYS: dict[str, int] = {
    "0": 0,
    "5min": 0,
    "10min": 0,
    "15min": 0,
    "30min": 0,
    "1h": 0,
    "2h": 0,
    "4h": 0,
    "1d": 1,
    "7d": 7,
    "14d": 14,
    "1m": 30,
    "3m": 91,
    "6m": 182,
}
REMINDER_CODES: tuple[str, ...] = tuple(REMINDER_OFFSET_DAYS)
REMINDER_NOTIFICATION_KIND = "calendar_reminder"
RECURRENCE_FREQUENCIES: tuple[str, ...] = ("weekly", "monthly", "yearly")
# Safety bound of the expansion of one entry (weekly for ten years).
MAX_OCCURRENCES = 520


def _add_months(day: date, months: int) -> date:
    """Same day of month ``months`` later; a missing day (31st) clips to the month end."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def expand_occurrences(
    starts_on: date, recurrence: dict[str, Any] | None, start: date, end: date
) -> list[date]:
    """Occurrence dates of an entry inside [start, end] (inclusive). Without a recurrence
    the single start date is returned when it lies in the window. The recurrence is
    ``{"frequency": weekly|monthly|yearly, "interval": n, "until": "JJJJ-MM-TT"}``;
    occurrences are computed on read and never persisted."""
    if not recurrence:
        return [starts_on] if start <= starts_on <= end else []
    frequency = recurrence.get("frequency")
    if frequency not in RECURRENCE_FREQUENCIES:
        return [starts_on] if start <= starts_on <= end else []
    interval = max(int(recurrence.get("interval") or 1), 1)
    until_raw = recurrence.get("until")
    until = date.fromisoformat(str(until_raw)) if until_raw else None
    last = min(end, until) if until is not None else end
    out: list[date] = []
    step = 0
    while step < MAX_OCCURRENCES:
        if frequency == "weekly":
            occurrence = starts_on + timedelta(weeks=step * interval)
        elif frequency == "monthly":
            occurrence = _add_months(starts_on, step * interval)
        else:
            occurrence = _add_months(starts_on, 12 * step * interval)
        if occurrence > last:
            break
        if occurrence >= start:
            out.append(occurrence)
        step += 1
    return out


def reminder_key(code: str, occurrence: date) -> str:
    return f"{code}@{occurrence.isoformat()}"


async def notify_reminders(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> int:
    """One notification per reminder code and occurrence of a calendar entry when the
    offset of the code is reached (``REMINDER_OFFSET_DAYS``); ``reminders_sent`` on the
    entry keeps the job idempotent across reruns. Generated entries notify the users with
    the update permission of their kind and link to the source row; manual entries notify
    their owner and link to the calendar. The lead time notification of the deadline list
    (``notify_deadlines``) is a separate, list based notification and stays as it is. An
    unread reminder of the same entry and user is not duplicated by a later code or
    occurrence (``notify`` idempotency); the code is still recorded as sent."""
    from mhvp.banking.tasks import users_with_permission

    rows = (
        await session.scalars(
            select(CalendarEntry).where(func.jsonb_array_length(CalendarEntry.reminders) > 0)
        )
    ).all()
    horizon = today + timedelta(days=max(REMINDER_OFFSET_DAYS.values()))
    recipients: dict[str, list[uuid.UUID]] = {}
    created = 0
    for entry in rows:
        codes = [str(c) for c in entry.reminders if str(c) in REMINDER_OFFSET_DAYS]
        if not codes:
            continue
        occurrences = expand_occurrences(entry.starts_on, entry.recurrence, today, horizon)
        if not occurrences:
            continue
        # Keys of past occurrences can never fire again and are dropped.
        sent = [
            str(k)
            for k in entry.reminders_sent
            if "@" in str(k) and str(k).split("@", 1)[1] >= today.isoformat()
        ]
        due_keys: list[tuple[str, date]] = [
            (code, occurrence)
            for occurrence in occurrences
            for code in codes
            if occurrence - timedelta(days=REMINDER_OFFSET_DAYS[code]) <= today
            and reminder_key(code, occurrence) not in sent
        ]
        if not due_keys and sent == list(entry.reminders_sent):
            continue
        target_type: str
        target_id: uuid.UUID | None
        if entry.owner_user_id is not None:
            users = [entry.owner_user_id]
            target_type, target_id = "calendar_entry", entry.id
        else:
            permission = DEADLINE_PERMISSIONS.get(entry.category, ("", "tenant_settings:update"))[1]
            if permission not in recipients:
                recipients[permission] = await users_with_permission(session, tenant_id, permission)
            users = recipients[permission]
            target_type, target_id = entry.source_type, entry.source_id
        for code, occurrence in due_keys:
            days = (occurrence - today).days
            when = "heute" if days == 0 else f"in {days} Tagen"
            for user_id in users:
                note = await notify(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    kind=REMINDER_NOTIFICATION_KIND,
                    title=f"Erinnerung: {entry.title} ({occurrence:%d.%m.%Y}, {when})",
                    body=(
                        f"Erinnerung {code} zum Termin am {occurrence:%d.%m.%Y}. "
                        "Termine aus den Stammdaten sind zu prüfen; rechtliche Fristen "
                        "werden nicht berechnet (M1-09)."
                    ),
                    target_type=target_type,
                    target_id=target_id,
                )
                created += int(note is not None)
            sent.append(reminder_key(code, occurrence))
        entry.reminders_sent = sent
    await session.flush()
    return created


async def calendar_sync(session: AsyncSession, tenant_id: uuid.UUID, today: date) -> dict[str, int]:
    """Upsert the generated calendar entries from the source readers and delete entries whose
    source or date vanished. Idempotent: a second run on the same data changes nothing.
    Generated entries have no owner and are shared; manual entries are never touched."""
    since = today - timedelta(days=CALENDAR_PAST_DAYS)
    candidates = await deadline_candidates(session, tenant_id, today, since=since)
    existing = {
        (row.source_type, row.source_id, row.category): row
        for row in (
            await session.scalars(
                select(CalendarEntry).where(CalendarEntry.owner_user_id.is_(None))
            )
        ).all()
    }
    counts = {"created": 0, "updated": 0, "deleted": 0}
    seen: set[tuple[str, uuid.UUID | None, str]] = set()
    for cand in candidates:
        key = (cand["source_type"], cand["source_id"], cand["kind"])
        if key in seen:
            continue
        seen.add(key)
        wanted = {
            "title": cand["reference"],
            "starts_on": cand["due_on"],
            "property_id": cand["property_id"],
            "reminders": reminders_for(cand["kind"], cand.get("reminders")),
        }
        row = existing.get(key)
        if row is None:
            session.add(
                CalendarEntry(
                    tenant_id=tenant_id,
                    owner_user_id=None,
                    source_type=cand["source_type"],
                    source_id=cand["source_id"],
                    category=cand["kind"],
                    all_day=True,
                    shared=True,
                    ends_on=None,
                    **wanted,
                )
            )
            counts["created"] += 1
            continue
        changed = False
        for field, value in wanted.items():
            if getattr(row, field) != value:
                setattr(row, field, value)
                changed = True
        counts["updated"] += int(changed)
    for key, row in existing.items():
        if key not in seen:
            await session.delete(row)
            counts["deleted"] += 1
    await session.flush()
    return counts


async def sync_work_order_entry(session: AsyncSession, order: Any) -> None:
    """Writes the internal calendar entry of one work order right when ``scheduled_at`` is set
    (M19-06, in addition to the daily ``calendar_sync``, which stays the safety net). Same key
    and wording as ``_read_work_order_appointments``, so the job finds the entry and changes
    nothing. Internal only; nothing is sent to the provider or an external calendar."""
    from mhvp.tickets.models import Ticket
    from mhvp.workspace.services import _LOCAL

    if order.scheduled_at is None:
        return
    number = property_id = None
    if order.ticket_id is not None:
        ticket = await session.get(Ticket, order.ticket_id)
        if ticket is not None:
            number, property_id = ticket.number, ticket.property_id
    local = order.scheduled_at.astimezone(_LOCAL)
    label = f"Auftragstermin {local:%H:%M} Uhr"
    if number:
        label += f" Ticket {number}"
    cand = _candidate(
        "work_order_appointment", "work_order", order.id, label, local.date(), property_id
    )
    if cand is None:
        return
    row = await session.scalar(
        select(CalendarEntry).where(
            CalendarEntry.owner_user_id.is_(None),
            CalendarEntry.source_type == "work_order",
            CalendarEntry.source_id == order.id,
            CalendarEntry.category == "work_order_appointment",
        )
    )
    wanted = {
        "title": cand["reference"],
        "starts_on": cand["due_on"],
        "property_id": property_id,
        "reminders": reminders_for("work_order_appointment", None),
    }
    if row is None:
        session.add(
            CalendarEntry(
                tenant_id=order.tenant_id,
                owner_user_id=None,
                source_type="work_order",
                source_id=order.id,
                category="work_order_appointment",
                all_day=True,
                shared=True,
                ends_on=None,
                **wanted,
            )
        )
    else:
        for field, value in wanted.items():
            setattr(row, field, value)
    await session.flush()


# Digest (A40) --------------------------------------------------------------------------


async def build_digest(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str] | set[str],
    today: date,
) -> dict[str, Any]:
    """Daily overview of one user; every section follows the user's permissions or their
    personal involvement (assignee, submitter). Read only."""
    from mhvp.ai.models import AiProposal, Decision
    from mhvp.tickets.models import Ticket, TicketAssignee

    sections: dict[str, Any] = {}

    if "tickets:read" in permissions:
        assigned = select(TicketAssignee.ticket_id).where(TicketAssignee.user_id == user_id)
        tickets = (
            await session.scalars(
                select(Ticket)
                .where(
                    Ticket.status.in_(OPEN_TICKET_STATUSES),
                    Ticket.sla_due_at.is_not(None),
                    or_(Ticket.assignee_user_id == user_id, Ticket.id.in_(assigned)),
                )
                .order_by(Ticket.sla_due_at)
            )
        ).all()
        due_today: list[dict[str, Any]] = []
        overdue: list[dict[str, Any]] = []
        for t in tickets:
            if t.sla_due_at is None:
                continue
            day = local_date(t.sla_due_at)
            item = {
                "id": t.id,
                "number": t.number,
                "title": t.title,
                "due_at": t.sla_due_at,
                "priority": t.priority.value,
            }
            if day == today:
                due_today.append(item)
            elif day < today:
                overdue.append(item)
        sections["tickets_due_today"] = _section(due_today)
        sections["tickets_overdue"] = _section(overdue)

    approvals: list[dict[str, Any]] = []
    if "accounting:approve" in permissions:
        from mhvp.accounting.models import Invoice, ReviewStatus

        rows = (
            await session.execute(
                select(Invoice.id, Invoice.number, Invoice.gross)
                .where(
                    Invoice.review_status.in_(
                        (ReviewStatus.OPEN, ReviewStatus.PARTIALLY_REVIEWED, ReviewStatus.QUERY)
                    )
                )
                .order_by(Invoice.invoice_date)
            )
        ).all()
        approvals += [
            {"kind": "invoice", "id": i, "title": f"Rechnung {n}", "amount": str(g)}
            for i, n, g in rows
        ]
    if "banking:approve" in permissions:
        from mhvp.banking.models import OrderStatus, PaymentApproval, PaymentOrder

        mine = select(PaymentApproval.order_id).where(
            PaymentApproval.user_id == user_id, PaymentApproval.invalidated_at.is_(None)
        )
        rows2 = (
            await session.execute(
                select(PaymentOrder.id, PaymentOrder.counterpart_name, PaymentOrder.amount)
                .where(PaymentOrder.status == OrderStatus.DRAFT, PaymentOrder.id.not_in(mine))
                .order_by(PaymentOrder.execution_date)
            )
        ).all()
        approvals += [
            {"kind": "payment", "id": i, "title": f"Zahlung {name}", "amount": str(a)}
            for i, name, a in rows2
        ]
    if "communication:approve" in permissions or "communication:create" in permissions:
        from mhvp.communication.models import Message

        where = [
            Message.direction == "out",
            Message.submitted_at.is_not(None),
            Message.approved_at.is_(None),
            Message.sent_at.is_(None),
            Message.rejection_note.is_(None),
        ]
        if "communication:approve" not in permissions:
            where.append(Message.submitted_by == user_id)
        rows3 = (
            await session.execute(
                select(Message.id, Message.subject).where(*where).order_by(Message.submitted_at)
            )
        ).all()
        approvals += [
            {"kind": "mail", "id": i, "title": f"Mail-Freigabe {s or '(ohne Betreff)'}"}
            for i, s in rows3
        ]
    sections["approvals"] = _section(approvals)

    deadline_rows = (
        await session.scalars(
            select(ComplianceDeadline)
            .where(ComplianceDeadline.status == "open", ComplianceDeadline.due_on >= today)
            .order_by(ComplianceDeadline.due_on)
        )
    ).all()
    deadlines = [
        {
            "id": r.id,
            "kind": r.kind,
            "reference": r.reference,
            "due_on": r.due_on,
            "lead_days": r.lead_days,
            "today": r.due_on == today,
        }
        for r in deadline_rows
        if DEADLINE_PERMISSIONS[r.kind][0] in permissions
        and (r.due_on == today or r.due_on - timedelta(days=r.lead_days) == today)
    ]
    sections["deadlines"] = _section(deadlines)

    if "ai:read" in permissions:
        rows4 = (
            await session.execute(
                select(AiProposal.id, AiProposal.entity_type, AiProposal.created_at)
                .where(AiProposal.decision == Decision.PENDING)
                .order_by(AiProposal.created_at)
            )
        ).all()
        sections["ai_proposals"] = _section(
            [{"id": i, "title": f"KI-Vorschlag {e}", "created_at": c} for i, e, c in rows4]
        )
    total = sum(int(s["count"]) for s in sections.values())
    return {"date": today, "total": total, "sections": sections}


def _section(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"count": len(items), "items": items[:DIGEST_LIST_LIMIT]}


def digest_text(digest: dict[str, Any]) -> str:
    """Plain German summary for the notification body and the optional system mail."""
    labels = {
        "tickets_due_today": "Heute fällige Tickets",
        "tickets_overdue": "Überfällige Tickets",
        "approvals": "Offene Freigaben",
        "deadlines": "Fristen des Tages (zu prüfen)",
        "ai_proposals": "Offene KI-Vorschläge",
    }
    lines: list[str] = []
    for key, section in digest["sections"].items():
        if not section["count"]:
            continue
        lines.append(f"{labels.get(key, key)}: {section['count']}")
        for item in section["items"]:
            title = item.get("title") or item.get("reference") or ""
            suffix = ""
            if "due_on" in item:
                suffix = f" ({item['due_on']:%d.%m.%Y})"
            elif "number" in item:
                title = f"#{item['number']} {title}"
            lines.append(f"  {title}{suffix}")
    return "\n".join(lines)


async def digest_tenant(
    session: AsyncSession,
    settings: Settings,
    tenant_id: uuid.UUID,
    today: date,
) -> dict[str, int]:
    """Per tenant half of ``tasks.digest``: one notification per active member and day,
    nothing for empty overviews, optional system mail (tenant switch, default off)."""
    from mhvp.core.auth.permissions import effective_permissions
    from mhvp.platform.models import Membership, MembershipStatus, User

    settings_row = await job_settings(session, tenant_id)
    members = (
        await session.execute(
            select(Membership.id, Membership.user_id, User.email)
            .join(User, User.id == Membership.user_id)
            .where(Membership.tenant_id == tenant_id, Membership.status == MembershipStatus.ACTIVE)
        )
    ).all()
    done_users = set(
        (
            await session.scalars(select(DigestRun.user_id).where(DigestRun.digest_date == today))
        ).all()
    )
    counts = {"users": 0, "notified": 0, "empty": 0, "skipped": 0, "mails": 0}
    for membership_id, user_id, email in members:
        counts["users"] += 1
        if user_id in done_users:
            counts["skipped"] += 1
            continue
        permissions, _roles = await effective_permissions(session, tenant_id, membership_id)
        digest = await build_digest(session, tenant_id, user_id, permissions, today)
        run = DigestRun(
            id=uuid7(),
            tenant_id=tenant_id,
            user_id=user_id,
            digest_date=today,
            counts={k: v["count"] for k, v in digest["sections"].items()},
            mail_status="empty" if digest["total"] == 0 else "not_sent",
        )
        session.add(run)
        if digest["total"] == 0:
            counts["empty"] += 1
            continue
        body = digest_text(digest)
        await notify(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=DIGEST_NOTIFICATION_KIND,
            title=f"Tagesübersicht {today:%d.%m.%Y}: {digest['total']} offene Punkte",
            body=body,
            entity_type="digest_run",
            entity_id=run.id,
        )
        counts["notified"] += 1
        if settings_row.digest_mail_enabled:
            from mhvp.sla.channels import send_email

            error = await send_email(
                session,
                settings,
                tenant_id,
                email,
                f"Tagesübersicht {today:%d.%m.%Y}",
                body + "\n\nAutomatische Systemmail der Verwaltungsplattform.",
            )
            run.mail_status = "sent" if error is None else "failed"
            if error is not None:
                run.counts = {**run.counts, "mail_error": error[:200]}
            counts["mails"] += int(error is None)
    await session.flush()
    return counts
