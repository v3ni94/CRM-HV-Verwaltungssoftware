"""Derivation and evaluation of access grants (6.9.6, 14): tenants see their contracts,
owners additionally the administrative documents of their GdWE (§ 18 Abs. 4 WEG), never SEV
or tenant files of others or other communities; providers only their work orders."""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.portal.models import AccessGrant, PortalAccount

if TYPE_CHECKING:
    pass

# Grants that are not derived from contracts and therefore survive a resync: the handover
# protocol access of a participant (M30 stage 3, docs/rules/M30-01.md).
MANUAL_BASES = frozenset({"handover_participant"})


async def sync_grants(session: AsyncSession, account: PortalAccount) -> int:
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    await session.execute(
        delete(AccessGrant).where(
            AccessGrant.account_id == account.id, AccessGrant.legal_basis.not_in(MANUAL_BASES)
        )
    )
    parties = list(
        await session.scalars(
            select(PartyMember.party_id).where(PartyMember.contact_id == account.contact_id)
        )
    )
    contracts = (
        (await session.scalars(select(Contract).where(Contract.party_id.in_(parties)))).all()
        if parties
        else []
    )
    rows: list[AccessGrant] = []

    def grant(scope: tuple[str, uuid.UUID], right: str, basis: str, role: str, c: Contract) -> None:
        rows.append(
            AccessGrant(
                tenant_id=account.tenant_id,
                account_id=account.id,
                scope_type=scope[0],
                scope_id=scope[1],
                right=right,
                legal_basis=basis,
                role=role,
                valid_from=c.start_date,
                valid_to=c.end_date,
            )
        )

    for c in contracts:
        role = "owner" if c.kind is ContractKind.OWNERSHIP else "tenant"
        grant(("contract", c.id), "comment", "contract", role, c)
        grant(("unit", c.unit_id), "read", "contract", role, c)
        if c.kind is ContractKind.OWNERSHIP:
            hoa = await session.scalar(
                select(LegalEntity.id).where(
                    LegalEntity.property_id == c.property_id,
                    LegalEntity.kind == LegalEntityKind.HOA,
                )
            )
            if hoa is not None:
                grant(("legal_entity", hoa), "download", "hoa_member_right", "owner", c)
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def grants(session: AsyncSession, account: PortalAccount, today: date) -> list[AccessGrant]:
    return list(
        (
            await session.scalars(
                select(AccessGrant).where(
                    AccessGrant.account_id == account.id,
                    AccessGrant.valid_from <= today,
                    or_(AccessGrant.valid_to.is_(None), AccessGrant.valid_to >= today),
                )
            )
        ).all()
    )


def roles(active: list[AccessGrant], is_provider: bool) -> set[str]:
    out = set()
    if any(g.legal_basis == "hoa_member_right" for g in active):
        out.add("owner")
    if any(g.legal_basis == "contract" and g.scope_type == "contract" for g in active):
        out.add("tenant_or_owner")
    if is_provider:
        out.add("provider")
    return out


async def visible_documents(
    session: AsyncSession, account: PortalAccount, today: date
) -> list[Any]:
    """Documents linked to a granted scope and released for the role of that grant."""
    from mhvp.documents.models import Document, DocumentLink

    active = await grants(session, account, today)
    scopes: dict[tuple[str, uuid.UUID], set[str]] = {}
    for g in active:
        scopes.setdefault((g.scope_type, g.scope_id), set()).add(g.role)
    links = (
        []
        if not scopes
        else (
            await session.execute(
                select(
                    DocumentLink.document_id, DocumentLink.entity_type, DocumentLink.entity_id
                ).where(
                    or_(
                        *[
                            (DocumentLink.entity_type == t) & (DocumentLink.entity_id == i)
                            for t, i in scopes
                        ]
                    )
                )
            )
        ).all()
    )
    allowed: set[uuid.UUID] = set()
    for document_id, entity_type, entity_id in links:
        document = await session.get(Document, document_id)
        if document is not None and scopes[(entity_type, entity_id)] & set(document.visibility):
            allowed.add(document_id)
    # Portal inbox (M23): documents dispatched to this contact via the portal and own uploads;
    # other documents merely linked to the contact stay internal.
    from mhvp.communication.models import Dispatch

    allowed |= set(
        await session.scalars(
            select(Dispatch.document_id).where(
                Dispatch.contact_id == account.contact_id, Dispatch.channel == "portal"
            )
        )
    )
    allowed |= set(
        await session.scalars(select(Document.id).where(Document.created_by == account.user_id))
    )
    if not allowed:
        return []
    query = select(Document).where(Document.id.in_(allowed)).order_by(Document.created_at.desc())
    return list((await session.scalars(query)).all())
