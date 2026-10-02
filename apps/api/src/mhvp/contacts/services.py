"""Contact services: create/replace with children, search text, duplicates, export."""

import calendar
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, String, cast, delete, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts import schemas
from mhvp.contacts.models import (
    BankAccountApproval,
    BankAccountChangeKind,
    Consent,
    Contact,
    ContactAddress,
    ContactBankAccount,
    ContactBankAccountChange,
    ContactDate,
    ContactEmail,
    ContactIdentifier,
    ContactKind,
    ContactMandateStatus,
    ContactNote,
    ContactPhone,
    ContactRelation,
    ContactTag,
    ContactTagLink,
    ContactType,
    ContactTypeCode,
    Party,
    PartyMember,
    PartyRole,
)
from mhvp.contacts.validation import mask_iban, normalise_iban, normalise_phone
from mhvp.contracts.models import Contract
from mhvp.core import crypto
from mhvp.core.events import DomainEvent, emit
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.documents.models import RetentionProfile, RetentionStart
from mhvp.objektakte.models import ObjektakteAssignment
from mhvp.properties.models import LegalEntity, Property, PropertyContact, PropertyOwner, Unit

_CHILDREN = (
    ContactAddress,
    ContactPhone,
    ContactEmail,
    ContactIdentifier,
    ContactDate,
    ContactBankAccount,
    ContactType,
    ContactTagLink,
)


def display_name(data: schemas.ContactIn) -> str:
    if data.kind is ContactKind.COMPANY:
        return (data.company_name or "").strip()
    last = (data.last_name or "").strip()
    first = " ".join(p for p in (data.title, data.first_name) if p).strip()
    return f"{last}, {first}" if last and first else (last or first)


def build_search_text(data: schemas.ContactIn, iban_suffixes: list[str] | None = None) -> str:
    parts: list[str] = [
        data.first_name or "",
        data.last_name or "",
        data.company_name or "",
        *(e.email for e in data.emails),
        *(p.number for p in data.phones),
        *(p.number.lstrip("+") for p in data.phones),
        *(
            (iban_suffixes or [])
            if data.bank_accounts is None
            else [b.iban[-4:] for b in data.bank_accounts]
        ),
        *(a.city or "" for a in data.addresses),
    ]
    return " ".join(p for p in parts if p).lower()


async def _tag_ids(
    session: AsyncSession, tenant_id: uuid.UUID, names: list[str]
) -> list[uuid.UUID]:
    ids = []
    for raw in sorted({n.strip() for n in names if n.strip()}):
        tag = await session.scalar(select(ContactTag).where(ContactTag.name == raw))
        if tag is None:
            tag = ContactTag(tenant_id=tenant_id, name=raw[:63])
            session.add(tag)
            await session.flush()
        ids.append(tag.id)
    return ids


def _single_primary(items: list[Any]) -> None:
    primaries = [i for i in items if i.is_primary]
    if not primaries and items:
        items[0].is_primary = True
    for extra in primaries[1:]:
        extra.is_primary = False


