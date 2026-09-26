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
# protocol access of a participant (M30 stage 3, docs/rules/M30-01.md) and the mandatory
# tenant wide staff grant (M2-08 entschieden, docs/rules/M2-07.md).
MANUAL_BASES = frozenset({"handover_participant", "staff_access"})
STAFF_ACCESS_LEGAL_BASIS = "staff_access"


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


async def has_staff_grant(session: AsyncSession, account_id: uuid.UUID) -> bool:
    """True if the account holds the tenant wide staff grant (M2-08 entschieden)."""
    return (
        await session.scalar(
            select(AccessGrant.id).where(
                AccessGrant.account_id == account_id,
                AccessGrant.legal_basis == STAFF_ACCESS_LEGAL_BASIS,
            )
        )
    ) is not None


async def has_external_grant(session: AsyncSession, account_id: uuid.UUID) -> bool:
    """True if the account holds any access grant other than the staff grant, i.e. an
    external legal basis (owner, tenant, provider, handover participant, ...). Used to keep
    a staff portal account from also carrying external visibility (Sicherheitsreview
    2026-09-25, Befund 1)."""
    return (
        await session.scalar(
            select(AccessGrant.id).where(
                AccessGrant.account_id == account_id,
                AccessGrant.legal_basis != STAFF_ACCESS_LEGAL_BASIS,
            )
        )
    ) is not None


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


async def staff_permissions(session: AsyncSession, account: PortalAccount) -> frozenset[str]:
    """The staff portal permission set of this account's tenant member, or an empty set when
    the account holds no tenant wide staff grant (an external portal user)."""
    from mhvp.platform.models import (
        Membership,
        MembershipRole,
        Role,
        TenantSettings,
    )
    from mhvp.portal.staff_access import effective_permissions_for_role_codes
    from mhvp.workspace.services import local_today

    # Only a currently valid staff grant counts: a grant deactivated on a role change into an
    # exempt role (valid_to in the past, see the role change in platform.routers) unlocks nothing.
    today = local_today()
    has_staff_grant = await session.scalar(
        select(AccessGrant.id).where(
            AccessGrant.account_id == account.id,
            AccessGrant.legal_basis == STAFF_ACCESS_LEGAL_BASIS,
            AccessGrant.valid_from <= today,
            or_(AccessGrant.valid_to.is_(None), AccessGrant.valid_to >= today),
        )
    )
    if has_staff_grant is None:
        return frozenset()
    role_codes = list(
        await session.scalars(
            select(Role.code)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .join(Membership, Membership.id == MembershipRole.membership_id)
            .where(Membership.tenant_id == account.tenant_id, Membership.user_id == account.user_id)
        )
    )
    settings = await session.scalar(
        select(TenantSettings.portal_role_permissions).where(
            TenantSettings.tenant_id == account.tenant_id
        )
    )
    return effective_permissions_for_role_codes(settings or {}, role_codes)


async def visible_documents(
    session: AsyncSession, account: PortalAccount, today: date
) -> list[Any]:
    """Documents linked to a granted scope and released for the role of that grant. A staff
    account with "documents:read" (M2-08 entschieden) sees every document of the tenant instead,
    since the tenant wide grant is not scoped to individual entities."""
    from mhvp.documents.models import Document, DocumentLink

    staff_perms = await staff_permissions(session, account)
    if "documents:read" in staff_perms:
        query = (
            select(Document)
            .where(Document.tenant_id == account.tenant_id)
            .order_by(Document.created_at.desc())
        )
        return list((await session.scalars(query)).all())

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


async def visible_document_ids(
    session: AsyncSession, account: PortalAccount, today: date
) -> set[uuid.UUID]:
    return {d.id for d in await visible_documents(session, account, today)}


async def document_scope_for_user(
    session: AsyncSession, user_id: uuid.UUID | None, today: date
) -> set[uuid.UUID] | None:
    """Central document filter for paths that do not go through a portal endpoint but act on
    behalf of a user, e.g. the AI context of a run (6.9.6: the matrix also covers RAG search;
    D30). Returns the ids the user may see through the portal matrix, or None when the user
    is not an external portal user (no active portal account, or the tenant wide staff grant),
    in which case CRM permissions and RLS alone govern access."""
    if user_id is None:
        return None
    account = await session.scalar(
        select(PortalAccount).where(
            PortalAccount.user_id == user_id, PortalAccount.status == "active"
        )
    )
    if account is None or await has_staff_grant(session, account.id):
        return None
    return await visible_document_ids(session, account, today)


REDACTION_NOTE = (
    "Für Sie freigegebene Fassung: Angaben Dritter sind geschwärzt, das Original ist nicht "
    "Teil der Freigabe."
)


async def redaction_notes(
    session: AsyncSession, document_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Documents that are a released version of another document (E06, D31): a document
    linked to its original with ``entity_type="document"`` and role ``generated`` carries a
    redaction note in the portal. The original itself stays behind the matrix."""
    from mhvp.documents.models import DocumentLink, LinkRole

    if not document_ids:
        return {}
    rows = await session.scalars(
        select(DocumentLink.document_id).where(
            DocumentLink.document_id.in_(document_ids),
            DocumentLink.entity_type == "document",
            DocumentLink.role == LinkRole.GENERATED,
        )
    )
    return dict.fromkeys(rows, REDACTION_NOTE)
