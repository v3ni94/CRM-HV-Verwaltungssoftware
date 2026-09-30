"""Follow-up maintenance of contracts (package P16, M5-02, M5-06, M5-07).

Custom fields in place, correction of payment rows and payment plans, change of deposits
with a status model. A row that a posted receivable already uses keeps its financial
content (rule 7: no overwriting after posting); it is ended by a new row or corrected by
reversal in the ledger.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.accounting.models import ItemStatus, ReceivableItem
from mhvp.contracts import schemas as s
from mhvp.contracts import services as svc
from mhvp.contracts.models import (
    Contract,
    ContractPayment,
    Deposit,
    DepositMovement,
    DepositStatus,
    PaymentSchedule,
)
from mhvp.contracts.routers import UPDATE, _deposit_out, _event, _flush, _get, _out, _plain
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import diff
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.properties.models import Property
from mhvp.properties.services import check_custom_fields, check_ledger_account

router = APIRouter(tags=["Verträge"])

_TRANSITIONS: dict[str, set[str]] = {
    DepositStatus.OPEN: {DepositStatus.ACTIVE, DepositStatus.SETTLED},
    DepositStatus.ACTIVE: {DepositStatus.OPEN, DepositStatus.SETTLED},
    DepositStatus.SETTLED: set(),
}


def _locked(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.CONFLICT, detail=detail)


def _own(contract: Contract, row: Any) -> None:
    if row.contract_id != contract.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


@router.patch("/contracts/{contract_id}/custom-fields", summary="Zusatzfelder des Vertrags ändern")
async def patch_custom_fields(
    contract_id: uuid.UUID,
    body: s.ContractCustomFieldsPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ContractOut:
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        prop = await _get(session, Property, contract.property_id)
        merged = {**contract.custom_fields, **body.custom_fields}
        merged = {k: v for k, v in merged.items() if v is not None}
        stored = await check_custom_fields(
            session,
            "contract",
            merged,
            management_type=prop.management_type,
            contract_kind=contract.kind.value,
            entity_id=contract.id,
        )
        before = {"custom_fields": dict(contract.custom_fields)}
        contract.custom_fields = stored
        contract.updated_by = principal.user_id
        await session.flush()
        await _event(
            session,
            principal,
            "contract.updated",
            contract.id,
            changes=diff(before, {"custom_fields": stored}),
            fields="custom_fields",
        )
        return await _out(session, contract)


async def _posted_items(session: Any, **where: uuid.UUID) -> bool:
    ((column, value),) = where.items()
    found = await session.scalar(
        select(ReceivableItem.id)
        .where(getattr(ReceivableItem, column) == value, ReceivableItem.status == ItemStatus.POSTED)
        .limit(1)
    )
    return found is not None


_PAYMENT_FINANCIAL = {"net", "vat_percent", "gross", "valid_from", "valid_to", "reason"}


@router.patch(
    "/contracts/{contract_id}/payments/{payment_id}", summary="Zahlungsposition korrigieren"
)
async def patch_payment(
    contract_id: uuid.UUID,
    payment_id: uuid.UUID,
    body: s.ContractPaymentPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PaymentOut:
    data = body.model_dump(exclude_unset=True)
    for key in ("net", "vat_percent", "gross", "valid_from", "reason"):
        if key in data and data[key] is None:
            raise svc.invalid(f"{key} darf nicht leer übergeben werden.")
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        row = await _get(session, ContractPayment, payment_id)
        _own(contract, row)
        financial = _PAYMENT_FINANCIAL & set(data)
        if financial and await _posted_items(session, contract_payment_id=row.id):
            raise _locked(
                "Die Zahlungsposition ist bereits Grundlage gebuchter Sollstellungen und kann "
                "nur über eine neue Position und Storno im Buchungskreis geändert werden."
            )
        if (
            data.get("document_id") is not None
            and await session.get(Document, data["document_id"]) is None
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Beleg nicht gefunden.")
        if data.get("revenue_account_id") is not None:
            await check_ledger_account(
                session, data["revenue_account_id"], contract.property_id, "Das Ertragskonto"
            )
        net = data.get("net", row.net)
        vat = data.get("vat_percent", row.vat_percent)
        gross = data.get("gross", row.gross)
        start = data.get("valid_from", row.valid_from)
        end = data.get("valid_to", row.valid_to)
        if financial & {"net", "vat_percent", "gross"}:
            svc.check_amounts(row.payment_type_code, net, vat, gross)
        if end is not None and end < start:
            raise svc.invalid("valid_to liegt vor valid_from.")
        if start < contract.start_date or (
            contract.end_date is not None and start > contract.end_date
        ):
            raise svc.invalid("Die Zahlung liegt außerhalb der Vertragslaufzeit.")
        before = _plain({k: getattr(row, k) for k in data})
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await _flush(session, "Die Zahlung überschneidet sich mit einer bestehenden Zahlung.")
        await _event(
            session,
            principal,
            "contract.payment_updated",
            contract.id,
            changes=diff(before, _plain({k: getattr(row, k) for k in before})),
            payment_id=row.id,
        )
        return s.PaymentOut.model_validate(row)


@router.patch(
    "/contracts/{contract_id}/schedules/{schedule_id}", summary="Zahlungsplan korrigieren"
)
async def patch_schedule(
    contract_id: uuid.UUID,
    schedule_id: uuid.UUID,
    body: s.ContractSchedulePatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ScheduleOut:
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is None and key != "valid_to":
            raise svc.invalid(f"{key} darf nicht leer übergeben werden.")
    async with tenant_tx(request, principal) as session:
        contract = await _get(session, Contract, contract_id)
        row = await _get(session, PaymentSchedule, schedule_id)
        _own(contract, row)
        if data and await _posted_items(session, payment_schedule_id=row.id):
            raise _locked(
                "Der Zahlungsplan ist bereits Grundlage gebuchter Sollstellungen und kann nur "
                "über einen neuen Plan geändert werden."
            )
        start = data.get("valid_from", row.valid_from)
        end = data.get("valid_to", row.valid_to)
        if end is not None and end < start:
            raise svc.invalid("valid_to liegt vor valid_from.")
        before = _plain({k: getattr(row, k) for k in data})
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await _flush(session, "Der Zahlungsplan überschneidet sich mit einem bestehenden.")
        await _event(
            session,
            principal,
            "contract.schedule_updated",
            contract.id,
            changes=diff(before, _plain({k: getattr(row, k) for k in before})),
            schedule_id=row.id,
        )
        return s.ScheduleOut.model_validate(row)


@router.patch("/deposits/{deposit_id}", summary="Kaution ändern (Status, Dokumente, Betrag)")
async def patch_deposit(
    deposit_id: uuid.UUID,
    body: s.DepositPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DepositOut:
    data = body.model_dump(exclude_unset=True)
    for key in ("amount_due", "installments", "documents", "status"):
        if key in data and data[key] is None:
            raise svc.invalid(f"{key} darf nicht leer übergeben werden.")
    async with tenant_tx(request, principal) as session:
        deposit = await _get(session, Deposit, deposit_id)
        contract = await _get(session, Contract, deposit.contract_id)
        settled = deposit.status == DepositStatus.SETTLED
        if settled and set(data) - {"documents"}:
            raise _locked("Eine abgerechnete Kaution kann nur noch um Dokumente ergänzt werden.")
        if {"amount_due", "installments"} & set(data):
            has_movements = await session.scalar(
                select(DepositMovement.id).where(DepositMovement.deposit_id == deposit.id).limit(1)
            )
            if has_movements is not None:
                raise _locked(
                    "Betrag und Raten sind nach der ersten Kautionsbewegung nicht mehr änderbar."
                )
        if (
            "status" in data
            and data["status"] != deposit.status
            and data["status"] not in _TRANSITIONS.get(deposit.status, set())
        ):
            raise svc.invalid(
                f"Statuswechsel von {deposit.status} nach {data['status']} ist nicht zulässig."
            )
        if "property_bank_account_id" in data:
            await svc.check_deposit_account(session, contract, data["property_bank_account_id"])
        if "documents" in data:
            ids = {str(d) for d in data["documents"]}
            found = {
                str(d)
                for d in await session.scalars(
                    select(Document.id).where(Document.id.in_([uuid.UUID(i) for i in ids]))
                )
            }
            if found != ids:
                raise svc.invalid("Mindestens ein Dokument wurde nicht gefunden.")
            data["documents"] = sorted(ids)
        start = deposit.valid_from
        end = data.get("valid_to", deposit.valid_to)
        if end is not None and end < start:
            raise svc.invalid("valid_to liegt vor valid_from.")
        before = _plain({k: getattr(deposit, k) for k in data})
        for key, value in data.items():
            setattr(deposit, key, value)
        deposit.updated_by = principal.user_id
        await session.flush()
        await _event(
            session,
            principal,
            "deposit.updated",
            contract.id,
            changes=diff(before, _plain({k: getattr(deposit, k) for k in before})),
            deposit_id=deposit.id,
        )
        return await _deposit_out(session, deposit)
