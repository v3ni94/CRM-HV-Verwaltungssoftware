"""Contact endpoints (/api/v1/contacts, /parties, /search)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import case, func, literal, or_, select

from mhvp.ai.examples import delete_examples_for_contact
from mhvp.contacts import schemas, services
from mhvp.contacts.models import (
    Consent,
    Contact,
    ContactBankAccount,
    ContactBankAccountChange,
    ContactMandateStatus,
    ContactNote,
    ContactRelation,
    ContactTag,
    ContactTagLink,
    DeliveryMode,
    Party,
    PartyMember,
    RelationKind,
)
from mhvp.contacts.validation import mask_iban
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError, body_validation_error

router = APIRouter(tags=["Kontakte"])

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
READ = require_permission("contacts:read")
CREATE = require_permission("contacts:create")
UPDATE = require_permission("contacts:update")
DELETE = require_permission("contacts:delete")
EXPORT = require_permission("contacts:export")
APPROVE = require_permission("contacts:approve")


def _not_found() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def _active(session: Any, contact_id: uuid.UUID) -> Contact:
    contact: Contact | None = await session.get(Contact, contact_id)
    if contact is None or contact.deleted_at is not None:
        raise _not_found()
    return contact


@router.get("/contacts", summary="Kontakte suchen und auflisten")
async def list_contacts(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    kind: str | None = None,
    tag: str | None = None,
    role: str | None = Query(default=None, description="Filter: eigentuemer, mieter, ..."),
    blocked: bool | None = Query(default=None, description="Sperrliste: true zeigt nur gesperrte"),
    include_deleted: bool = False,
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(READ),
) -> schemas.ContactPage:
    async with tenant_tx(request, principal) as session:
        query = select(Contact)
        if not include_deleted:
            query = query.where(Contact.deleted_at.is_(None))
        if kind:
            query = query.where(Contact.kind == kind)
        if role:
            query = query.where(literal(role).op("=")(func.any(Contact.roles)))
        if blocked is not None:
            query = query.where(Contact.blocked.is_(blocked))
        if tag:
            query = query.where(
                Contact.id.in_(
                    select(ContactTagLink.contact_id)
                    .join(ContactTag, ContactTag.id == ContactTagLink.tag_id)
                    .where(ContactTag.name == tag)
                )
            )
        if q:
            query = services.search_filter(query, q)
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (
            await session.scalars(
                query.order_by(Contact.display_name, Contact.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return schemas.ContactPage(
            items=await services.summaries(session, list(rows)),
            total=total,
            page=page,
            page_size=page_size,
        )


@router.post("/contacts", status_code=201, summary="Kontakt anlegen")
async def create_contact(
    body: schemas.ContactIn,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(CREATE),
) -> schemas.ContactOut:
    async with tenant_tx(request, principal) as session:
        contact = Contact(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            kind=body.kind,
            display_name="",
        )
        services.apply_fields(contact, body)
        await services.apply_retention(session, contact, body.retention_profile_id)
        session.add(contact)
        await session.flush()
        await services.write_children(
            session, principal.tenant_id, contact.id, body, actor_user_id=principal.user_id
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.created",
            entity_type="contact",
            entity_id=contact.id,
            actor_user_id=principal.user_id,
            payload={"kind": contact.kind.value},
        )
        out = await services.load(session, contact.id)
        assert out is not None  # noqa: S101 - just created in this transaction
        response.headers["ETag"] = f'"{out.version}"'
        return out


@router.post("/contacts/roles/recompute", summary="Abgeleitete Rollen neu berechnen")
async def recompute_roles(
    request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> schemas.RecomputeRolesOut:
    """Adds eigentuemer/mieter from active contracts and ownerships; never removes roles."""
    async with tenant_tx(request, principal) as session:
        changed = await services.recompute_all(session, principal.tenant_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.roles_recomputed",
            entity_type="contact",
            entity_id=None,
            actor_user_id=principal.user_id,
            payload={"changed": changed},
        )
        return schemas.RecomputeRolesOut(changed=changed)


@router.get("/contacts/duplicates", summary="Dublettenvorschläge für neue Angaben")
async def duplicates(
    request: Request,
    first_name: str | None = None,
    last_name: str | None = None,
    company_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    iban: str | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[schemas.DuplicateCandidate]:
    probe = schemas.DuplicateQuery(
        first_name=first_name,
        last_name=last_name,
        company_name=company_name,
        email=email,
        phone=phone,
        iban=iban,
    )
    async with tenant_tx(request, principal) as session:
        found = await services.find_duplicates(session, probe)
        summaries = await services.summaries(session, [c for c, _, _ in found])
        return [
            schemas.DuplicateCandidate(contact=s, score=round(score, 2), reasons=reasons)
            for s, (_, score, reasons) in zip(summaries, found, strict=True)
        ]


@router.get("/contacts/{contact_id}", summary="Kontakt lesen")
async def get_contact(
    contact_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> schemas.ContactOut:
    async with tenant_tx(request, principal) as session:
        out = await services.load(session, contact_id)
        if out is None:
            raise _not_found()
        response.headers["ETag"] = f'"{out.version}"'
        return out


@router.get("/contacts/{contact_id}/name", summary="Anzeigename eines Kontakts (nur Name)")
async def get_contact_name(
    contact_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> schemas.ContactName:
    """Data minimisation: previews (e.g. ticket merge) only need the name, not the record."""
    async with tenant_tx(request, principal) as session:
        row = (
            await session.execute(
                select(Contact.id, Contact.display_name).where(
                    Contact.id == contact_id, Contact.deleted_at.is_(None)
                )
            )
        ).first()
        if row is None:
            raise _not_found()
        return schemas.ContactName(id=row[0], display_name=row[1])


@router.put("/contacts/{contact_id}", summary="Kontakt ändern (vollständig)")
async def replace_contact(
    contact_id: uuid.UUID,
    body: schemas.ContactIn,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.ContactOut:
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        if if_match is not None and if_match.strip('"') != str(contact.version):
            raise ProblemError(ErrorCodes.VERSION_CONFLICT)
        before = await services.load(session, contact_id)
        services.apply_fields(contact, body, await services.iban_suffixes(session, contact_id))
        await services.apply_retention(session, contact, body.retention_profile_id)
        changed_mandate_references = await services.write_children(
            session, principal.tenant_id, contact.id, body, actor_user_id=principal.user_id
        )
        for reference in changed_mandate_references:
            session.add(
                ContactNote(
                    tenant_id=principal.tenant_id,
                    contact_id=contact.id,
                    created_by=principal.user_id,
                    category="sepa_mandate",
                    body=(
                        f"IBAN der Bankverbindung mit SEPA-Mandat {reference} wurde geändert. "
                        "Ein neues Mandat kann erforderlich sein; das bestehende Mandat wurde "
                        "nicht automatisch widerrufen."
                    ),
                    pinned=True,
                )
            )
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="contact.mandate_iban_changed",
                entity_type="contact",
                entity_id=contact.id,
                actor_user_id=principal.user_id,
                payload={"mandate_reference": reference},
            )
        contact.version += 1
        contact.updated_by = principal.user_id
        after = await services.load(session, contact_id)
        if before is None or after is None:  # pragma: no cover - loaded in this transaction
            raise _not_found()
        ignore = {"version", "updated_at", "created_at"}
        old = before.model_dump(mode="json", exclude=ignore)
        new = after.model_dump(mode="json", exclude=ignore)
        # Child ids are regenerated on replace; compare content only.
        for doc in (old, new):
            for key in ("addresses", "phones", "emails", "identifiers", "bank_accounts"):
                doc[key] = [{k: v for k, v in item.items() if k != "id"} for item in doc[key]]
        changes = diff(old, new)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.updated",
            entity_type="contact",
            entity_id=contact.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(changes)},
            changes=changes,
        )
        response.headers["ETag"] = f'"{after.version}"'
        return after


_CHILD_IN: dict[str, type[BaseModel]] = {
    "addresses": schemas.AddressIn,
    "phones": schemas.PhoneIn,
    "emails": schemas.EmailIn,
    "identifiers": schemas.IdentifierIn,
    "dates": schemas.ContactDateIn,
}
_MASTER_ONLY = {
    "id",
    "display_name",
    "blocked_at",
    "delete_after",
    "bank_accounts",
    "version",
    "created_at",
    "updated_at",
    "deleted_at",
}


def _as_input(current: schemas.ContactOut, patch: schemas.ContactPatch) -> schemas.ContactIn:
    """Current contact plus the patched fields as ``ContactIn`` so that the same validators
    apply as on ``PUT`` (names per kind, language, lengths)."""
    data: dict[str, Any] = current.model_dump(exclude=_MASTER_ONLY)
    for key, model in _CHILD_IN.items():
        data[key] = [
            {k: v for k, v in item.items() if k in model.model_fields} for item in data[key]
        ]
    data["bank_accounts"] = None  # unchanged; the search text keeps the stored IBAN suffixes
    data.update(patch.model_dump(exclude_unset=True))
    try:
        return schemas.ContactIn.model_validate(data)
    except ValidationError as exc:
        raise body_validation_error(exc) from None


@router.patch("/contacts/{contact_id}", summary="Kontakt teilweise ändern (Stammdaten, If-Match)")
async def patch_contact(
    contact_id: uuid.UUID,
    body: schemas.ContactPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.ContactOut:
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        if if_match is not None and if_match.strip('"') != str(contact.version):
            raise ProblemError(ErrorCodes.VERSION_CONFLICT)
        before = await services.load(session, contact_id)
        if before is None:  # pragma: no cover - loaded in this transaction
            raise _not_found()
        merged = _as_input(before, body)
        services.apply_fields(contact, merged, await services.iban_suffixes(session, contact_id))
        if "retention_profile_id" in body.model_fields_set:
            await services.apply_retention(session, contact, body.retention_profile_id)
        contact.version += 1
        contact.updated_by = principal.user_id
        after = await services.load(session, contact_id)
        if after is None:  # pragma: no cover - loaded in this transaction
            raise _not_found()
        ignore = {"version", "updated_at", "created_at"}
        changes = diff(
            before.model_dump(mode="json", exclude=ignore),
            after.model_dump(mode="json", exclude=ignore),
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.updated",
            entity_type="contact",
            entity_id=contact.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(changes)},
            changes=changes,
        )
        response.headers["ETag"] = f'"{after.version}"'
        return after


@router.delete("/contacts/{contact_id}", status_code=204, summary="Kontakt löschen (weich)")
async def delete_contact(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        contact.deleted_at = datetime.now(UTC)
        contact.updated_by = principal.user_id
        # ADR 0010, M7-04: learning examples built from the contact's tickets go with it.
        await delete_examples_for_contact(session, contact.id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.deleted",
            entity_type="contact",
            entity_id=contact.id,
            actor_user_id=principal.user_id,
        )
    return Response(status_code=204)


@router.get("/contacts/{contact_id}/duplicates", summary="Dublettenvorschläge zu einem Kontakt")
async def contact_duplicates(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.DuplicateCandidate]:
    async with tenant_tx(request, principal) as session:
        contact = await services.load(session, contact_id)
        if contact is None:
            raise _not_found()
        probe = schemas.DuplicateQuery(
            first_name=contact.first_name,
            last_name=contact.last_name,
            company_name=contact.company_name,
            email=contact.emails[0].email if contact.emails else None,
            phone=contact.phones[0].number if contact.phones else None,
        )
        found = await services.find_duplicates(session, probe, exclude_id=contact_id)
        summaries = await services.summaries(session, [c for c, _, _ in found])
        return [
            schemas.DuplicateCandidate(contact=s, score=round(score, 2), reasons=reasons)
            for s, (_, score, reasons) in zip(summaries, found, strict=True)
        ]


@router.get("/contacts/{contact_id}/export", summary="DSGVO-Auskunft (Entwurf zur Prüfung)")
async def export_contact(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(EXPORT)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        data = await services.export(session, contact_id)
        if data is None:
            raise _not_found()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.exported",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"purpose": "data_subject_access"},
        )
        return data


@router.get("/contacts/{contact_id}/sepa-mandates", summary="SEPA-Mandate eines Kontakts (kompakt)")
async def list_sepa_mandates(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.SepaMandateOut]:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        rows = (
            await session.scalars(
                select(ContactBankAccount).where(
                    ContactBankAccount.contact_id == contact_id,
                    ContactBankAccount.sepa_enabled.is_(True),
                )
            )
        ).all()
        return [
            schemas.SepaMandateOut(
                bank_account_id=b.id,
                iban_masked=mask_iban(b.iban),
                mandate_reference=b.mandate_reference,
                mandate_signed_on=b.mandate_signed_on,
                mandate_scheme=b.mandate_scheme,
                mandate_status=b.mandate_status,
                mandate_revoked_on=b.mandate_revoked_on,
            )
            for b in rows
        ]


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/mandate/revoke",
    summary="SEPA-Mandat widerrufen",
)
async def revoke_mandate(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.SepaMandateOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        account = await session.get(ContactBankAccount, account_id)
        if account is None or account.contact_id != contact_id:
            raise _not_found()
        if not account.sepa_enabled or account.mandate_status == ContactMandateStatus.REVOKED:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kein aktives SEPA-Mandat auf dieser Bankverbindung."
            )
        account.mandate_status = ContactMandateStatus.REVOKED
        account.mandate_revoked_on = datetime.now(UTC).date()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.mandate_revoked",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={
                "mandate_reference": account.mandate_reference,
                "bank_account_id": str(account.id),
            },
        )
        await session.flush()
        return schemas.SepaMandateOut(
            bank_account_id=account.id,
            iban_masked=mask_iban(account.iban),
            mandate_reference=account.mandate_reference,
            mandate_signed_on=account.mandate_signed_on,
            mandate_scheme=account.mandate_scheme,
            mandate_status=account.mandate_status,
            mandate_revoked_on=account.mandate_revoked_on,
        )


async def _decide_bank_account(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal,
    *,
    approve: bool,
    body: schemas.BankAccountDecisionIn | None,
) -> schemas.BankAccountOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        account = await session.get(ContactBankAccount, account_id)
        if account is None or account.contact_id != contact_id:
            raise _not_found()
        changed_reference = await services.decide_bank_account(
            session,
            account,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            approve=approve,
            is_platform_admin=principal.is_platform_admin,
            reason=body.reason if body else None,
        )
        if changed_reference is not None:
            await _note_mandate_iban_changed(session, principal, contact_id, changed_reference)
        loaded = await services.load(session, contact_id)
        if loaded is None:
            raise _not_found()
        return next(b for b in loaded.bank_accounts if b.id == account_id)


async def _note_mandate_iban_changed(
    session: Any, principal: TenantPrincipal, contact_id: uuid.UUID, reference: str
) -> None:
    """Pinned note and event when the IBAN under an active SEPA mandate changed (M3-02); the
    mandate is never revoked automatically."""
    session.add(
        ContactNote(
            tenant_id=principal.tenant_id,
            contact_id=contact_id,
            created_by=principal.user_id,
            category="sepa_mandate",
            body=(
                f"IBAN der Bankverbindung mit SEPA-Mandat {reference} wurde geändert. "
                "Ein neues Mandat kann erforderlich sein; das bestehende Mandat wurde "
                "nicht automatisch widerrufen."
            ),
            pinned=True,
        )
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="contact.mandate_iban_changed",
        entity_type="contact",
        entity_id=contact_id,
        actor_user_id=principal.user_id,
        payload={"mandate_reference": reference},
    )


async def _account_out(
    session: Any, contact_id: uuid.UUID, account_id: uuid.UUID
) -> schemas.BankAccountOut:
    loaded = await services.load(session, contact_id)
    if loaded is None:
        raise _not_found()
    return next(b for b in loaded.bank_accounts if b.id == account_id)


async def _own_account(
    session: Any, contact_id: uuid.UUID, account_id: uuid.UUID
) -> ContactBankAccount:
    account: ContactBankAccount | None = await session.get(ContactBankAccount, account_id)
    if account is None or account.contact_id != contact_id:
        raise _not_found()
    return account


@router.post(
    "/contacts/{contact_id}/bank-accounts",
    status_code=201,
    summary="Bankverbindung an bestehendem Kontakt hinzufügen (zur Freigabe)",
)
async def add_bank_account(
    contact_id: uuid.UUID,
    body: schemas.BankAccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.BankAccountOut:
    """The account starts as ``pending``; a second person with ``contacts:approve`` releases
    it (M5-01). Same rules as on ``POST /contacts``, without rewriting the other accounts."""
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        row = await services.add_bank_account(
            session,
            contact,
            body,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
        )
        return await _account_out(session, contact_id, row.id)


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/replace",
    status_code=201,
    summary="Bankverbindung ändern: neue Version mit neuer IBAN (zur Freigabe)",
)
async def replace_bank_account(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    body: schemas.BankAccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.BankAccountOut:
    """Creates the new version as a pending row that points to the replaced account
    (``replaces_account_id``). On release the old row gets ``valid_to`` the day before the new
    ``valid_from`` and hands over the default flag; its IBAN history stays."""
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        old = await _own_account(session, contact_id, account_id)
        row = await services.add_bank_account(
            session,
            contact,
            body,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            replaces=old,
        )
        return await _account_out(session, contact_id, row.id)


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/end",
    summary="Bankverbindung beenden (Gültig bis), Vier-Augen-Prinzip bei Rechtsträgern",
)
async def end_bank_account(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    body: schemas.BankAccountEndIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.BankAccountOut:
    """Applied at once when the caller holds ``contacts:approve`` and the contact is no legal
    entity; otherwise the answer carries ``pending_change`` for a second person."""
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        account = await _own_account(session, contact_id, account_id)
        await services.end_bank_account(
            session,
            contact,
            account,
            body,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            can_approve=principal.has("contacts:approve"),
            is_platform_admin=principal.is_platform_admin,
        )
        return await _account_out(session, contact_id, account_id)


async def _decide_change(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    change_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal,
    *,
    approve: bool,
    body: schemas.BankAccountDecisionIn | None,
) -> schemas.BankAccountOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        await _own_account(session, contact_id, account_id)
        change = await session.get(ContactBankAccountChange, change_id)
        if change is None or change.bank_account_id != account_id:
            raise _not_found()
        await services.decide_bank_account_change(
            session,
            change,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            approve=approve,
            is_platform_admin=principal.is_platform_admin,
            reason=body.reason if body else None,
        )
        return await _account_out(session, contact_id, account_id)


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/changes/{change_id}/approve",
    summary="Änderung an Bankverbindung bestätigen (Vier-Augen-Prinzip, zweite Person)",
)
async def approve_bank_account_change(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    change_id: uuid.UUID,
    request: Request,
    body: schemas.BankAccountDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> schemas.BankAccountOut:
    return await _decide_change(
        contact_id, account_id, change_id, request, principal, approve=True, body=body
    )


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/changes/{change_id}/reject",
    summary="Änderung an Bankverbindung ablehnen (Vier-Augen-Prinzip, zweite Person)",
)
async def reject_bank_account_change(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    change_id: uuid.UUID,
    request: Request,
    body: schemas.BankAccountDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> schemas.BankAccountOut:
    return await _decide_change(
        contact_id, account_id, change_id, request, principal, approve=False, body=body
    )


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/approve",
    summary="Bankverbindung freigeben (Vier-Augen-Prinzip, zweite Person)",
)
async def approve_bank_account(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    body: schemas.BankAccountDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> schemas.BankAccountOut:
    return await _decide_bank_account(
        contact_id, account_id, request, principal, approve=True, body=body
    )


@router.post(
    "/contacts/{contact_id}/bank-accounts/{account_id}/reject",
    summary="Bankverbindung ablehnen (Vier-Augen-Prinzip, zweite Person)",
)
async def reject_bank_account(
    contact_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    body: schemas.BankAccountDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> schemas.BankAccountOut:
    return await _decide_bank_account(
        contact_id, account_id, request, principal, approve=False, body=body
    )


# Notes, relations, consents ------------------------------------------------------------


@router.get("/contacts/{contact_id}/notes", summary="Notizen")
async def list_notes(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.NoteOut]:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        rows = (
            await session.scalars(
                select(ContactNote)
                .where(ContactNote.contact_id == contact_id)
                .order_by(ContactNote.pinned.desc(), ContactNote.created_at.desc())
            )
        ).all()
        return [schemas.NoteOut.model_validate(n, from_attributes=True) for n in rows]


@router.post("/contacts/{contact_id}/notes", status_code=201, summary="Notiz anlegen")
async def add_note(
    contact_id: uuid.UUID,
    body: schemas.NoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.NoteOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        note = ContactNote(
            tenant_id=principal.tenant_id,
            contact_id=contact_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(note)
        await session.flush()
        await session.refresh(note)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.note_added",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"note_id": str(note.id)},
        )
        return schemas.NoteOut.model_validate(note, from_attributes=True)


@router.post("/contacts/{contact_id}/relations", status_code=201, summary="Beziehung anlegen")
async def add_relation(
    contact_id: uuid.UUID,
    body: schemas.RelationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.RelationOut:
    if body.related_contact_id == contact_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Ein Kontakt kann nicht mit sich selbst verknüpft werden."
        )
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        await _active(session, body.related_contact_id)
        relation = ContactRelation(
            tenant_id=principal.tenant_id, contact_id=contact_id, **body.model_dump()
        )
        session.add(relation)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.relation_added",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={
                "kind": body.kind.value,
                "relation_id": str(relation.id),
                "related_contact_id": str(body.related_contact_id),
                "delivery_mode": body.delivery_mode.value,
            },
            changes={
                "representative" if body.kind is RelationKind.REPRESENTATIVE else "relation": {
                    "old": None,
                    "new": str(body.related_contact_id),
                }
            },
        )
        related = await session.get(Contact, body.related_contact_id)
        return schemas.RelationOut(
            id=relation.id,
            related_display_name=related.display_name if related else None,
            **body.model_dump(),
        )


def _relation_out(row: ContactRelation, contact_id: uuid.UUID, name: str) -> schemas.RelationOut:
    outgoing = row.contact_id == contact_id
    return schemas.RelationOut(
        id=row.id,
        related_contact_id=row.related_contact_id if outgoing else row.contact_id,
        related_display_name=name,
        kind=row.kind,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        delivery_mode=DeliveryMode(row.delivery_mode),
        direction="outgoing" if outgoing else "incoming",
    )


@router.get(
    "/contacts/{contact_id}/contact-relations",
    summary="Beziehungen zu anderen Kontakten (Bevollmächtigte, Ehepartner, Erben)",
)
async def list_contact_relations(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.RelationOut]:
    """Outgoing relations (this contact names the other) and incoming ones (this contact is
    named, for example as authorised representative of the other)."""
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        rows = (
            await session.execute(
                select(ContactRelation, Contact.display_name)
                .join(
                    Contact,
                    Contact.id
                    == case(
                        (
                            ContactRelation.contact_id == contact_id,
                            ContactRelation.related_contact_id,
                        ),
                        else_=ContactRelation.contact_id,
                    ),
                )
                .where(
                    or_(
                        ContactRelation.contact_id == contact_id,
                        ContactRelation.related_contact_id == contact_id,
                    ),
                    Contact.deleted_at.is_(None),
                )
                .order_by(ContactRelation.created_at, ContactRelation.id)
            )
        ).all()
        return [_relation_out(row, contact_id, name) for row, name in rows]


def _relation_state(row: ContactRelation) -> dict[str, Any]:
    return {
        "delivery_mode": str(row.delivery_mode),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
    }


async def _own_relation(
    session: Any, contact_id: uuid.UUID, relation_id: uuid.UUID
) -> ContactRelation:
    row: ContactRelation | None = await session.get(ContactRelation, relation_id)
    if row is None or row.contact_id != contact_id:
        raise _not_found()
    return row


@router.patch(
    "/contacts/{contact_id}/contact-relations/{relation_id}",
    summary="Zustellregel oder Gültigkeit einer Beziehung ändern",
)
async def patch_contact_relation(
    contact_id: uuid.UUID,
    relation_id: uuid.UUID,
    body: schemas.RelationPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.RelationOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        row = await _own_relation(session, contact_id, relation_id)
        if "delivery_mode" in body.fields:
            if body.delivery_mode is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Zustellregel fehlt.")
            if (
                row.kind is not RelationKind.REPRESENTATIVE
                and body.delivery_mode is not DeliveryMode.BOTH
            ):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Eine Zustellregel gibt es nur für Bevollmächtigte.",
                )
        before = _relation_state(row)
        for name in body.fields:
            setattr(row, name, getattr(body, name))
        if row.valid_from and row.valid_to and row.valid_to < row.valid_from:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Das Ende der Gültigkeit liegt vor dem Beginn."
            )
        row.updated_by = principal.user_id
        after = _relation_state(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.relation_updated",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"relation_id": str(row.id), "kind": row.kind.value, "fields": body.fields},
            changes=diff(before, after),
        )
        related = await session.get(Contact, row.related_contact_id)
        return _relation_out(row, contact_id, related.display_name if related else "")


@router.delete(
    "/contacts/{contact_id}/contact-relations/{relation_id}",
    status_code=204,
    summary="Beziehung beenden (löschen)",
)
async def delete_contact_relation(
    contact_id: uuid.UUID,
    relation_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        row = await _own_relation(session, contact_id, relation_id)
        payload = {
            "relation_id": str(row.id),
            "kind": row.kind.value,
            "related_contact_id": str(row.related_contact_id),
            "delivery_mode": str(row.delivery_mode),
        }
        await session.delete(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.relation_removed",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload=payload,
            changes={
                "representative" if row.kind is RelationKind.REPRESENTATIVE else "relation": {
                    "old": str(row.related_contact_id),
                    "new": None,
                }
            },
        )
    return Response(status_code=204)


@router.get("/contacts/{contact_id}/relations", summary="Objektbezüge eines Kontakts")
async def list_object_relations(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.ObjectRelationOut]:
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        return await services.object_relations(session, contact)


@router.get("/contacts/{contact_id}/consents", summary="Einwilligungen")
async def list_consents(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.ConsentOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(Consent).where(Consent.contact_id == contact_id).order_by(Consent.granted_at)
            )
        ).all()
        return [schemas.ConsentOut.model_validate(c, from_attributes=True) for c in rows]


@router.post("/contacts/{contact_id}/consents", status_code=201, summary="Einwilligung erfassen")
async def add_consent(
    contact_id: uuid.UUID,
    body: schemas.ConsentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.ConsentOut:
    async with tenant_tx(request, principal) as session:
        await _active(session, contact_id)
        consent = Consent(tenant_id=principal.tenant_id, contact_id=contact_id, **body.model_dump())
        session.add(consent)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="consent.granted",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"kind": body.kind.value, "source": body.source},
        )
        return schemas.ConsentOut(id=consent.id, revoked_at=None, **body.model_dump())


@router.post("/consents/{consent_id}/revoke", summary="Einwilligung widerrufen")
async def revoke_consent(
    consent_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> schemas.ConsentOut:
    async with tenant_tx(request, principal) as session:
        consent = await session.get(Consent, consent_id)
        if consent is None or consent.revoked_at is not None:
            raise _not_found()
        consent.revoked_at = datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="consent.revoked",
            entity_type="contact",
            entity_id=consent.contact_id,
            actor_user_id=principal.user_id,
            payload={"kind": consent.kind.value},
        )
        return schemas.ConsentOut.model_validate(consent, from_attributes=True)


# Parties -------------------------------------------------------------------------------


async def _party_out(session: Any, party: Party) -> schemas.PartyOut:
    return (await _parties_out(session, [party]))[0]


async def _parties_out(session: Any, parties: Sequence[Party]) -> list[schemas.PartyOut]:
    """Members and display names of all parties in one query."""
    if not parties:
        return []
    members: dict[uuid.UUID, list[schemas.PartyMemberOut]] = {}
    for m, name in (
        await session.execute(
            select(PartyMember, Contact.display_name)
            .join(Contact, Contact.id == PartyMember.contact_id)
            .where(PartyMember.party_id.in_([p.id for p in parties]))
            .order_by(PartyMember.id)
        )
    ).all():
        members.setdefault(m.party_id, []).append(
            schemas.PartyMemberOut(
                contact_id=m.contact_id,
                role=m.role,
                share_percent=m.share_percent,
                display_name=name,
            )
        )
    return [schemas.PartyOut(id=p.id, name=p.name, members=members.get(p.id, [])) for p in parties]


@router.post("/parties", status_code=201, summary="Vertragspartei anlegen")
async def create_party(
    body: schemas.PartyIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> schemas.PartyOut:
    if len({m.contact_id for m in body.members}) != len(body.members):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Ein Kontakt darf nur einmal Mitglied einer Partei sein."
        )
    shares = [m.share_percent for m in body.members if m.share_percent is not None]
    if shares and sum(shares) > 100:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Die Anteile übersteigen 100 Prozent.")
    async with tenant_tx(request, principal) as session:
        members = [(await _active(session, m.contact_id), m) for m in body.members]
        party = Party(
            tenant_id=principal.tenant_id,
            name=body.name or services.party_name(members),
            created_by=principal.user_id,
        )
        session.add(party)
        await session.flush()
        for _, member in members:
            session.add(
                PartyMember(tenant_id=principal.tenant_id, party_id=party.id, **member.model_dump())
            )
        await session.flush()
        await services.recompute_for_party(session, party.id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="party.created",
            entity_type="party",
            entity_id=party.id,
            actor_user_id=principal.user_id,
            payload={"members": len(members)},
        )
        return await _party_out(session, party)


@router.get("/parties/{party_id}", summary="Vertragspartei lesen")
async def get_party(
    party_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> schemas.PartyOut:
    async with tenant_tx(request, principal) as session:
        party = await session.get(Party, party_id)
        if party is None:
            raise _not_found()
        return await _party_out(session, party)


@router.get("/parties", summary="Parteien eines Kontakts")
async def list_parties(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[schemas.PartyOut]:
    async with tenant_tx(request, principal) as session:
        parties = (
            await session.scalars(
                select(Party)
                .join(PartyMember, PartyMember.party_id == Party.id)
                .where(PartyMember.contact_id == contact_id)
                .order_by(Party.name, Party.id)
            )
        ).all()
        return await _parties_out(session, parties)


# Global search -------------------------------------------------------------------------


@router.get("/search", summary="Globale Suche (Strg+K)")
async def global_search(
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    principal: TenantPrincipal = Depends(READ),
) -> list[schemas.SearchHit]:
    async with tenant_tx(request, principal) as session:
        similarity = func.similarity(Contact.search_text, q.lower())
        query = services.search_filter(
            select(Contact, similarity.label("s")).where(Contact.deleted_at.is_(None)), q
        )
        rows = (
            await session.execute(
                query.order_by(similarity.desc(), Contact.display_name).limit(limit)
            )
        ).all()
        summaries = await services.summaries(session, [r[0] for r in rows])
        return [
            schemas.SearchHit(
                entity_type="contact",
                id=s.id,
                title=s.display_name,
                subtitle=", ".join(p for p in (s.city, s.primary_email) if p) or None,
                score=round(float(r.s), 3),
            )
            for s, r in zip(summaries, rows, strict=True)
        ]
