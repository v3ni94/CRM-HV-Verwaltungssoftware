"""Contact endpoints (/api/v1/contacts, /parties, /search)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select

from mhvp.contacts import schemas, services
from mhvp.contacts.models import (
    Consent,
    Contact,
    ContactBankAccount,
    ContactMandateStatus,
    ContactNote,
    ContactRelation,
    ContactTag,
    ContactTagLink,
    Party,
    PartyMember,
)
from mhvp.contacts.validation import mask_iban
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError

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
            query = query.where(Contact.roles.contains([role]))
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


@router.delete("/contacts/{contact_id}", status_code=204, summary="Kontakt löschen (weich)")
async def delete_contact(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        contact = await _active(session, contact_id)
        contact.deleted_at = datetime.now(UTC)
        contact.updated_by = principal.user_id
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
        await services.decide_bank_account(
            session,
            account,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            approve=approve,
            is_platform_admin=principal.is_platform_admin,
            reason=body.reason if body else None,
        )
        loaded = await services.load(session, contact_id)
        if loaded is None:
            raise _not_found()
        return next(b for b in loaded.bank_accounts if b.id == account_id)


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
            payload={"kind": body.kind.value},
        )
        return schemas.RelationOut(id=relation.id, **body.model_dump())


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
