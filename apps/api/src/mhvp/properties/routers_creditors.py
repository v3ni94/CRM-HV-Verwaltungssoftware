"""Creditors per property (rule M11-05): tab "Dienstleister/Handwerker", creditor contact
from a bank transaction, backfill, and the contact's properties as creditor.

Permissions: ``properties:read`` for the list, ``properties:update`` for link, trade, unlink
and backfill; ``contacts:read`` for the counterparty lookup and the contact section;
``contacts:create`` plus ``properties:update`` for "Kreditor anlegen" (contact and link).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.banking.models import BankTransaction
from mhvp.contacts.models import BankAccountApproval, Contact, ContactBankAccount
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties import creditors as svc
from mhvp.properties.models import (
    Property,
    PropertyBankAccount,
    PropertyCreditor,
    PropertyCreditorSource,
)
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Objekte"])
READ = require_permission("properties:read")
UPDATE = require_permission("properties:update")
CONTACTS_READ = require_permission("contacts:read")
CONTACTS_CREATE = require_permission("contacts:create")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PropertyCreditorOut(_Out):
    id: uuid.UUID
    property_id: uuid.UUID
    contact_id: uuid.UUID
    contact_name: str
    contact_roles: list[str]
    trade: str | None
    since: date | None
    source: PropertyCreditorSource
    source_transaction_id: uuid.UUID | None
    phone: str | None
    email: str | None
    last_invoice_date: date | None
    last_invoice_amount: Decimal | None
    open_invoice_amount: Decimal | None = Field(
        default=None,
        description="Summe der Rechnungen des Kreditors am Objekt, die noch nicht gebucht sind "
        "(Belegeingang); keine offenen Posten der Buchhaltung.",
    )
    work_orders_count: int


class PropertyCreditorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: uuid.UUID
    trade: str | None = Field(default=None, max_length=100)
    since: date | None = None


class PropertyCreditorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trade: str | None = Field(default=None, max_length=100)
    since: date | None = None


class BackfillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None


class BackfillOut(BaseModel):
    scanned: int
    created: int


class CreditorPropertyOut(_Out):
    id: uuid.UUID
    property_id: uuid.UUID
    property_number: str
    property_name: str
    trade: str | None
    since: date | None
    source: PropertyCreditorSource


class CounterpartyContactOut(BaseModel):
    contact_id: uuid.UUID | None
    display_name: str | None
    basis: str | None = Field(default=None, description="iban oder name; kein Beweis")
    is_creditor: bool
    property_id: uuid.UUID
    linked_to_property: bool
    counterpart_name: str | None
    has_counterpart_iban: bool


class CreditorFromTransactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=200)
    trade: str | None = Field(default=None, max_length=100)
    link_property: bool = True


class CreditorFromTransactionOut(BaseModel):
    contact_id: uuid.UUID
    display_name: str
    created: bool
    property_id: uuid.UUID
    link_id: uuid.UUID | None
    bank_account_pending: bool = Field(
        description="IBAN aus dem Umsatz wartet auf die Freigabe durch eine zweite Person."
    )


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


@router.get("/properties/{property_id}/creditors", summary="Dienstleister/Handwerker des Objekts")
async def list_creditors(
    property_id: uuid.UUID,
    request: Request,
    trade: str | None = Query(default=None, max_length=100),
    principal: TenantPrincipal = Depends(READ),
) -> list[PropertyCreditorOut]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise _nf()
        rows = await svc.list_for_property(session, property_id, trade=trade)
        return [PropertyCreditorOut.model_validate(r) for r in rows]


@router.post(
    "/properties/{property_id}/creditors",
    status_code=201,
    summary="Kreditor mit dem Objekt verknüpfen (Rolle Dienstleister wird ergänzt)",
)
async def add_creditor(
    property_id: uuid.UUID,
    body: PropertyCreditorIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> PropertyCreditorOut:
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise _nf()
        contact = await session.get(Contact, body.contact_id)
        if contact is None or contact.deleted_at is not None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kontakt nicht gefunden.")
        row, _ = await svc.link(
            session,
            tenant_id=principal.tenant_id,
            property_id=property_id,
            contact=contact,
            source=PropertyCreditorSource.MANUAL,
            actor_user_id=principal.user_id,
            trade=body.trade,
            since=body.since,
        )
        if body.trade is not None and row.trade != body.trade:
            row.trade = body.trade
            row.updated_by = principal.user_id
        await session.flush()
        rows = await svc.list_for_property(session, property_id)
        return next(PropertyCreditorOut.model_validate(r) for r in rows if r["id"] == row.id)


@router.patch("/properties/{property_id}/creditors/{link_id}", summary="Gewerk oder Beginn ändern")
async def patch_creditor(
    property_id: uuid.UUID,
    link_id: uuid.UUID,
    body: PropertyCreditorPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> PropertyCreditorOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PropertyCreditor, link_id)
        if row is None or row.property_id != property_id:
            raise _nf()
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        rows = await svc.list_for_property(session, property_id)
        return next(PropertyCreditorOut.model_validate(r) for r in rows if r["id"] == row.id)


@router.delete(
    "/properties/{property_id}/creditors/{link_id}",
    status_code=204,
    summary="Verknüpfung lösen (der Kontakt bleibt)",
)
async def unlink_creditor(
    property_id: uuid.UUID,
    link_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(PropertyCreditor, link_id)
        if row is None or row.property_id != property_id:
            raise _nf()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_creditor.unlinked",
            entity_type="property_creditor",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(property_id), "contact_id": str(row.contact_id)},
        )
        await session.delete(row)
        await session.flush()


@router.post(
    "/properties/creditors/backfill",
    summary="Kreditorenverknüpfungen aus vorhandenen Buchungen und Rechnungen nachziehen",
)
async def backfill_creditors(
    body: BackfillIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> BackfillOut:
    """Idempotent per tenant: a second run creates nothing. Only contacts with the creditor
    role (bank transactions) or with an invoice of the property are linked."""
    async with tenant_tx(request, principal) as session:
        if body.property_id is not None and await session.get(Property, body.property_id) is None:
            raise _nf()
        result = await svc.backfill(
            session,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            property_id=body.property_id,
        )
        return BackfillOut(**result)


@router.get("/contacts/{contact_id}/creditor-properties", summary="Objekte als Dienstleister")
async def creditor_properties(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CONTACTS_READ)
) -> list[CreditorPropertyOut]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Contact, contact_id) is None:
            raise _nf()
        rows = await svc.properties_of_creditor(session, contact_id)
        return [CreditorPropertyOut.model_validate(r) for r in rows]


async def _tx_with_property(session: object, tx_id: uuid.UUID) -> tuple[BankTransaction, uuid.UUID]:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)  # noqa: S101 - typing aid
    tx = await session.get(BankTransaction, tx_id)
    if tx is None:
        raise _nf()
    account = await session.get(PropertyBankAccount, tx.property_bank_account_id)
    if account is None:
        raise _nf()
    return tx, account.property_id


@router.get(
    "/banking/transactions/{transaction_id}/counterparty-contact",
    summary="Gegenpartei eines Umsatzes als Kontakt (IBAN oder Name, kein Beweis)",
)
async def counterparty_contact(
    transaction_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_READ),
) -> CounterpartyContactOut:
    async with tenant_tx(request, principal) as session:
        tx, property_id = await _tx_with_property(session, transaction_id)
        contact, basis = await svc.find_counterparty_contact(session, tx)
        linked = False
        if contact is not None:
            linked = (
                await session.scalar(
                    select(PropertyCreditor.id).where(
                        PropertyCreditor.property_id == property_id,
                        PropertyCreditor.contact_id == contact.id,
                    )
                )
            ) is not None
        return CounterpartyContactOut(
            contact_id=contact.id if contact else None,
            display_name=contact.display_name if contact else None,
            basis=basis,
            is_creditor=bool(contact and svc.CREDITOR_ROLE in (contact.roles or [])),
            property_id=property_id,
            linked_to_property=linked,
            counterpart_name=tx.counterpart_name,
            has_counterpart_iban=bool(tx.counterpart_iban_fingerprint),
        )


@router.post(
    "/banking/transactions/{transaction_id}/creditor-contact",
    status_code=201,
    summary="Kreditor anlegen: Kontakt mit Rolle Dienstleister, IBAN zur Freigabe",
)
async def creditor_from_transaction(
    transaction_id: uuid.UUID,
    body: CreditorFromTransactionIn,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_CREATE),
) -> CreditorFromTransactionOut:
    if body.link_property and not principal.has("properties:update"):
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Missing permission properties:update."
        )
    async with tenant_tx(request, principal) as session:
        tx, property_id = await _tx_with_property(session, transaction_id)
        contact, created = await svc.create_creditor_from_transaction(
            session,
            tx,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            name=body.name,
            trade=body.trade,
            today=local_today(),
        )
        link_id: uuid.UUID | None = None
        if body.link_property:
            row, _ = await svc.link(
                session,
                tenant_id=principal.tenant_id,
                property_id=property_id,
                contact=contact,
                source=PropertyCreditorSource.PROPOSAL,
                actor_user_id=principal.user_id,
                trade=body.trade,
                since=tx.booking_date,
                source_transaction_id=tx.id,
            )
            link_id = row.id
        await session.flush()
        pending = (
            await session.scalar(
                select(ContactBankAccount.id).where(
                    ContactBankAccount.contact_id == contact.id,
                    ContactBankAccount.approval_status == BankAccountApproval.PENDING,
                )
            )
        ) is not None
        return CreditorFromTransactionOut(
            contact_id=contact.id,
            display_name=contact.display_name,
            created=created,
            property_id=property_id,
            link_id=link_id,
            bank_account_pending=pending,
        )