async def write_children(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    data: schemas.ContactIn,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> list[str]:
    """Returns mandate reference values for which the IBAN changed while the mandate was
    still active, so the caller can add a note and emit an event (M3-02).

    Bank accounts are rewritten as a whole. An IBAN that already existed on the contact keeps
    its release state; every new or changed IBAN starts as pending with ``actor_user_id`` as
    requester and needs a second person's release (M5-01, ``bank_account.pending``)."""
    changed_mandate_references: list[str] = []
    reject_b2b_mandates(data.bank_accounts or [])
    # fingerprint -> (approval_status, requested_by, decided_by, decided_at) before rewrite
    carried: dict[str, tuple[Any, ...]] = {}
    if data.bank_accounts is not None:
        for old in (
            await session.execute(
                select(
                    ContactBankAccount.iban_fingerprint,
                    ContactBankAccount.approval_status,
                    ContactBankAccount.requested_by,
                    ContactBankAccount.decided_by,
                    ContactBankAccount.decided_at,
                ).where(ContactBankAccount.contact_id == contact_id)
            )
        ).all():
            carried.setdefault(old[0], tuple(old[1:]))
    if data.bank_accounts is not None:
        previous = (
            await session.execute(
                select(
                    ContactBankAccount.mandate_reference,
                    ContactBankAccount.iban_fingerprint,
                ).where(
                    ContactBankAccount.contact_id == contact_id,
                    ContactBankAccount.sepa_enabled.is_(True),
                    ContactBankAccount.mandate_status == ContactMandateStatus.ACTIVE,
                    ContactBankAccount.mandate_reference.is_not(None),
                )
            )
        ).all()
        previous_fingerprints = {row.mandate_reference: row.iban_fingerprint for row in previous}
        for account in data.bank_accounts:
            if not account.sepa_enabled or not account.mandate_reference:
                continue
            old_fingerprint = previous_fingerprints.get(account.mandate_reference)
            new_fingerprint = crypto.fingerprint(account.iban)
            if old_fingerprint is not None and old_fingerprint != new_fingerprint:
                changed_mandate_references.append(account.mandate_reference)
    for model in _CHILDREN:
        if model is ContactBankAccount and data.bank_accounts is None:
            continue  # omitted: bank accounts stay as they are (ids referenced by mandates)
        if model is ContactBankAccount:
            await _check_accounts_unreferenced(session, contact_id)
            await _check_no_pending_changes(session, contact_id)
        await session.execute(delete(model).where(model.contact_id == contact_id))
    _single_primary(data.addresses)
    _single_primary(data.phones)
    _single_primary(data.emails)
    common = {"tenant_id": tenant_id, "contact_id": contact_id}
    for address in data.addresses:
        session.add(ContactAddress(**common, **address.model_dump()))
    for phone in data.phones:
        session.add(ContactPhone(**common, **phone.model_dump()))
    for email in data.emails:
        session.add(ContactEmail(**common, **email.model_dump()))
    for identifier in data.identifiers:
        session.add(ContactIdentifier(**common, **identifier.model_dump()))
    for item in data.dates:
        session.add(ContactDate(**common, kind=item.kind, value=item.date, note=item.note))
    pending: list[ContactBankAccount] = []
    for account in data.bank_accounts or []:
        values = account.model_dump()
        fingerprint = crypto.fingerprint(account.iban)
        row = ContactBankAccount(
            **common,
            **values,
            iban_suffix=account.iban[-4:],
            iban_fingerprint=fingerprint,
        )
        previous_state = carried.get(fingerprint)
        if previous_state is not None:
            row.approval_status, row.requested_by, row.decided_by, row.decided_at = previous_state
        else:
            row.approval_status = BankAccountApproval.PENDING
            row.requested_by = actor_user_id
            pending.append(row)
        session.add(row)
    for type_code in sorted(set(data.types)):
        session.add(ContactType(**common, type=type_code, source="manual"))
    for tag_id in await _tag_ids(session, tenant_id, data.tags):
        session.add(ContactTagLink(**common, tag_id=tag_id))
    await session.flush()
    for row in pending:
        await emit(
            session,
            tenant_id=tenant_id,
            type="bank_account.pending",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=actor_user_id,
            payload={"bank_account_id": str(row.id), "iban_suffix": row.iban_suffix},
        )
    return changed_mandate_references


def approval_block_reason(account: Any) -> str | None:
    """Why a contact bank account may not be used for mandates or payments yet (M5-01)."""
    status = getattr(account, "approval_status", None)
    if status == BankAccountApproval.APPROVED:
        return None
    if status == BankAccountApproval.REJECTED:
        return "Bankverbindung abgelehnt (Vier-Augen-Freigabe)"
    return "Bankverbindung noch nicht freigegeben (Vier-Augen-Freigabe)"


async def decide_bank_account(
    session: AsyncSession,
    account: ContactBankAccount,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    approve: bool,
    is_platform_admin: bool = False,
    reason: str | None = None,
) -> str | None:
    """Second person releases or rejects a pending IBAN; the requester never decides (M5-01).

    A released row that replaces another account (CRM change, ``replaces_account_id``) ends
    the old row the day before its own ``valid_from`` and takes over the default flag. Returns
    the mandate reference of the replaced account when that account carried an active SEPA
    mandate, so the caller can add the note of M3-02."""
    if account.approval_status != BankAccountApproval.PENDING:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Bankverbindung wartet nicht auf eine Freigabe."
        )
    _check_second_person(account.requested_by, actor_user_id, is_platform_admin)
    account.approval_status = (
        BankAccountApproval.APPROVED if approve else BankAccountApproval.REJECTED
    )
    account.decided_by = actor_user_id
    account.decided_at = datetime.now(UTC)
    account.rejected_reason = None if approve else (reason or None)
    payload: dict[str, Any] = {
        "bank_account_id": str(account.id),
        "iban_suffix": account.iban_suffix,
        "requested_by": str(account.requested_by) if account.requested_by else None,
    }
    if reason:
        payload["reason"] = reason
    changed_mandate_reference: str | None = None
    if approve and account.replaces_account_id is not None:
        old = await session.get(ContactBankAccount, account.replaces_account_id)
        if old is not None and old.contact_id == account.contact_id:
            end = account.valid_from - timedelta(days=1)
            if old.valid_to is None or old.valid_to > end:
                old.valid_to = end
            if old.is_default:
                old.is_default = False
                await session.flush()  # partial unique index: one default per contact
                account.is_default = True
            if (
                old.sepa_enabled
                and old.mandate_status == ContactMandateStatus.ACTIVE
                and old.mandate_reference
            ):
                changed_mandate_reference = old.mandate_reference
            payload["replaces_account_id"] = str(old.id)
            payload["replaced_valid_to"] = old.valid_to.isoformat() if old.valid_to else None
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.approved" if approve else "bank_account.rejected",
        entity_type="contact",
        entity_id=account.contact_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    await session.flush()
    return changed_mandate_reference


def _check_second_person(
    requested_by: uuid.UUID | None, actor_user_id: uuid.UUID | None, is_platform_admin: bool
) -> None:
    """Four eyes (M5-01): the requester, a platform admin and a call without user never
    decide."""
    if actor_user_id is None or is_platform_admin or requested_by == actor_user_id:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die Freigabe muss eine andere Person als die erfassende vornehmen.",
        )


# Bankverbindungen am Kontakt (CRM screen, M5-01 addendum 28.09.2026) ---------------------


