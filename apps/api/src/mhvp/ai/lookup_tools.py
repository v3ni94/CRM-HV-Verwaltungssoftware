"""Area tools of the assistant lookup (rule AI-LOOKUP-01): calendar, deadlines, documents,
WEG, rent increases, work orders, bank transactions, open items.

The chat bubble tells the API which menu item and sub page are open (``area``, ``sub_area``);
``tools_of_area`` adds the tools of that area to a question so the chat answers the page's
standard questions ("Welche Termine habe ich heute?") without a search term. Like the classic
tools of ``mhvp.ai.lookup`` every tool runs in the caller's session under tenant RLS, checks
the permission of its regular endpoint, follows the legal entity scope of the membership
(A37, ``session_allowed_legal_entity_ids``) and returns at most ``LIMIT`` hits. Amounts are
strings (``1.234,56 EUR``), never floats; IBANs never leave the platform.

Reserve balances come from the last calculated annual statement of the community's ledger and
are only reported when the caller's scope covers that legal entity, otherwise the tool says so.
Deadlines and appointments are orientation only, never a legal deadline calculation (M1-09).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.lookup import LIMIT, Query, _date, _like, _link, _score, flat
from mhvp.core.auth.scope import (
    property_allowed,
    session_allowed_legal_entity_ids,
    session_allowed_property_ids,
    session_principal,
)

DEFAULT_DAYS = 7  # horizon of the calendar and deadline tools when no range is named
FREE_SLOT_DAYS = 30  # how far the free slot search looks ahead
WEEKDAYS = (0, 1, 2, 3, 4)

DEADLINE_KIND_LABELS = {
    "contract_end": "Vertragsende",
    "contract_termination": "Kündigung",
    "meter_calibration": "Eichfrist",
    "bank_consent": "Bankzustimmung",
    "document_retention_end": "Aufbewahrungsende",
    "service_contract_notice": "Kündigungsfrist Dienstleistervertrag",
    "meeting_resolution_deadline": "Beschlussfrist",
    "energy_certificate": "Energieausweis",
    "move_in": "Einzug",
    "move_out": "Auszug",
    "maintenance": "Wartung",
    "note_follow_up": "Wiedervorlage",
    "meeting": "Versammlung",
    "ticket": "Ticketfrist",
    "appointment": "Termin",
}
RESOLUTION_STATUS = {
    "positive": "angenommen",
    "negative": "abgelehnt",
    "final": "bestandskräftig",
    "contested": "angefochten",
    "annulled": "für ungültig erklärt",
    "legally_binding": "rechtskräftig",
    "void": "nichtig",
}
MEETING_STATUS = {
    "planned": "geplant",
    "invited": "eingeladen",
    "held": "durchgeführt",
    "closed": "abgeschlossen",
}
RENT_INCREASE_STATUS = {
    "draft": "Entwurf",
    "checked": "geprüft",
    "approved": "freigegeben",
    "sent": "versandt",
    "consented": "zugestimmt",
    "rejected": "abgelehnt",
    "applied": "übernommen",
    "cancelled": "abgebrochen",
}
ORDER_STATUS = {
    "draft": "Entwurf",
    "requested": "angefragt",
    "quoted": "Angebot liegt vor",
    "approved": "freigegeben",
    "scheduled": "terminiert",
    "in_progress": "in Arbeit",
    "done": "erledigt",
    "invoiced": "abgerechnet",
    "accepted": "abgenommen",
    "rejected": "abgelehnt",
    "cancelled": "storniert",
}
OPEN_ORDER = ("draft", "requested", "quoted", "approved", "scheduled", "in_progress")
UNMATCHED = ("new", "needs_review", "proposed")
TRANSACTION_STATUS = {
    "new": "nicht zugeordnet",
    "needs_review": "zu prüfen",
    "proposed": "Vorschlag liegt vor",
    "booked": "gebucht",
    "ignored": "ignoriert",
    "split": "aufgeteilt",
}


def local_today() -> date:
    from mhvp.workspace.services import local_today as today

    return today()


def eur(value: Decimal | int | str | None) -> str:
    """``1.234,56 EUR`` from a decimal; amounts never leave as floats (6.9.8)."""
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{grouped},{cents} EUR"


def _span(query: Query, days: int = DEFAULT_DAYS) -> tuple[date, date]:
    if query.range is not None:
        return query.range
    if "overdue" in query.flags:
        return (query.today - timedelta(days=365), query.today - timedelta(days=1))
    return (query.today, query.today + timedelta(days=days))


def _scoped(session: AsyncSession, legal_entity_id: uuid.UUID | None) -> bool:
    allowed = session_allowed_legal_entity_ids(session)
    return allowed is None or (legal_entity_id is not None and legal_entity_id in allowed)


def _term_filter(columns: list[Any], terms: list[str]) -> Any:
    return or_(*[c.ilike(_like(t), escape="\\") for c in columns for t in terms])


async def _focus_property_id(session: AsyncSession, query: Query) -> uuid.UUID | None:
    """The property of the record open on the page, when it has one and it lies inside the
    membership's property assignment (M2-02/S16-02)."""
    property_id = await _focus_property_raw(session, query)
    if property_id is not None and not property_allowed(session_principal(session), property_id):
        return None
    return property_id


