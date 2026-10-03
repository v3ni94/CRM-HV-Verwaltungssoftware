"""Intake and monitoring of data subject access requests (AK06, GAI-507, migration 0448).

A request is recorded with receipt date and channel, worked through the statuses
``received`` -> ``in_progress`` -> ``answered`` | ``rejected`` | ``withdrawn`` and monitored
against the tenant setting ``privacy_request_deadlines.access_days``. That setting has no
default value (legal question OPEN_QUESTIONS AJ13-01): without it no due date is computed and
nothing is entered into the deadline register. Computed dates are an orientation to be
verified, never a legal calculation. Closing a request is no legal declaration; the answer
itself goes out through the reviewed access export (``contacts.access_export``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings
from mhvp.privacy.models import (
    ACCESS_REQUEST_OPEN,
    PrivacyAccessRequest,
)

router = APIRouter(tags=["Datenschutz"])
READ = require_permission("privacy:read")
MANAGE = require_permission("privacy:manage")

DEADLINE_KIND = "privacy_access_request"
DEADLINES_KEY = "privacy_request_deadlines"
_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "received": ("in_progress", "answered", "rejected", "withdrawn"),
    "in_progress": ("answered", "rejected", "withdrawn"),
}
Channel = Literal["email", "letter", "portal", "phone", "in_person", "other"]
Status = Literal["received", "in_progress", "answered", "rejected", "withdrawn"]


class PrivacyAccessRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID
    received_on: date
    channel: Channel
    note: str | None = Field(default=None, max_length=1000)


class PrivacyAccessRequestStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["in_progress", "answered", "rejected", "withdrawn"]
    note: str | None = Field(default=None, max_length=1000)
    export_id: uuid.UUID | None = None


class PrivacyAccessRequestOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str | None
    received_on: date
    channel: str
    status: str
    note: str | None
    export_id: uuid.UUID | None
    closed_on: date | None
    close_note: str | None
    due_on: date | None
    warn_on: date | None
    state: Literal["unconfigured", "ok", "warn", "overdue", "closed"]


def access_days(sources: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """``access_days`` and ``warn_days`` of the tenant setting; invalid values count as unset."""
    raw = (sources or {}).get(DEADLINES_KEY)
    raw = raw if isinstance(raw, dict) else {}

    def _int(key: str, low: int, high: int) -> int | None:
        val = raw.get(key)
        if isinstance(val, int) and not isinstance(val, bool) and low <= val <= high:
            return val
        return None

    return _int("access_days", 1, 365), _int("warn_days", 0, 180)


def due_dates(
    received: date, days: int | None, warn_days: int | None, today: date
) -> tuple[date | None, date | None, str]:
    if days is None:
        return None, None, "unconfigured"
    due = received + timedelta(days=days)
    warn = due - timedelta(days=warn_days or 0)
    if today > due:
        return warn, due, "overdue"
    if today >= warn:
        return warn, due, "warn"
    return warn, due, "ok"


async def _settings(session: AsyncSession) -> tuple[int | None, int | None]:
    row = await session.scalar(select(TenantSettings))
    return access_days(row.sources if row else None)


def _out(
    row: PrivacyAccessRequest,
    name: str | None,
    cfg: tuple[int | None, int | None],
    today: date,
) -> PrivacyAccessRequestOut:
    warn, due, state = due_dates(row.received_on, cfg[0], cfg[1], today)
    if row.status not in ACCESS_REQUEST_OPEN:
        state = "closed"
    return PrivacyAccessRequestOut(
        id=row.id,
        contact_id=row.contact_id,
        contact_name=name,
        received_on=row.received_on,
        channel=row.channel,
        status=row.status,
        note=row.note,
        export_id=row.export_id,
        closed_on=row.closed_on,
        close_note=row.close_note,
        due_on=due,
        warn_on=warn,
        state=state,
    )


async def _name(session: AsyncSession, contact_id: uuid.UUID) -> str | None:
    name = await session.scalar(select(Contact.display_name).where(Contact.id == contact_id))
    return str(name) if name is not None else None


@router.get(
    "/privacy/access-requests",
    summary="Auskunftsanträge (Art. 15) mit Eingang, Status und Frist",
    dependencies=[Depends(strict_query)],
)
async def list_access_requests(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    status: Status | None = Query(default=None),
    open_only: bool = Query(default=False),
) -> list[PrivacyAccessRequestOut]:
    today = local_today()
    async with tenant_tx(request, principal) as session:
        cfg = await _settings(session)
        stmt = (
            select(PrivacyAccessRequest, Contact.display_name)
            .join(Contact, Contact.id == PrivacyAccessRequest.contact_id)
            .order_by(PrivacyAccessRequest.received_on.desc(), PrivacyAccessRequest.id.desc())
            .limit(500)
        )
        if status is not None:
            stmt = stmt.where(PrivacyAccessRequest.status == status)
        if open_only:
            stmt = stmt.where(PrivacyAccessRequest.status.in_(ACCESS_REQUEST_OPEN))
        rows = (await session.execute(stmt)).all()
        return [_out(r, n, cfg, today) for r, n in rows]


@router.post(
    "/privacy/access-requests",
    status_code=201,
    summary="Auskunftsantrag erfassen (Eingang)",
)
async def create_access_request(
    body: PrivacyAccessRequestIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> PrivacyAccessRequestOut:
    today = local_today()
    if body.received_on > today:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Eingangsdatum liegt in der Zukunft.")
    async with tenant_tx(request, principal) as session:
        name = await _name(session, body.contact_id)
        if name is None and await session.get(Contact, body.contact_id) is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        row = PrivacyAccessRequest(
            tenant_id=principal.tenant_id,
            contact_id=body.contact_id,
            received_on=body.received_on,
            channel=body.channel,
            status="received",
            note=body.note,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy_access_request.received",
            entity_type="privacy_access_request",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"received_on": body.received_on.isoformat(), "channel": body.channel},
        )
        cfg = await _settings(session)
        await sync_deadline(session, row, cfg)
        return _out(row, name, cfg, today)


@router.get(
    "/privacy/access-requests/{request_id}",
    summary="Auskunftsantrag",
    dependencies=[Depends(strict_query)],
)
async def get_access_request(
    request_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> PrivacyAccessRequestOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PrivacyAccessRequest, request_id)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        cfg = await _settings(session)
        return _out(row, await _name(session, row.contact_id), cfg, local_today())


@router.post(
    "/privacy/access-requests/{request_id}/status",
    summary="Status eines Auskunftsantrags setzen (in Bearbeitung, beantwortet, abgelehnt)",
)
async def set_access_request_status(
    request_id: uuid.UUID,
    body: PrivacyAccessRequestStatusIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> PrivacyAccessRequestOut:
    today = local_today()
    async with tenant_tx(request, principal) as session:
        row = await session.get(PrivacyAccessRequest, request_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        if body.status not in _TRANSITIONS.get(row.status, ()):
            raise ProblemError(ErrorCodes.PRIVACY_STATE)
        before = row.status
        row.status = body.status
        row.updated_by = principal.user_id
        if body.export_id is not None:
            row.export_id = body.export_id
        if body.status in ACCESS_REQUEST_OPEN:
            if body.note:
                row.note = body.note
        else:
            row.closed_on = today
            row.closed_by = principal.user_id
            row.close_note = body.note
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="privacy_access_request.status_changed",
            entity_type="privacy_access_request",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": body.status},
        )
        cfg = await _settings(session)
        await sync_deadline(session, row, cfg)
        return _out(row, await _name(session, row.contact_id), cfg, today)


# --- deadline register (compliance_deadline) ---------------------------------------------


def reference(row: PrivacyAccessRequest) -> str:
    return (
        f"Auskunftsantrag vom {row.received_on:%d.%m.%Y} "
        "(Orientierung, zu prüfen; Frist aus der Mandanteneinstellung)"
    )


async def read_candidates(session: AsyncSession, since: date, today: date) -> list[dict[str, Any]]:
    """Source reader of ``workspace.jobs.calendar_sources``: open access requests with a due
    date from the tenant setting. No setting, no candidate (no default, AJ13-01)."""
    days, _warn = await _settings(session)
    if days is None:
        return []
    out: list[dict[str, Any]] = []
    for row in await session.scalars(
        select(PrivacyAccessRequest).where(PrivacyAccessRequest.status.in_(ACCESS_REQUEST_OPEN))
    ):
        due = row.received_on + timedelta(days=days)
        if due < since:
            continue
        out.append(
            {
                "kind": DEADLINE_KIND,
                "source_type": "privacy_access_request",
                "source_id": row.id,
                "reference": reference(row)[:300],
                "due_on": due,
                "property_id": None,
            }
        )
    return out


async def sync_deadline(
    session: AsyncSession, row: PrivacyAccessRequest, cfg: tuple[int | None, int | None]
) -> None:
    """Mirror the request into the deadline register at once (the nightly job keeps it in
    sync): open with a configured period -> open row; closed -> the open row is done."""
    from mhvp.workspace.jobs import job_settings, lead_days_for
    from mhvp.workspace.models import ComplianceDeadline

    existing = (
        await session.scalars(
            select(ComplianceDeadline).where(
                ComplianceDeadline.kind == DEADLINE_KIND,
                ComplianceDeadline.source_id == row.id,
                ComplianceDeadline.status == "open",
            )
        )
    ).all()
    days, _warn = cfg
    due = row.received_on + timedelta(days=days) if days is not None else None
    now = datetime.now(UTC)
    keep = None
    for item in existing:
        if row.status in ACCESS_REQUEST_OPEN and item.due_on == due:
            keep = item
        else:
            item.status, item.done_at = "done", now
    if row.status in ACCESS_REQUEST_OPEN and due is not None and keep is None:
        prior = await session.scalar(
            select(ComplianceDeadline).where(
                ComplianceDeadline.kind == DEADLINE_KIND,
                ComplianceDeadline.source_id == row.id,
                ComplianceDeadline.due_on == due,
            )
        )
        # Same lead time as the nightly refresh (tenant setting of the deadline list), so the
        # job does not flip the row; the warn days of the privacy setting drive the monitor.
        lead_days = lead_days_for(
            DEADLINE_KIND, (await job_settings(session, row.tenant_id)).deadline_lead_days
        )
        if prior is not None:
            prior.status, prior.done_at = "open", None
        else:
            session.add(
                ComplianceDeadline(
                    tenant_id=row.tenant_id,
                    kind=DEADLINE_KIND,
                    source_type="privacy_access_request",
                    source_id=row.id,
                    reference=reference(row)[:300],
                    due_on=due,
                    lead_days=lead_days,
                    status="open",
                    property_id=None,
                )
            )
    await session.flush()
