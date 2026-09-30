"""Payer IBAN proposal into the four eyes release of contact bank accounts (7.4 no. 6, plan
M12 S7, Lückenliste M12-03).

After a person confirmed a booking of an incoming payment, the payer's IBAN of that bank
transaction can be proposed as a new bank account of a member of the debtor party. The
proposal is created through ``mhvp.contacts.services.add_bank_account`` and therefore always
``pending``: a second person with ``contacts:approve`` releases or rejects it. Nothing here
approves an IBAN, and nothing runs automatically (AI and runner never call it)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import BankTransaction, TransactionStatus
from mhvp.core.problems import ErrorCodes, ProblemError

_BIC = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
LABEL = "Zahler-IBAN aus Bankumsatz"


def _refuse(detail: str) -> None:
    raise ProblemError(ErrorCodes.BANK_PAYER_IBAN_NOT_PROPOSABLE, detail=detail)


async def candidates(session: AsyncSession, tx: BankTransaction) -> dict[str, Any]:
    """Contacts of the debtor party of the confirmed booking and whether the payer IBAN is
    already known on one of them (any approval state except rejected)."""
    from mhvp.accounting.models import JournalLine, LedgerAccount
    from mhvp.contacts.models import (
        BankAccountApproval,
        Contact,
        ContactBankAccount,
        PartyMember,
    )

    proposable = (
        tx.status is TransactionStatus.BOOKED
        and tx.journal_entry_id is not None
        and tx.amount > 0
        and bool(tx.counterpart_iban)
    )
    contacts: list[dict[str, Any]] = []
    known = False
    if tx.journal_entry_id is not None:
        party_ids = set(
            await session.scalars(
                select(LedgerAccount.party_id)
                .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
                .where(
                    JournalLine.journal_entry_id == tx.journal_entry_id,
                    LedgerAccount.party_id.is_not(None),
                )
            )
        )
        if party_ids:
            rows = (
                await session.execute(
                    select(Contact.id, Contact.display_name)
                    .join(PartyMember, PartyMember.contact_id == Contact.id)
                    .where(PartyMember.party_id.in_(party_ids))
                    .order_by(Contact.display_name)
                )
            ).all()
            seen: set[uuid.UUID] = set()
            for contact_id, name in rows:
                if contact_id not in seen:
                    seen.add(contact_id)
                    contacts.append({"contact_id": contact_id, "display_name": name})
    if tx.counterpart_iban_fingerprint and contacts:
        known = (
            await session.scalar(
                select(ContactBankAccount.id).where(
                    ContactBankAccount.contact_id.in_([c["contact_id"] for c in contacts]),
                    ContactBankAccount.iban_fingerprint == tx.counterpart_iban_fingerprint,
                    ContactBankAccount.approval_status != BankAccountApproval.REJECTED,
                )
            )
            is not None
        )
    iban = tx.counterpart_iban or ""
    return {
        "bank_transaction_id": tx.id,
        "proposable": proposable and bool(contacts) and not known,
        "iban_known": known,
        "iban_suffix": iban[-4:] if iban else None,
        "contacts": contacts,
    }


async def propose(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    contact_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> Any:
    """Creates the pending bank account; returns the ``ContactBankAccount`` row."""
    from mhvp.contacts import schemas as contact_schemas
    from mhvp.contacts import services as contact_services
    from mhvp.contacts.models import Contact

    info = await candidates(session, tx)
    if tx.status is not TransactionStatus.BOOKED or tx.journal_entry_id is None:
        _refuse("Nur nach bestätigter Buchung des Umsatzes.")
    if tx.amount <= 0:
        _refuse("Nur für Zahlungseingänge.")
    if not tx.counterpart_iban:
        _refuse("Der Umsatz enthält keine Zahler-IBAN.")
    if info["iban_known"]:
        _refuse("Die IBAN ist beim Vertragspartner bereits hinterlegt oder zur Freigabe.")
    if contact_id not in {c["contact_id"] for c in info["contacts"]}:
        _refuse("Der Kontakt gehört nicht zum Vertragspartner der Buchung.")
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    bic = (tx.counterpart_bic or "").upper() or None
    data = contact_schemas.BankAccountIn(
        label=LABEL,
        iban=tx.counterpart_iban,
        bic=bic if bic and _BIC.match(bic) else None,
        holder=(tx.counterpart_name or None),
        valid_from=tx.booking_date,
    )
    return await contact_services.add_bank_account(
        session, contact, data, tenant_id=tenant_id, actor_user_id=user_id
    )
