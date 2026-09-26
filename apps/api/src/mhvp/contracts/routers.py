"""Contract endpoints (/api/v1/contracts, /sepa-mandates, /deposits, occupancy)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.contacts.models import ContactBankAccount, Party, PartyMember
from mhvp.contacts.services import approval_block_reason
from mhvp.contacts.validation import mask_iban
from mhvp.contracts import schemas as s
from mhvp.contracts import services as svc
from mhvp.contracts.models import (
    Contract,
    ContractKind,
    ContractPayment,
    DebtorAccountReservation,
    Deposit,
    DepositMovement,
    MandateStatus,
    PaymentSchedule,
    SepaMandate,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import ManagementType, Property, Unit
from mhvp.properties.services import check_catalog

router = APIRouter(tags=["Verträge"])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")


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
    account = await session.get(DebtorAccountReservation, contract.debtor_account_id)
    payments = (
        await session.scalars(
            select(ContractPayment)
            .where(ContractPayment.contract_id == contract.id)
            .order_by(ContractPayment.payment_type_code, ContractPayment.valid_from)
        )
    ).all()
    schedules = (
        await session.scalars(
            select(PaymentSchedule)
            .where(PaymentSchedule.contract_id == contract.id)
            .order_by(PaymentSchedule.valid_from)
        )
    ).all()
    data = {c.key: getattr(contract, c.key) for c in Contract.__table__.columns}
    return s.ContractOut.model_validate(
        {
            **data,
            "debtor_account": s.DebtorAccountOut.model_validate(account),
            "payments": [s.PaymentOut.model_validate(p) for p in payments],
            "schedules": [s.ScheduleOut.model_validate(x) for x in schedules],
        }
    )


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
    return contract


# Contracts -----------------------------------------------------------------------------


@router.get("/contracts", summary="Verträge")
async def list_contracts(
    request: Request,
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    party_id: uuid.UUID | None = None,
    kind: ContractKind | None = None,
    active_on: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.ContractOut]:
    async with tenant_tx(request, principal) as session:
        query = select(Contract)
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
        rows = (await session.scalars(query.order_by(Contract.number, Contract.version))).all()
        return [await _out(session, c) for c in rows]


@router.post("/contracts", status_code=201, summary="Vertrag anlegen")
async def create_contract(
    body: s.ContractIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _create(session, principal, body)
        await _event(session, principal, "contract.created", contract.id, kind=body.kind.value)
        return await _out(session, contract)


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
        return [await _out(session, c) for c in rows]


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
        contract.updated_by = principal.user_id
        await _event(session, principal, "contract.terminated", contract.id, end_date=body.end_date)
        return await _out(session, contract)


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
    account = await session.get(ContactBankAccount, mandate.contact_bank_account_id)
    out = s.MandateOut.model_validate(mandate)
    out.iban_masked = mask_iban(account.iban) if account is not None else None
    return out


@router.get("/sepa-mandates", summary="SEPA-Mandate")
async def list_mandates(
    request: Request,
    party_id: uuid.UUID | None = None,
    status: MandateStatus | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.MandateOut]:
    async with tenant_tx(request, principal) as session:
        query = select(SepaMandate)
        if party_id is not None:
            query = query.where(SepaMandate.party_id == party_id)
        if status is not None:
            query = query.where(SepaMandate.status == status)
        rows = (await session.scalars(query.order_by(SepaMandate.signed_at))).all()
        return [await _mandate_out(session, m) for m in rows]


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
    movements = list(
        (
            await session.scalars(
                select(DepositMovement)
                .where(DepositMovement.deposit_id == deposit.id)
                .order_by(DepositMovement.date)
            )
        ).all()
    )
    received, balance = svc.deposit_totals(deposit, movements)
    out = s.DepositOut.model_validate(deposit)
    out.received = received
    out.balance = balance
    out.outstanding = max(deposit.amount_due - received, Decimal("0.00"))
    out.movements = []
    for m in movements:
        row = s.DepositMovementOut.model_validate(m)
        row.review_required = m.posting_id is None  # not yet a ledger posting (M10, G1)
        out.movements.append(row)
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
            await session.scalars(select(Deposit).where(Deposit.contract_id == contract_id))
        ).all()
        return [await _deposit_out(session, d) for d in rows]


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
