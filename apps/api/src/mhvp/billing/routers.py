"""Operating cost statements (/api/v1/statements, M17). Issuing a statement requires G3."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc, results, services
from mhvp.billing.models import (
    Statement,
    StatementCostItem,
    StatementEvent,
    StatementKind,
    StatementSnapshot,
)
from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard, session_allowed_property_ids
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.workspace.services import local_today

# M2-02/S16-02: statements outside the membership's property assignment answer 404.
STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)
# Issuing, due, result posting and period lock of a rental statement stay behind G3 (M17-01).
RESULT_GATED = frozenset(
    {
        StatementStatus.ISSUED,
        StatementStatus.DUE,
        StatementStatus.POSTED,
        StatementStatus.LOCKED,
    }
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatementSettingsIn(_In):
    """Letter settings (6.5 settings JSONB, A07): texts, format, bundled output."""

    text_credit: str | None = Field(default=None, max_length=4000)
    text_additional_payment: str | None = Field(default=None, max_length=4000)
    format: str | None = Field(default=None, pattern="^(pdf_single|pdf_bundle)$")
    bundled: bool | None = None


class StatementIn(_In):
    ledger_id: uuid.UUID
    period_from: date
    period_to: date
    # M17-04 (A05): unterjährige Abrechnung only with a stated purpose.
    interim: bool = False
    purpose: str | None = Field(default=None, min_length=3, max_length=2000)
    include_heating: bool = True
    settings: StatementSettingsIn | None = None


def check_period(period_from: date, period_to: date, interim: bool, purpose: str | None) -> None:
    """A period other than twelve months needs ``interim`` and a purpose (A05, M17-04)."""
    if period_to < period_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
    twelve = (period_to - period_from).days + 1 in (365, 366) and (
        period_from.day == 1 and (period_to.month - period_from.month) % 12 == 11
    )
    if (interim or not twelve) and not purpose:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Unterjährige Abrechnung oder Sonderzeitraum nur mit ausgewiesenem Zweck (A05)."
            ),
        )
    if not twelve and not interim:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Zeitraum umfasst keine zwölf Monate: als unterjährig kennzeichnen (A05).",
        )


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
        "interim": st.interim,
        "purpose": st.purpose,
        "include_heating": st.include_heating,
        "settings": st.settings,
        "deadline_exception": st.deadline_exception,
        "deadline_exception_document_id": st.deadline_exception_document_id,
        "deadline_exception_set_by": st.deadline_exception_set_by,
        "deadline_exception_set_at": st.deadline_exception_set_at,
        "deadline_exception_effective": st.deadline_exception_effective,
        "result_entry_ids": st.result_entry_ids,
        "locked_at": st.locked_at,
        "deadline_orientation": calc.deadline(st.period_to),
        "snapshot": {
            "id": snap.id,
            "hash": snap.hash,
            "rule_version": snap.rule_version,
            "rule_register": snap.inputs.get("rule_register"),
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

    check_period(body.period_from, body.period_to, body.interim, body.purpose)
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
            interim=body.interim,
            purpose=body.purpose,
            include_heating=body.include_heating,
            settings=body.settings.model_dump(exclude_none=True) if body.settings else {},
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


@router.get(
    "/{statement_id}/occupants",
    summary="Nutzer und Leerstand im Zeitraum",
    dependencies=[Depends(strict_query)],
)
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
    if body.target in RESULT_GATED:
        await ensure_release_gate_open(
            ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
        )
    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        if body.target in (StatementStatus.ISSUED, StatementStatus.DUE, StatementStatus.POSTED):
            from mhvp.billing import allocation_basis

            await allocation_basis.ensure_complete(session, st)
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
            if snap is None:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Ergebnis-Snapshot.")
            from mhvp.billing import deadline as deadline_policy

            services.check_issue(
                st,
                snap,
                body.delivered_at,
                await deadline_policy.policy(session, principal.tenant_id),
            )
            st.delivered_at = body.delivered_at
        if body.target is StatementStatus.POSTED:
            await results.check_result_entries_posted(session, st)
        if body.target is StatementStatus.LOCKED:
            st.locked_at = datetime.now(UTC)
        await _transition(session, st, body.target, principal, body.note)
        if body.target is StatementStatus.ISSUED:
            # Q12 webhook statement.confirmed: a rental statement counts as confirmed when it
            # is issued (A-R07-01, docs/ASSUMPTIONS.md); the issue itself stays behind G3.
            from mhvp.core.events import emit

            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="statement.confirmed",
                entity_type="statement",
                entity_id=st.id,
                actor_user_id=principal.user_id,
                payload={"kind": "rental", "status": body.target.value},
            )
        lock_info: dict[str, Any] = {}
        if body.target is StatementStatus.LOCKED:
            from mhvp.accounting import period_lock

            lock_info = await period_lock.lock_for_closed_statement(
                session,
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                source="statement",
                statement_id=st.id,
                ledger_id=st.ledger_id,
                property_id=st.property_id,
                period_from=st.period_from,
                period_to=st.period_to,
            )
        await session.flush()
        return {**await _out(session, st), **lock_info}


@router.get("/{statement_id}/period-lock", summary="Periodensperre der Abrechnung (P06-02)")
async def statement_period_lock(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from sqlalchemy import select

    from mhvp.accounting import period_lock
    from mhvp.accounting.models import PeriodLock

    async with tenant_tx(request, principal) as session:
        st = await _statement(session, statement_id)
        rows = (
            await session.scalars(
                select(PeriodLock).where(
                    PeriodLock.statement_id == st.id, PeriodLock.source == "statement"
                )
            )
        ).all()
        setting = period_lock.setting_out(await period_lock.get_setting(session))
        return {
            "locks": [period_lock.to_out(r).model_dump(mode="json") for r in rows],
            "auto_lock_on_close": setting.auto_lock_on_close,
            "lock_mode": setting.lock_mode,
        }


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
            interim=old.interim,
            purpose=old.purpose,
            include_heating=old.include_heating,
            settings=old.settings,
            deadline_exception=old.deadline_exception,
            deadline_exception_document_id=old.deadline_exception_document_id,
            deadline_exception_set_by=old.deadline_exception_set_by,
            deadline_exception_set_at=old.deadline_exception_set_at,
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
                    "account_id": i.account_id,
                    "external_amounts": i.external_amounts,
                }
                for i in items
            ]
        }


@router.get("", summary="Betriebskostenabrechnungen", dependencies=[Depends(strict_query)])
async def list_statements(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Statement).order_by(Statement.period_to.desc(), Statement.version.desc())
        if ledger_id is not None:
            query = query.where(Statement.ledger_id == ledger_id)
        allowed = session_allowed_property_ids(session)  # M2-02/S16-02
        if allowed is not None:
            query = query.where(Statement.property_id.in_(allowed))
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
