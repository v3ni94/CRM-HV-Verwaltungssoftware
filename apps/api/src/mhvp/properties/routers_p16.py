"""Follow-up maintenance of property master data (package P16, M4-01 to M4-03).

Bank accounts and service provider relations can be changed or ended after creation, the
VAT option history of a unit is readable. IBAN, account kind and legal entity stay fixed
(6.9.1, D56): a different account is a new account. Permissions equal the create routes
(``properties:update``); every change writes an audit event with the diff.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select

from mhvp.contacts.models import ContactBankAccount
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties import schemas as s
from mhvp.properties import services as svc
from mhvp.properties.models import (
    PropertyBankAccount,
    ServiceProviderRelation,
    Unit,
    UnitVatOption,
)
from mhvp.properties.routers import READ, UPDATE, _account_out, _get

router = APIRouter(tags=["Objekte"])


def _snapshot(row: object, fields: set[str]) -> dict[str, object]:
    out: dict[str, object] = {}
    for name in fields:
        value = getattr(row, name)
        out[name] = (
            value.isoformat()
            if isinstance(value, date)
            else str(value)
            if isinstance(value, uuid.UUID)
            else value
        )
    return out


def _apply(row: object, patch: BaseModel) -> set[str]:
    data = patch.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    return set(data)


@router.patch(
    "/properties/{property_id}/bank-accounts/{account_id}",
    summary="Bankkonto eines Objekts ändern oder beenden (valid_to)",
)
async def patch_account(
    property_id: uuid.UUID,
    account_id: uuid.UUID,
    body: s.BankAccountPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BankAccountOut:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, PropertyBankAccount, account_id)
        if account.property_id != property_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if data.get("holder", "x") is None:
            raise svc.invalid("Der Kontoinhaber darf nicht leer sein.")
        valid_to = data.get("valid_to", account.valid_to)
        if valid_to is not None and valid_to < account.valid_from:
            raise svc.invalid("valid_to liegt vor valid_from.")
        if "ledger_account_id" in data:
            await svc.check_ledger_account(
                session, data["ledger_account_id"], property_id, "Das Sachkonto"
            )
        if "bank_connection_id" in data:
            await svc.check_bank_connection(session, data["bank_connection_id"])
        fields = set(data)
        before = _snapshot(account, fields)
        _apply(account, body)
        if account.valid_to is not None and account.is_default:
            # An ended account is no payment target any more.
            account.is_default = False
            fields.add("is_default")
            before["is_default"] = True
        account.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_bank_account.updated",
            entity_type="property_bank_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(fields)},
            changes=diff(before, _snapshot(account, fields)),
        )
        return _account_out(account)


@router.patch(
    "/properties/{property_id}/service-providers/{relation_id}",
    summary="Dienstleisterverhältnis ändern oder beenden (valid_to)",
)
async def patch_provider(
    property_id: uuid.UUID,
    relation_id: uuid.UUID,
    body: s.ProviderPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ProviderOut:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, ServiceProviderRelation, relation_id)
        if row.property_id != property_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        if data.get("categories", []) is None:
            raise svc.invalid("Die Kategorien dürfen nicht leer übergeben werden.")
        valid_to = data.get("valid_to", row.valid_to)
        if valid_to is not None and valid_to < row.valid_from:
            raise svc.invalid("valid_to liegt vor valid_from.")
        if data.get("contact_bank_account_id"):
            account = await _get(session, ContactBankAccount, data["contact_bank_account_id"])
            if account.contact_id != row.contact_id:
                raise svc.invalid("Die Bankverbindung gehört nicht zum Dienstleister.")
        if "creditor_account_id" in data:
            await svc.check_ledger_account(
                session, data["creditor_account_id"], property_id, "Das Kreditorenkonto"
            )
        fields = set(data)
        before = _snapshot(row, fields)
        _apply(row, body)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="service_provider_relation.updated",
            entity_type="service_provider_relation",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(fields)},
            changes=diff(before, _snapshot(row, fields)),
        )
        return s.ProviderOut.model_validate(row)


@router.get(
    "/units/{unit_id}/vat-options",
    summary="Historie der Umsatzsteueroptionen einer Einheit",
)
async def list_vat_options(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.VatOptionHistoryOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Unit, unit_id)
        rows = (
            await session.scalars(
                select(UnitVatOption)
                .where(UnitVatOption.unit_id == unit_id)
                .order_by(UnitVatOption.valid_from.desc(), UnitVatOption.id)
            )
        ).all()
        return [s.VatOptionHistoryOut.model_validate(r) for r in rows]
