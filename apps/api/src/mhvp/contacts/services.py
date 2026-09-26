"""Contact services: create/replace with children, search text, duplicates, export."""

import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts import schemas
from mhvp.contacts.models import (
    BankAccountApproval,
    Consent,
    Contact,
    ContactAddress,
    ContactBankAccount,
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
    Party,
    PartyMember,
)
from mhvp.contacts.validation import mask_iban, normalise_iban, normalise_phone
from mhvp.contracts.models import Contract
from mhvp.core import crypto
from mhvp.core.events import DomainEvent, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.objektakte.models import ObjektakteAssignment
from mhvp.properties.models import Property, PropertyContact, PropertyOwner, Unit

_CHILDREN = (
    ContactAddress,
    ContactPhone,
    ContactEmail,
    ContactIdentifier,
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
) -> None:
    """Second person releases or rejects a pending IBAN; the requester never decides (M5-01)."""
    if account.approval_status != BankAccountApproval.PENDING:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Bankverbindung wartet nicht auf eine Freigabe."
        )
    if actor_user_id is None or is_platform_admin or account.requested_by == actor_user_id:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die Freigabe muss eine andere Person als die erfassende vornehmen.",
        )
    account.approval_status = (
        BankAccountApproval.APPROVED if approve else BankAccountApproval.REJECTED
    )
    account.decided_by = actor_user_id
    account.decided_at = datetime.now(UTC)
    payload: dict[str, Any] = {
        "bank_account_id": str(account.id),
        "iban_suffix": account.iban_suffix,
        "requested_by": str(account.requested_by) if account.requested_by else None,
    }
    if reason:
        payload["reason"] = reason
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
            "bank_accounts",
            "types",
            "roles",
            "tags",
        }
    )
    for key, value in fields.items():
        setattr(contact, key, value)
    contact.display_name = display_name(data)
    contact.search_text = build_search_text(data, suffixes)
    # Full replacement per the update semantics of this endpoint (rule 0.1.7 style updates
    # apply everywhere): the client always sends the roles it wants kept, including any
    # derived ones it saw in the previous GET. See recompute_derived_roles for how derived
    # roles are added automatically when a contract exists.
    contact.roles = sorted({r.value for r in data.roles})


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
    return schemas.ContactOut(
        id=contact.id,
        kind=contact.kind,
        display_name=contact.display_name,
        salutation=contact.salutation,
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
        bank_accounts=[
            schemas.BankAccountOut(
                id=b.id,
                label=b.label,
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
            )
            for b in await rows(ContactBankAccount)
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
    emails = {
        r.contact_id: r.email
        for r in (
            await session.execute(
                select(ContactEmail.contact_id, ContactEmail.email).where(
                    ContactEmail.contact_id.in_(ids), ContactEmail.is_primary.is_(True)
                )
            )
        ).all()
    }
    phones = {
        r.contact_id: r.number
        for r in (
            await session.execute(
                select(ContactPhone.contact_id, ContactPhone.number).where(
                    ContactPhone.contact_id.in_(ids), ContactPhone.is_primary.is_(True)
                )
            )
        ).all()
    }
    cities = {
        r.contact_id: r.city
        for r in (
            await session.execute(
                select(ContactAddress.contact_id, ContactAddress.city).where(
                    ContactAddress.contact_id.in_(ids), ContactAddress.is_primary.is_(True)
                )
            )
        ).all()
    }
    tags: dict[uuid.UUID, list[str]] = {}
    for r in (
        await session.execute(
            select(ContactTagLink.contact_id, ContactTag.name)
            .join(ContactTag, ContactTag.id == ContactTagLink.tag_id)
            .where(ContactTagLink.contact_id.in_(ids))
        )
    ).all():
        tags.setdefault(r.contact_id, []).append(r.name)
    types: dict[uuid.UUID, list[Any]] = {}
    for t in (
        await session.execute(
            select(ContactType.contact_id, ContactType.type).where(ContactType.contact_id.in_(ids))
        )
    ).all():
        types.setdefault(t.contact_id, []).append(t.type)
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
