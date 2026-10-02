"""Tenant portal: released operating cost statements of the own tenancy contracts (GAC-02,
section 14 role tenant, phase 4), read only.

Scope: only contracts with an active access grant (scope ``contract``, role ``tenant``). A
foreign statement or contract answers 404 without a hint. Only statements issued to tenants
(issued, due, posted, locked) appear, and only while release gate G3 is open and the tenant
switch ``tenant_statement_enabled`` (portal feature setting, default off) is on; otherwise
the list is empty with a note and detail and PDF answer 403. Explanations come exclusively
from approved text blocks (``portal_tenant_statement_*``); without approval a placeholder is
shown, the software ships no explanatory legal text. Opening the detail and downloading the
PDF write a read receipt (indication only, see :mod:`mhvp.portal.read_receipts`)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.models import Statement, StatementResult, StatementSnapshot
from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.documents.text_blocks import approved_texts
from mhvp.portal import access, read_receipts
from mhvp.portal import features as portal_features
from mhvp.portal.models import PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/tenant-statements", tags=["Portal"])
PROVIDED = (
    StatementStatus.ISSUED,
    StatementStatus.DUE,
    StatementStatus.POSTED,
    StatementStatus.LOCKED,
)
TEXT_CODES = {
    "key": "portal_tenant_statement_key",
    "consumption": "portal_tenant_statement_consumption",
    "advance": "portal_tenant_statement_advance",
    "balance": "portal_tenant_statement_balance",
}
PLACEHOLDER = "Erläuterung noch nicht freigegeben."
DISABLED_NOTE = "Die Abrechnungen sind im Portal für Ihre Verwaltung nicht freigeschaltet."
GATE_NOTE = "Abrechnungen werden im Portal erst nach Freigabe durch die Verwaltung angezeigt."
NOTE = (
    "Abrechnung Ihres Mietvertrags nach Ausgabe durch die Verwaltung. Der Abruf im Portal wird "
    "als Indiz vermerkt; er ist keine Zustellung."
)


async def _gate_open(request: Request, tenant_id: uuid.UUID) -> bool:
    try:
        await ensure_release_gate_open(
            ReleaseGate.G3, tenant_id, request.app.state.release_gate_resolver
        )
    except ProblemError:
        return False
    return True


async def _own_contracts(session: AsyncSession, account: PortalAccount) -> set[uuid.UUID]:
    return {
        g.scope_id
        for g in await access.grants(session, account, local_today())
        if g.scope_type == "contract" and g.role == "tenant"
    }


async def _rows(
    session: AsyncSession, contracts: set[uuid.UUID]
) -> list[tuple[Statement, StatementResult]]:
    if not contracts:
        return []
    return [
        (st, res)
        for st, res in (
            await session.execute(
                select(Statement, StatementResult)
                .join(StatementResult, StatementResult.statement_id == Statement.id)
                .where(
                    StatementResult.contract_id.in_(contracts),
                    Statement.status.in_(PROVIDED),
                )
                .order_by(Statement.period_to.desc(), Statement.version.desc())
            )
        ).all()
    ]


def _result_of(snapshot: StatementSnapshot | None, contract_id: uuid.UUID) -> dict[str, Any] | None:
    rows = (snapshot.results if snapshot else {}).get("results", [])
    return next((r for r in rows if r.get("contract_id") == str(contract_id)), None)


def _summary(st: Statement, res: StatementResult, row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "statement_id": st.id,
        "contract_id": res.contract_id,
        "period_from": st.period_from,
        "period_to": st.period_to,
        "version": st.version,
        "status": st.status.value,
        "unit_number": (row or {}).get("unit_number"),
        "costs": (row or {}).get("costs"),
        "advances_paid": (row or {}).get("advances_paid"),
        "balance": (row or {}).get("balance"),
        "has_pdf": res.document_id is not None,
    }


async def _ensure_enabled(request: Request, session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if not (await portal_features.get_or_default(session)).tenant_statement_enabled:
        raise ProblemError(ErrorCodes.FORBIDDEN, detail=DISABLED_NOTE)
    await ensure_release_gate_open(
        ReleaseGate.G3, tenant_id, request.app.state.release_gate_resolver
    )


async def _own(
    session: AsyncSession, account: PortalAccount, statement_id: uuid.UUID, contract_id: uuid.UUID
) -> tuple[Statement, StatementResult]:
    contracts = await _own_contracts(session, account)
    if contract_id not in contracts:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    for st, res in await _rows(session, {contract_id}):
        if st.id == statement_id:
            return st, res
    raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


@router.get(
    "",
    summary="Ausgegebene Betriebs- und Heizkostenabrechnungen der eigenen Mietverträge",
    dependencies=[Depends(strict_query)],
)
async def list_tenant_statements(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        if not (await portal_features.get_or_default(session)).tenant_statement_enabled:
            return {"items": [], "available": False, "note": DISABLED_NOTE}
        if not await _gate_open(request, principal.tenant_id):
            return {"items": [], "available": False, "note": GATE_NOTE}
        items = []
        for st, res in await _rows(session, await _own_contracts(session, account)):
            snapshot = (
                await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
            )
            items.append(_summary(st, res, _result_of(snapshot, res.contract_id)))
        return {"items": items, "available": True, "note": NOTE}


@router.get(
    "/{statement_id}/contracts/{contract_id}",
    summary="Abrechnung eines eigenen Mietvertrags mit Erläuterungen",
)
async def get_tenant_statement(
    statement_id: uuid.UUID,
    contract_id: uuid.UUID,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _ensure_enabled(request, session, principal.tenant_id)
        st, res = await _own(session, account, statement_id, contract_id)
        snapshot = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
        row = _result_of(snapshot, contract_id)
        own_key = f"contract:{contract_id}"
        positions = []
        for p in ((snapshot.inputs if snapshot else {}) or {}).get("positions", []):
            share = (p.get("split") or {}).get(own_key)
            if share is None:
                continue
            positions.append(
                {
                    "label": p.get("label"),
                    "basis": p.get("basis"),
                    "allocation_key": (p.get("allocation_key") or {}).get("name")
                    if isinstance(p.get("allocation_key"), dict)
                    else None,
                    "amount_total": p.get("amount"),
                    "own_share": str(Decimal(str(share))),
                }
            )
        texts = await approved_texts(session, tuple(TEXT_CODES.values()))
        explanations = {
            topic: {
                "code": code,
                "released": code in texts,
                "text": texts.get(code, PLACEHOLDER),
            }
            for topic, code in TEXT_CODES.items()
        }
        receipt: dict[str, Any] | None = None
        if res.document_id is not None:
            await read_receipts.record(session, account, res.document_id, "opened")
            state = (
                await read_receipts.states_for_account(session, account, {res.document_id})
            ).get(res.document_id)
            receipt = {"first": state["first"], "last": state["last"]} if state else None
        return {
            **_summary(st, res, row),
            "positions": positions,
            "explanations": explanations,
            "delivered_at": res.delivered_at,
            "read_receipt": receipt,
            "receipt_note": read_receipts.LEGAL_NOTE,
            "note": NOTE,
        }


@router.get(
    "/{statement_id}/contracts/{contract_id}/pdf",
    summary="Abrechnung eines eigenen Mietvertrags als PDF",
)
async def tenant_statement_pdf(
    statement_id: uuid.UUID,
    contract_id: uuid.UUID,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> Response:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _ensure_enabled(request, session, principal.tenant_id)
        st, res = await _own(session, account, statement_id, contract_id)
        document = await session.get(Document, res.document_id) if res.document_id else None
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        await read_receipts.record(session, account, document.id, "downloaded")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="statement.portal_download",
            entity_type="statement",
            entity_id=st.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(account.id), "contract_id": str(contract_id)},
        )
        period: date = st.period_to
        return Response(
            content=data,
            media_type=document.mime_type or "application/pdf",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", f"Betriebskostenabrechnung-{period.year}.pdf"
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
