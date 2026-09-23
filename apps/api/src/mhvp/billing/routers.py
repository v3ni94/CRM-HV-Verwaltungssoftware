"""Operating cost statements (/api/v1/statements, M17). Issuing a statement requires G3."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc, services
from mhvp.billing.models import (
    Statement,
    StatementCostItem,
    StatementEvent,
    StatementKind,
    StatementSnapshot,
)
from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/statements", tags=["Abrechnung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatementIn(_In):
    ledger_id: uuid.UUID
    period_from: date
    period_to: date


class CostItemIn(_In):
    label: str = Field(min_length=1, max_length=200)
    account_id: uuid.UUID | None = None
    amount: Decimal = Field(gt=0)
    allocation_key_id: uuid.UUID | None = None
    external_amounts: dict[str, Decimal] = Field(default_factory=dict)
    basis: str = Field(min_length=3, max_length=2000)
    heating: bool = False


class TransitionIn(_In):
    target: StatementStatus
    note: str | None = Field(default=None, max_length=2000)
    delivered_at: date | None = None


class Co2In(_In):
    specific_emissions: Decimal
    costs: Decimal


async def _statement(session: AsyncSession, statement_id: uuid.UUID) -> Statement:
    row = await session.get(Statement, statement_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _out(session: AsyncSession, st: Statement) -> dict[str, Any]:
    snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
    return {
        "id": st.id,
        "kind": st.kind.value,
        "ledger_id": st.ledger_id,
        "property_id": st.property_id,
        "period_from": st.period_from,
        "period_to": st.period_to,
        "status": st.status.value,
        "version": st.version,
        "supersedes_id": st.supersedes_id,
        "delivered_at": st.delivered_at,
        "deadline_orientation": calc.deadline(st.period_to),
        "snapshot": {
            "id": snap.id,
            "hash": snap.hash,
            "rule_version": snap.rule_version,
            **snap.results,
        }
        if snap
        else None,
    }


@router.post("", status_code=201, summary="Betriebskostenabrechnung anlegen (Entwurf)")
async def create(
    body: StatementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    if body.period_to < body.period_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
    async with tenant_tx(request, principal) as session:
        ledger = await session.get(Ledger, body.ledger_id)
        entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
        if ledger is None or entity is None or ledger.property_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if entity.kind not in (LegalEntityKind.RENTAL_OWNER, LegalEntityKind.SEV_OWNER):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Betriebskostenabrechnungen nur im Buchungskreis des Vermieters.",
            )
        st = Statement(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            kind=StatementKind.OPERATING_COSTS,
            ledger_id=ledger.id,
            property_id=ledger.property_id,
            period_from=body.period_from,
            period_to=body.period_to,
        )
        session.add(st)
        await session.flush()
        return await _out(session, st)


@router.post(
    "/{statement_id}/cost-items", status_code=201, summary="Kostenposition mit Grundlage erfassen"
)
async def add_item(
    statement_id: uuid.UUID,
    body: CostItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Nach der Berechnung nur über eine neue Version änderbar.",
            )
        item = StatementCostItem(
            tenant_id=principal.tenant_id,
            statement_id=st.id,
            **body.model_dump(exclude={"external_amounts"}),
            external_amounts={k: str(v) for k, v in body.external_amounts.items()},
        )
        session.add(item)
        await session.flush()
        return {"id": item.id}


@router.get("/{statement_id}/occupants", summary="Nutzer und Leerstand im Zeitraum")
async def list_occupants(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        return await services.occupants(session, st)


@router.post("/{statement_id}/calculate", summary="Berechnen (Ergebnis-Snapshot)")
async def calculate(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Bereits berechnet: Änderungen über neue Version."
            )
        snap = await services.calculate(session, st, principal.user_id, local_today())
        await _transition(session, st, StatementStatus.CALCULATED, principal, None)
        st.snapshot_id = snap.id
        await session.flush()
        return await _out(session, st)


async def _transition(
    session: AsyncSession,
    st: Statement,
    target: StatementStatus,
    principal: TenantPrincipal,
    note: str | None,
) -> None:
    try:
        check_transition(st.status, target, is_hoa=False)
    except TransitionError as exc:
        raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from None
    session.add(
        StatementEvent(
            tenant_id=st.tenant_id,
            statement_id=st.id,
            from_status=st.status.value,
            to_status=target.value,
            user_id=principal.user_id,
            note=note,
        )
    )
    st.status = target


@router.post("/{statement_id}/transition", summary="Statuswechsel (6.9.3); Ausgabe nur mit G3")
async def transition(
    statement_id: uuid.UUID,
    body: TransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if body.target is StatementStatus.ISSUED:
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if (
            body.target is StatementStatus.INTERNALLY_APPROVED
            and st.created_by == principal.user_id
        ):
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die interne Freigabe muss eine andere Person erteilen.",
            )
        if body.target is StatementStatus.ISSUED:
            if body.delivered_at is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Zugangsdatum fehlt (Fristwahrung durch Zugang)."
                )
            snap = await session.get(StatementSnapshot, st.snapshot_id)
            if snap and any(r["late_claim_blocked"] for r in snap.results["results"]):
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Nachforderung nach Fristablauf ohne geprüfte Ausnahme.",
                )
            st.delivered_at = body.delivered_at
        await _transition(session, st, body.target, principal, body.note)
        await session.flush()
        return await _out(session, st)


@router.post("/{statement_id}/new-version", status_code=201, summary="Neue Version mit Bezug")
async def new_version(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        old = await _statement(session, statement_id)
        if old.status is StatementStatus.DRAFT:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ein Entwurf wird direkt bearbeitet.")
        new = Statement(
            tenant_id=old.tenant_id,
            created_by=principal.user_id,
            kind=old.kind,
            ledger_id=old.ledger_id,
            property_id=old.property_id,
            period_from=old.period_from,
            period_to=old.period_to,
            version=old.version + 1,
            supersedes_id=old.id,
        )
        session.add(new)
        await session.flush()
        for item in (
            await session.scalars(
                select(StatementCostItem).where(StatementCostItem.statement_id == old.id)
            )
        ).all():
            session.add(
                StatementCostItem(
                    tenant_id=old.tenant_id,
                    statement_id=new.id,
                    label=item.label,
                    account_id=item.account_id,
                    amount=item.amount,
                    allocation_key_id=item.allocation_key_id,
                    external_amounts=item.external_amounts,
                    basis=item.basis,
                    heating=item.heating,
                )
            )
        await session.flush()
        return await _out(session, new)


@router.get("/{statement_id}", summary="Abrechnung mit Ergebnis")
async def get(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        items = (
            await session.scalars(
                select(StatementCostItem)
                .where(StatementCostItem.statement_id == st.id)
                .order_by(StatementCostItem.created_at)
            )
        ).all()
        return await _out(session, st) | {
            "cost_items": [
                {
                    "id": i.id,
                    "label": i.label,
                    "amount": i.amount,
                    "basis": i.basis,
                    "heating": i.heating,
                    "allocation_key_id": i.allocation_key_id,
                }
                for i in items
            ]
        }


@router.get("", summary="Betriebskostenabrechnungen")
async def list_statements(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Statement).order_by(Statement.period_to.desc(), Statement.version.desc())
        if ledger_id is not None:
            query = query.where(Statement.ledger_id == ledger_id)
        rows = (await session.scalars(query.limit(200))).all()
        return [
            {
                "id": r.id,
                "ledger_id": r.ledger_id,
                "property_id": r.property_id,
                "period_from": r.period_from,
                "period_to": r.period_to,
                "status": r.status.value,
                "version": r.version,
            }
            for r in rows
        ]


@router.post("/co2-split", summary="CO₂-Kostenaufteilung Wohngebäude (Stufentabelle)")
async def co2(body: Co2In, principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    try:
        result = calc.co2_split(body.specific_emissions, body.costs)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    return {
        **result,
        "rule_version": calc.CO2_RULE_VERSION,
        "note": "Anwendbarkeit und Eingangswerte je Gebäude prüfen (H04).",
    }
