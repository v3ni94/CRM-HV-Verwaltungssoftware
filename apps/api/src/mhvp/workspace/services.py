"""Notification helper and derived calendar dates (M9)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.workspace.models import Notification

REMIND_DAYS = {"14d": 14, "1m": 30, "3m": 91, "6m": 182}
DEFAULT_REMIND_DAYS = 14
# Display calendar only; the time zone of legal deadlines is still open (M1-09).
_LOCAL = ZoneInfo("Europe/Berlin")


def local_today() -> date:
    return datetime.now(UTC).astimezone(_LOCAL).date()


async def notify(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification | None:
    """Create a notification unless the same unread one exists (idempotent for jobs)."""
    if entity_id is not None:
        existing = await session.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.kind == kind,
                Notification.entity_id == entity_id,
                Notification.read_at.is_(None),
            )
        )
        if existing is not None:
            return None
    row = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(row)
    return row


async def derived_dates(
    session: AsyncSession, start: date, end: date, *, contracts: bool, properties: bool
) -> list[dict[str, Any]]:
    """Maintenance due dates and contract end/termination dates in [start, end]."""
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import MaintenanceItem, Property

    items: list[dict[str, Any]] = []
    if properties:
        rows = (
            await session.execute(
                select(MaintenanceItem, Property.number, Property.name)
                .join(Property, Property.id == MaintenanceItem.property_id)
                .where(
                    MaintenanceItem.status == "open",
                    MaintenanceItem.due_date.between(start, end),
                )
            )
        ).all()
        items += [
            {
                "kind": "maintenance",
                "title": f"{m.title} ({number} {name})",
                "date": m.due_date,
                "entity_type": "maintenance_item",
                "entity_id": m.id,
                "property_id": m.property_id,
            }
            for m, number, name in rows
        ]
    if contracts:
        rows2 = (
            await session.scalars(
                select(Contract).where(
                    or_(
                        Contract.end_date.between(start, end),
                        Contract.termination_date.between(start, end),
                    )
                )
            )
        ).all()
        for c in rows2:
            for field, label in (("end_date", "Vertragsende"), ("termination_date", "Kündigung")):
                value = getattr(c, field)
                if value is not None and start <= value <= end:
                    items.append(
                        {
                            "kind": f"contract_{field}",
                            "title": f"{label} Vertrag {c.number}",
                            "date": value,
                            "entity_type": "contract",
                            "entity_id": c.id,
                            "property_id": c.property_id,
                        }
                    )
    return items


async def maintenance_reminders(session: AsyncSession, today: date) -> int:
    """Notify the property manager about open maintenance items inside their reminder window."""
    from mhvp.platform.models import Membership
    from mhvp.properties.models import MaintenanceItem, Property

    horizon = today + timedelta(days=max(REMIND_DAYS.values()))
    rows = (
        await session.execute(
            select(MaintenanceItem, Property)
            .join(Property, Property.id == MaintenanceItem.property_id)
            .join(
                Membership,
                and_(
                    Membership.user_id == Property.manager_user_id,
                    Membership.tenant_id == Property.tenant_id,
                ),
            )
            .where(
                and_(
                    MaintenanceItem.status == "open",
                    MaintenanceItem.due_date.is_not(None),
                    MaintenanceItem.due_date <= horizon,
                    Property.manager_user_id.is_not(None),
                )
            )
        )
    ).all()
    created = 0
    for item, prop in rows:
        days = REMIND_DAYS.get(item.remind_before or "", DEFAULT_REMIND_DAYS)
        if item.due_date is None or item.due_date - timedelta(days=days) > today:
            continue
        overdue = item.due_date < today
        row = await notify(
            session,
            tenant_id=item.tenant_id,
            user_id=prop.manager_user_id,
            kind="maintenance_overdue" if overdue else "maintenance_due",
            title=f"{'Überfällig' if overdue else 'Fällig'}: {item.title}",
            body=f"Objekt {prop.number} {prop.name}, fällig am {item.due_date:%d.%m.%Y}",
            entity_type="maintenance_item",
            entity_id=item.id,
        )
        created += row is not None
    await session.flush()
    return created