async def _focus_property_raw(session: AsyncSession, query: Query) -> uuid.UUID | None:
    if query.focus is None:
        return None
    kind, id_ = query.focus
    if kind in ("property", "hoa"):
        return id_
    if kind == "unit":
        from mhvp.properties.models import Unit

        unit = await session.get(Unit, id_)
        return unit.property_id if unit else None
    if kind == "contract":
        from mhvp.contracts.models import Contract

        contract = await session.get(Contract, id_)
        return contract.property_id if contract else None
    return None


async def _property_ids_of_terms(session: AsyncSession, query: Query) -> list[uuid.UUID]:
    from mhvp.properties.models import Property

    if not query.terms:
        return []
    conditions = []
    for term in query.terms:
        conditions += [Property.number == term, Property.name.ilike(_like(term), escape="\\")]
    stmt = select(Property.id).where(or_(*conditions))
    allowed = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed is not None:
        stmt = stmt.where(Property.id.in_(allowed))
    return list((await session.scalars(stmt)).all())


# Calendar -----------------------------------------------------------------------------------


async def search_calendar(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Own and shared appointments plus the generated entries the caller may read (as
    ``GET /workspace/calendar``), in the range the question names (default: the next seven
    days). Flags: handover appointments, meetings; ``free`` adds the next working day
    without an entry as a fact. Google calendars are not read here (network, cache of the
    calendar page); the fact says so."""
    from mhvp.workspace import jobs
    from mhvp.workspace.models import CalendarEntry

    principal = session_principal(session)
    if principal is None:
        return []
    start, end = _span(query)
    if "free" in query.flags:
        end = max(end, start + timedelta(days=FREE_SLOT_DAYS))
    stmt = select(CalendarEntry).where(
        or_(
            CalendarEntry.owner_user_id == principal.user_id,
            CalendarEntry.shared,
            CalendarEntry.owner_user_id.is_(None),
        ),
        CalendarEntry.starts_on <= end,
        or_(
            func.coalesce(CalendarEntry.ends_on, CalendarEntry.starts_on) >= start,
            CalendarEntry.recurrence.is_not(None),
        ),
    )
    if "handover" in query.flags:
        stmt = stmt.where(
            or_(CalendarEntry.source_type == "handover", CalendarEntry.title.ilike("%übergabe%"))
        )
    if "meeting" in query.flags:
        stmt = stmt.where(
            or_(CalendarEntry.category == "meeting", CalendarEntry.title.ilike("%versammlung%"))
        )
    if query.terms:
        stmt = stmt.where(_term_filter([CalendarEntry.title, CalendarEntry.notes], query.terms))
    allowed_props = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed_props is not None:
        # Generated entries follow the property assignment; own and shared appointments stay.
        stmt = stmt.where(
            or_(
                CalendarEntry.owner_user_id.is_not(None),
                CalendarEntry.property_id.in_(allowed_props),
            )
        )
    rows = (
        await session.scalars(stmt.order_by(CalendarEntry.starts_on, CalendarEntry.title))
    ).all()
    items: list[tuple[date, CalendarEntry]] = []
    for e in rows:
        if e.owner_user_id is None:
            read = jobs.DEADLINE_PERMISSIONS.get(e.category, ("", ""))[0]
            if read and not principal.has(read):
                continue
        if e.owner_user_id is not None and e.recurrence:
            for occurrence in jobs.expand_occurrences(e.starts_on, e.recurrence, start, end):
                items.append((occurrence, e))
            continue
        items.append((e.starts_on, e))
    items.sort(key=lambda item: (item[0], item[1].title))
    if "free" in query.flags:
        busy = {day for day, _ in items}
        day = max(start, query.today)
        while day <= end and (day in busy or day.weekday() not in WEEKDAYS):
            day += timedelta(days=1)
        if day <= end:
            query.facts.append(
                f"Nächster Werktag ohne Termin im CRM-Kalender: {day:%d.%m.%Y} (Google-Kalender "
                "nicht geprüft)"
            )
        else:
            query.facts.append("Kein freier Werktag im geprüften Zeitraum gefunden.")
    if not items:
        query.facts.append(
            f"Keine Termine im CRM-Kalender vom {start:%d.%m.%Y} bis {end:%d.%m.%Y} "
            "(Google-Kalender nicht geprüft)."
        )
    links = []
    for day, e in items[:LIMIT]:
        kind = DEADLINE_KIND_LABELS.get(e.category, e.category)
        detail = ", ".join(
            p
            for p in (
                f"{day:%d.%m.%Y}",
                kind
                if e.category != "appointment"
                else ("geteilt" if e.shared else "eigener Termin"),
                flat(e.notes)[:120] if e.notes else "",
            )
            if p
        )
        links.append(
            _link(
                "calendar_entry",
                f"{e.id}:{day.isoformat()}",
                e.title,
                f"/kalender?termin={e.id}&datum={day.isoformat()}",
                detail,
            )
        )
    return links


# Deadlines ----------------------------------------------------------------------------------


async def search_deadlines(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Deadline list (``GET /workspace/deadlines``): kinds the caller may read, overdue or due
    in the named range (default: the next seven days), plus own and shared appointments with a
    reminder. Orientation only (M1-09). A responsible person per deadline is not stored; the
    list is grouped by the permission that maintains the source."""
    from mhvp.workspace import jobs, links
    from mhvp.workspace.models import CalendarEntry, ComplianceDeadline

    principal = session_principal(session)
    if principal is None:
        return []
    allowed = [k for k, (read, _u) in jobs.DEADLINE_PERMISSIONS.items() if principal.has(read)]
    start, end = _span(query)
    overdue = "overdue" in query.flags
    out: list[dict[str, Any]] = []
    if allowed:
        stmt = select(ComplianceDeadline).where(
            ComplianceDeadline.kind.in_(allowed), ComplianceDeadline.status == "open"
        )
        stmt = (
            stmt.where(ComplianceDeadline.due_on < query.today)
            if overdue
            else stmt.where(ComplianceDeadline.due_on >= start, ComplianceDeadline.due_on <= end)
        )
        if query.terms:
            stmt = stmt.where(_term_filter([ComplianceDeadline.reference], query.terms))
        allowed_props = session_allowed_property_ids(session)  # M2-02/S16-02
        if allowed_props is not None:
            stmt = stmt.where(ComplianceDeadline.property_id.in_(allowed_props))
        rows = (
            await session.scalars(
                stmt.order_by(ComplianceDeadline.due_on, ComplianceDeadline.reference).limit(LIMIT)
            )
        ).all()
        for d in rows:
            days = (d.due_on - query.today).days
            when = f"überfällig seit {-days} Tagen" if days < 0 else f"fällig in {days} Tagen"
            out.append(
                _link(
                    "deadline",
                    d.id,
                    f"{DEADLINE_KIND_LABELS.get(d.kind, d.kind)}: {d.reference}",
                    links.target_href(d.source_type, d.source_id, property_id=d.property_id)
                    or "/fristen",
                    f"{d.due_on:%d.%m.%Y}, {when}, zu prüfen",
                )
            )
    if not overdue:
        own = select(CalendarEntry).where(
            CalendarEntry.owner_user_id.is_not(None),
            or_(CalendarEntry.owner_user_id == principal.user_id, CalendarEntry.shared),
            func.jsonb_array_length(CalendarEntry.reminders) > 0,
            CalendarEntry.starts_on >= start,
            CalendarEntry.starts_on <= end,
        )
        if query.terms:
            own = own.where(_term_filter([CalendarEntry.title], query.terms))
        for e in (await session.scalars(own.order_by(CalendarEntry.starts_on).limit(LIMIT))).all():
            out.append(
                _link(
                    "calendar_entry",
                    f"{e.id}:{e.starts_on.isoformat()}",
                    e.title,
                    f"/kalender?termin={e.id}&datum={e.starts_on.isoformat()}",
                    f"{e.starts_on:%d.%m.%Y}, eigener Termin mit Erinnerung",
                )
            )
    out.sort(key=lambda link: link["detail"][6:10] + link["detail"][3:5] + link["detail"][:2])
    if not out:
        query.facts.append(
            "Keine überfälligen Fristen."
            if overdue
            else f"Keine Fristen vom {start:%d.%m.%Y} bis {end:%d.%m.%Y}."
        )
    return out[:LIMIT]


# Documents ----------------------------------------------------------------------------------


async def search_documents(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Title, category name and property (``GET /documents`` with ``q`` and the property
    link), under the legal entity scope of the document list."""
    from mhvp.documents.models import Document, DocumentCategory, DocumentLink
    from mhvp.documents.routers import _property_scope_filter, _scope_filter

    property_ids = await _property_ids_of_terms(session, query)
    focus_property = await _focus_property_id(session, query)
    if focus_property is not None:
        property_ids.append(focus_property)
    if not query.terms and not property_ids:
        return []
    stmt = (
        select(Document, DocumentCategory.name)
        .outerjoin(DocumentCategory, DocumentCategory.id == Document.category_id)
        .where(Document.duplicate_of_id.is_(None))
    )
    conditions: list[Any] = []
    if query.terms:
        conditions.append(_term_filter([Document.title, Document.filename], query.terms))
        conditions.append(_term_filter([DocumentCategory.name], query.terms))
    if property_ids:
        conditions.append(
            Document.id.in_(
                select(DocumentLink.document_id).where(
                    DocumentLink.entity_type == "property", DocumentLink.entity_id.in_(property_ids)
                )
            )
        )
    stmt = stmt.where(or_(*conditions))
    for scoped in (_scope_filter(session), _property_scope_filter(session)):  # A37, M2-02
        if scoped is not None:
            stmt = stmt.where(Document.id.in_(scoped))
    rows = (await session.execute(stmt.order_by(Document.created_at.desc()).limit(LIMIT * 4))).all()
    scored = [
        (_score(f"{d.title} {d.filename} {category or ''}", query.terms), (d, category))
        for d, category in rows
    ]
    scored.sort(key=lambda item: -item[0])
    return [
        _link(
            "document",
            d.id,
            d.title,
            f"/dokumente/{d.id}",
            ", ".join(p for p in (category, f"vom {_date(d.created_at)}") if p),
        )
        for _, (d, category) in scored[:LIMIT]
    ]


# WEG ----------------------------------------------------------------------------------------


async def _hoa_entities(session: AsyncSession, query: Query) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(legal_entity_id, property_id) of the communities the question or the page is about:
    the open property, properties named in the question, else all communities."""
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    stmt = select(LegalEntity.id, LegalEntity.property_id).where(
        LegalEntity.kind == LegalEntityKind.HOA, LegalEntity.property_id.is_not(None)
    )
    focus_property = await _focus_property_id(session, query)
    named = await _property_ids_of_terms(session, query)
    if focus_property is not None:
        stmt = stmt.where(LegalEntity.property_id == focus_property)
    elif named:
        stmt = stmt.where(LegalEntity.property_id.in_(named))
    allowed = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed is not None:
        stmt = stmt.where(LegalEntity.property_id.in_(allowed))
    rows = (await session.execute(stmt)).all()
    return [(le, prop) for le, prop in rows if _scoped(session, le)]


async def search_resolutions(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Resolutions of the community open on the page or named in the question (subject),
    newest first (``GET /hoa/resolutions``, ``accounting:read``)."""
    from mhvp.hoa.models import Resolution

    entities = await _hoa_entities(session, query)
    if not entities:
        return []
    by_entity = dict(entities)
    stmt = select(Resolution).where(Resolution.legal_entity_id.in_(list(by_entity)))
    if query.terms:
        stmt = stmt.where(_term_filter([Resolution.subject, Resolution.wording], query.terms))
    rows = (await session.scalars(stmt.order_by(Resolution.decided_on.desc()).limit(LIMIT))).all()
    links = []
    for r in rows:
        property_id = by_entity[r.legal_entity_id]
        href = (
            f"/weg/{property_id}/versammlung/{r.meeting_id}"
            if r.meeting_id
            else f"/weg/{property_id}"
        )
        links.append(
            _link(
                "resolution",
                r.id,
                f"Beschluss {r.number}: {r.subject}",
                href,
                f"{_date(r.decided_on)}, {RESOLUTION_STATUS.get(r.status, r.status)}",
            )
        )
    return links


async def search_meetings(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Owners' meetings of the community (upcoming first), ``accounting:read``."""
    from mhvp.hoa.models import Meeting

    entities = await _hoa_entities(session, query)
    if not entities:
        return []
    by_entity = dict(entities)
    stmt = select(Meeting).where(Meeting.legal_entity_id.in_(list(by_entity)))
    if query.range is not None:
        start, end = query.range
        stmt = stmt.where(
            func.date(Meeting.scheduled_at) >= start, func.date(Meeting.scheduled_at) <= end
        )
    rows = (await session.scalars(stmt.order_by(Meeting.scheduled_at.desc()).limit(LIMIT))).all()
    return [
        _link(
            "meeting",
            m.id,
            f"Eigentümerversammlung {m.scheduled_at:%d.%m.%Y}",
            f"/weg/{by_entity[m.legal_entity_id]}/versammlung/{m.id}",
            ", ".join(
                p
                for p in (MEETING_STATUS.get(m.status, m.status), m.mode, flat(m.location)[:80])
                if p
            ),
        )
        for m in rows
    ]


async def search_reserve(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Reserve balance per community from the last calculated annual statement of its ledger;
    reported only when the caller's legal entity scope covers the community (the tool says so
    otherwise). No live balance: the statement is the released figure (W08)."""
    from mhvp.accounting.models import Ledger
    from mhvp.hoa.models import HoaStatement
    from mhvp.properties.models import LegalEntity, LegalEntityKind, Property

    focus_property = await _focus_property_id(session, query)
    named = await _property_ids_of_terms(session, query)
    wanted = [focus_property] if focus_property else named
    if not wanted:
        query.facts.append("Rücklage: bitte das Objekt (WEG) nennen oder öffnen.")
        return []
    rows = (
        await session.execute(
            select(LegalEntity.id, Property.number, Property.name)
            .join(Property, Property.id == LegalEntity.property_id)
            .where(LegalEntity.kind == LegalEntityKind.HOA, LegalEntity.property_id.in_(wanted))
        )
    ).all()
    if not rows:
        query.facts.append("Rücklage: für das Objekt ist keine Gemeinschaft (GdWE) angelegt.")
    for entity_id, number, name in rows:
        label = f"{number} {name}"
        if not _scoped(session, entity_id):
            query.facts.append(
                f"Rücklage {label}: Rechtsträger nicht im Zugriff Ihrer Zuordnung, nicht gelesen."
            )
            continue
        ledger_id = await session.scalar(
            select(Ledger.id).where(Ledger.legal_entity_id == entity_id)
        )
        statement = (
            await session.scalar(
                select(HoaStatement)
                .where(HoaStatement.ledger_id == ledger_id, HoaStatement.snapshot.is_not(None))
                .order_by(HoaStatement.year.desc(), HoaStatement.version.desc())
                .limit(1)
            )
            if ledger_id is not None
            else None
        )
        reserve = (statement.snapshot or {}).get("reserve") if statement is not None else None
        if statement is None or not reserve or "closing" not in reserve:
            query.facts.append(f"Rücklage {label}: keine berechnete Jahresabrechnung vorhanden.")
            continue
        query.facts.append(
            f"Erhaltungsrücklage {label} laut Jahresabrechnung {statement.year} "
            f"({statement.status.value}): Endstand {eur(reserve['closing'])}, davon zugeführt "
            f"{eur(reserve.get('contributions_paid'))}, entnommen {eur(reserve.get('withdrawals'))}"
        )
    return []


# Letting ------------------------------------------------------------------------------------


async def search_rent_increases(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Rent increase cases (``GET /letting/rent-increases``, ``contracts:read``) by party,
    property or unit; open cases first."""
    from mhvp.contacts.models import Party
    from mhvp.contracts.models import Contract
    from mhvp.letting.models import RentIncreaseCase
    from mhvp.properties.models import Property, Unit

    stmt = (
        select(RentIncreaseCase, Party.name, Property.number, Unit.number)
        .join(Contract, Contract.id == RentIncreaseCase.contract_id)
        .join(Party, Party.id == Contract.party_id)
        .join(Property, Property.id == Contract.property_id)
        .join(Unit, Unit.id == Contract.unit_id)
    )
    focus_property = await _focus_property_id(session, query)
    if focus_property is not None:
        stmt = stmt.where(Contract.property_id == focus_property)
    elif query.focus is not None and query.focus[0] == "contract":
        stmt = stmt.where(Contract.id == query.focus[1])
    if query.terms:
        stmt = stmt.where(
            or_(
                _term_filter([Party.name, Property.name], query.terms),
                *[Property.number == t for t in query.terms],
                *[Unit.number == t for t in query.terms],
            )
        )
    allowed = session_allowed_legal_entity_ids(session)
    if allowed is not None:
        stmt = stmt.where(Contract.legal_entity_id.in_(list(allowed)))
    allowed_props = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed_props is not None:
        stmt = stmt.where(Contract.property_id.in_(allowed_props))
    rows = (
        await session.execute(
            stmt.order_by(RentIncreaseCase.status, RentIncreaseCase.effective_date.desc()).limit(
                LIMIT
            )
        )
    ).all()
    return [
        _link(
            "rent_increase",
            case.id,
            f"Mieterhöhung {party}, Objekt {prop_number} Einheit {unit_number}",
            f"/vermietung/mieterhoehung/{case.id}",
            f"{RENT_INCREASE_STATUS.get(case.status, case.status)}, von {eur(case.current_rent)} "
            f"auf {eur(case.target_rent)} zum {_date(case.effective_date)}, Basis {case.basis}",
        )
        for case, party, prop_number, unit_number in rows
    ]


# Work orders --------------------------------------------------------------------------------


async def search_work_orders(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Work orders (``tickets:read``): description, provider, property; open ones first."""
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import Property
    from mhvp.tickets.models import WorkOrder

    stmt = (
        select(WorkOrder, Contact.display_name, Property.number)
        .join(Contact, Contact.id == WorkOrder.provider_contact_id)
        .join(Property, Property.id == WorkOrder.property_id)
    )
    focus_property = await _focus_property_id(session, query)
    if focus_property is not None:
        stmt = stmt.where(WorkOrder.property_id == focus_property)
    elif query.focus is not None and query.focus[0] == "ticket":
        stmt = stmt.where(WorkOrder.ticket_id == query.focus[1])
    if query.terms:
        stmt = stmt.where(
            or_(
                _term_filter(
                    [WorkOrder.description, Contact.display_name, Property.name], query.terms
                ),
                *[Property.number == t for t in query.terms],
            )
        )
    else:
        stmt = stmt.where(WorkOrder.status.in_(OPEN_ORDER))
    allowed_props = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed_props is not None:
        stmt = stmt.where(WorkOrder.property_id.in_(allowed_props))
    rows = (await session.execute(stmt.order_by(WorkOrder.created_at.desc()).limit(LIMIT))).all()
    return [
        _link(
            "work_order",
            o.id,
            f"Auftrag {flat(o.description)[:80]}",
            f"/auftraege/{o.id}",
            ", ".join(
                p
                for p in (
                    ORDER_STATUS.get(o.status.value, o.status.value),
                    f"Dienstleister {provider}",
                    f"Objekt {number}",
                    f"Termin {o.scheduled_at:%d.%m.%Y}" if o.scheduled_at else "",
                )
                if p
            ),
        )
        for o, provider, number in rows
    ]


# Bank ---------------------------------------------------------------------------------------


async def search_bank_transactions(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Bank transactions (``accounting:read``, legal entity scope): unmatched ones by default,
    by counterparty name or purpose when a term is given, newest first. Amounts as strings;
    the IBAN never appears."""
    from mhvp.banking.models import BankTransaction
    from mhvp.banking.property_scope import session_account_filter

    stmt = select(BankTransaction)
    if query.terms:
        stmt = stmt.where(
            _term_filter([BankTransaction.counterpart_name, BankTransaction.purpose], query.terms)
        )
    if "unmatched" in query.flags or not query.terms:
        stmt = stmt.where(BankTransaction.status.in_(UNMATCHED))
    if query.range is not None:
        stmt = stmt.where(
            BankTransaction.booking_date >= query.range[0],
            BankTransaction.booking_date <= query.range[1],
        )
    allowed = session_allowed_legal_entity_ids(session)
    if allowed is not None:
        stmt = stmt.where(BankTransaction.legal_entity_id.in_(list(allowed)))
    visible = session_account_filter(session)  # M2-02/S16-02
    if visible is not None:
        stmt = stmt.where(BankTransaction.property_bank_account_id.in_(visible))
    rows = (
        await session.scalars(
            stmt.order_by(BankTransaction.booking_date.desc(), BankTransaction.id.desc()).limit(
                LIMIT
            )
        )
    ).all()
    return [
        _link(
            "bank_transaction",
            t.id,
            f"Umsatz {t.booking_date:%d.%m.%Y} {eur(t.amount)} {flat(t.counterpart_name)}".strip(),
            "/bank",
            ", ".join(
                p
                for p in (
                    TRANSACTION_STATUS.get(t.status.value, t.status.value),
                    flat(t.purpose)[:100] if t.purpose else "",
                )
                if p
            ),
        )
        for t in rows
    ]


# Open items ---------------------------------------------------------------------------------


async def search_open_items(session: AsyncSession, query: Query) -> list[dict[str, Any]]:
    """Open items per debtor (``accounting:read``, legal entity scope): remaining amount per
    contract party as of today (settlements deducted, B07), the largest first. With a term the
    debtor's name is matched; with a property open on the page its contracts."""
    from mhvp.accounting.models import Ledger, OpenItem, OpenItemSettlement
    from mhvp.accounting.write_offs import not_written_off_as_of
    from mhvp.contacts.models import Party
    from mhvp.contracts.models import Contract

    settled = (
        select(OpenItemSettlement.open_item_id, func.sum(OpenItemSettlement.amount).label("s"))
        .where(OpenItemSettlement.date <= query.today)
        .group_by(OpenItemSettlement.open_item_id)
        .subquery()
    )
    remaining = OpenItem.amount - func.coalesce(settled.c.s, 0)
    stmt = (
        select(
            Contract.id,
            Contract.number,
            Party.name,
            Ledger.id,
            func.count(OpenItem.id),
            func.sum(remaining),
            func.min(OpenItem.due_date),
        )
        .join(Ledger, Ledger.id == OpenItem.ledger_id)
        .join(Contract, Contract.id == OpenItem.contract_id)
        .join(Party, Party.id == Contract.party_id)
        .outerjoin(settled, settled.c.open_item_id == OpenItem.id)
        .where(
            OpenItem.kind == "receivable",
            # AO01 (GAK-104): date aware, written off only from written_off_on (B07).
            not_written_off_as_of(query.today),
            OpenItem.booking_date <= query.today,
        )
        .group_by(Contract.id, Contract.number, Party.name, Ledger.id)
        .having(func.sum(remaining) > 0)
    )
    focus_property = await _focus_property_id(session, query)
    if focus_property is not None:
        stmt = stmt.where(Contract.property_id == focus_property)
    elif query.focus is not None and query.focus[0] == "contract":
        stmt = stmt.where(Contract.id == query.focus[1])
    if query.terms:
        stmt = stmt.where(_term_filter([Party.name, Contract.number], query.terms))
    allowed = session_allowed_legal_entity_ids(session)
    if allowed is not None:
        stmt = stmt.where(Ledger.legal_entity_id.in_(list(allowed)))
    allowed_props = session_allowed_property_ids(session)  # M2-02/S16-02
    if allowed_props is not None:
        stmt = stmt.where(Ledger.property_id.in_(allowed_props))
    rows = (await session.execute(stmt.order_by(func.sum(remaining).desc()).limit(LIMIT))).all()
    return [
        _link(
            "open_items",
            contract_id,
            f"Offene Posten {party}",
            f"/buchhaltung/{ledger_id}",
            f"Vertrag {number}: {count} Posten, Rest {eur(total)}"
            + (f", älteste Fälligkeit {_date(oldest)}" if oldest else ""),
        )
        for contract_id, number, party, ledger_id, count, total, oldest in rows
    ]


# Registry -----------------------------------------------------------------------------------

AREA_TOOLS: dict[str, tuple[str, str | None, Any]] = {
    "calendar": ("Termine", None, search_calendar),
    "deadlines": ("Fristen", None, search_deadlines),
    "documents": ("Dokumente", "documents:read", search_documents),
    "resolutions": ("Beschlüsse", "accounting:read", search_resolutions),
    "meetings": ("Versammlungen", "accounting:read", search_meetings),
    "reserve": ("Rücklage", "accounting:read", search_reserve),
    "rent_increases": ("Mieterhöhungen", "contracts:read", search_rent_increases),
    "work_orders": ("Aufträge", "tickets:read", search_work_orders),
    "bank_transactions": ("Bankumsätze", "accounting:read", search_bank_transactions),
    "open_items": ("Offene Posten", "accounting:read", search_open_items),
}
# Tools that answer without a search term (the page's standard questions).
TERMLESS = frozenset(
    {
        "calendar",
        "deadlines",
        "documents",
        "resolutions",
        "meetings",
        "reserve",
        "rent_increases",
        "work_orders",
        "bank_transactions",
        "open_items",
    }
)
# Never added by the "nothing found, widen" step: they answer without a term and would fill
# every unrelated question with appointments or bank transactions.
NO_WIDENING = frozenset(AREA_TOOLS)
# Intent words that add an area tool from any page.
INTENT: dict[str, re.Pattern[str]] = {
    "calendar": re.compile(r"termin|kalender|besichtigung|übergabetermin", re.I),
    "deadlines": re.compile(r"frist|fällig|faellig|überfällig|wiedervorlage", re.I),
    "documents": re.compile(r"dokument|datei|unterlage|pdf|protokoll|schreiben\b", re.I),
    "resolutions": re.compile(r"beschl[uü]ss", re.I),
    "meetings": re.compile(r"versammlung", re.I),
    "reserve": re.compile(r"rücklage|ruecklage", re.I),
    "rent_increases": re.compile(r"mieterhöhung|mieterhoehung|mietanpassung", re.I),
    "work_orders": re.compile(r"auftrag|aufträge|auftraege|handwerker", re.I),
    "bank_transactions": re.compile(
        r"umsatz|umsätze|umsaetze|zugeordnet|überweisung|zahlungseingang", re.I
    ),
    "open_items": re.compile(
        r"offene posten|rückstand|rueckstand|forderung|debitor|schuldet|offene beträge", re.I
    ),
}
# Area and sub area of the CRM (chat-suggestions.ts) -> tools that run without a term.
AREA_MAP: dict[str, list[str]] = {
    "start": ["calendar", "deadlines"],
    "calendar": ["calendar"],
    "deadlines": ["deadlines"],
    "documents": ["documents"],
    "dms": ["documents"],
    "hoa": ["resolutions", "meetings", "reserve"],
    "letting": ["rent_increases"],
    "orders": ["work_orders"],
    "tickets": ["work_orders"],
    "bank": ["bank_transactions", "open_items"],
    "accounting": ["open_items"],
    "dunning": ["open_items"],
    "invoices": ["bank_transactions"],
    "handover": ["calendar"],
    "broker": ["calendar"],
}
SUB_AREA_MAP: dict[str, list[str]] = {
    "letting/rentIncrease": ["rent_increases"],
    "hoa/meeting": ["meetings", "resolutions"],
    "bank/payments": ["bank_transactions"],
    "bank/directDebits": ["open_items"],
    "properties/detail": ["documents"],
}


def tools_of_area(area: str | None, sub_area: str | None) -> list[str]:
    if not area:
        return []
    tools = list(AREA_MAP.get(area, []))
    if sub_area:
        tools += SUB_AREA_MAP.get(f"{area}/{sub_area}", [])
    return list(dict.fromkeys(tools))


# Focus of the new record types ---------------------------------------------------------------

FOCUS_PERMISSION: dict[str, str | None] = {
    "document": "documents:read",
    "meeting": "accounting:read",
    "rent_increase": "contracts:read",
    "work_order": "tickets:read",
    "calendar_entry": None,
}


async def focus_extra(
    session: AsyncSession, permissions: frozenset[str], entity_type: str, entity_id: uuid.UUID
) -> tuple[list[dict[str, Any]], list[str]]:
    """Links and facts of a record type the classic focus (``lookup.focus_record``) does not
    know: document, meeting, rent increase, work order, calendar entry."""
    if entity_type not in FOCUS_PERMISSION:
        return [], []
    permission = FOCUS_PERMISSION[entity_type]
    if permission is not None and permission not in permissions:
        return [], []
    links: list[dict[str, Any]] = []
    facts: list[str] = []
    if entity_type == "document":
        from mhvp.documents.models import Document, DocumentCategory

        row = await session.execute(
            select(Document, DocumentCategory.name)
            .outerjoin(DocumentCategory, DocumentCategory.id == Document.category_id)
            .where(Document.id == entity_id)
        )
        found = row.first()
        if found is not None:
            d, category = found
            links.append(
                _link(
                    "document",
                    d.id,
                    d.title,
                    f"/dokumente/{d.id}",
                    ", ".join(p for p in (category, f"vom {_date(d.created_at)}") if p),
                )
            )
            if d.ocr_text:
                facts.append("Textauszug: " + flat(d.ocr_text)[:600])
    elif entity_type == "meeting":
        from mhvp.hoa.models import AgendaItem, Meeting
        from mhvp.properties.models import LegalEntity

        m = await session.get(Meeting, entity_id)
        if m is not None and _scoped(session, m.legal_entity_id):
            entity = await session.get(LegalEntity, m.legal_entity_id)
            property_id = entity.property_id if entity else None
            links.append(
                _link(
                    "meeting",
                    m.id,
                    f"Eigentümerversammlung {m.scheduled_at:%d.%m.%Y}",
                    f"/weg/{property_id}/versammlung/{m.id}",
                    MEETING_STATUS.get(m.status, m.status),
                )
            )
            items = (
                await session.scalars(
                    select(AgendaItem)
                    .where(AgendaItem.meeting_id == m.id)
                    .order_by(AgendaItem.position)
                )
            ).all()
            if items:
                facts.append(
                    "Tagesordnung: "
                    + "; ".join(f"TOP {i.position} {flat(i.title)}" for i in items[:LIMIT])
                )
    elif entity_type == "rent_increase":
        query = Query(terms=[], role=None, help=False, intents=set(), today=local_today())
        query.focus = ("rent_increase", entity_id)
        from mhvp.letting.models import RentIncreaseCase

        case = await session.get(RentIncreaseCase, entity_id)
        if case is not None:
            query.focus = ("contract", case.contract_id)
            links += await search_rent_increases(session, query)
    elif entity_type == "work_order":
        from mhvp.tickets.models import WorkOrder

        order = await session.get(WorkOrder, entity_id)
        if order is not None:
            query = Query(terms=[], role=None, help=False, intents=set(), today=local_today())
            query.focus = ("property", order.property_id)
            links += [
                x for x in await search_work_orders(session, query) if x["id"] == str(order.id)
            ]
            if order.completion_report:
                facts.append("Abschlussbericht: " + flat(order.completion_report)[:600])
    elif entity_type == "calendar_entry":
        from mhvp.workspace.models import CalendarEntry

        principal = session_principal(session)
        e = await session.get(CalendarEntry, entity_id)
        if (
            e is not None
            and principal is not None
            and (e.shared or e.owner_user_id in (None, principal.user_id))
        ):
            links.append(
                _link(
                    "calendar_entry",
                    f"{e.id}:{e.starts_on.isoformat()}",
                    e.title,
                    f"/kalender?termin={e.id}&datum={e.starts_on.isoformat()}",
                    f"{e.starts_on:%d.%m.%Y}" + (f", {flat(e.notes)[:200]}" if e.notes else ""),
                )
            )
    return links, facts


__all__ = [
    "AREA_MAP",
    "AREA_TOOLS",
    "INTENT",
    "NO_WIDENING",
    "TERMLESS",
    "eur",
    "focus_extra",
    "local_today",
    "tools_of_area",
]
