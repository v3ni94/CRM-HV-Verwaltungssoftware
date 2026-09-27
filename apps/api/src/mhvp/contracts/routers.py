"""Contract endpoints (/api/v1/contracts, /sepa-mandates, /deposits, occupancy)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.contacts.models import ContactBankAccount, Party, PartyMember
from mhvp.contacts.services import approval_block_reason, recompute_for_party
from mhvp.contacts.validation import mask_iban
from mhvp.contracts import schemas as s
from mhvp.contracts import services as svc
from mhvp.contracts.models import (
    Contract,
    ContractAllocationValue,
    ContractKind,
    ContractPayment,
    ContractTerminationReading,
    DebtorAccountReservation,
    Deposit,
    DepositMovement,
    MandateStatus,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import AllocationKey, ManagementType, Property, Unit
from mhvp.properties.services import check_catalog

router = APIRouter(tags=["Verträge"])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
# Management approval of imported contracts (tenant_admin and administrator only).
APPROVE = require_permission("contracts:approve")


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise _nf()
    return row


async def _flush(session: Any, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ProblemError(ErrorCodes.CONFLICT, detail=message) from None


async def _out(session: Any, contract: Contract) -> s.ContractOut:
    await session.flush()
    await session.refresh(contract)
    return (await _outs(session, [contract]))[0]


async def _outs(session: Any, contracts: Sequence[Contract]) -> list[s.ContractOut]:
    """Output of several contracts with three batched queries (debtor accounts, payments,
    schedules) instead of three per row (performance review 26.09.2026)."""
    if not contracts:
        return []
    ids = [c.id for c in contracts]
    accounts = {
        a.id: a
        for a in (
            await session.scalars(
                select(DebtorAccountReservation).where(
                    DebtorAccountReservation.id.in_({c.debtor_account_id for c in contracts})
                )
            )
        ).all()
    }
    payments: dict[uuid.UUID, list[ContractPayment]] = {}
    for p in (
        await session.scalars(
            select(ContractPayment)
            .where(ContractPayment.contract_id.in_(ids))
            .order_by(ContractPayment.payment_type_code, ContractPayment.valid_from)
        )
    ).all():
        payments.setdefault(p.contract_id, []).append(p)
    schedules: dict[uuid.UUID, list[PaymentSchedule]] = {}
    for x in (
        await session.scalars(
            select(PaymentSchedule)
            .where(PaymentSchedule.contract_id.in_(ids))
            .order_by(PaymentSchedule.valid_from)
        )
    ).all():
        schedules.setdefault(x.contract_id, []).append(x)
    out = []
    for contract in contracts:
        data = {c.key: getattr(contract, c.key) for c in Contract.__table__.columns}
        out.append(
            s.ContractOut.model_validate(
                {
                    **data,
                    "debtor_account": s.DebtorAccountOut.model_validate(
                        accounts[contract.debtor_account_id]
                    ),
                    "payments": [
                        s.PaymentOut.model_validate(p) for p in payments.get(contract.id, [])
                    ],
                    "schedules": [
                        s.ScheduleOut.model_validate(x) for x in schedules.get(contract.id, [])
                    ],
                }
            )
        )
    return out


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type=type_.split(".")[0],
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={k: str(v) if v is not None else None for k, v in payload.items()},
    )


async def _create(
    session: Any,
    principal: TenantPrincipal,
    body: s.ContractIn,
    supersedes: uuid.UUID | None = None,
) -> Contract:
    unit = await _get(session, Unit, body.unit_id)
    prop = await _get(session, Property, unit.property_id)
    party = await _get(session, Party, body.party_id)
    creditor = await svc.creditor_entity(
        session, prop, unit, body.kind, body.start_date, body.legal_entity_id
    )
    await svc.check_mandate(session, body.sepa_mandate_id, body.direct_debit, party.id, creditor)
    if body.sev_enabled and prop.management_type is not ManagementType.HOA_WITH_SEV:
        raise svc.invalid("SEV ist nur in Objekten mit der Verwaltungsart WEG mit SEV möglich.")
    if body.sev_fee_debtor_party_id is not None:
        await _get(session, Party, body.sev_fee_debtor_party_id)
    account = await svc.debtor_account(session, principal.tenant_id, creditor, party, unit)
    data = body.model_dump(exclude={"legal_entity_id"})
    if body.sev_enabled and data["sev_fee_debtor_party_id"] is None:
        data["sev_fee_debtor_party_id"] = party.id
    contract = Contract(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        property_id=prop.id,
        legal_entity_id=creditor,
        debtor_account_id=account.id,
        number=await svc.contract_number(session, principal.tenant_id),
        supersedes_contract_id=supersedes,
        **data,
    )
    session.add(contract)
    await _flush(
        session,
        "Für die Einheit besteht im Zeitraum bereits ein Vertrag dieser Art "
        "(Mietverhältnis oder Eigentum).",
    )
    await recompute_for_party(session, party.id)
    return contract


# Contracts -----------------------------------------------------------------------------


@router.get("/contracts", summary="Verträge", responses=PAGE_HEADERS)
async def list_contracts(
    request: Request,
    response: Response,
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    party_id: uuid.UUID | None = None,
    kind: ContractKind | None = None,
    active_on: date | None = None,
    status: Literal["active", "ended", "upcoming"] | None = Query(
        default=None,
        description="Laufzeitstatus zum Stichtag as_of: active, ended (Ende vor dem Stichtag), "
        "upcoming (Beginn nach dem Stichtag)",
    ),
    as_of: date | None = Query(default=None, description="Stichtag für status, Standard heute"),
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.ContractOut]:
    """Verträge nach Nummer und Version. Paginierung wie ``GET /tickets``: die Antwort bleibt
    eine Liste, Gesamtzahl und Seite stehen in ``X-Total-Count``, ``X-Page``, ``X-Page-Size``.
    ``status=ended`` liefert beendete Verträge (Ende vor dem Stichtag)."""
    async with tenant_tx(request, principal) as session:
        query = select(Contract)
        if status is not None:
            day = as_of or datetime.now(UTC).date()
            if status == "ended":
                query = query.where(Contract.end_date.is_not(None), Contract.end_date < day)
            elif status == "upcoming":
                query = query.where(Contract.start_date > day)
            else:
                query = query.where(
                    Contract.start_date <= day,
                    or_(Contract.end_date.is_(None), Contract.end_date >= day),
                )
        for column, value in (
            (Contract.property_id, property_id),
            (Contract.unit_id, unit_id),
            (Contract.party_id, party_id),
            (Contract.kind, kind),
        ):
            if value is not None:
                query = query.where(column == value)
        if active_on is not None:
            query = query.where(
                Contract.start_date <= active_on,
                or_(Contract.end_date.is_(None), Contract.end_date >= active_on),
            )
        rows = await paginate(
            session,
            query.order_by(Contract.number, Contract.version),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        return await _outs(session, rows)


@router.post("/contracts", status_code=201, summary="Vertrag anlegen")
async def create_contract(
    body: s.ContractIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _create(session, principal, body)
        await _event(session, principal, "contract.created", contract.id, kind=body.kind.value)
        return await _out(session, contract)


# Approval of imported contracts (Betreiberauftrag 26.09.2026, migration 0133) --------------


async def _pending_out(session: Any, rows: Sequence[Contract]) -> list[s.PendingContractOut]:
    if not rows:
        return []
    props = {
        p.id: p
        for p in (
            await session.scalars(
                select(Property).where(Property.id.in_({c.property_id for c in rows}))
            )
        ).all()
    }
    units = {
        u.id: u
        for u in (
            await session.scalars(select(Unit).where(Unit.id.in_({c.unit_id for c in rows})))
        ).all()
    }
    parties = {
        p.id: p
        for p in (
            await session.scalars(select(Party).where(Party.id.in_({c.party_id for c in rows})))
        ).all()
    }
    amounts: dict[uuid.UUID, Decimal] = {}
    starts = {c.id: c.start_date for c in rows}
    for p in (
        await session.scalars(
            select(ContractPayment).where(ContractPayment.contract_id.in_(list(starts)))
        )
    ).all():
        start = starts[p.contract_id]
        if p.valid_from <= start and (p.valid_to is None or p.valid_to >= start):
            amounts[p.contract_id] = amounts.get(p.contract_id, Decimal("0.00")) + p.gross
    return [
        s.PendingContractOut(
            id=c.id,
            number=c.number,
            kind=c.kind,
            property_id=c.property_id,
            property_number=props[c.property_id].number,
            property_name=props[c.property_id].name,
            unit_id=c.unit_id,
            unit_number=units[c.unit_id].number,
            party_id=c.party_id,
            party_name=parties[c.party_id].name,
            start_date=c.start_date,
            monthly_amount=amounts.get(c.id, Decimal("0.00")),
            source=c.source,
            notes=c.notes,
        )
        for c in rows
    ]


@router.get(
    "/contracts/pending-approval",
    summary="Importverträge mit ausstehender Freigabe",
    responses=PAGE_HEADERS,
)
async def pending_approval(
    request: Request,
    response: Response,
    source: str | None = None,
    property_id: uuid.UUID | None = None,
    kind: ContractKind | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=5000),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.PendingContractOut]:
    """Verträge mit ``approval_status = pending``. Ihre Zahlungspläne erzeugen im
    Sollstellungslauf keine Forderungen, bis die Geschäftsführung sie freigibt."""
    async with tenant_tx(request, principal) as session:
        query = select(Contract).where(Contract.approval_status == "pending")
        for column, value in (
            (Contract.source, source),
            (Contract.property_id, property_id),
            (Contract.kind, kind),
        ):
            if value is not None:
                query = query.where(column == value)
        rows = await paginate(
            session,
            query.order_by(Contract.number, Contract.version),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        return await _pending_out(session, rows)


@router.post("/contracts/approve", summary="Importverträge freigeben")
async def approve_contracts(
    body: s.ApproveIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> s.ApproveOut:
    """Gibt ausstehende Verträge frei (``ids`` oder ``all`` mit optionaler ``source``). Jeder
    Vertrag erhält ``approved_by``/``approved_at`` und ein Ereignis ``contract.approved``.
    Bereits entschiedene Verträge werden übergangen (wiederholter Klick ohne Wirkung)."""
    async with tenant_tx(request, principal) as session:
        query = select(Contract).where(Contract.approval_status == "pending")
        if body.all:
            if body.source is not None:
                query = query.where(Contract.source == body.source)
        else:
            query = query.where(Contract.id.in_(body.ids))
        rows = (await session.scalars(query.order_by(Contract.number).with_for_update())).all()
        now = datetime.now(UTC)
        for contract in rows:
            contract.approval_status = "approved"
            contract.approved_by = principal.user_id
            contract.approved_at = now
            contract.updated_by = principal.user_id
            await _event(
                session,
                principal,
                "contract.approved",
                contract.id,
                source=contract.source,
                approved_by=principal.user_id,
                approved_at=now.isoformat(),
            )
        await session.flush()
        return s.ApproveOut(approved=len(rows), ids=[c.id for c in rows])


@router.post("/contracts/{contract_id}/reject-import", summary="Importvertrag ablehnen")
async def reject_import(
    contract_id: uuid.UUID,
    body: s.RejectImportIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.RejectImportOut:
    """Fehlzuordnung: beendet den ausstehenden Vertrag zum Beginn (``end_date = start_date``,
    Zahlungen und Zahlungspläne ebenso) und markiert ihn ``rejected``. Er erzeugt keine
    Sollstellung; die Einheit ist ab dem Folgetag für die richtige Zuordnung frei."""
    async with tenant_tx(request, principal) as session:
        contract = await session.get(Contract, contract_id, with_for_update=True)
        if contract is None:
            raise _nf()
        if contract.approval_status != "pending":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vertrag wartet nicht auf Freigabe.")
        await svc.end_contract(session, contract, contract.start_date)
        now = datetime.now(UTC)
        contract.approval_status = "rejected"
        contract.approved_by = principal.user_id
        contract.approved_at = now
        contract.termination_reason = body.reason or "Fehlzuordnung aus dem Import abgelehnt"
        contract.updated_by = principal.user_id
        await session.flush()
        await recompute_for_party(session, contract.party_id)
        await _event(
            session,
            principal,
            "contract.import_rejected",
            contract.id,
            source=contract.source,
            end_date=contract.end_date,
            reason=body.reason,
        )
        return s.RejectImportOut(
            id=contract.id, approval_status="rejected", end_date=contract.start_date
        )


@router.get("/contracts/{contract_id}", summary="Vertrag lesen")
async def get_contract(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        return await _out(session, await _get(session, Contract, contract_id))


@router.get("/contracts/{contract_id}/versions", summary="Vertragsversionen")
async def contract_versions(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ContractOut]:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(Contract)
                .where(Contract.number == contract.number)
                .order_by(Contract.version)
            )
        ).all()
        return await _outs(session, rows)


@router.post("/contracts/{contract_id}/versions", status_code=201, summary="Neue Vertragsversion")
async def new_version(
    contract_id: uuid.UUID,
    body: s.ContractVersionIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        old = await _get(session, Contract, contract_id)
        latest = await session.scalar(
            select(Contract.id).where(Contract.number == old.number, Contract.version > old.version)
        )
        if latest is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Es gibt bereits eine neuere Version.")
        if body.effective_date <= old.start_date or (
            old.end_date is not None and body.effective_date > old.end_date
        ):
            raise svc.invalid("Die neue Version muss innerhalb der Laufzeit nach Beginn starten.")
        changes = body.model_dump(exclude={"effective_date"}, exclude_unset=True)
        data = {
            c.key: getattr(old, c.key)
            for c in Contract.__table__.columns
            if c.key not in ("id", "created_at", "updated_at", "created_by", "updated_by")
        }
        data.update(changes)
        if data.get("dunning_block") and not data.get("dunning_block_reason"):
            raise svc.invalid("Mahnsperre braucht eine Begründung")
        await svc.check_mandate(
            session,
            data["sepa_mandate_id"],
            data["direct_debit"],
            old.party_id,
            old.legal_entity_id,
        )
        old_end = old.end_date
        old.end_date = body.effective_date - timedelta(days=1)
        await session.flush()
        data.update(
            start_date=body.effective_date,
            end_date=old_end,
            version=old.version + 1,
            supersedes_contract_id=old.id,
        )
        new = Contract(created_by=principal.user_id, **data)
        session.add(new)
        await _flush(session, "Die Version überschneidet sich mit einem anderen Vertrag.")
        await svc.move_open_rows(session, old, new, body.effective_date)
        await recompute_for_party(session, new.party_id)
        await _event(
            session,
            principal,
            "contract.versioned",
            new.id,
            previous=old.id,
            effective_date=body.effective_date,
        )
        return await _out(session, new)


@router.post("/contracts/{contract_id}/termination", summary="Vertrag beenden")
async def terminate(
    contract_id: uuid.UUID,
    body: s.TerminationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        if contract.kind is ContractKind.OWNERSHIP:
            raise svc.invalid("Eigentum endet nur durch Eigentümerwechsel.")
        await svc.end_contract(session, contract, body.end_date)
        contract.termination_date = body.termination_date
        contract.termination_reason = body.termination_reason
        if body.move_out_on is not None:
            contract.move_out_on = body.move_out_on
        contract.updated_by = principal.user_id
        readings = await svc.record_termination_readings(
            session,
            contract,
            [(r.meter_id, r.value, r.read_at) for r in body.meter_readings],
            principal.user_id,
        )
        await _event(
            session,
            principal,
            "contract.terminated",
            contract.id,
            end_date=body.end_date,
            move_out_on=body.move_out_on,
            meter_readings=len(readings),
        )
        return await _out(session, contract)


@router.get(
    "/contracts/{contract_id}/termination-readings",
    summary="Zählerstände zur Vertragsbeendigung",
)
async def termination_readings(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.TerminationReadingOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(ContractTerminationReading)
                .where(ContractTerminationReading.contract_id == contract_id)
                .order_by(ContractTerminationReading.read_at, ContractTerminationReading.id)
            )
        ).all()
        return [s.TerminationReadingOut.model_validate(r) for r in rows]


# Contract related allocation values (4.5 Eigenschaften) --------------------------------


async def _allocation_values_out(
    session: Any, rows: Sequence[ContractAllocationValue]
) -> list[s.ContractAllocationValueOut]:
    if not rows:
        return []
    keys = {
        k.id: k
        for k in (
            await session.scalars(
                select(AllocationKey).where(
                    AllocationKey.id.in_({r.allocation_key_id for r in rows})
                )
            )
        ).all()
    }
    out = []
    for r in rows:
        item = s.ContractAllocationValueOut.model_validate(r)
        key = keys.get(r.allocation_key_id)
        if key is not None:
            item.allocation_key_code = key.code
            item.allocation_key_name = key.name
            item.unit_of_measure = key.unit_of_measure
        out.append(item)
    return out


@router.get("/contracts/{contract_id}/allocation-values", summary="Umlagewerte des Vertrags")
async def list_allocation_values(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ContractAllocationValueOut]:
    """Vertragsbezogene Umlagewerte mit Zeitraum (z. B. Personen), alle Versionen der
    Vertragsnummer."""
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        ids = (
            await session.scalars(select(Contract.id).where(Contract.number == contract.number))
        ).all()
        rows = (
            await session.scalars(
                select(ContractAllocationValue)
                .where(ContractAllocationValue.contract_id.in_(ids))
                .order_by(
                    ContractAllocationValue.allocation_key_id, ContractAllocationValue.valid_from
                )
            )
        ).all()
        return await _allocation_values_out(session, rows)


@router.post(
    "/contracts/{contract_id}/allocation-values",
    status_code=201,
    summary="Umlagewert am Vertrag erfassen",
)
async def add_allocation_value(
    contract_id: uuid.UUID,
    body: s.ContractAllocationValueIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractAllocationValueOut:
    """Schließt einen offenen Vorwert desselben Schlüssels am Vortag; Zeiträume je Schlüssel
    überschneiden sich nie. Keine Buchung, keine Abrechnungswirkung außerhalb der Module."""
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        open_row = await session.scalar(
            select(ContractAllocationValue).where(
                ContractAllocationValue.contract_id == contract.id,
                ContractAllocationValue.allocation_key_id == body.allocation_key_id,
                ContractAllocationValue.valid_to.is_(None),
                ContractAllocationValue.valid_from < body.valid_from,
            )
        )
        if open_row is not None:
            open_row.valid_to = body.valid_from - timedelta(days=1)
            open_row.updated_by = principal.user_id
            await session.flush()
        row = await svc.add_allocation_value(
            session, contract, body.allocation_key_id, body.value, body.valid_from, body.valid_to
        )
        row.created_by = principal.user_id
        await _flush(session, "Der Umlagewert überschneidet sich mit einem bestehenden Wert.")
        await _event(
            session,
            principal,
            "contract.allocation_value_added",
            contract.id,
            allocation_key_id=body.allocation_key_id,
            value=body.value,
            valid_from=body.valid_from,
        )
        return (await _allocation_values_out(session, [row]))[0]


@router.post(
    "/contracts/{contract_id}/ownership-transfer", status_code=201, summary="Eigentümerwechsel"
)
async def ownership_transfer(
    contract_id: uuid.UUID,
    body: s.OwnershipTransferIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    """Ends the current ownership the day before the title transfer (D16, D17)."""
    async with tenant_tx(request, principal) as session:
        old = await _get(session, Contract, contract_id)
        if old.kind is not ContractKind.OWNERSHIP:
            raise svc.invalid("Nur Eigentumsverhältnisse können übertragen werden.")
        if old.end_date is not None:
            raise svc.invalid("Das Eigentumsverhältnis ist bereits beendet.")
        if body.new_party_id == old.party_id:
            raise svc.invalid("Der neue Eigentümer ist identisch mit dem bisherigen.")
        await svc.end_contract(session, old, body.title_transfer_date - timedelta(days=1))
        old.updated_by = principal.user_id
        new = await _create(
            session,
            principal,
            s.ContractIn(
                kind=ContractKind.OWNERSHIP,
                unit_id=old.unit_id,
                party_id=body.new_party_id,
                start_date=body.title_transfer_date,
                title_transfer_date=body.title_transfer_date,
                benefit_burden_date=body.benefit_burden_date,
                acquisition_kind=body.acquisition_kind,
                special_succession_liability=body.special_succession_liability,
                sev_enabled=body.sev_enabled,
            ),
        )
        await _event(
            session,
            principal,
            "contract.ownership_transferred",
            new.id,
            previous=old.id,
            title_transfer_date=body.title_transfer_date,
        )
        return await _out(session, new)


# Payments and schedules ----------------------------------------------------------------


@router.post("/contracts/{contract_id}/payments", status_code=201, summary="Sollstellung erfassen")
async def add_payment(
    contract_id: uuid.UUID,
    body: s.PaymentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PaymentOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        await check_catalog(session, "payment_type", body.payment_type_code)
        svc.check_amounts(body.payment_type_code, body.net, body.vat_percent, body.gross)
        row = ContractPayment(
            tenant_id=principal.tenant_id, contract_id=contract.id, **body.model_dump()
        )
        await svc.add_payment(session, contract, row)
        await _flush(session, "Die Zahlung überschneidet sich mit einer bestehenden Zahlung.")
        await _event(
            session,
            principal,
            "contract.payment_added",
            contract.id,
            payment_type=body.payment_type_code,
            gross=body.gross,
            valid_from=body.valid_from,
        )
        return s.PaymentOut.model_validate(row)


@router.get("/contracts/{contract_id}/payments", summary="Zahlungshistorie")
async def payment_history(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.PaymentOut]:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        ids = (
            await session.scalars(select(Contract.id).where(Contract.number == contract.number))
        ).all()
        rows = (
            await session.scalars(
                select(ContractPayment)
                .where(ContractPayment.contract_id.in_(ids))
                .order_by(ContractPayment.valid_from, ContractPayment.payment_type_code)
            )
        ).all()
        return [s.PaymentOut.model_validate(r) for r in rows]


@router.post("/contracts/{contract_id}/schedules", status_code=201, summary="Zahlungsplan")
async def add_schedule(
    contract_id: uuid.UUID,
    body: s.ScheduleIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ScheduleOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        row = PaymentSchedule(
            tenant_id=principal.tenant_id, contract_id=contract.id, **body.model_dump()
        )
        await svc.add_schedule(session, contract, row)
        await _flush(session, "Der Zahlungsplan überschneidet sich mit einem bestehenden.")
        return s.ScheduleOut.model_validate(row)


# SEPA mandates (recording only; collection stays locked until G2) ----------------------


async def _mandate_out(session: Any, mandate: SepaMandate) -> s.MandateOut:
    return (await _mandates_out(session, [mandate]))[0]


async def _mandates_out(session: Any, mandates: Sequence[SepaMandate]) -> list[s.MandateOut]:
    """One query for the bank accounts of all mandates (masked IBAN)."""
    if not mandates:
        return []
    accounts = {
        a.id: a
        for a in (
            await session.scalars(
                select(ContactBankAccount).where(
                    ContactBankAccount.id.in_({m.contact_bank_account_id for m in mandates})
                )
            )
        ).all()
    }
    out = []
    for mandate in mandates:
        row = s.MandateOut.model_validate(mandate)
        account = accounts.get(mandate.contact_bank_account_id)
        row.iban_masked = mask_iban(account.iban) if account is not None else None
        out.append(row)
    return out


@router.get("/sepa-mandates", summary="SEPA-Mandate", responses=PAGE_HEADERS)
async def list_mandates(
    request: Request,
    response: Response,
    party_id: uuid.UUID | None = None,
    status: MandateStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1, description="Seite (ab 1), zusammen mit page_size"),
    page_size: int | None = Query(
        default=None,
        ge=1,
        le=1000,
        description="Einträge je Seite; ohne Angabe gilt limit (erste Seite)",
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.MandateOut]:
    """Paginierung wie ``GET /tickets`` (Kopfzeilen ``X-Total-Count``, ``X-Page``,
    ``X-Page-Size``), Antwort bleibt eine Liste."""
    async with tenant_tx(request, principal) as session:
        query = select(SepaMandate)
        if party_id is not None:
            query = query.where(SepaMandate.party_id == party_id)
        if status is not None:
            query = query.where(SepaMandate.status == status)
        rows = await paginate(
            session,
            query.order_by(SepaMandate.signed_at, SepaMandate.id),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        return await _mandates_out(session, rows)


@router.post("/sepa-mandates", status_code=201, summary="SEPA-Mandat erfassen")
async def create_mandate(
    body: s.MandateIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.MandateOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Party, body.party_id)
        account = await _get(session, ContactBankAccount, body.contact_bank_account_id)
        member = await session.scalar(
            select(PartyMember.id).where(
                PartyMember.party_id == body.party_id, PartyMember.contact_id == account.contact_id
            )
        )
        if member is None:
            raise svc.invalid("Das Konto gehört keinem Beteiligten der Vertragspartei.")
        if (unreleased := approval_block_reason(account)) is not None:
            raise svc.invalid(f"{unreleased}: kein Mandat auf nicht freigegebener IBAN (M5-01).")
        await svc.check_b2b(session, body.party_id, body.type)
        if body.valid_until is not None and body.valid_until < body.signed_at:
            raise svc.invalid("Das Mandat endet vor der Unterschrift.")
        for code in body.payment_type_codes:
            await check_catalog(session, "payment_type", code)
        mandate = SepaMandate(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(mandate)
        await _flush(session, "Die Mandatsreferenz ist für diese Gläubiger-ID bereits vergeben.")
        await _event(
            session, principal, "sepa_mandate.created", mandate.id, reference=body.reference
        )
        return await _mandate_out(session, mandate)


@router.post("/sepa-mandates/{mandate_id}/revoke", summary="SEPA-Mandat widerrufen")
async def revoke_mandate(
    mandate_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> s.MandateOut:
    async with tenant_tx(request, principal) as session:
        mandate = await _get(session, SepaMandate, mandate_id)
        mandate.status = MandateStatus.REVOKED
        mandate.revoked_at = datetime.now(UTC)
        users = (
            await session.scalars(
                select(Contract).where(
                    Contract.sepa_mandate_id == mandate.id, Contract.direct_debit.is_(True)
                )
            )
        ).all()
        for c in users:  # direct debit stops; the contract is flagged, not rewritten
            c.direct_debit = False
        await _event(session, principal, "sepa_mandate.revoked", mandate.id, contracts=len(users))
        return await _mandate_out(session, mandate)


# Deposits ------------------------------------------------------------------------------


async def _deposit_out(session: Any, deposit: Deposit) -> s.DepositOut:
    await session.flush()
    await session.refresh(deposit)
    return (await _deposits_out(session, [deposit]))[0]


async def _deposits_out(session: Any, deposits: Sequence[Deposit]) -> list[s.DepositOut]:
    """Movements of all deposits in one query."""
    if not deposits:
        return []
    movements: dict[uuid.UUID, list[DepositMovement]] = {}
    for m in (
        await session.scalars(
            select(DepositMovement)
            .where(DepositMovement.deposit_id.in_([d.id for d in deposits]))
            .order_by(DepositMovement.date)
        )
    ).all():
        movements.setdefault(m.deposit_id, []).append(m)
    out = []
    for deposit in deposits:
        rows = movements.get(deposit.id, [])
        received, balance = svc.deposit_totals(deposit, rows)
        item = s.DepositOut.model_validate(deposit)
        item.received = received
        item.balance = balance
        item.outstanding = max(deposit.amount_due - received, Decimal("0.00"))
        item.movements = []
        for m in rows:
            row = s.DepositMovementOut.model_validate(m)
            row.review_required = m.posting_id is None  # not yet a ledger posting (M10, G1)
            item.movements.append(row)
        out.append(item)
    return out


@router.post("/contracts/{contract_id}/deposits", status_code=201, summary="Kaution erfassen")
async def create_deposit(
    contract_id: uuid.UUID,
    body: s.DepositIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.DepositOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        await svc.check_deposit_account(session, contract, body.property_bank_account_id)
        deposit = Deposit(
            tenant_id=principal.tenant_id, contract_id=contract.id, **body.model_dump()
        )
        session.add(deposit)
        await _event(session, principal, "deposit.created", contract.id, amount=body.amount_due)
        return await _deposit_out(session, deposit)


@router.get("/contracts/{contract_id}/deposits", summary="Kautionen")
async def list_deposits(
    contract_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.DepositOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Contract, contract_id)
        rows = (
            await session.scalars(
                select(Deposit).where(Deposit.contract_id == contract_id).order_by(Deposit.id)
            )
        ).all()
        return await _deposits_out(session, rows)


@router.get("/deposits", summary="Kautionsliste", responses=PAGE_HEADERS)
async def list_all_deposits(
    request: Request,
    response: Response,
    property_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, description="Kautionsstatus, z. B. open"),
    outstanding_only: bool = Query(default=False, description="Nur mit offenem Sollbetrag"),
    limit: int = Query(default=200, ge=1, le=1000),
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.DepositListRow]:
    """Kautionen über alle Verträge mit Objekt, Einheit, Partei, Sollbetrag, erhaltenem
    Betrag, Guthaben und offenem Betrag (Datensätze, keine Buchungen; M10, G1)."""
    async with tenant_tx(request, principal) as session:
        query = select(Deposit).join(Contract, Contract.id == Deposit.contract_id)
        if property_id is not None:
            query = query.where(Contract.property_id == property_id)
        if status is not None:
            query = query.where(Deposit.status == status)
        rows = await paginate(
            session,
            query.order_by(Contract.number, Deposit.valid_from, Deposit.id),
            response,
            page=page,
            page_size=page_size,
            limit=limit,
        )
        totals = {d.id: d for d in await _deposits_out(session, rows)}
        contracts = {
            c.id: c
            for c in (
                await session.scalars(
                    select(Contract).where(Contract.id.in_({d.contract_id for d in rows}))
                )
            ).all()
        }
        props = {
            p.id: p
            for p in (
                await session.scalars(
                    select(Property).where(
                        Property.id.in_({c.property_id for c in contracts.values()})
                    )
                )
            ).all()
        }
        units = {
            u.id: u
            for u in (
                await session.scalars(
                    select(Unit).where(Unit.id.in_({c.unit_id for c in contracts.values()}))
                )
            ).all()
        }
        parties = {
            p.id: p
            for p in (
                await session.scalars(
                    select(Party).where(Party.id.in_({c.party_id for c in contracts.values()}))
                )
            ).all()
        }
        out = []
        for d in rows:
            c = contracts[d.contract_id]
            t = totals[d.id]
            if outstanding_only and t.outstanding <= 0:
                continue
            out.append(
                s.DepositListRow(
                    id=d.id,
                    contract_id=c.id,
                    contract_number=c.number,
                    property_id=c.property_id,
                    property_number=props[c.property_id].number,
                    unit_id=c.unit_id,
                    unit_number=units[c.unit_id].number,
                    party_id=c.party_id,
                    party_name=parties[c.party_id].name,
                    kind=d.kind,
                    status=d.status,
                    amount_due=d.amount_due,
                    received=t.received,
                    balance=t.balance,
                    outstanding=t.outstanding,
                    valid_from=d.valid_from,
                    valid_to=d.valid_to,
                    contract_end_date=c.end_date,
                )
            )
        return out


@router.post("/deposits/{deposit_id}/movements", status_code=201, summary="Kautionsbewegung")
async def add_deposit_movement(
    deposit_id: uuid.UUID,
    body: s.DepositMovementIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DepositOut:
    """Records a movement; it becomes a posting only with the ledger (M10) behind G1."""
    async with tenant_tx(request, principal) as session:
        deposit = await _get(session, Deposit, deposit_id)
        existing = list(
            (
                await session.scalars(
                    select(DepositMovement).where(DepositMovement.deposit_id == deposit.id)
                )
            ).all()
        )
        _, balance = svc.deposit_totals(deposit, existing)
        if body.kind.value in ("payout", "offset") and body.amount > balance:
            raise svc.invalid("Auszahlung oder Verrechnung übersteigt das Kautionsguthaben.")
        session.add(
            DepositMovement(
                tenant_id=principal.tenant_id, deposit_id=deposit.id, **body.model_dump()
            )
        )
        await _event(
            session,
            principal,
            "deposit.movement_recorded",
            deposit.id,
            kind=body.kind.value,
            amount=body.amount,
        )
        return await _deposit_out(session, deposit)


# Overviews -----------------------------------------------------------------------------


@router.get("/properties/{property_id}/occupancy", summary="Belegungsliste")
async def occupancy(
    property_id: uuid.UUID,
    request: Request,
    as_of: date = Query(default_factory=date.today),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.OccupancyRow]:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        units = (
            await session.scalars(
                select(Unit).where(Unit.property_id == property_id).order_by(Unit.number)
            )
        ).all()
        active = (
            await session.scalars(
                select(Contract).where(
                    Contract.property_id == property_id,
                    Contract.start_date <= as_of,
                    or_(Contract.end_date.is_(None), Contract.end_date >= as_of),
                )
            )
        ).all()
        names = {
            p.id: p.name
            for p in (
                await session.scalars(
                    select(Party).where(Party.id.in_({c.party_id for c in active}))
                )
            ).all()
        }
        by_unit: dict[tuple[uuid.UUID, ContractKind], Contract] = {
            (c.unit_id, c.kind): c for c in active
        }
        rows = []
        for u in units:
            tenancy = by_unit.get((u.id, ContractKind.TENANCY))
            owner = by_unit.get((u.id, ContractKind.OWNERSHIP))
            rows.append(
                s.OccupancyRow(
                    unit_id=u.id,
                    unit_number=u.number,
                    unit_label=u.label,
                    unit_type=u.unit_type.value,
                    tenancy_contract_id=tenancy.id if tenancy else None,
                    tenant_party=names.get(tenancy.party_id) if tenancy else None,
                    ownership_contract_id=owner.id if owner else None,
                    owner_party=names.get(owner.party_id) if owner else None,
                    # Vacancy applies to let units: rental properties or SEV ownership.
                    vacant=tenancy is None
                    and (
                        prop.management_type is ManagementType.RENTAL
                        or (owner is not None and owner.sev_enabled)
                    ),
                )
            )
        return rows


@router.get("/properties/{property_id}/vacancies", summary="Leerstand zum Stichtag")
async def vacancies(
    property_id: uuid.UUID,
    request: Request,
    as_of: date = Query(default_factory=date.today),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.VacancyRow]:
    """Vermietbare Einheiten ohne Mietverhältnis zum Stichtag (Mietobjekte und SEV-Eigentum)
    mit Leerstandsbeginn (Tag nach dem letzten Mietende) und letztem Mietvertrag."""
    async with tenant_tx(request, principal) as session:
        occupancy_rows = await occupancy(property_id, request, as_of, principal)
        vacant = [r for r in occupancy_rows if r.vacant]
        if not vacant:
            return []
        unit_ids = [r.unit_id for r in vacant]
        previous: dict[uuid.UUID, Contract] = {}
        for c in (
            await session.scalars(
                select(Contract)
                .where(
                    Contract.unit_id.in_(unit_ids),
                    Contract.kind == ContractKind.TENANCY,
                    Contract.end_date.is_not(None),
                    Contract.end_date < as_of,
                )
                .order_by(Contract.end_date.desc())
            )
        ).all():
            previous.setdefault(c.unit_id, c)
        return [
            s.VacancyRow(
                unit_id=r.unit_id,
                unit_number=r.unit_number,
                unit_label=r.unit_label,
                unit_type=r.unit_type,
                vacant_since=(
                    prev.end_date + timedelta(days=1)
                    if (prev := previous.get(r.unit_id)) is not None and prev.end_date
                    else None
                ),
                previous_contract_id=prev.id if prev is not None else None,
                ownership_contract_id=r.ownership_contract_id,
                owner_party=r.owner_party,
            )
            for r in vacant
        ]