async def is_legal_entity_contact(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    """True when the contact stands for a legal entity of section 6.9.1: it is a member of
    the party of a ``legal_entity`` (GdWE, rental owner, SEV owner) or carries the contact
    type ``manager`` (the management company itself). Their bank account changes always need
    a second person, whoever proposes them."""
    linked = await session.scalar(
        select(LegalEntity.id)
        .join(PartyMember, PartyMember.party_id == LegalEntity.party_id)
        .where(PartyMember.contact_id == contact_id)
        .limit(1)
    )
    if linked is not None:
        return True
    manager = await session.scalar(
        select(ContactType.id)
        .where(ContactType.contact_id == contact_id, ContactType.type == ContactTypeCode.MANAGER)
        .limit(1)
    )
    return manager is not None


def _is_ended(account: ContactBankAccount, today: date) -> bool:
    return account.approval_status == BankAccountApproval.REJECTED or (
        account.valid_to is not None and account.valid_to < today
    )


async def _pending_change(
    session: AsyncSession, account_id: uuid.UUID
) -> ContactBankAccountChange | None:
    row: ContactBankAccountChange | None = await session.scalar(
        select(ContactBankAccountChange).where(
            ContactBankAccountChange.bank_account_id == account_id,
            ContactBankAccountChange.status == BankAccountApproval.PENDING,
        )
    )
    return row


async def _pending_replacement(session: AsyncSession, account_id: uuid.UUID) -> bool:
    row = await session.scalar(
        select(ContactBankAccount.id).where(
            ContactBankAccount.replaces_account_id == account_id,
            ContactBankAccount.approval_status == BankAccountApproval.PENDING,
        )
    )
    return row is not None


async def _check_no_pending(session: AsyncSession, account: ContactBankAccount) -> None:
    if account.approval_status == BankAccountApproval.PENDING:
        raise ProblemError(
            ErrorCodes.CONTACT_BANK_CHANGE_PENDING,
            detail="Die Bankverbindung selbst wartet noch auf ihre Freigabe.",
        )
    if await _pending_change(session, account.id) is not None or await _pending_replacement(
        session, account.id
    ):
        raise ProblemError(ErrorCodes.CONTACT_BANK_CHANGE_PENDING)


def _add_search_suffix(contact: Contact, suffix: str) -> None:
    """Keep the IBAN suffix searchable (``build_search_text`` on PUT does the same)."""
    if suffix.lower() not in (contact.search_text or "").split():
        contact.search_text = f"{contact.search_text or ''} {suffix.lower()}".strip()


async def _clear_default(session: AsyncSession, contact_id: uuid.UUID) -> None:
    for row in await session.scalars(
        select(ContactBankAccount).where(
            ContactBankAccount.contact_id == contact_id, ContactBankAccount.is_default.is_(True)
        )
    ):
        row.is_default = False
    await session.flush()


def reject_b2b_mandates(accounts: list[schemas.BankAccountIn]) -> None:
    """B2B mandates are refused on capture (GAA-05): the platform has no B2B collection run
    (other lead time, no refund right) and the legal and bank agreement is open (AF07-01)."""
    from mhvp.contacts.models import MandateScheme

    for i, account in enumerate(accounts):
        if account.mandate_scheme is MandateScheme.B2B:
            raise ProblemError(
                ErrorCodes.CONTACT_MANDATE_B2B_UNSUPPORTED,
                errors=[
                    FieldError(
                        location=["body", "mandate_scheme"],
                        field="mandate_scheme",
                        code="unsupported",
                        message=f"Bankverbindung {i + 1}: B2B wird nicht unterstützt",
                    )
                ],
            )


async def add_bank_account(
    session: AsyncSession,
    contact: Contact,
    data: schemas.BankAccountIn,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    replaces: ContactBankAccount | None = None,
) -> ContactBankAccount:
    """New bank account on an existing contact, always ``pending`` for a second person
    (M5-01). With ``replaces`` the row is the new version of that account: the old row keeps
    its IBAN and gets ``valid_to`` on release, never before."""
    reject_b2b_mandates([data])
    fingerprint = crypto.fingerprint(data.iban)
    duplicate = await session.scalar(
        select(ContactBankAccount.id).where(
            ContactBankAccount.contact_id == contact.id,
            ContactBankAccount.iban_fingerprint == fingerprint,
            ContactBankAccount.approval_status != BankAccountApproval.REJECTED,
        )
    )
    if duplicate is not None:
        raise ProblemError(ErrorCodes.CONTACT_BANK_ACCOUNT_DUPLICATE)
    values = data.model_dump()
    if replaces is not None:
        if replaces.contact_id != contact.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if _is_ended(replaces, datetime.now(UTC).date()):
            raise ProblemError(ErrorCodes.CONTACT_BANK_ACCOUNT_ENDED)
        await _check_no_pending(session, replaces)
        if data.valid_from <= replaces.valid_from:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Gültig ab der neuen Version muss nach Gültig ab der bisherigen liegen.",
                errors=[
                    FieldError(
                        location=["body", "valid_from"],
                        field="valid_from",
                        code="invalid",
                        message="liegt nicht nach der bisherigen Version",
                    )
                ],
            )
        values["is_default"] = False  # handed over on release
    elif data.is_default:
        await _clear_default(session, contact.id)
    row = ContactBankAccount(
        tenant_id=tenant_id,
        contact_id=contact.id,
        **values,
        iban_suffix=data.iban[-4:],
        iban_fingerprint=fingerprint,
        approval_status=BankAccountApproval.PENDING,
        requested_by=actor_user_id,
        replaces_account_id=replaces.id if replaces is not None else None,
        created_by=actor_user_id,
    )
    session.add(row)
    _add_search_suffix(contact, row.iban_suffix)
    contact.version += 1
    contact.updated_by = actor_user_id
    await session.flush()
    payload: dict[str, Any] = {
        "bank_account_id": str(row.id),
        "iban_suffix": row.iban_suffix,
        "source": "crm",
    }
    if replaces is not None:
        payload["replaces_account_id"] = str(replaces.id)
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.pending",
        entity_type="contact",
        entity_id=contact.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    return row


async def end_bank_account(
    session: AsyncSession,
    contact: Contact,
    account: ContactBankAccount,
    data: schemas.BankAccountEndIn,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    can_approve: bool,
    is_platform_admin: bool,
) -> ContactBankAccountChange | None:
    """Set ``valid_to`` on an existing account. Applied at once only when the requester
    holds ``contacts:approve``, is a tenant user (no platform admin) and the contact is no
    legal entity; otherwise a pending change is stored for a second person and returned.
    The IBAN row itself is never deleted."""
    if account.contact_id != contact.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    today = datetime.now(UTC).date()
    if _is_ended(account, today):
        raise ProblemError(ErrorCodes.CONTACT_BANK_ACCOUNT_ENDED)
    await _check_no_pending(session, account)
    if data.valid_to < account.valid_from:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Gültig bis liegt vor Gültig ab.",
            errors=[
                FieldError(
                    location=["body", "valid_to"],
                    field="valid_to",
                    code="invalid",
                    message="liegt vor Gültig ab",
                )
            ],
        )
    four_eyes = (
        not can_approve
        or is_platform_admin
        or actor_user_id is None
        or await is_legal_entity_contact(session, contact.id)
    )
    payload: dict[str, Any] = {
        "bank_account_id": str(account.id),
        "iban_suffix": account.iban_suffix,
        "valid_to": data.valid_to.isoformat(),
    }
    if data.note:
        payload["note"] = data.note
    if not four_eyes:
        account.valid_to = data.valid_to
        account.updated_by = actor_user_id
        contact.version += 1
        contact.updated_by = actor_user_id
        await emit(
            session,
            tenant_id=tenant_id,
            type="bank_account.ended",
            entity_type="contact",
            entity_id=contact.id,
            actor_user_id=actor_user_id,
            payload=payload,
        )
        await session.flush()
        return None
    change = ContactBankAccountChange(
        tenant_id=tenant_id,
        contact_id=contact.id,
        bank_account_id=account.id,
        kind=BankAccountChangeKind.END,
        valid_to=data.valid_to,
        note=data.note,
        status=BankAccountApproval.PENDING,
        requested_by=actor_user_id,
        created_by=actor_user_id,
    )
    session.add(change)
    await session.flush()
    payload["change_id"] = str(change.id)
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.end_requested",
        entity_type="contact",
        entity_id=contact.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    return change


