"""Follow-up maintenance of contacts (package P16, M3-01, M3-02, M3-04).

Parties (members, roles, shares, name), contact notes (change, delete) and the tag
administration of a tenant (list, rename, merge, delete). Permissions follow the existing
contact routes; every change writes an audit event.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from mhvp.contacts import schemas, services
from mhvp.contacts.models import (
    Contact,
    ContactNote,
    ContactTag,
    ContactTagLink,
    Party,
    PartyMember,
)
from mhvp.contacts.routers import DELETE, READ, UPDATE, _active, _not_found, _party_out
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(tags=["Kontakte"])


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


# Parties -------------------------------------------------------------------------------


class PartyPatch(BaseModel):
    """Name and/or complete member list (replaces the members when sent)."""

    name: str | None = Field(default=None, min_length=1, max_length=400)
    members: list[schemas.PartyMemberIn] | None = Field(default=None, min_length=1, max_length=20)


@router.patch("/parties/{party_id}", summary="Vertragspartei ändern (Name, Mitglieder, Anteile)")
async def patch_party(
    party_id: uuid.UUID,
    body: PartyPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.PartyOut:
    if body.members is not None:
        if len({m.contact_id for m in body.members}) != len(body.members):
            raise _invalid("Ein Kontakt darf nur einmal Mitglied einer Partei sein.")
        shares = [m.share_percent for m in body.members if m.share_percent is not None]
        if shares and sum(shares) > 100:
            raise _invalid("Die Anteile übersteigen 100 Prozent.")
    async with tenant_tx(request, principal) as session:
        party = await session.get(Party, party_id)
        if party is None:
            raise _not_found()
        affected: set[uuid.UUID] = set()
        changed: list[str] = []
        if body.name is not None and body.name != party.name:
            party.name = body.name
            changed.append("name")
        if body.members is not None:
            for member in body.members:
                await _active(session, member.contact_id)
            existing = {
                m.contact_id: m
                for m in (
                    await session.scalars(
                        select(PartyMember).where(PartyMember.party_id == party_id)
                    )
                ).all()
            }
            wanted = {m.contact_id: m for m in body.members}
            affected |= set(existing) | set(wanted)
            for contact_id, row in existing.items():
                if contact_id not in wanted:
                    await session.delete(row)
            for contact_id, member in wanted.items():
                current = existing.get(contact_id)
                if current is None:
                    session.add(
                        PartyMember(
                            tenant_id=principal.tenant_id, party_id=party_id, **member.model_dump()
                        )
                    )
                else:
                    current.role = member.role
                    current.share_percent = member.share_percent
            changed.append("members")
        if not changed:
            return await _party_out(session, party)
        party.updated_by = principal.user_id
        await session.flush()
        if affected:
            await services.recompute_for_contacts(session, affected)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="party.updated",
            entity_type="party",
            entity_id=party.id,
            actor_user_id=principal.user_id,
            payload={"fields": changed},
        )
        return await _party_out(session, party)


@router.delete("/parties/{party_id}", status_code=204, summary="Vertragspartei löschen")
async def delete_party(
    party_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    """Only a party without references (contracts, owners, receivables) can be deleted;
    anything else would break traceability (rule 7)."""
    async with tenant_tx(request, principal) as session:
        party = await session.get(Party, party_id)
        if party is None:
            raise _not_found()
        contact_ids = set(
            await session.scalars(
                select(PartyMember.contact_id).where(PartyMember.party_id == party_id)
            )
        )
        try:
            async with session.begin_nested():
                await session.delete(party)
                await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    "Die Partei wird noch verwendet (Verträge, Eigentümer oder Forderungen) "
                    "und kann nicht gelöscht werden."
                ),
            ) from None
        await services.recompute_for_contacts(session, contact_ids)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="party.deleted",
            entity_type="party",
            entity_id=party_id,
            actor_user_id=principal.user_id,
            payload={"members": len(contact_ids)},
        )
        return Response(status_code=204)


# Notes ---------------------------------------------------------------------------------


async def _note(session: Any, contact_id: uuid.UUID, note_id: uuid.UUID) -> ContactNote:
    await _active(session, contact_id)
    note: ContactNote | None = await session.get(ContactNote, note_id)
    if note is None or note.contact_id != contact_id:
        raise _not_found()
    return note


class NoteChange(schemas.NoteIn):
    """All fields optional: only the sent fields change."""

    body: str | None = Field(default=None, min_length=1, max_length=20_000)  # type: ignore[assignment]
    pinned: bool | None = None  # type: ignore[assignment]


@router.patch("/contacts/{contact_id}/notes/{note_id}", summary="Notiz ändern")
async def patch_note(
    contact_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteChange,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> schemas.NoteOut:
    data = body.model_dump(exclude_unset=True)
    if data.get("body", "x") is None or data.get("pinned", False) is None:
        raise _invalid("Text und Anheftung dürfen nicht leer übergeben werden.")
    async with tenant_tx(request, principal) as session:
        note = await _note(session, contact_id, note_id)
        for key, value in data.items():
            setattr(note, key, value)
        note.updated_by = principal.user_id
        await session.flush()
        await session.refresh(note)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.note_updated",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"note_id": str(note.id), "fields": sorted(data)},
        )
        return schemas.NoteOut.model_validate(note, from_attributes=True)


@router.delete("/contacts/{contact_id}/notes/{note_id}", status_code=204, summary="Notiz löschen")
async def delete_note(
    contact_id: uuid.UUID,
    note_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(DELETE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        note = await _note(session, contact_id, note_id)
        await session.delete(note)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact.note_deleted",
            entity_type="contact",
            entity_id=contact_id,
            actor_user_id=principal.user_id,
            payload={"note_id": str(note_id), "at": datetime.now(UTC).isoformat()},
        )
        return Response(status_code=204)


# Tags ----------------------------------------------------------------------------------


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    contacts: int


class TagRename(BaseModel):
    name: str = Field(min_length=1, max_length=63)


class TagMerge(BaseModel):
    target_id: uuid.UUID


async def _tag(session: Any, tag_id: uuid.UUID) -> ContactTag:
    tag: ContactTag | None = await session.get(ContactTag, tag_id)
    if tag is None:
        raise _not_found()
    return tag


async def _tag_out(session: Any, tag: ContactTag) -> TagOut:
    count = await session.scalar(
        select(func.count())
        .select_from(ContactTagLink)
        .join(Contact, Contact.id == ContactTagLink.contact_id)
        .where(ContactTagLink.tag_id == tag.id, Contact.deleted_at.is_(None))
    )
    return TagOut(id=tag.id, name=tag.name, contacts=int(count or 0))


@router.get("/contact-tags", summary="Tags des Mandanten mit Verwendung")
async def list_tags(request: Request, principal: TenantPrincipal = Depends(READ)) -> list[TagOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(ContactTag, func.count(Contact.id))
                .outerjoin(ContactTagLink, ContactTagLink.tag_id == ContactTag.id)
                .outerjoin(
                    Contact,
                    (Contact.id == ContactTagLink.contact_id) & Contact.deleted_at.is_(None),
                )
                .group_by(ContactTag.id)
                .order_by(ContactTag.name)
            )
        ).all()
        return [TagOut(id=t.id, name=t.name, contacts=int(n)) for t, n in rows]


@router.patch("/contact-tags/{tag_id}", summary="Tag umbenennen")
async def rename_tag(
    tag_id: uuid.UUID,
    body: TagRename,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TagOut:
    name = body.name.strip()
    if not name:
        raise _invalid("Der Tag-Name darf nicht leer sein.")
    async with tenant_tx(request, principal) as session:
        tag = await _tag(session, tag_id)
        old = tag.name
        try:
            async with session.begin_nested():
                tag.name = name
                await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Ein Tag mit diesem Namen existiert bereits, bitte zusammenführen.",
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact_tag.renamed",
            entity_type="contact_tag",
            entity_id=tag.id,
            actor_user_id=principal.user_id,
            payload={"from": old, "to": name},
        )
        return await _tag_out(session, tag)


@router.post("/contact-tags/{tag_id}/merge", summary="Tag in einen anderen Tag zusammenführen")
async def merge_tag(
    tag_id: uuid.UUID,
    body: TagMerge,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> TagOut:
    if body.target_id == tag_id:
        raise _invalid("Quelle und Ziel sind derselbe Tag.")
    async with tenant_tx(request, principal) as session:
        source = await _tag(session, tag_id)
        target = await _tag(session, body.target_id)
        already = select(ContactTagLink.contact_id).where(ContactTagLink.tag_id == target.id)
        links = (
            await session.scalars(
                select(ContactTagLink).where(
                    ContactTagLink.tag_id == source.id,
                    ContactTagLink.contact_id.not_in(already),
                )
            )
        ).all()
        for link in links:
            link.tag_id = target.id
        await session.flush()
        await session.execute(delete(ContactTagLink).where(ContactTagLink.tag_id == source.id))
        source_name = source.name
        await session.delete(source)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact_tag.merged",
            entity_type="contact_tag",
            entity_id=target.id,
            actor_user_id=principal.user_id,
            payload={"merged": source_name, "moved_links": len(links)},
        )
        return await _tag_out(session, target)


@router.delete("/contact-tags/{tag_id}", status_code=204, summary="Tag löschen")
async def delete_tag(
    tag_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        tag = await _tag(session, tag_id)
        name = tag.name
        await session.delete(tag)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="contact_tag.deleted",
            entity_type="contact_tag",
            entity_id=tag_id,
            actor_user_id=principal.user_id,
            payload={"name": name},
        )
        return Response(status_code=204)
