"""Owner portal, read only (section 14 role owner, A51): resolution collection of the own
community, contact persons of the property and the owner's hoa fee account.

Every endpoint requires the portal role ``owner`` (an active grant with legal basis
``hoa_member_right``, 6.9.6); tenants, providers and staff accounts are answered with 403.
Scope is derived from the existing grants only, never from a client supplied id. RLS applies
through ``tenant_tx``. No endpoint opens a gate: the hoa fee account shows posted journal
lines of the community's ledger as information, it is no statement and has no legal effect.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access
from mhvp.portal.models import PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])

OWNER_BASIS = "hoa_member_right"
# Property contact categories shown to owners (6.2 property_contact.category): caretaker and
# emergency service. Board members and utilities stay out of this list.
CONTACT_CATEGORIES = ("caretaker", "emergency")
HOA_ACCOUNT_NOTE = (
    "Kontoübersicht aus gebuchten Einträgen des Buchungskreises der Gemeinschaft. "
    "Keine Abrechnung, keine Rechtsfolge; maßgeblich sind Wirtschaftsplan, "
    "Jahresabrechnung und Beschlüsse."
)
NO_LEDGER_NOTE = "Für diese Gemeinschaft ist noch kein Buchungskreis eingerichtet."
LEGACY_NOTE = "Vorläufig: Die führende Buchhaltung ist noch das Altsystem."


async def _owner_scope(
    session: AsyncSession, account: PortalAccount, today: date
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """(hoa legal entity ids, ownership contract ids) of the active owner grants; 403 when
    the account holds no owner grant at all."""
    from mhvp.contracts.models import Contract, ContractKind

    active = await access.grants(session, account, today)
    hoa_ids = {g.scope_id for g in active if g.legal_basis == OWNER_BASIS}
    if not hoa_ids:
        raise ProblemError(ErrorCodes.FORBIDDEN, detail="Nur für Eigentümer verfügbar.")
    contract_ids = {g.scope_id for g in active if g.scope_type == "contract"}
    ownership = set(
        await session.scalars(
            select(Contract.id).where(
                Contract.id.in_(contract_ids),
                Contract.kind == ContractKind.OWNERSHIP,
                Contract.legal_entity_id.in_(hoa_ids),
            )
        )
        if contract_ids
        else []
    )
    return hoa_ids, ownership


def _votes_summary(votes: dict[str, Any]) -> dict[str, Any] | None:
    """Result of the vote as announced (meeting) or the text form consents (circular);
    externally captured resolutions carry no tally."""
    if not votes:
        return None
    if "consents" in votes:
        consents = votes.get("consents") or {}
        return {
            "principle": "text_form",
            "yes": str(sum(1 for v in consents.values() if v == "yes")),
            "no": str(sum(1 for v in consents.values() if v == "no")),
            "abstain": str(sum(1 for v in consents.values() if v == "abstain")),
        }
    if "yes" in votes:
        return {
            "principle": votes.get("principle"),
            "yes": votes.get("yes"),
            "no": votes.get("no"),
            "abstain": votes.get("abstain"),
        }
    return None


@router.get("/resolutions", summary="Beschluss-Sammlung der eigenen Gemeinschaft (Eigentümer)")
async def resolutions(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    """Announced resolutions only: a resolution row exists once a result was announced
    (``/hoa/agenda/{id}/announce``), a circular resolution was recorded or an external
    resolution was captured. Tallies without announcement are proposals and never listed."""
    from mhvp.hoa.models import Resolution
    from mhvp.properties.models import LegalEntity

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ = await _owner_scope(session, account, local_today())
        names: dict[uuid.UUID, str] = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(LegalEntity.id, LegalEntity.name).where(LegalEntity.id.in_(hoa_ids))
                )
            ).all()
        }
        rows = await session.scalars(
            select(Resolution)
            .where(Resolution.legal_entity_id.in_(hoa_ids))
            .order_by(Resolution.decided_on.desc(), Resolution.number.desc())
        )
        return [
            {
                "id": r.id,
                "number": r.number,
                "decided_on": r.decided_on,
                "subject": r.subject,
                "wording": r.wording,
                "status": r.status,
                "kind": r.kind,
                "majority_basis": r.majority_basis,
                "votes": _votes_summary(r.votes or {}),
                "legal_entity_name": names.get(r.legal_entity_id),
            }
            for r in rows.all()
        ]


@router.get("/property-contacts", summary="Ansprechpartner des Objekts (Eigentümer)")
async def property_contacts(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    """Per property of the own ownership contracts: the responsible manager
    (``Property.manager_user_id``, display name only) and the property contacts of the
    categories caretaker and emergency that are released for owners in the master data
    (``visible_in_portal_for``). Private phone numbers are never returned."""
    from mhvp.contacts.models import Contact, ContactPhone, PhoneLabel
    from mhvp.contracts.models import Contract
    from mhvp.platform.models import User
    from mhvp.properties.models import Property, PropertyContact

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, today)
        property_ids = set(
            await session.scalars(select(Contract.property_id).where(Contract.id.in_(ownership)))
            if ownership
            else []
        )
        out: list[dict[str, Any]] = []
        for prop in (
            (
                await session.scalars(
                    select(Property).where(Property.id.in_(property_ids)).order_by(Property.number)
                )
            ).all()
            if property_ids
            else []
        ):
            manager = (
                await session.scalar(
                    select(User.display_name).where(User.id == prop.manager_user_id)
                )
                if prop.manager_user_id is not None
                else None
            )
            links = (
                await session.scalars(
                    select(PropertyContact)
                    .where(
                        PropertyContact.property_id == prop.id,
                        PropertyContact.category_code.in_(CONTACT_CATEGORIES),
                        PropertyContact.visible_in_portal_for.contains(["owner"]),
                        PropertyContact.valid_from <= today,
                        or_(PropertyContact.valid_to.is_(None), PropertyContact.valid_to >= today),
                    )
                    .order_by(PropertyContact.category_code)
                )
            ).all()
            contacts: list[dict[str, Any]] = []
            for link in links:
                contact = await session.get(Contact, link.contact_id)
                if contact is None or contact.deleted_at is not None:
                    continue
                phones = (
                    await session.scalars(
                        select(ContactPhone.number)
                        .where(
                            ContactPhone.contact_id == contact.id,
                            ContactPhone.label != PhoneLabel.PRIVATE,
                        )
                        .order_by(ContactPhone.is_primary.desc(), ContactPhone.number)
                    )
                ).all()
                contacts.append(
                    {
                        "category": link.category_code,
                        "name": contact.display_name,
                        "phones": list(phones),
                    }
                )
            address = " ".join(p for p in (prop.street, prop.house_number) if p)
            town = " ".join(p for p in (prop.postal_code, prop.city) if p)
            out.append(
                {
                    "property_id": prop.id,
                    "property_number": prop.number,
                    "property_name": prop.name,
                    "address": ", ".join(p for p in (address, town) if p) or None,
                    "manager_name": manager,
                    "contacts": contacts,
                }
            )
        return out


@router.get("/hoa-account", summary="Hausgeldkonto des Eigentümers (nur gebuchte Einträge)")
async def hoa_account(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    """Posted journal lines on the owner's debtor account in the ledger of the community
    (legal entity kind hoa, 6.9.1): debits are charges (Sollstellungen), credits are payments
    or credit notes; balance = debits minus credits (positive: amount owed). Drafts are never
    shown. Without a ledger the contract is listed with a note and no amounts."""
    from mhvp.accounting.models import (
        EntryStatus,
        JournalEntry,
        JournalLine,
        LeadingSystem,
        Ledger,
        LedgerAccount,
    )
    from mhvp.contracts.models import Contract, DebtorAccountReservation

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, local_today())
        contracts: list[dict[str, Any]] = []
        legacy = False
        for contract in (
            (
                await session.scalars(
                    select(Contract).where(Contract.id.in_(ownership)).order_by(Contract.number)
                )
            ).all()
            if ownership
            else []
        ):
            ledger = await session.scalar(
                select(Ledger).where(Ledger.legal_entity_id == contract.legal_entity_id)
            )
            reservation = await session.get(DebtorAccountReservation, contract.debtor_account_id)
            debtor = (
                await session.scalar(
                    select(LedgerAccount).where(
                        LedgerAccount.ledger_id == ledger.id,
                        LedgerAccount.number == reservation.number,
                    )
                )
                if ledger is not None and reservation is not None
                else None
            )
            if ledger is None or debtor is None:
                contracts.append(
                    {
                        "contract_number": contract.number,
                        "entries": [],
                        "charges": None,
                        "credits": None,
                        "balance": None,
                        "note": NO_LEDGER_NOTE,
                    }
                )
                continue
            legacy = legacy or ledger.leading_system is LeadingSystem.IMMOWARE24
            rows = (
                await session.execute(
                    select(JournalEntry, JournalLine)
                    .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
                    .where(
                        JournalLine.account_id == debtor.id,
                        JournalEntry.status == EntryStatus.POSTED,
                    )
                    .order_by(JournalEntry.booking_date, JournalEntry.number, JournalLine.line_no)
                )
            ).all()
            charges = Decimal("0.00")
            credits = Decimal("0.00")
            entries: list[dict[str, Any]] = []
            for entry, line in rows:
                charges += line.debit
                credits += line.credit
                entries.append(
                    {
                        "booking_date": entry.booking_date,
                        "due_date": entry.due_date,
                        "text": entry.text,
                        "kind": entry.kind.value,
                        "direction": "charge" if line.debit > 0 else "credit",
                        "amount": line.debit if line.debit > 0 else line.credit,
                        "reversed": entry.reversed_by_id is not None,
                    }
                )
            contracts.append(
                {
                    "contract_number": contract.number,
                    "entries": entries,
                    "charges": charges,
                    "credits": credits,
                    "balance": charges - credits,
                    "note": None,
                }
            )
        return {
            "contracts": contracts,
            "note": HOA_ACCOUNT_NOTE,
            "legacy_note": LEGACY_NOTE if legacy else None,
        }
