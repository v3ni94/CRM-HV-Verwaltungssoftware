"""Deep links of notifications (operator 26.09.2026): from a notification the user jumps to
the subject, e.g. into the ticket or the calendar entry.

The notification stores a structured target (``target_type``, ``target_id``; the database
columns are ``entity_type`` and ``entity_id``). The route is derived here on read, never
stored, so a renamed page needs no data migration. CRM users get the CRM route, portal
recipients the portal route; a target without a page yields ``None`` and the entry is shown
without a link.
"""

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.workspace.models import CalendarEntry, CalendarEvent, Notification
from mhvp.workspace.services import local_date

# Target types whose route is a plain "/<page>/<id>" in the CRM.
CRM_DETAIL_ROUTES: dict[str, str] = {
    "ticket": "/tickets",
    "work_order": "/auftraege",
    "document": "/dokumente",
    "contract": "/vertraege",
    "property": "/objekte",
    "ai_conversation": "/assistent",
    "contact": "/kontakte",
}
# Target types that lead to a list page of the CRM (no detail page or the id is not needed).
CRM_LIST_ROUTES: dict[str, str] = {
    "compliance_deadline": "/fristen",
    "digest_run": "/start",
    "bank_connection": "/bank",
    "proposal": "/assistent",
    "invoice": "/rechnungen",
    # AE36: scale monitoring alarm for platform administrators (page Plattform, Betrieb).
    "platform_scale": "/plattform/betrieb",
    # User created deadlines (rule WS-01) are listed on the deadline page.
    "deadline_entry": "/fristen",
}
# Portal: tickets are "Meldungen"; work orders and handovers have detail pages.
PORTAL_DETAIL_ROUTES: dict[str, str] = {
    "ticket": "/meldungen",
    "work_order": "/auftraege",
    "handover": "/uebergabe",
}
PORTAL_LIST_ROUTES: dict[str, str] = {
    "document": "/dokumente",
    "notice": "/aushaenge",
    "form": "/formulare",
    # Rule H03: monthly consumption information (portal page /verbrauch).
    "consumption_info": "/verbrauch",
}

# Targets that open the calendar with the entry focused (CRM page /kalender?termin=<id>).
APPOINTMENT_TYPES = frozenset({"appointment", "calendar_entry", "calendar_event"})
# Targets whose route needs the property id, resolved from the generated calendar entry.
PROPERTY_HINT_TYPES = frozenset({"meter", "building", "owners_meeting", "contact_note"})


def target_href(
    target_type: str | None,
    target_id: uuid.UUID | None,
    *,
    portal: bool = False,
    appointment_date: date | None = None,
    property_id: uuid.UUID | None = None,
) -> str | None:
    """Route of a notification target for the CRM (default) or the portal.

    ``appointment_date`` (start of the calendar entry) and ``property_id`` (of a maintenance
    item) are optional hints resolved by :func:`resolve_hints`; without them the calendar
    opens on the current month and the maintenance item falls back to the property list.
    """
    if not target_type:
        return None
    if portal:
        if target_id is not None and target_type in PORTAL_DETAIL_ROUTES:
            return f"{PORTAL_DETAIL_ROUTES[target_type]}/{target_id}"
        return PORTAL_LIST_ROUTES.get(target_type)
    if target_type in APPOINTMENT_TYPES:
        if target_id is None:
            return "/kalender"
        query = f"termin={target_id}"
        if appointment_date is not None:
            query += f"&datum={appointment_date.isoformat()}"
        return f"/kalender?{query}"
    if target_type == "message":
        return f"/mail?message={target_id}" if target_id is not None else "/mail"
    if target_type == "approval":
        # Approvals of mail replies live on the message itself (mail.approval_requested).
        return f"/mail?message={target_id}" if target_id is not None else "/mail"
    if target_type == "maintenance_item":
        return f"/objekte/{property_id}#wartung" if property_id is not None else "/objekte"
    # Sources of generated calendar entries (P1 AP7): meters, buildings and the energy
    # certificate live on the property page, meetings under the HOA section of the property.
    if target_type == "meter":
        return f"/objekte/{property_id}#zaehler" if property_id is not None else "/objekte"
    if target_type == "building":
        return f"/objekte/{property_id}#gebaeude" if property_id is not None else "/objekte"
    if target_type == "owners_meeting":
        if property_id is not None and target_id is not None:
            return f"/weg/{property_id}/versammlung/{target_id}"
        return "/weg"
    if target_type == "contact_note":
        return f"/kontakte/{property_id}" if property_id is not None else "/kontakte"
    if target_id is not None and target_type in CRM_DETAIL_ROUTES:
        return f"{CRM_DETAIL_ROUTES[target_type]}/{target_id}"
    return CRM_LIST_ROUTES.get(target_type)


async def resolve_hints(
    session: AsyncSession, rows: Iterable[Notification]
) -> tuple[dict[uuid.UUID, date], dict[uuid.UUID, uuid.UUID]]:
    """Batch lookup of the hints of :func:`target_href` for a page of notifications:
    start dates of appointment targets and property ids of maintenance items."""
    from mhvp.properties.models import MaintenanceItem

    appointment_ids = {
        r.entity_id for r in rows if r.entity_type in APPOINTMENT_TYPES and r.entity_id
    }
    maintenance_ids = {
        r.entity_id for r in rows if r.entity_type == "maintenance_item" and r.entity_id
    }
    dates: dict[uuid.UUID, date] = {}
    properties: dict[uuid.UUID, uuid.UUID] = {}
    if appointment_ids:
        for entry_id, starts_on in (
            await session.execute(
                select(CalendarEntry.id, CalendarEntry.starts_on).where(
                    CalendarEntry.id.in_(appointment_ids)
                )
            )
        ).all():
            dates[entry_id] = starts_on
        for event_id, starts_at in (
            await session.execute(
                select(CalendarEvent.id, CalendarEvent.starts_at).where(
                    CalendarEvent.id.in_(appointment_ids)
                )
            )
        ).all():
            dates.setdefault(event_id, local_date(starts_at))
    if maintenance_ids:
        for item_id, property_id in (
            await session.execute(
                select(MaintenanceItem.id, MaintenanceItem.property_id).where(
                    MaintenanceItem.id.in_(maintenance_ids)
                )
            )
        ).all():
            properties[item_id] = property_id
    # Sources of generated calendar entries (meter, building, owners_meeting, contact_note):
    # the generated entry carries the property of the source (reminder notifications).
    source_ids = {
        r.entity_id
        for r in rows
        if r.entity_type in PROPERTY_HINT_TYPES and r.entity_id and r.entity_id not in properties
    }
    if source_ids:
        for source_id, property_id in (
            await session.execute(
                select(CalendarEntry.source_id, CalendarEntry.property_id).where(
                    CalendarEntry.source_id.in_(source_ids),
                    CalendarEntry.owner_user_id.is_(None),
                    CalendarEntry.property_id.is_not(None),
                )
            )
        ).all():
            if source_id is not None and property_id is not None:
                properties.setdefault(source_id, property_id)
    return dates, properties
