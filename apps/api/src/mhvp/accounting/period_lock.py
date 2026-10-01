"""Period lock per property and period (P06-02, AE20, rule P06-02).

The ledger wide ``Ledger.locked_until`` stays untouched (B03). In addition a tenant can switch
to ``object_period``: a posting or reversal whose lines belong to a locked property and whose
date lies in the locked period is refused. The property of a line comes from its unit (and from
``journal_line.property_id`` once that column exists, Q15-01); a ledger bound to one property
counts for all its lines. Lines without a property are not covered by an object lock.
Closing a statement only sets the lock when the tenant switch ``auto_lock_on_close`` is on;
releasing needs the switch ``reopen_enabled``, a reason and a second person (four eyes) and
never deletes the row. Nothing here books, sends or deletes anything.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import JournalLine, Ledger, PeriodLock, PeriodLockSetting
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

LOCK_MODES = ("ledger_only", "object_period")


class PeriodLockIn(BaseModel):
    ledger_id: uuid.UUID
    property_id: uuid.UUID
    period_from: date
    period_to: date
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def _order(self) -> "PeriodLockIn":
        if self.period_from > self.period_to:
            raise ValueError("period_from must not be after period_to")
        return self


class PeriodLockReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PeriodLockSettingIn(BaseModel):
    lock_mode: str | None = None
    auto_lock_on_close: bool | None = None
    reopen_enabled: bool | None = None

    @model_validator(mode="after")
    def _mode(self) -> "PeriodLockSettingIn":
        if self.lock_mode is not None and self.lock_mode not in LOCK_MODES:
            raise ValueError("lock_mode must be ledger_only or object_period")
        return self


class PeriodLockSettingOut(BaseModel):
    lock_mode: str
    auto_lock_on_close: bool
    reopen_enabled: bool
    decision_open: bool = True
    open_questions: list[str] = ["P06-02", "AA08-01"]


class PeriodLockOut(BaseModel):
    id: uuid.UUID
    ledger_id: uuid.UUID
    property_id: uuid.UUID
    period_from: date
    period_to: date
    source: str
    statement_id: uuid.UUID | None
    reason: str | None
    active: bool
    created_by: uuid.UUID | None
    released_at: datetime | None
    released_by: uuid.UUID | None
    release_reason: str | None
    release_requested_by: uuid.UUID | None
    release_requested_at: datetime | None
    release_request_reason: str | None


def to_out(row: PeriodLock) -> PeriodLockOut:
    return PeriodLockOut(
        id=row.id,
        ledger_id=row.ledger_id,
        property_id=row.property_id,
        period_from=row.period_from,
        period_to=row.period_to,
        source=row.source,
        statement_id=row.statement_id,
        reason=row.reason,
        active=row.released_at is None,
        created_by=row.created_by,
        released_at=row.released_at,
        released_by=row.released_by,
        release_reason=row.release_reason,
        release_requested_by=row.release_requested_by,
        release_requested_at=row.release_requested_at,
        release_request_reason=row.release_request_reason,
    )


async def get_setting(session: AsyncSession) -> PeriodLockSetting | None:
    return await session.scalar(select(PeriodLockSetting))


def setting_out(row: PeriodLockSetting | None) -> PeriodLockSettingOut:
    return PeriodLockSettingOut(
        lock_mode=row.lock_mode if row else "ledger_only",
        auto_lock_on_close=row.auto_lock_on_close if row else False,
        reopen_enabled=row.reopen_enabled if row else False,
    )


async def update_setting(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    body: PeriodLockSettingIn,
) -> PeriodLockSettingOut:
    row = await get_setting(session)
    if row is None:
        row = PeriodLockSetting(
            tenant_id=tenant_id,
            lock_mode="ledger_only",
            auto_lock_on_close=False,
            reopen_enabled=False,
        )
        session.add(row)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    row.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="period_lock.settings_changed",
        entity_type="period_lock_setting",
        entity_id=row.id,
        actor_user_id=user_id,
        payload=setting_out(row).model_dump(
            include={"lock_mode", "auto_lock_on_close", "reopen_enabled"}
        ),
    )
    return setting_out(row)


async def property_ids_of_lines(
    session: AsyncSession, ledger: Ledger, entry_id: uuid.UUID
) -> set[uuid.UUID]:
    """Properties an entry touches: ledger property plus the property of every line."""
    from mhvp.properties.models import Unit

    found: set[uuid.UUID] = set()
    if ledger.property_id is not None:
        found.add(ledger.property_id)
    rows = (
        await session.scalars(
            select(Unit.property_id)
            .join(JournalLine, JournalLine.unit_id == Unit.id)
            .where(JournalLine.journal_entry_id == entry_id)
            .distinct()
        )
    ).all()
    found.update(rows)
    column: Any = getattr(JournalLine, "property_id", None)  # after Q15-01 (AE21)
    if column is not None:
        extra = (
            await session.scalars(
                select(column).where(JournalLine.journal_entry_id == entry_id, column.is_not(None))
            )
        ).all()
        found.update(extra)
    return found


async def ensure_open_for_properties(
    session: AsyncSession, ledger: Ledger, property_ids: set[uuid.UUID], day: date
) -> None:
    """Refuse when an active lock of one of the properties covers ``day`` (mode switch)."""
    if not property_ids:
        return
    setting = await get_setting(session)
    if setting is None or setting.lock_mode != "object_period":
        return
    hit = await session.scalar(
        select(PeriodLock)
        .where(
            PeriodLock.ledger_id == ledger.id,
            PeriodLock.property_id.in_(property_ids),
            PeriodLock.released_at.is_(None),
            PeriodLock.period_from <= day,
            PeriodLock.period_to >= day,
        )
        .limit(1)
    )
    if hit is not None:
        raise ProblemError(
            ErrorCodes.ACC_PERIOD_LOCKED_OBJECT,
            detail=(
                f"Der Zeitraum {hit.period_from:%d.%m.%Y} bis {hit.period_to:%d.%m.%Y} "
                "ist für dieses Objekt gesperrt."
            ),
        )


async def ensure_open_for_entry(
    session: AsyncSession, ledger: Ledger, entry_id: uuid.UUID, day: date
) -> None:
    setting = await get_setting(session)
    if setting is None or setting.lock_mode != "object_period":
        return
    await ensure_open_for_properties(
        session, ledger, await property_ids_of_lines(session, ledger, entry_id), day
    )


async def _overlap(
    session: AsyncSession, ledger_id: uuid.UUID, property_id: uuid.UUID, start: date, end: date
) -> PeriodLock | None:
    found: PeriodLock | None = await session.scalar(
        select(PeriodLock)
        .where(
            PeriodLock.ledger_id == ledger_id,
            PeriodLock.property_id == property_id,
            PeriodLock.released_at.is_(None),
            PeriodLock.period_from <= end,
            PeriodLock.period_to >= start,
        )
        .limit(1)
    )
    return found


async def create_lock(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    ledger_id: uuid.UUID,
    property_id: uuid.UUID,
    period_from: date,
    period_to: date,
    reason: str,
    source: str = "manual",
    statement_id: uuid.UUID | None = None,
) -> PeriodLock:
    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Buchungskreis nicht gefunden.")
    from mhvp.properties.models import Property

    if await session.get(Property, property_id) is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Objekt nicht gefunden.")
    if await _overlap(session, ledger_id, property_id, period_from, period_to) is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für Objekt und Zeitraum besteht bereits eine Sperre."
        )
    row = PeriodLock(
        tenant_id=tenant_id,
        ledger_id=ledger_id,
        property_id=property_id,
        period_from=period_from,
        period_to=period_to,
        source=source,
        statement_id=statement_id,
        reason=reason,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="period_lock.created",
        entity_type="period_lock",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={
            "property_id": str(property_id),
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "source": source,
        },
    )
    return row


async def lock_for_closed_statement(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    source: str,
    statement_id: uuid.UUID,
    ledger_id: uuid.UUID,
    property_id: uuid.UUID,
    period_from: date,
    period_to: date,
) -> dict[str, Any]:
    """Called when a statement is closed. With the switch off only a proposal is returned."""
    setting = await get_setting(session)
    proposal = {"period_lock_proposed": True, "period_lock_id": None}
    if setting is None or not setting.auto_lock_on_close:
        return proposal
    existing = await session.scalar(
        select(PeriodLock).where(
            PeriodLock.source == source,
            PeriodLock.statement_id == statement_id,
            PeriodLock.released_at.is_(None),
        )
    )
    if existing is None:
        if await _overlap(session, ledger_id, property_id, period_from, period_to) is not None:
            return proposal  # a lock of the period exists already; nothing to add
        existing = await create_lock(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            ledger_id=ledger_id,
            property_id=property_id,
            period_from=period_from,
            period_to=period_to,
            reason="Abschluss der Abrechnung",
            source=source,
            statement_id=statement_id,
        )
    return {"period_lock_proposed": False, "period_lock_id": str(existing.id)}


async def _active(session: AsyncSession, lock_id: uuid.UUID) -> PeriodLock:
    row = await session.scalar(select(PeriodLock).where(PeriodLock.id == lock_id).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND, detail="Sperre nicht gefunden.")
    if row.released_at is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Sperre ist bereits aufgehoben.")
    return row


async def request_release(
    session: AsyncSession, lock_id: uuid.UUID, user_id: uuid.UUID | None, reason: str
) -> PeriodLock:
    setting = await get_setting(session)
    if setting is None or not setting.reopen_enabled:
        raise ProblemError(ErrorCodes.ACC_PERIOD_LOCK_RELEASE_DISABLED)
    row = await _active(session, lock_id)
    row.release_requested_by = user_id
    row.release_requested_at = datetime.now(UTC)
    row.release_request_reason = reason
    row.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="period_lock.release_requested",
        entity_type="period_lock",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"reason": reason},
    )
    return row


async def release(
    session: AsyncSession, lock_id: uuid.UUID, user_id: uuid.UUID | None, reason: str
) -> PeriodLock:
    setting = await get_setting(session)
    if setting is None or not setting.reopen_enabled:
        raise ProblemError(ErrorCodes.ACC_PERIOD_LOCK_RELEASE_DISABLED)
    row = await _active(session, lock_id)
    if row.release_requested_by is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Es liegt kein Aufhebungsantrag vor.")
    if user_id is None or user_id == row.release_requested_by:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die Aufhebung muss eine andere Person als die antragstellende freigeben.",
        )
    row.released_at = datetime.now(UTC)
    row.released_by = user_id
    row.release_reason = reason
    row.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="period_lock.released",
        entity_type="period_lock",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"reason": reason, "requested_by": str(row.release_requested_by)},
    )
    return row
