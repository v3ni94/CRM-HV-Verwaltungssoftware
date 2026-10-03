"""Write off of open items as its own procedure (AN15, GAK-104; 7.1 B03, B07).

``open_item.written_off`` used to be a bare flag without date, reason or author and without
any writing path. A write off is now proposed with reason, effective date and an optional
voucher (``open_item_write_off``). A proposal has no effect on balances or reports. Approval
by a second person is possible only with the tenant switch
``accounting_tax_settings.write_off_approval_enabled`` (default off, question AN15-02) and gate
G1 open; it sets ``written_off`` with date, time, reason and author on the item. Nothing is
posted here: the legal basis (waiver, uncollectibility) and the booking procedure stay an open
decision; reports read the flag only from ``written_off_on`` onwards (as of date, B07).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import period_lock
from mhvp.accounting import services as acc
from mhvp.accounting.audit_events import record_change, snap
from mhvp.accounting.models import Ledger, OpenItem, OpenItemWriteOff
from mhvp.accounting.tax_models import AccountingTaxSettings
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open

router = APIRouter(prefix="/open-item-write-offs", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")

QUESTION = "AN15-02"
_FIELDS = ("status", "decided_by", "decided_at", "decision_note")
_ITEM_FIELDS = (
    "written_off",
    "written_off_on",
    "written_off_at",
    "written_off_reason",
    "written_off_by",
)


class AccountingWriteOffProposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    open_item_id: uuid.UUID
    effective_on: date
    reason: str = Field(min_length=10, max_length=500)
    document_id: uuid.UUID | None = None


class AccountingWriteOffDecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class AccountingWriteOffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    open_item_id: uuid.UUID
    status: str
    effective_on: date
    amount: Decimal
    reason: str
    document_id: uuid.UUID | None
    proposed_by: uuid.UUID | None
    proposed_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    posting_effect: bool = False
    approval_enabled: bool = False
    question: str = QUESTION


async def approval_enabled(session: AsyncSession) -> bool:
    return bool(await session.scalar(select(AccountingTaxSettings.write_off_approval_enabled)))


def _out(row: OpenItemWriteOff, enabled: bool) -> AccountingWriteOffOut:
    out = AccountingWriteOffOut.model_validate(row)
    out.approval_enabled = enabled
    return out


async def propose(
    session: AsyncSession,
    item: OpenItem,
    *,
    effective_on: date,
    reason: str,
    document_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> OpenItemWriteOff:
    """Proposal without any effect; amount is the remaining amount as of ``effective_on``."""
    if effective_on > local_today():
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Datum liegt in der Zukunft.")
    if effective_on < item.booking_date:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Datum liegt vor der Entstehung des Postens."
        )
    if item.kind.value != "receivable":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur Forderungen können ausgebucht werden."
        )
    if item.written_off:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Posten ist bereits ausgebucht.")
    active = await session.scalar(
        select(OpenItemWriteOff.id).where(
            OpenItemWriteOff.open_item_id == item.id,
            OpenItemWriteOff.status.in_(("proposed", "approved")),
        )
    )
    if active is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Es liegt bereits ein Vorschlag vor.")
    remaining = await acc.remaining(session, item.id, effective_on)
    if remaining <= 0:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Posten ist zum Stichtag nicht mehr offen."
        )
    if document_id is not None:
        from mhvp.documents.models import Document

        if await session.get(Document, document_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Beleg nicht gefunden.")
    row = OpenItemWriteOff(
        tenant_id=item.tenant_id,
        open_item_id=item.id,
        status="proposed",
        effective_on=effective_on,
        amount=remaining,
        reason=reason.strip(),
        document_id=document_id,
        proposed_by=user_id,
    )
    session.add(row)
    await session.flush()
    await record_change(
        session,
        tenant_id=item.tenant_id,
        actor_user_id=user_id,
        type="open_item_write_off.proposed",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before={},
        after={
            "open_item_id": str(item.id),
            "effective_on": effective_on.isoformat(),
            "amount": str(remaining),
            "reason": row.reason,
        },
    )
    await session.refresh(row)
    return row


async def decide(
    session: AsyncSession,
    row: OpenItemWriteOff,
    *,
    decision: str,
    note: str | None,
    user_id: uuid.UUID,
) -> OpenItemWriteOff:
    """Reject is always possible; approve needs the switch, a second person and an open
    period. The G1 check sits in the route (gate resolver of the app)."""
    if row.status != "proposed":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vorschlag ist bereits entschieden.")
    item = await session.get(OpenItem, row.open_item_id, with_for_update=True)
    if item is None:  # pragma: no cover
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    before = snap(row, _FIELDS)
    if decision == "approve":
        if row.proposed_by is not None and row.proposed_by == user_id:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vier Augen: die vorschlagende Person kann nicht freigeben.",
            )
        ledger = await session.get(Ledger, item.ledger_id)
        if ledger is not None:
            await period_lock.ensure_open_for_entry(
                session, ledger, item.journal_entry_id, row.effective_on
            )
        item_before = snap(item, _ITEM_FIELDS)
        now = datetime.now(UTC)
        item.written_off = True
        item.written_off_on = row.effective_on
        item.written_off_at = now
        item.written_off_reason = row.reason
        item.written_off_by = user_id
        row.status = "approved"
        row.decided_at = now
        await session.flush()
        await record_change(
            session,
            tenant_id=item.tenant_id,
            actor_user_id=user_id,
            type="open_item.written_off",
            entity_type="open_item",
            entity_id=item.id,
            before=item_before,
            after=snap(item, _ITEM_FIELDS),
            payload={"write_off_id": str(row.id)},
        )
    else:
        row.status = "rejected"
        row.decided_at = datetime.now(UTC)
    row.decided_by = user_id
    row.decision_note = note
    await session.flush()
    await record_change(
        session,
        tenant_id=row.tenant_id,
        actor_user_id=user_id,
        type=f"open_item_write_off.{row.status}",
        entity_type="open_item_write_off",
        entity_id=row.id,
        before=before,
        after=snap(row, _FIELDS),
    )
    return row


@router.get(
    "",
    summary="Ausbuchungsvorschläge offener Posten (AN15, ohne Buchungswirkung)",
    response_model=list[AccountingWriteOffOut],
    dependencies=[Depends(strict_query)],
)
async def list_write_offs(
    request: Request,
    open_item_id: uuid.UUID | None = Query(default=None),
    status: Literal["proposed", "approved", "rejected"] | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[AccountingWriteOffOut]:
    async with tenant_tx(request, principal) as session:
        query = select(OpenItemWriteOff).order_by(OpenItemWriteOff.proposed_at.desc())
        if open_item_id is not None:
            query = query.where(OpenItemWriteOff.open_item_id == open_item_id)
        if status is not None:
            query = query.where(OpenItemWriteOff.status == status)
        enabled = await approval_enabled(session)
        return [_out(r, enabled) for r in (await session.scalars(query.limit(500))).all()]


@router.post(
    "",
    status_code=201,
    summary="Ausbuchung eines offenen Postens vorschlagen (Grund, Datum, Beleg; keine Wirkung)",
    response_model=AccountingWriteOffOut,
)
async def propose_write_off(
    body: AccountingWriteOffProposeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountingWriteOffOut:
    async with tenant_tx(request, principal) as session:
        item = await session.get(OpenItem, body.open_item_id, with_for_update=True)
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await propose(
            session,
            item,
            effective_on=body.effective_on,
            reason=body.reason,
            document_id=body.document_id,
            user_id=principal.user_id,
        )
        return _out(row, await approval_enabled(session))


@router.post(
    "/{write_off_id}/decision",
    summary="Ausbuchungsvorschlag freigeben (Schalter, Vier Augen, G1) oder ablehnen",
    response_model=AccountingWriteOffOut,
)
async def decide_write_off(
    write_off_id: uuid.UUID,
    body: AccountingWriteOffDecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountingWriteOffOut:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Needs a person.")
    async with tenant_tx(request, principal) as session:
        row = await session.get(OpenItemWriteOff, write_off_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        enabled = await approval_enabled(session)
        if body.decision == "approve":
            if not enabled:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=(
                        "Die Freigabe von Ausbuchungen ist für diesen Mandanten nicht "
                        f"eingeschaltet (offene Frage {QUESTION}); der Vorschlag bleibt ohne "
                        "Wirkung."
                    ),
                )
            await ensure_release_gate_open(
                ReleaseGate.G1, principal.tenant_id, request.app.state.release_gate_resolver
            )
        row = await decide(
            session, row, decision=body.decision, note=body.note, user_id=principal.user_id
        )
        return _out(row, enabled)