async def decide_bank_account_change(
    session: AsyncSession,
    change: ContactBankAccountChange,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    approve: bool,
    is_platform_admin: bool = False,
    reason: str | None = None,
) -> None:
    """Second person confirms or rejects a pending change (end); same four eyes rules as
    the IBAN release."""
    if change.status != BankAccountApproval.PENDING:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Änderung wartet nicht auf eine Freigabe."
        )
    _check_second_person(change.requested_by, actor_user_id, is_platform_admin)
    account = await session.get(ContactBankAccount, change.bank_account_id)
    if account is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    change.status = BankAccountApproval.APPROVED if approve else BankAccountApproval.REJECTED
    change.decided_by = actor_user_id
    change.decided_at = datetime.now(UTC)
    change.rejected_reason = None if approve else (reason or None)
    change.updated_by = actor_user_id
    if approve and change.kind is BankAccountChangeKind.END:
        account.valid_to = change.valid_to
        account.updated_by = actor_user_id
    payload: dict[str, Any] = {
        "change_id": str(change.id),
        "kind": change.kind.value,
        "bank_account_id": str(account.id),
        "iban_suffix": account.iban_suffix,
        "valid_to": change.valid_to.isoformat(),
        "requested_by": str(change.requested_by) if change.requested_by else None,
    }
    if reason:
        payload["reason"] = reason
    await emit(
        session,
        tenant_id=tenant_id,
        type="bank_account.end_approved" if approve else "bank_account.end_rejected",
        entity_type="contact",
        entity_id=change.contact_id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    await session.flush()


def bank_account_change_out(c: ContactBankAccountChange) -> schemas.BankAccountChangeOut:
    return schemas.BankAccountChangeOut(
        id=c.id,
        bank_account_id=c.bank_account_id,
        kind=c.kind,
        valid_to=c.valid_to,
        note=c.note,
        status=c.status,
        requested_by=c.requested_by,
        decided_by=c.decided_by,
        decided_at=c.decided_at,
        rejected_reason=c.rejected_reason,
        created_at=c.created_at,
    )


async def pending_changes(
    session: AsyncSession, contact_id: uuid.UUID
) -> dict[uuid.UUID, ContactBankAccountChange]:
    rows = await session.scalars(
        select(ContactBankAccountChange).where(
            ContactBankAccountChange.contact_id == contact_id,
            ContactBankAccountChange.status == BankAccountApproval.PENDING,
        )
    )
    return {row.bank_account_id: row for row in rows}


async def _check_accounts_unreferenced(session: AsyncSession, contact_id: uuid.UUID) -> None:
    from mhvp.contracts.models import SepaMandate  # local: contracts import contacts

    used = await session.scalar(
        select(SepaMandate.id)
        .join(ContactBankAccount, ContactBankAccount.id == SepaMandate.contact_bank_account_id)
        .where(ContactBankAccount.contact_id == contact_id)
        .limit(1)
    )
    if used is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=(
                "Eine Bankverbindung ist mit einem SEPA-Mandat verknüpft und kann nicht "
                "ersetzt werden. Bankverbindungen beim Ändern weglassen."
            ),
        )


async def _check_no_pending_changes(session: AsyncSession, contact_id: uuid.UUID) -> None:
    """A PUT rewrite deletes and recreates the bank account rows; that would cascade delete
    a pending end request and drop ``replaces_account_id`` of a pending new version, so a
    four eyes request of the CRM screen (M5-01 addendum) would vanish without a decision.
    Refused until the second person has decided."""
    pending_change = await session.scalar(
        select(ContactBankAccountChange.id)
        .where(
            ContactBankAccountChange.contact_id == contact_id,
            ContactBankAccountChange.status == BankAccountApproval.PENDING,
        )
        .limit(1)
    )
    pending_replacement = await session.scalar(
        select(ContactBankAccount.id)
        .where(
            ContactBankAccount.contact_id == contact_id,
            ContactBankAccount.replaces_account_id.is_not(None),
            ContactBankAccount.approval_status == BankAccountApproval.PENDING,
        )
        .limit(1)
    )
    if pending_change is not None or pending_replacement is not None:
        raise ProblemError(
            ErrorCodes.CONTACT_BANK_CHANGE_PENDING,
            detail=(
                "Eine Bankverbindung dieses Kontakts wartet auf die Freigabe einer Änderung; "
                "erst entscheiden, dann Bankverbindungen neu schreiben oder beim Ändern "
                "weglassen."
            ),
        )


async def iban_suffixes(session: AsyncSession, contact_id: uuid.UUID) -> list[str]:
    rows = await session.scalars(
        select(ContactBankAccount.iban_suffix).where(ContactBankAccount.contact_id == contact_id)
    )
    return list(rows.all())


def apply_fields(
    contact: Contact, data: schemas.ContactIn, suffixes: list[str] | None = None
) -> None:
    fields = data.model_dump(
        exclude={
            "addresses",
            "phones",
            "emails",
            "identifiers",
            "dates",
            "bank_accounts",
            "types",
            "roles",
            "tags",
            "retention_profile_id",
        }
    )
    for key, value in fields.items():
        setattr(contact, key, value)
    # Block date (4.1): set when the block starts, cleared when it is lifted.
    if contact.blocked and contact.blocked_at is None:
        contact.blocked_at = datetime.now(UTC)
    elif not contact.blocked:
        contact.blocked_at = None
    contact.display_name = display_name(data)
    contact.search_text = build_search_text(data, suffixes)
    # Full replacement per the update semantics of this endpoint (rule 0.1.7 style updates
    # apply everywhere): the client always sends the roles it wants kept, including any
    # derived ones it saw in the previous GET. See recompute_derived_roles for how derived
    # roles are added automatically when a contract exists.
    contact.roles = sorted({r.value for r in data.roles})


