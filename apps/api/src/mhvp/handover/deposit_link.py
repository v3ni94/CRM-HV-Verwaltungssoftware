"""Deposit and refund account of a completed handover protocol (AN19, GAK-206; 13.4, 6.3).

The protocol records the deposit amount and the refund IBAN as entered values only. This
module links them to the follow-up processes without moving money:

* the deposit of the linked contract (``contracts.deposit``) is looked up and compared with
  the protocol amount (difference shown, nothing changed on the deposit);
* the refund IBAN becomes a bank account of the moving out tenant's contact through the
  existing four eyes release (``contacts.services.add_bank_account``, status ``pending``);
  an account with the same IBAN is reused, never duplicated. Only a released account may
  later feed a deposit payout; payouts stay behind G2 and the deposit settlement stays a
  draft (G3).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.handover.models import HandoverParticipant, HandoverProtocol

OUT_ROLES = ("moving_out",)


async def _deposit(session: AsyncSession, contract_id: uuid.UUID | None) -> Any:
    if contract_id is None:
        return None
    from mhvp.contracts.models import Deposit

    return await session.scalar(
        select(Deposit)
        .where(Deposit.contract_id == contract_id)
        .order_by(Deposit.valid_from.desc())
        .limit(1)
    )


async def _contact_id(
    session: AsyncSession, p: HandoverProtocol, wanted: uuid.UUID | None
) -> uuid.UUID | None:
    rows = (
        await session.scalars(
            select(HandoverParticipant.contact_id).where(
                HandoverParticipant.protocol_id == p.id,
                HandoverParticipant.contact_id.is_not(None),
            )
        )
    ).all()
    if wanted is not None:
        if wanted not in rows:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kontakt ist kein Teilnehmer des Protokolls."
            )
        return wanted
    out = (
        await session.scalars(
            select(HandoverParticipant.contact_id).where(
                HandoverParticipant.protocol_id == p.id,
                HandoverParticipant.role.in_(OUT_ROLES),
                HandoverParticipant.contact_id.is_not(None),
            )
        )
    ).all()
    return out[0] if len(out) == 1 else None


async def _existing_account(session: AsyncSession, contact_id: uuid.UUID, iban: str) -> Any:
    from mhvp.contacts.models import BankAccountApproval, ContactBankAccount
    from mhvp.core import crypto

    return await session.scalar(
        select(ContactBankAccount).where(
            ContactBankAccount.contact_id == contact_id,
            ContactBankAccount.iban_fingerprint == crypto.fingerprint(iban),
            ContactBankAccount.approval_status != BankAccountApproval.REJECTED,
        )
    )


def _normalised_iban(p: HandoverProtocol) -> str | None:
    if not p.deposit_iban:
        return None
    from mhvp.contacts.validation import InvalidValueError, normalise_iban

    try:
        return normalise_iban(p.deposit_iban)
    except InvalidValueError:
        return None


async def state(
    session: AsyncSession, p: HandoverProtocol, contact_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Preview: deposit of the contract, amount comparison, refund account and its release."""
    deposit = await _deposit(session, p.contract_id)
    hints: list[str] = []
    difference: Decimal | None = None
    if p.contract_id is None:
        hints.append("Kein Vertrag verknüpft.")
    elif deposit is None:
        hints.append("Zum Vertrag ist keine Kaution erfasst.")
    if deposit is not None and p.deposit_amount is not None:
        difference = p.deposit_amount - deposit.amount_due
        if difference != 0:
            hints.append("Kautionsbetrag im Protokoll weicht von der Kaution des Vertrags ab.")
    iban = _normalised_iban(p)
    if p.deposit_iban and iban is None:
        hints.append("Rückzahlungs-IBAN ist ungültig.")
    cid = await _contact_id(session, p, contact_id)
    if iban and cid is None:
        hints.append("Kontakt des ausziehenden Mieters fehlt oder ist nicht eindeutig.")
    account = await _existing_account(session, cid, iban) if (iban and cid) else None
    return {
        "protocol_id": p.id,
        "contract_id": p.contract_id,
        "deposit_id": deposit.id if deposit is not None else None,
        "deposit_status": deposit.status if deposit is not None else None,
        "deposit_amount_due": deposit.amount_due if deposit is not None else None,
        "protocol_deposit_amount": p.deposit_amount,
        "difference": difference,
        "iban_suffix": iban[-4:] if iban else None,
        "contact_id": cid,
        "bank_account_id": account.id if account is not None else None,
        "bank_account_approval": (
            str(account.approval_status.value) if account is not None else None
        ),
        "hints": hints,
        "draft_only": True,
    }


async def link(
    session: AsyncSession,
    p: HandoverProtocol,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Hand the refund IBAN to the four eyes release; returns the new state."""
    if p.status != "completed":
        raise ProblemError(ErrorCodes.CONFLICT, detail="Erst nach dem Abschluss verknüpfen.")
    iban = _normalised_iban(p)
    if iban is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine gültige Rückzahlungs-IBAN.")
    cid = await _contact_id(session, p, contact_id)
    if cid is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Kontakt des ausziehenden Mieters fehlt oder ist nicht eindeutig.",
        )
    created = False
    if await _existing_account(session, cid, iban) is None:
        from mhvp.contacts import schemas, services
        from mhvp.contacts.models import Contact
        from mhvp.core.clock import local_today

        contact = await session.get(Contact, cid)
        if contact is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await services.add_bank_account(
            session,
            contact,
            schemas.BankAccountIn(
                label="Kautionsrückzahlung (Übergabeprotokoll)",
                iban=iban,
                bic=p.deposit_bic or None,
                bank_name=p.deposit_bank_name,
                holder=p.deposit_account_holder,
                valid_from=p.handover_date or local_today(),
            ),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
        )
        created = True
    return await state(session, p, cid) | {"bank_account_created": created}
