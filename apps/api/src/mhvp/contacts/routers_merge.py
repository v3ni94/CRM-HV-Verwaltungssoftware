"""Contact merge endpoints (M3-03): proposal, check, reject, execute (four eyes)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.contacts import merge
from mhvp.contacts.models import Contact, ContactMerge
from mhvp.contacts.routers import APPROVE, READ, UPDATE
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(tags=["Kontakte"])


class ContactMergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: uuid.UUID
    target_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=1000)


class ContactMergeDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=1000)


class ContactMergeOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    target_id: uuid.UUID
    source_name: str | None = None
    target_name: str | None = None
    status: str
    reason: str | None
    check_result: dict[str, Any]
    proposed_by: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    result: dict[str, Any] | None
    created_at: datetime


async def _out(session: Any, rows: list[ContactMerge]) -> list[ContactMergeOut]:
    ids = {r.source_id for r in rows} | {r.target_id for r in rows}
    names: dict[uuid.UUID, str] = {}
    if ids:
        found = await session.execute(
            select(Contact.id, Contact.display_name).where(Contact.id.in_(ids))
        )
        names = dict(found.all())
    return [
        ContactMergeOut(
            **merge.to_dict(r),
            source_name=names.get(r.source_id),
            target_name=names.get(r.target_id),
        )
        for r in rows
    ]


async def _load(session: Any, merge_id: uuid.UUID) -> ContactMerge:
    row: ContactMerge | None = await session.get(ContactMerge, merge_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/contact-merges", summary="Zusammenführungsvorschläge von Kontakten")
async def list_merges(
    request: Request,
    status: str | None = Query(default=None, pattern="^(proposed|executed|rejected)$"),
    principal: TenantPrincipal = Depends(READ),
) -> list[ContactMergeOut]:
    async with tenant_tx(request, principal) as session:
        query = select(ContactMerge).order_by(ContactMerge.created_at.desc()).limit(200)
        if status:
            query = query.where(ContactMerge.status == status)
        rows = list((await session.scalars(query)).all())
        return await _out(session, rows)


@router.post("/contact-merges", status_code=201, summary="Zusammenführung vorschlagen")
async def propose_merge(
    body: ContactMergeIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> ContactMergeOut:
    async with tenant_tx(request, principal) as session:
        row = await merge.propose(
            session,
            tenant_id=principal.tenant_id,
            source_id=body.source_id,
            target_id=body.target_id,
            reason=body.reason,
            user_id=principal.user_id,
        )
        return (await _out(session, [row]))[0]


@router.get("/contact-merges/{merge_id}", summary="Zusammenführungsvorschlag mit Prüfung")
async def get_merge(
    merge_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> ContactMergeOut:
    async with tenant_tx(request, principal) as session:
        return (await _out(session, [await _load(session, merge_id)]))[0]


@router.post("/contact-merges/{merge_id}/reject", summary="Zusammenführung ablehnen")
async def reject_merge(
    merge_id: uuid.UUID,
    body: ContactMergeDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> ContactMergeOut:
    async with tenant_tx(request, principal) as session:
        row = await merge.reject(
            session, await _load(session, merge_id), user_id=principal.user_id, note=body.note
        )
        return (await _out(session, [row]))[0]


@router.post("/contact-merges/{merge_id}/execute", summary="Zusammenführung ausführen")
async def execute_merge(
    merge_id: uuid.UUID,
    body: ContactMergeDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> ContactMergeOut:
    async with tenant_tx(request, principal) as session:
        row = await merge.execute(
            session, await _load(session, merge_id), user_id=principal.user_id, note=body.note
        )
        return (await _out(session, [row]))[0]