def delete_after(
    profile: RetentionProfile | None, *, blocked_at: datetime | None, reference: date
) -> date | None:
    """Deletion reservation of a contact from its retention profile (4.1).

    Operator decision 26.09.2026: the date is a reservation only, shown as due; the deletion
    itself is a manual four eyes step on the existing deletion path, no automatic job. The period
    starts at the block date if the contact is blocked, otherwise at ``reference`` (the date of
    the assignment); ``end_of_year_*`` rules round the start up to 31.12. Permanent profiles
    yield no date."""
    if profile is None or profile.permanent:
        return None
    start = blocked_at.date() if blocked_at is not None else reference
    if profile.start_rule in (
        RetentionStart.END_OF_YEAR_CREATED,
        RetentionStart.END_OF_YEAR_LAST_ENTRY,
    ):
        start = date(start.year, 12, 31)
    months = start.month + profile.retention_months
    year = start.year + profile.retention_years + (months - 1) // 12
    month = (months - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def _retention_error(message: str) -> FieldError:
    return FieldError(
        location=["body", "retention_profile_id"],
        field="retention_profile_id",
        code="invalid",
        message=message,
    )


async def apply_retention(
    session: AsyncSession, contact: Contact, profile_id: uuid.UUID | None
) -> None:
    """Assigns the retention profile and recomputes ``delete_after``; only a released profile of
    the tenant is accepted (RLS scopes the lookup)."""
    profile: RetentionProfile | None = None
    if profile_id is not None:
        profile = await session.get(RetentionProfile, profile_id)
        if profile is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Löschprofil nicht gefunden",
                errors=[_retention_error("Löschprofil nicht gefunden")],
            )
        if profile.released_at is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Löschprofil ist nicht freigegeben",
                errors=[_retention_error("Löschprofil ist nicht freigegeben")],
            )
    contact.retention_profile_id = profile_id
    contact.delete_after = delete_after(
        profile, blocked_at=contact.blocked_at, reference=datetime.now(UTC).date()
    )


TENANCY_ROLE = "mieter"
OWNER_ROLE = "eigentuemer"


def derive_roles(contract_kinds: set[str], has_owner_link: bool) -> set[str]:
    """Map active contract kinds and ownership links to contact roles (6.9)."""
    derived: set[str] = set()
    if "tenancy" in contract_kinds:
        derived.add(TENANCY_ROLE)
    if "ownership" in contract_kinds or has_owner_link:
        derived.add(OWNER_ROLE)
    return derived


def merge_roles(current: list[str] | None, derived: set[str]) -> list[str]:
    """Add derived roles; manually set roles are never removed."""
    return sorted(set(current or []) | derived)


async def recompute_derived_roles(
    session: AsyncSession, contact: Contact, today: date | None = None
) -> bool:
    """Derive eigentuemer/mieter from active contracts and ownerships (6.9, task M3-01).

    Parties are resolved over party_member. A contract is active when end_date is null or
    not before today, a property owner when valid_to is null or not before today. Objektakte
    staging assignments (owner/tenant) count as well. Returns True when roles changed.
    """
    day = today or datetime.now(UTC).date()
    party_ids = select(PartyMember.party_id).where(PartyMember.contact_id == contact.id)
    kinds = {
        (k.value if hasattr(k, "value") else str(k))
        for k in (
            await session.scalars(
                select(Contract.kind)
                .where(
                    Contract.tenant_id == contact.tenant_id,
                    Contract.party_id.in_(party_ids),
                    or_(Contract.end_date.is_(None), Contract.end_date >= day),
                )
                .distinct()
            )
        ).all()
    }
    owner = await session.scalar(
        select(PropertyOwner.id)
        .where(
            PropertyOwner.tenant_id == contact.tenant_id,
            PropertyOwner.party_id.in_(party_ids),
            or_(PropertyOwner.valid_to.is_(None), PropertyOwner.valid_to >= day),
        )
        .limit(1)
    )
    for role in (
        await session.scalars(
            select(ObjektakteAssignment.role)
            .where(
                ObjektakteAssignment.tenant_id == contact.tenant_id,
                ObjektakteAssignment.contact_id == contact.id,
                or_(ObjektakteAssignment.valid_to.is_(None), ObjektakteAssignment.valid_to >= day),
            )
            .distinct()
        )
    ).all():
        kinds.add("tenancy" if str(getattr(role, "value", role)) == "tenant" else "ownership")
    merged = merge_roles(contact.roles, derive_roles(kinds, owner is not None))
    if merged == sorted(contact.roles or []):
        return False
    contact.roles = merged
    return True


async def recompute_for_contacts(
    session: AsyncSession, contact_ids: list[uuid.UUID] | set[uuid.UUID]
) -> int:
    changed = 0
    for contact_id in contact_ids:
        contact = await session.get(Contact, contact_id)
        if contact is not None and contact.deleted_at is None:
            changed += int(await recompute_derived_roles(session, contact))
    await session.flush()
    return changed


async def party_for_contact(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, contact_id: uuid.UUID
) -> Party:
    """The own party of a contact: the oldest party whose only member is this contact in role
    primary; created when missing. Contracts reference parties, never contacts (6.1), so
    screens that pick a contact (e.g. the acquirer of an ownership transfer) resolve it here.
    Joint parties (several members) are never returned or created."""
    contact: Contact | None = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
    single = (
        select(PartyMember.party_id)
        .group_by(PartyMember.party_id)
        .having(func.count(PartyMember.id) == 1)
    )
    party: Party | None = await session.scalar(
        select(Party)
        .join(PartyMember, PartyMember.party_id == Party.id)
        .where(
            PartyMember.contact_id == contact.id,
            PartyMember.role == PartyRole.PRIMARY,
            Party.id.in_(single),
        )
        .order_by(Party.created_at, Party.id)
        .limit(1)
    )
    if party is not None:
        return party
    party = Party(tenant_id=tenant_id, name=contact.display_name[:400], created_by=user_id)
    session.add(party)
    await session.flush()
    session.add(
        PartyMember(
            tenant_id=tenant_id, party_id=party.id, contact_id=contact.id, role=PartyRole.PRIMARY
        )
    )
    await session.flush()
    await recompute_for_party(session, party.id)
    return party


