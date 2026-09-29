"""Creditors per property (rule M11-05): link a contact with role ``dienstleister`` to a
property, create a creditor contact from a bank transaction's counterparty, backfill links from
existing creditor postings and invoices, and the list for the tab "Dienstleister/Handwerker".

Master data only. The counterparty IBAN of a transaction is stored on the new contact as a
pending bank account, never approved here: release stays with the existing four eyes path
(M5-01, ``contacts:approve``). No posting, no payment.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Invoice, Ledger, PostingStatus
from mhvp.banking.models import BankTransaction, TransactionStatus
from mhvp.contacts import schemas as contact_schemas
from mhvp.contacts import services as contact_services
from mhvp.contacts.models import (
    BankAccountApproval,
    Contact,
    ContactBankAccount,
    ContactEmail,
    ContactKind,
    ContactPhone,
    ContactRoleCode,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import (
    Property,
    PropertyBankAccount,
    PropertyCreditor,
    PropertyCreditorSource,
)
from mhvp.tickets.models import WorkOrder

CREDITOR_ROLE = ContactRoleCode.DIENSTLEISTER.value


def ensure_creditor_role(contact: Contact) -> bool:
    """Adds the role ``dienstleister``; returns whether the contact changed."""
    if CREDITOR_ROLE in (contact.roles or []):
        return False
    contact.roles = sorted({*(contact.roles or []), CREDITOR_ROLE})
    return True


async def link(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    property_id: uuid.UUID,
    contact: Contact,
    source: PropertyCreditorSource,
    actor_user_id: uuid.UUID | None,
    trade: str | None = None,
    since: date | None = None,
    source_transaction_id: uuid.UUID | None = None,
) -> tuple[PropertyCreditor, bool]:
    """Idempotent link of ``contact`` to ``property_id``. An existing link keeps its source
    and gets ``trade`` / ``since`` only where they were empty. Returns (row, created)."""
    existing = await session.scalar(
        select(PropertyCreditor).where(
            PropertyCreditor.property_id == property_id,
            PropertyCreditor.contact_id == contact.id,
        )
    )
    role_added = ensure_creditor_role(contact)
    if existing is not None:
        changed = role_added
        if trade and not existing.trade:
            existing.trade = trade
            changed = True
        if since and not existing.since:
            existing.since = since
            changed = True
        if changed:
            existing.updated_by = actor_user_id
        return existing, False
    row = PropertyCreditor(
        tenant_id=tenant_id,
        created_by=actor_user_id,
        property_id=property_id,
        contact_id=contact.id,
        trade=trade,
        since=since,
        source=source,
        source_transaction_id=source_transaction_id,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="property_creditor.linked",
        entity_type="property_creditor",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        payload={
            "property_id": str(property_id),
            "contact_id": str(contact.id),
            "source": source.value,
            "trade": trade,
        },
    )
    return row, True


async def find_counterparty_contact(
    session: AsyncSession, tx: BankTransaction
) -> tuple[Contact | None, str | None]:
    """Contact matching the counterparty of ``tx``: first by IBAN fingerprint of a contact bank
    account (pending or approved, not rejected), then by exact company or display name.
    Returns (contact, basis) with basis ``iban`` or ``name``; the IBAN alone proves no
    debtor or creditor, the basis is shown to the user."""
    if tx.counterpart_iban_fingerprint:
        contact = await session.scalar(
            select(Contact)
            .join(ContactBankAccount, ContactBankAccount.contact_id == Contact.id)
            .where(
                ContactBankAccount.iban_fingerprint == tx.counterpart_iban_fingerprint,
                ContactBankAccount.approval_status != BankAccountApproval.REJECTED,
                Contact.deleted_at.is_(None),
            )
            .order_by(Contact.created_at)
            .limit(1)
        )
        if contact is not None:
            return contact, "iban"
    name = (tx.counterpart_name or "").strip()
    if name:
        contact = await session.scalar(
            select(Contact)
            .where(
                Contact.deleted_at.is_(None),
                func.lower(func.coalesce(Contact.company_name, Contact.display_name))
                == name.lower(),
            )
            .order_by(Contact.created_at)
            .limit(1)
        )
        if contact is not None:
            return contact, "name"
    return None, None


async def create_creditor_from_transaction(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    name: str | None,
    trade: str | None,
    today: date,
) -> tuple[Contact, bool]:
    """ "Kreditor anlegen" from a posting proposal or manual booking: a company contact with
    role ``dienstleister`` from the counterparty name; the counterparty IBAN becomes a pending
    bank account (four eyes, M5-01). When the counterparty already is a contact, that contact
    is returned (created = False) and only gets the role."""
    found, _ = await find_counterparty_contact(session, tx)
    if found is not None:
        ensure_creditor_role(found)
        return found, False
    company = (name or tx.counterpart_name or "").strip()
    if len(company) < 2:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Umsatz nennt keine Gegenpartei; bitte den Namen des Kreditors angeben.",
        )
    bank_accounts: list[contact_schemas.BankAccountIn] = []
    if tx.counterpart_iban:
        bank_accounts.append(
            contact_schemas.BankAccountIn(
                iban=tx.counterpart_iban,
                bic=tx.counterpart_bic,
                holder=company[:200],
                valid_from=today,
                is_default=True,
                label="aus Bankumsatz",
            )
        )
    data = contact_schemas.ContactIn(
        kind=ContactKind.COMPANY,
        company_name=company[:200],
        roles=[ContactRoleCode.DIENSTLEISTER],
        notes=(f"Gewerk: {trade}" if trade else None),
        bank_accounts=bank_accounts,
    )
    contact = Contact(
        tenant_id=tenant_id, created_by=actor_user_id, kind=data.kind, display_name=""
    )
    contact_services.apply_fields(contact, data)
    session.add(contact)
    await session.flush()
    await contact_services.write_children(
        session, tenant_id, contact.id, data, actor_user_id=actor_user_id
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type="contact.created",
        entity_type="contact",
        entity_id=contact.id,
        actor_user_id=actor_user_id,
        payload={"kind": contact.kind.value, "source": "bank_transaction", "tx": str(tx.id)},
    )
    return contact, True


async def backfill(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    property_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Idempotent: links creditors that already appear on a property's accounts. Sources:
    (a) booked outgoing bank transactions whose counterparty IBAN matches a contact bank
    account (not rejected); (b) invoices of a ledger with ``property_id``. ``since`` is the
    earliest booking or invoice date. Existing links are left untouched."""
    created = 0
    scanned = 0
    # (property, contact) -> [since, source transaction, seen on an invoice]
    candidates: dict[tuple[uuid.UUID, uuid.UUID], list[Any]] = {}

    tx_query = (
        select(
            PropertyBankAccount.property_id,
            ContactBankAccount.contact_id,
            func.min(BankTransaction.booking_date),
            func.min(cast(BankTransaction.id, String)),
        )
        .join(
            PropertyBankAccount,
            PropertyBankAccount.id == BankTransaction.property_bank_account_id,
        )
        .join(
            ContactBankAccount,
            ContactBankAccount.iban_fingerprint == BankTransaction.counterpart_iban_fingerprint,
        )
        .where(
            BankTransaction.amount < Decimal(0),
            BankTransaction.status.in_([TransactionStatus.BOOKED, TransactionStatus.SPLIT]),
            BankTransaction.counterpart_iban_fingerprint.is_not(None),
            ContactBankAccount.approval_status != BankAccountApproval.REJECTED,
        )
        .group_by(PropertyBankAccount.property_id, ContactBankAccount.contact_id)
    )
    if property_id is not None:
        tx_query = tx_query.where(PropertyBankAccount.property_id == property_id)
    for prop_id, contact_id, first, tx_id in (await session.execute(tx_query)).all():
        scanned += 1
        candidates[(prop_id, contact_id)] = [first, uuid.UUID(tx_id) if tx_id else None, False]

    inv_query = (
        select(Ledger.property_id, Invoice.provider_contact_id, func.min(Invoice.invoice_date))
        .join(Ledger, Ledger.id == Invoice.ledger_id)
        .where(Ledger.property_id.is_not(None), Invoice.posting_status != PostingStatus.REVERSED)
        .group_by(Ledger.property_id, Invoice.provider_contact_id)
    )
    if property_id is not None:
        inv_query = inv_query.where(Ledger.property_id == property_id)
    for prop_id, contact_id, first in (await session.execute(inv_query)).all():
        scanned += 1
        entry = candidates.setdefault((prop_id, contact_id), [None, None, True])
        entry[2] = True
        dates = [d for d in (entry[0], first) if d is not None]
        entry[0] = min(dates) if dates else None

    for (prop_id, contact_id), (since, tx_id, on_invoice) in sorted(
        candidates.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        contact = await session.get(Contact, contact_id)
        if contact is None or contact.deleted_at is not None:
            continue
        # A payment to an owner or tenant (refund, credit) is no creditor relation: a bank
        # transaction alone links only contacts that already carry the creditor role; an
        # invoice of the property always does.
        if not on_invoice and CREDITOR_ROLE not in (contact.roles or []):
            continue
        _, is_new = await link(
            session,
            tenant_id=tenant_id,
            property_id=prop_id,
            contact=contact,
            source=PropertyCreditorSource.BACKFILL,
            actor_user_id=actor_user_id,
            since=since,
            source_transaction_id=tx_id,
        )
        created += int(is_new)
    return {"scanned": scanned, "created": created}


async def list_for_property(
    session: AsyncSession, property_id: uuid.UUID, *, trade: str | None = None
) -> list[dict[str, Any]]:
    """Rows of the tab: contact data, last invoice, open invoice amount (invoices not yet posted
    or without journal entry are "offen" in the sense of the intake; the accounting module's
    open items per creditor are not modelled yet), work order count."""
    query = (
        select(PropertyCreditor, Contact)
        .join(Contact, Contact.id == PropertyCreditor.contact_id)
        .where(PropertyCreditor.property_id == property_id, Contact.deleted_at.is_(None))
        .order_by(Contact.display_name)
    )
    if trade:
        query = query.where(func.lower(PropertyCreditor.trade) == trade.strip().lower())
    rows = (await session.execute(query)).all()
    if not rows:
        return []
    contact_ids = [c.id for _, c in rows]
    phones = {
        p.contact_id: p.number
        for p in (
            await session.scalars(
                select(ContactPhone)
                .where(ContactPhone.contact_id.in_(contact_ids))
                .order_by(ContactPhone.is_primary.desc(), ContactPhone.created_at)
            )
        ).all()[::-1]
    }
    emails = {
        e.contact_id: e.email
        for e in (
            await session.scalars(
                select(ContactEmail)
                .where(ContactEmail.contact_id.in_(contact_ids))
                .order_by(ContactEmail.is_primary.desc(), ContactEmail.created_at)
            )
        ).all()[::-1]
    }
    invoices = (
        await session.execute(
            select(
                Invoice.provider_contact_id,
                Invoice.invoice_date,
                Invoice.gross,
                Invoice.posting_status,
            )
            .join(Ledger, Ledger.id == Invoice.ledger_id)
            .where(Ledger.property_id == property_id, Invoice.provider_contact_id.in_(contact_ids))
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
        )
    ).all()
    last: dict[uuid.UUID, tuple[date, Decimal]] = {}
    open_sum: dict[uuid.UUID, Decimal] = {}
    for contact_id, inv_date, gross, posting in invoices:
        last.setdefault(contact_id, (inv_date, gross))
        if posting is PostingStatus.UNPOSTED:
            open_sum[contact_id] = open_sum.get(contact_id, Decimal(0)) + gross
    orders: dict[uuid.UUID, int] = {}
    for provider_id, count in (
        await session.execute(
            select(WorkOrder.provider_contact_id, func.count())
            .where(
                WorkOrder.property_id == property_id,
                WorkOrder.provider_contact_id.in_(contact_ids),
            )
            .group_by(WorkOrder.provider_contact_id)
        )
    ).all():
        orders[provider_id] = int(count)
    out: list[dict[str, Any]] = []
    for row, contact in rows:
        last_inv = last.get(contact.id)
        out.append(
            {
                "id": row.id,
                "property_id": row.property_id,
                "contact_id": contact.id,
                "contact_name": contact.display_name,
                "contact_roles": list(contact.roles or []),
                "trade": row.trade,
                "since": row.since,
                "source": row.source,
                "source_transaction_id": row.source_transaction_id,
                "phone": phones.get(contact.id),
                "email": emails.get(contact.id),
                "last_invoice_date": last_inv[0] if last_inv else None,
                "last_invoice_amount": last_inv[1] if last_inv else None,
                "open_invoice_amount": open_sum.get(contact.id),
                "work_orders_count": int(orders.get(contact.id, 0)),
            }
        )
    return out


async def properties_of_creditor(
    session: AsyncSession, contact_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(PropertyCreditor, Property)
            .join(Property, Property.id == PropertyCreditor.property_id)
            .where(PropertyCreditor.contact_id == contact_id)
            .order_by(Property.number)
        )
    ).all()
    return [
        {
            "id": row.id,
            "property_id": prop.id,
            "property_number": prop.number,
            "property_name": prop.name,
            "trade": row.trade,
            "since": row.since,
            "source": row.source,
        }
        for row, prop in rows
    ]
