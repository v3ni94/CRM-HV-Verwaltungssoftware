"""Rental statement: draft editing, results per contract, access, difference report, result
entries and Belegeinsicht (/api/v1/statements, M17-01 to M17-08).

Editing is allowed in ``draft`` only; after ``calculated`` a change needs a new version
(6.9.3). Result entries are drafts and need G3 (M17-01); nothing here posts or sends.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import letters as tenant_letters
from mhvp.billing import results
from mhvp.billing.models import (
    Statement,
    StatementCostItem,
    StatementInspection,
    StatementResult,
    StatementSnapshot,
)
from mhvp.billing.routers import StatementSettingsIn, check_period
from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.workspace.services import local_date

# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
router = APIRouter(
    tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)  # included by mhvp.billing.routers (prefix)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")

DELIVERY_OPEN = frozenset(
    {
        StatementStatus.INTERNALLY_APPROVED,
        StatementStatus.BOARD_REVIEWED,
        StatementStatus.ISSUED,
        StatementStatus.DUE,
    }
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatementPatchIn(_In):
    period_from: date | None = None
    period_to: date | None = None
    interim: bool | None = None
    purpose: str | None = Field(default=None, min_length=3, max_length=2000)
    include_heating: bool | None = None
    settings: StatementSettingsIn | None = None
    deadline_exception: str | None = Field(default=None, min_length=3, max_length=2000)


class StatementCostItemUpdateIn(_In):
    label: str = Field(min_length=1, max_length=200)
    account_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    allocation_key_id: uuid.UUID | None = None
    external_amounts: dict[str, Decimal] = Field(default_factory=dict)
    basis: str = Field(min_length=3, max_length=2000)
    heating: bool = False


class StatementDeliveryIn(_In):
    delivery_method: Literal["post", "registered_mail", "hand_delivery", "email", "portal"]
    delivered_at: date
    evidence: str = Field(min_length=3, max_length=2000)
    evidence_document_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class StatementResultEntriesIn(_In):
    booking_date: date
    due_date: date


class StatementInspectionIn(_In):
    contract_id: uuid.UUID
    requested_at: date
    channel: Literal["letter", "email", "phone", "portal", "in_person"]
    scope: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)


class StatementInspectionPatchIn(_In):
    provision: Literal["electronic", "copies", "appointment"] | None = None
    provided_at: date | None = None
    document_ids: list[uuid.UUID] | None = None
    redaction_note: str | None = Field(default=None, max_length=2000)
    objection_received_at: date | None = None
    objection_text: str | None = Field(default=None, max_length=8000)
    close: bool = False
    note: str | None = Field(default=None, max_length=2000)


async def _statement(session: AsyncSession, statement_id: uuid.UUID) -> Statement:
    row = await session.get(Statement, statement_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


def _draft_only(st: Statement) -> None:
    if st.status is not StatementStatus.DRAFT:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über eine neue Version änderbar."
        )


async def _snapshot(session: AsyncSession, st: Statement) -> StatementSnapshot:
    snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
    if snap is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Ergebnis-Snapshot.")
    return snap


async def _document_exists(session: AsyncSession, document_id: uuid.UUID | None) -> None:
    from mhvp.documents.models import Document

    if document_id is not None and await session.get(Document, document_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument nicht gefunden.")


@router.patch("/{statement_id}", summary="Kopfdaten des Entwurfs ändern (Zeitraum, Zweck, Texte)")
async def patch_statement(
    statement_id: uuid.UUID,
    body: StatementPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.billing.routers import _out

    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        _draft_only(st)
        data = body.model_dump(exclude_unset=True)
        for field in ("period_from", "period_to", "interim", "include_heating"):
            if data.get(field) is not None:
                setattr(st, field, data[field])
        if "purpose" in data:
            st.purpose = data["purpose"]
        if "deadline_exception" in data:
            st.deadline_exception = data["deadline_exception"]
        if body.settings is not None:
            st.settings = {**st.settings, **body.settings.model_dump(exclude_none=True)}
        check_period(st.period_from, st.period_to, st.interim, st.purpose)
        await session.flush()
        return await _out(session, st)


async def _item(
    session: AsyncSession, statement_id: uuid.UUID, item_id: uuid.UUID
) -> tuple[Statement, StatementCostItem]:
    st = await _statement(session, statement_id)
    item = await session.get(StatementCostItem, item_id)
    if item is None or item.statement_id != st.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    _draft_only(st)
    return st, item


@router.put("/{statement_id}/cost-items/{item_id}", summary="Kostenposition im Entwurf ändern")
async def update_item(
    statement_id: uuid.UUID,
    item_id: uuid.UUID,
    body: StatementCostItemUpdateIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        _, item = await _item(session, statement_id, item_id)
        for field, value in body.model_dump(exclude={"external_amounts"}).items():
            setattr(item, field, value)
        item.external_amounts = {k: str(v) for k, v in body.external_amounts.items()}
        item.updated_by = principal.user_id
        await session.flush()
        return {"id": item.id}


@router.delete(
    "/{statement_id}/cost-items/{item_id}",
    status_code=204,
    summary="Kostenposition im Entwurf entfernen",
)
async def delete_item(
    statement_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        _, item = await _item(session, statement_id, item_id)
        await session.delete(item)
        await session.flush()
    return Response(status_code=204)


def _result_out(
    row: dict[str, Any], stored: StatementResult | None, snap: StatementSnapshot
) -> dict[str, Any]:
    delivered = stored.delivered_at if stored else None
    return {
        **row,
        "lines": tenant_letters.tenant_lines(snap, row["contract_id"]),
        "document_id": stored.document_id if stored else None,
        "delivery_method": stored.delivery_method if stored else None,
        "delivered_at": delivered,
        "evidence": stored.evidence if stored else None,
        "evidence_document_id": stored.evidence_document_id if stored else None,
        "objection_deadline_orientation": results.objection_deadline_orientation(delivered),
    }


@router.get("/{statement_id}/results", summary="Ergebnis je Vertrag mit Aufstellung und Zugang")
async def list_results(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        snap = await _snapshot(session, st)
        stored = await results.result_rows(session, st)
        return [
            _result_out(r, stored.get(str(r["contract_id"])), snap)
            for r in results.snapshot_rows(snap)
        ]


@router.put(
    "/{statement_id}/results/{contract_id}/delivery",
    summary="Zugang je Mieter erfassen (Versandart, Datum, Nachweis)",
)
async def put_delivery(
    statement_id: uuid.UUID,
    contract_id: uuid.UUID,
    body: StatementDeliveryIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        snap = await _snapshot(session, st)
        if st.status not in DELIVERY_OPEN:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Zugang erst nach interner Freigabe und vor der Ergebnisbuchung.",
            )
        row = next(
            (r for r in results.snapshot_rows(snap) if str(r["contract_id"]) == str(contract_id)),
            None,
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht im Ergebnis.")
        if body.delivered_at < local_date(snap.created_at):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Zugang liegt vor der Berechnung; die Erstellung gilt nicht als Zugang.",
            )
        await _document_exists(session, body.evidence_document_id)
        await _document_exists(session, body.document_id)
        stored = (await results.result_rows(session, st)).get(str(contract_id))
        if stored is None:
            stored = StatementResult(
                tenant_id=st.tenant_id,
                statement_id=st.id,
                contract_id=contract_id,
                created_by=principal.user_id,
            )
            session.add(stored)
        stored.delivery_method = body.delivery_method
        stored.delivered_at = body.delivered_at
        stored.evidence = body.evidence
        stored.evidence_document_id = body.evidence_document_id
        if body.document_id is not None:
            stored.document_id = body.document_id
        stored.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="statement.delivery_recorded",
            entity_type="statement",
            entity_id=st.id,
            actor_user_id=principal.user_id,
            payload={"contract_id": str(contract_id), "method": body.delivery_method},
        )
        return _result_out(row, stored, snap)


@router.get("/{statement_id}/diff", summary="Differenzbericht zur ersetzten Version")
async def get_diff(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.supersedes_id is None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Keine Vorversion vorhanden.")
        old = await session.get(Statement, st.supersedes_id)
        old_snap = (
            await session.get(StatementSnapshot, old.snapshot_id)
            if old and old.snapshot_id
            else None
        )
        new_snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
        if new_snap is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Die neue Version ist noch nicht berechnet."
            )
        return {
            "statement_id": st.id,
            "supersedes_id": st.supersedes_id,
            "version": st.version,
            **results.diff(old_snap, new_snap),
        }


@router.post(
    "/{statement_id}/result-entries",
    status_code=201,
    summary="Ergebnisbuchungen als Entwurf erzeugen (Forderung/Gutschrift, G3)",
)
async def create_result_entries(
    statement_id: uuid.UUID,
    body: StatementResultEntriesIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    await ensure_release_gate_open(
        ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.status is not StatementStatus.DUE:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Ergebnisbuchung erst im Status fällig (6.9.3)."
            )
        snap = await _snapshot(session, st)
        ids = await results.create_result_drafts(
            session,
            st,
            snap,
            booking_date=body.booking_date,
            due_date=body.due_date,
            user_id=principal.user_id,
        )
        return {"statement_id": st.id, "entry_ids": ids, "status": "draft"}


def _inspection_out(row: StatementInspection) -> dict[str, Any]:
    return {
        "id": row.id,
        "statement_id": row.statement_id,
        "contract_id": row.contract_id,
        "requested_at": row.requested_at,
        "channel": row.channel,
        "scope": row.scope,
        "status": row.status,
        "provision": row.provision,
        "provided_at": row.provided_at,
        "document_ids": row.document_ids,
        "redaction_note": row.redaction_note,
        "objection_received_at": row.objection_received_at,
        "objection_text": row.objection_text,
        "note": row.note,
    }


@router.get("/{statement_id}/inspections", summary="Belegeinsicht: Anfragen der Mieter")
async def list_inspections(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        rows = (
            await session.scalars(
                select(StatementInspection)
                .where(StatementInspection.statement_id == st.id)
                .order_by(StatementInspection.requested_at, StatementInspection.created_at)
            )
        ).all()
        return [_inspection_out(r) for r in rows]


@router.post(
    "/{statement_id}/inspections", status_code=201, summary="Belegeinsicht: Anfrage erfassen"
)
async def create_inspection(
    statement_id: uuid.UUID,
    body: StatementInspectionIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        snap = await _snapshot(session, st)
        if str(body.contract_id) not in {
            str(r["contract_id"]) for r in results.snapshot_rows(snap)
        }:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht im Ergebnis.")
        row = StatementInspection(
            tenant_id=st.tenant_id,
            statement_id=st.id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return _inspection_out(row)


@router.patch(
    "/{statement_id}/inspections/{inspection_id}",
    summary="Belegeinsicht: Bereitstellung, Schwärzung, Einwendung, Abschluss",
)
async def patch_inspection(
    statement_id: uuid.UUID,
    inspection_id: uuid.UUID,
    body: StatementInspectionPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        row = await session.get(StatementInspection, inspection_id, with_for_update=True)
        if row is None or row.statement_id != st.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status == "closed":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Anfrage ist abgeschlossen.")
        if body.provision is not None or body.provided_at is not None:
            if body.provision is None or body.provided_at is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Art und Datum der Bereitstellung angeben."
                )
            if body.provided_at < row.requested_at:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Bereitstellung vor der Anfrage.")
            row.provision, row.provided_at, row.status = (
                body.provision,
                body.provided_at,
                "provided",
            )
        if body.document_ids is not None:
            for document_id in body.document_ids:
                await _document_exists(session, document_id)
            row.document_ids = [str(d) for d in body.document_ids]
        if body.redaction_note is not None:
            row.redaction_note = body.redaction_note
        if body.objection_received_at is not None:
            if not body.objection_text:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Inhalt der Einwendung fehlt.")
            row.objection_received_at = body.objection_received_at
            row.objection_text = body.objection_text
        if body.note is not None:
            row.note = body.note
        if body.close:
            if row.status != "provided":
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Abschluss erst nach der Bereitstellung."
                )
            row.status = "closed"
        row.updated_by = principal.user_id
        await session.flush()
        return _inspection_out(row)