async def recompute_for_party(session: AsyncSession, party_id: uuid.UUID) -> int:
    ids = (
        await session.scalars(
            select(PartyMember.contact_id).where(PartyMember.party_id == party_id)
        )
    ).all()
    return await recompute_for_contacts(session, set(ids))


async def recompute_all(session: AsyncSession, tenant_id: uuid.UUID, batch: int = 500) -> int:
    """Backfill for the whole tenant, keyset paginated by id."""
    changed = 0
    last: uuid.UUID | None = None
    while True:
        stmt = (
            select(Contact)
            .where(Contact.tenant_id == tenant_id, Contact.deleted_at.is_(None))
            .order_by(Contact.id)
            .limit(batch)
        )
        if last is not None:
            stmt = stmt.where(Contact.id > last)
        rows = list((await session.scalars(stmt)).all())
        if not rows:
            break
        for contact in rows:
            changed += int(await recompute_derived_roles(session, contact))
        await session.flush()
        last = rows[-1].id
        if len(rows) < batch:
            break
    return changed


def is_active(valid_to: date | None, today: date) -> bool:
    return valid_to is None or valid_to >= today


def sort_relations(rows: list[schemas.ObjectRelationOut]) -> list[schemas.ObjectRelationOut]:
    """Active first, then valid_from descending (missing dates last)."""
    return sorted(
        rows,
        key=lambda r: (
            not r.active,
            -(r.valid_from.toordinal() if r.valid_from else 0),
            r.property_name,
        ),
    )


def _unit_label(unit: Unit | None) -> str | None:
    if unit is None:
        return None
    return f"{unit.number} {unit.label}".strip() if unit.label else unit.number


async def object_relations(
    session: AsyncSession, contact: Contact, today: date | None = None
) -> list[schemas.ObjectRelationOut]:
    """Contracts and ownerships over the contact's parties plus direct property contacts."""
    day = today or datetime.now(UTC).date()
    tenant = contact.tenant_id
    party_ids = select(PartyMember.party_id).where(
        PartyMember.contact_id == contact.id, PartyMember.tenant_id == tenant
    )
    out: list[schemas.ObjectRelationOut] = []
    contracts = (
        await session.execute(
            select(Contract, Property, Unit)
            .join(Property, Property.id == Contract.property_id)
            .outerjoin(Unit, Unit.id == Contract.unit_id)
            .where(Contract.tenant_id == tenant, Contract.party_id.in_(party_ids))
        )
    ).all()
    for contract, prop, unit in contracts:
        kind_value = getattr(contract.kind, "value", contract.kind)
        out.append(
            schemas.ObjectRelationOut(
                kind="mieter" if kind_value == "tenancy" else "eigentuemer",
                property_id=prop.id,
                property_name=prop.name,
                property_city=prop.city,
                unit_id=contract.unit_id,
                unit_label=_unit_label(unit),
                valid_from=contract.start_date,
                valid_to=contract.end_date,
                active=is_active(contract.end_date, day),
                source="contract",
                contract_id=contract.id,
            )
        )
    owners = (
        await session.execute(
            select(PropertyOwner, Property)
            .join(Property, Property.id == PropertyOwner.property_id)
            .where(PropertyOwner.tenant_id == tenant, PropertyOwner.party_id.in_(party_ids))
        )
    ).all()
    for owner, prop in owners:
        out.append(
            schemas.ObjectRelationOut(
                kind="eigentuemer",
                property_id=prop.id,
                property_name=prop.name,
                property_city=prop.city,
                valid_from=owner.valid_from,
                valid_to=owner.valid_to,
                active=is_active(owner.valid_to, day),
                source="property_owner",
            )
        )
    links = (
        await session.execute(
            select(PropertyContact, Property)
            .join(Property, Property.id == PropertyContact.property_id)
            .where(PropertyContact.tenant_id == tenant, PropertyContact.contact_id == contact.id)
        )
    ).all()
    for link, prop in links:
        out.append(
            schemas.ObjectRelationOut(
                kind="kontakt",
                property_id=prop.id,
                property_name=prop.name,
                property_city=prop.city,
                valid_from=link.valid_from,
                valid_to=link.valid_to,
                active=is_active(link.valid_to, day),
                source="property_contact",
                category_code=link.category_code,
            )
        )
    return sort_relations(out)


def bank_account_out(
    b: ContactBankAccount, pending_change: ContactBankAccountChange | None = None
) -> schemas.BankAccountOut:
    """API view of a contact bank account; ``rejected_*`` mirror the decision of a rejected
    row (M5-01, M19-05 addendum), so the CRM can show the reason without reading events."""
    rejected = b.approval_status == BankAccountApproval.REJECTED
    return schemas.BankAccountOut(
        id=b.id,
        label=b.label,
        kind=b.kind,
        is_default=bool(getattr(b, "is_default", False)),
        bank_contact_id=b.bank_contact_id,
        iban_masked=mask_iban(b.iban),
        bic=b.bic,
        bank_name=b.bank_name,
        holder=b.holder,
        valid_from=b.valid_from,
        valid_to=b.valid_to,
        sepa_enabled=b.sepa_enabled,
        mandate_reference=b.mandate_reference,
        mandate_signed_on=b.mandate_signed_on,
        mandate_granted_via=b.mandate_granted_via,
        mandate_note=b.mandate_note,
        mandate_document_id=b.mandate_document_id,
        mandate_scheme=b.mandate_scheme,
        mandate_status=b.mandate_status,
        mandate_revoked_on=b.mandate_revoked_on,
        approval_status=b.approval_status,
        requested_by=b.requested_by,
        decided_by=b.decided_by,
        decided_at=b.decided_at,
        rejected_reason=b.rejected_reason,
        rejected_by=b.decided_by if rejected else None,
        rejected_at=b.decided_at if rejected else None,
        replaces_account_id=b.replaces_account_id,
        pending_change=bank_account_change_out(pending_change) if pending_change else None,
    )


async def load(session: AsyncSession, contact_id: uuid.UUID) -> schemas.ContactOut | None:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        return None
    await session.flush()
    await session.refresh(contact)  # server side updated_at, version after writes

    async def rows(model: Any) -> list[Any]:
        return list(
            (await session.scalars(select(model).where(model.contact_id == contact_id))).all()
        )

    tags = list(
        (
            await session.scalars(
                select(ContactTag.name)
                .join(ContactTagLink, ContactTagLink.tag_id == ContactTag.id)
                .where(ContactTagLink.contact_id == contact_id)
                .order_by(ContactTag.name)
            )
        ).all()
    )
    changes = await pending_changes(session, contact_id)
    return schemas.ContactOut(
        id=contact.id,
        kind=contact.kind,
        display_name=contact.display_name,
        salutation=contact.salutation,
        letter_salutation=contact.letter_salutation,
        title=contact.title,
        first_name=contact.first_name,
        last_name=contact.last_name,
        company_name=contact.company_name,
        legal_form=contact.legal_form,
        position=contact.position,
        date_of_birth=contact.date_of_birth,
        language=contact.language,
        notes=contact.notes,
        preferred_channel=contact.preferred_channel,
        blocked=contact.blocked,
        is_consumer=contact.is_consumer,
        blocked_at=contact.blocked_at,
        retention_profile_id=contact.retention_profile_id,
        delete_after=contact.delete_after,
        external_ids=contact.external_ids,
        completeness=contact.completeness,
        addresses=[
            schemas.AddressOut.model_validate(a, from_attributes=True)
            for a in await rows(ContactAddress)
        ],
        phones=[
            schemas.PhoneOut.model_validate(p, from_attributes=True)
            for p in await rows(ContactPhone)
        ],
        emails=[
            schemas.EmailOut.model_validate(e, from_attributes=True)
            for e in await rows(ContactEmail)
        ],
        identifiers=[
            schemas.IdentifierOut.model_validate(i, from_attributes=True)
            for i in await rows(ContactIdentifier)
        ],
        dates=[
            schemas.ContactDateOut(id=d.id, kind=d.kind, date=d.value, note=d.note)
            for d in await rows(ContactDate)
        ],
        bank_accounts=[
            bank_account_out(b, changes.get(b.id)) for b in await rows(ContactBankAccount)
        ],
        types=sorted(t.type for t in await rows(ContactType)),
        roles=sorted(contact.roles),
        tags=tags,
        version=contact.version,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        deleted_at=contact.deleted_at,
    )


async def summaries(session: AsyncSession, contacts: list[Contact]) -> list[schemas.ContactSummary]:
    ids = [c.id for c in contacts]
    if not ids:
        return []
    # Primary email, phone, city, tags and types of all contacts in ONE statement (UNION ALL of
    # (kind, contact_id, value)) instead of five (performance review 26.09.2026).
    emails_q: Any = select(
        literal_column("'email'").label("kind"),
        ContactEmail.contact_id.label("contact_id"),
        ContactEmail.email.label("value"),
    ).where(ContactEmail.contact_id.in_(ids), ContactEmail.is_primary.is_(True))
    parts: Any = emails_q.union_all(
        select(literal_column("'phone'"), ContactPhone.contact_id, ContactPhone.number).where(
            ContactPhone.contact_id.in_(ids), ContactPhone.is_primary.is_(True)
        ),
        select(literal_column("'city'"), ContactAddress.contact_id, ContactAddress.city).where(
            ContactAddress.contact_id.in_(ids), ContactAddress.is_primary.is_(True)
        ),
        select(literal_column("'tag'"), ContactTagLink.contact_id, ContactTag.name)
        .join(ContactTag, ContactTag.id == ContactTagLink.tag_id)
        .where(ContactTagLink.contact_id.in_(ids)),
        select(
            literal_column("'type'"), ContactType.contact_id, cast(ContactType.type, String)
        ).where(ContactType.contact_id.in_(ids)),
        # One row per contact with at least one IBAN awaiting the four eyes release (M5-01),
        # so the list can show "IBAN wartet auf Freigabe" without a query per contact.
        select(
            literal_column("'iban_pending'"),
            ContactBankAccount.contact_id,
            literal_column("'1'"),
        )
        .where(
            ContactBankAccount.contact_id.in_(ids),
            ContactBankAccount.approval_status == BankAccountApproval.PENDING,
        )
        .distinct(),
    )
    emails: dict[uuid.UUID, str] = {}
    iban_pending: set[uuid.UUID] = set()
    phones: dict[uuid.UUID, str] = {}
    cities: dict[uuid.UUID, str] = {}
    tags: dict[uuid.UUID, list[str]] = {}
    types: dict[uuid.UUID, list[Any]] = {}
    for kind, contact_id, value in (await session.execute(parts)).all():
        if value is None:
            continue
        if kind == "email":
            emails[contact_id] = value
        elif kind == "phone":
            phones[contact_id] = value
        elif kind == "city":
            cities[contact_id] = value
        elif kind == "tag":
            tags.setdefault(contact_id, []).append(value)
        elif kind == "iban_pending":
            iban_pending.add(contact_id)
        else:
            types.setdefault(contact_id, []).append(ContactTypeCode(value))
    return [
        schemas.ContactSummary(
            id=c.id,
            kind=c.kind,
            display_name=c.display_name,
            primary_email=emails.get(c.id),
            primary_phone=phones.get(c.id),
            city=cities.get(c.id),
            completeness=c.completeness,
            blocked=c.blocked,
            tags=sorted(tags.get(c.id, [])),
            types=sorted(types.get(c.id, [])),
            roles=sorted(c.roles),
            deleted=c.deleted_at is not None,
            iban_pending=c.id in iban_pending,
        )
        for c in contacts
    ]


def tsquery(text: str) -> str | None:
    terms = re.findall(r"\w+", text.lower())[:8]
    return " & ".join(f"{t}:*" for t in terms) if terms else None


def search_filter(query: Select[Any], q: str) -> Select[Any]:
    ts = tsquery(q)
    like = f"%{q.strip().lower()}%"
    conditions = [Contact.search_text.like(like)]
    if ts:
        conditions.append(Contact.search_vector.op("@@")(func.to_tsquery("simple", ts)))
    return query.where(or_(*conditions))


async def find_duplicates(
    session: AsyncSession,
    probe: schemas.DuplicateQuery,
    *,
    exclude_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[tuple[Contact, float, list[str]]]:
    scores: dict[uuid.UUID, tuple[float, list[str]]] = {}

    def add(contact_id: uuid.UUID, score: float, reason: str) -> None:
        current, reasons = scores.get(contact_id, (0.0, []))
        scores[contact_id] = (max(current, score), [*reasons, reason])

    if probe.email:
        for (cid,) in (
            await session.execute(
                select(ContactEmail.contact_id).where(ContactEmail.email == probe.email.lower())
            )
        ).all():
            add(cid, 0.95, "gleiche E-Mail-Adresse")
    if probe.phone:
        try:
            number = normalise_phone(probe.phone)
        except ValueError:
            number = None
        if number:
            for (cid,) in (
                await session.execute(
                    select(ContactPhone.contact_id).where(ContactPhone.number == number)
                )
            ).all():
                add(cid, 0.9, "gleiche Telefonnummer")
    if probe.iban:
        try:
            print_ = crypto.fingerprint(normalise_iban(probe.iban))
        except ValueError:
            print_ = None
        if print_:
            for (cid,) in (
                await session.execute(
                    select(ContactBankAccount.contact_id).where(
                        ContactBankAccount.iban_fingerprint == print_
                    )
                )
            ).all():
                add(cid, 0.95, "gleiche IBAN")
    name = (
        " ".join(p for p in (probe.last_name, probe.first_name, probe.company_name) if p)
        .strip()
        .lower()
    )
    if len(name) >= 3:
        similarity = func.similarity(func.lower(Contact.search_text), name)
        rows = (
            await session.execute(
                select(Contact.id, similarity.label("s"))
                .where(similarity > 0.3)
                .order_by(similarity.desc())
                .limit(limit)
            )
        ).all()
        for row in rows:
            add(row.id, min(0.85, float(row.s) + 0.2), "ähnlicher Name")
    if exclude_id:
        scores.pop(exclude_id, None)
    if not scores:
        return []
    contacts = (
        await session.scalars(
            select(Contact).where(Contact.id.in_(scores), Contact.deleted_at.is_(None))
        )
    ).all()
    ranked = sorted(
        ((c, *scores[c.id]) for c in contacts), key=lambda item: (-item[1], item[0].display_name)
    )
    return ranked[:limit]


async def export(session: AsyncSession, contact_id: uuid.UUID) -> dict[str, Any] | None:
    """Data subject access export (section 16, S06). Marked for review before release."""
    contact = await load(session, contact_id)
    if contact is None:
        return None
    accounts = (
        await session.scalars(
            select(ContactBankAccount).where(ContactBankAccount.contact_id == contact_id)
        )
    ).all()
    notes = (
        await session.scalars(select(ContactNote).where(ContactNote.contact_id == contact_id))
    ).all()
    consents = (
        await session.scalars(select(Consent).where(Consent.contact_id == contact_id))
    ).all()
    relations = (
        await session.scalars(
            select(ContactRelation).where(ContactRelation.contact_id == contact_id)
        )
    ).all()
    parties = (
        await session.execute(
            select(Party.id, Party.name, PartyMember.role)
            .join(PartyMember, PartyMember.party_id == Party.id)
            .where(PartyMember.contact_id == contact_id)
        )
    ).all()
    events = (
        await session.scalars(
            select(DomainEvent)
            .where(DomainEvent.entity_id == contact_id)
            .order_by(DomainEvent.occurred_at)
        )
    ).all()
    data = contact.model_dump(mode="json", exclude={"bank_accounts"})
    data["bank_accounts"] = [
        {
            "iban": a.iban,
            "bic": a.bic,
            "bank_name": a.bank_name,
            "holder": a.holder,
            "valid_from": a.valid_from.isoformat(),
            "valid_to": a.valid_to.isoformat() if a.valid_to else None,
        }
        for a in accounts
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "review_required": True,
        "review_note": (
            "Vor Herausgabe prüfen: Notizen und Beziehungen können Angaben Dritter enthalten "
            "(Art. 15 Abs. 4 DSGVO); Mitparteien werden nur mit Parteiname "
            "und eigener Rolle genannt."
        ),
        "contact": data,
        "notes": [
            {"category": n.category, "body": n.body, "created_at": n.created_at.isoformat()}
            for n in notes
        ],
        "consents": [
            {
                "kind": c.kind.value,
                "granted_at": c.granted_at.isoformat(),
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
                "source": c.source,
            }
            for c in consents
        ],
        "relations": [
            {"kind": r.kind.value, "related_contact_id": str(r.related_contact_id)}
            for r in relations
        ],
        "parties": [
            {"party_id": str(p.id), "name": p.name, "own_role": p.role.value} for p in parties
        ],
        "processing_log": [
            {"type": e.type, "occurred_at": e.occurred_at.isoformat()} for e in events
        ],
    }


def party_name(members: list[tuple[Contact, schemas.PartyMemberIn]]) -> str:
    persons = [c for c, _ in members if c.kind is ContactKind.PERSON]
    if len(members) == 1:
        return members[0][0].display_name
    last_names = {c.last_name for c in persons if c.last_name}
    if len(persons) == len(members) == 2 and len(last_names) == 1:
        first = [c.first_name or "" for c in persons]
        # Neutral wording: a shared last name does not prove a marriage.
        return f"{first[0]} und {first[1]} {last_names.pop()}".replace("  ", " ").strip()
    return " und ".join(c.display_name for c, _ in members)
