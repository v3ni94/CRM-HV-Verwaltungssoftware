"""Derivation and evaluation of access grants (6.9.6, 14): tenants see their contracts,
owners additionally the administrative documents of their GdWE (§ 18 Abs. 4 WEG), never SEV
or tenant files of others or other communities; providers only their work orders."""

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.portal.models import AccessGrant, PortalAccount

if TYPE_CHECKING:
    pass

# Grants that are not derived from contracts and therefore survive a resync: the handover
# protocol access of a participant (M30 stage 3, docs/rules/M30-01.md) and the mandatory
# tenant wide staff grant (M2-08 entschieden, docs/rules/M2-07.md).
# The board audit access (A52, docs/rules/M21-07.md) is granted per engagement in
# mhvp.hoa.board and is not derived from contracts either.
MANUAL_BASES = frozenset(
    {"handover_participant", "staff_access", "board_audit", "document_class_grant"}
)
# M21-05: grants of a representative (power of attorney) are derived again on every resync from
# the active ``PortalRepresentation`` rows; they are read only and end with the power of attorney.
REPRESENTATION_BASIS = "representation"
STAFF_ACCESS_LEGAL_BASIS = "staff_access"
# AG12 (AF15-R): owner of a rental property (Mietverwaltung, ``property_owner``) without an
# ownership contract: read access to the own ``rental_owner`` legal entity only, for the
# owner's period. Derived again on every resync, so an owner change revokes it.
RENTAL_OWNER_BASIS = "rental_owner_right"


async def sync_grants(session: AsyncSession, account: PortalAccount) -> int:
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import LegalEntity, LegalEntityKind, PropertyOwner

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
    owners = (
        (
            await session.scalars(select(PropertyOwner).where(PropertyOwner.party_id.in_(parties)))
        ).all()
        if parties
        else []
    )
    for po in owners:
        entity = await session.scalar(
            select(LegalEntity.id).where(
                LegalEntity.property_id == po.property_id,
                LegalEntity.party_id == po.party_id,
                LegalEntity.kind == LegalEntityKind.RENTAL_OWNER,
            )
        )
        if entity is None:
            continue
        rows.append(
            AccessGrant(
                tenant_id=account.tenant_id,
                account_id=account.id,
                scope_type="legal_entity",
                scope_id=entity,
                right="download",
                legal_basis=RENTAL_OWNER_BASIS,
                role="owner",
                valid_from=po.valid_from,
                valid_to=po.valid_to,
            )
        )
    rows.extend(await _representation_grants(session, account))
    session.add_all(rows)
    # GA02-07: roles of the account follow the access matrix (tenant, owner).
    account.roles = sorted({r.role for r in rows})
    await session.flush()
    return len(rows)


async def _representation_grants(
    session: AsyncSession, account: PortalAccount
) -> list[AccessGrant]:
    """Read only grants for the ownership contracts of the represented contacts (M21-05), limited
    to the period of the power of attorney; a revoked power of attorney yields nothing."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.portal.models import PortalRepresentation
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    reps = (
        await session.scalars(
            select(PortalRepresentation).where(
                PortalRepresentation.account_id == account.id,
                PortalRepresentation.status == "active",
            )
        )
    ).all()
    out: list[AccessGrant] = []
    for rep in reps:
        parties = list(
            await session.scalars(
                select(PartyMember.party_id).where(
                    PartyMember.contact_id == rep.principal_contact_id
                )
            )
        )
        if not parties:
            continue
        contracts = (
            await session.scalars(
                select(Contract).where(
                    Contract.party_id.in_(parties), Contract.kind == ContractKind.OWNERSHIP
                )
            )
        ).all()
        for c in contracts:
            start = max(c.start_date, rep.valid_from)
            ends = [d for d in (c.end_date, rep.valid_to) if d is not None]
            stop = min(ends) if ends else None
            if stop is not None and stop < start:
                continue
            hoa = await session.scalar(
                select(LegalEntity.id).where(
                    LegalEntity.property_id == c.property_id,
                    LegalEntity.kind == LegalEntityKind.HOA,
                )
            )
            scopes = [("contract", c.id, "read"), ("unit", c.unit_id, "read")]
            if hoa is not None:
                scopes.append(("legal_entity", hoa, "download"))
            for scope_type, scope_id, right in scopes:
                out.append(
                    AccessGrant(
                        tenant_id=account.tenant_id,
                        account_id=account.id,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        right=right,
                        legal_basis=REPRESENTATION_BASIS,
                        role="owner",
                        valid_from=start,
                        valid_to=stop,
                    )
                )
    return out


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
    if any(g.legal_basis in ("hoa_member_right", RENTAL_OWNER_BASIS) for g in active):
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


def _search_sort(query: Any, document: Any, q: str | None, sort: str | None) -> Any:
    """Receipt search and sort in the database (Q10, M25-06): a substring match on title and
    filename (case insensitive, wildcards escaped) and the requested order, both on top of the
    already scoped query, so the matrix of the account still decides what can be found."""
    from sqlalchemy import func

    needle = (q or "").strip()
    if needle:
        query = query.where(
            or_(
                func.lower(document.title).contains(needle.lower(), autoescape=True),
                func.lower(document.filename).contains(needle.lower(), autoescape=True),
            )
        )
    key, _, direction = (sort or "created_desc").rpartition("_")
    column = {
        "created": document.created_at,
        "title": func.lower(document.title),
        "filename": func.lower(document.filename),
    }.get(key, document.created_at)
    order = column.desc() if direction == "desc" else column.asc()
    return query.order_by(order, document.id)


async def _document_class_ids(
    session: AsyncSession, class_grants: dict[tuple[uuid.UUID, str], set[str]]
) -> set[uuid.UUID]:
    """Documents of granted classes (GA03-05, 6.9.6): linked to the legal entity of the grant,
    class taken from the retention profile of the document (else of its category), released
    for the role of the grant through ``Document.visibility``."""
    if not class_grants:
        return set()
    from mhvp.documents.models import Document, DocumentCategory, DocumentLink, RetentionProfile

    entity_ids = {entity for entity, _c in class_grants}
    rows = (
        await session.execute(
            select(
                DocumentLink.entity_id,
                Document.id,
                Document.visibility,
                RetentionProfile.document_class,
            )
            .join(Document, Document.id == DocumentLink.document_id)
            .outerjoin(DocumentCategory, DocumentCategory.id == Document.category_id)
            .join(
                RetentionProfile,
                RetentionProfile.id
                == func.coalesce(
                    Document.retention_profile_id, DocumentCategory.retention_profile_id
                ),
            )
            .where(
                DocumentLink.entity_type == "legal_entity", DocumentLink.entity_id.in_(entity_ids)
            )
        )
    ).all()
    return {
        document_id
        for entity_id, document_id, visibility, doc_class in rows
        if class_grants.get((entity_id, doc_class), set()) & set(visibility or [])
    }


async def visible_documents(
    session: AsyncSession,
    account: PortalAccount,
    today: date,
    q: str | None = None,
    sort: str | None = None,
) -> list[Any]:
    """Documents linked to a granted scope and released for the role of that grant. A staff
    account with "documents:read" (M2-08 entschieden) sees every document of the tenant instead,
    since the tenant wide grant is not scoped to individual entities."""
    from mhvp.documents.models import Document, DocumentLink

    staff_perms = await staff_permissions(session, account)
    if "documents:read" in staff_perms:
        query = select(Document).where(Document.tenant_id == account.tenant_id)
        query = _search_sort(query, Document, q, sort)
        return list((await session.scalars(query)).all())

    active = await grants(session, account, today)
    scopes: dict[tuple[str, uuid.UUID], set[str]] = {}
    class_grants: dict[tuple[uuid.UUID, str], set[str]] = {}
    for g in active:
        if g.scope_type == "document_class":
            # GA03-05: scope_id is the legal entity, the class narrows the released documents
            if g.document_class:
                class_grants.setdefault((g.scope_id, g.document_class), set()).add(g.role)
            continue
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
    link_ids = {document_id for document_id, _t, _i in links}
    visibility = (
        {}
        if not link_ids
        else {
            row_id: set(vis or [])
            for row_id, vis in (
                await session.execute(
                    select(Document.id, Document.visibility).where(Document.id.in_(link_ids))
                )
            ).all()
        }
    )
    for document_id, entity_type, entity_id in links:
        if scopes[(entity_type, entity_id)] & visibility.get(document_id, set()):
            allowed.add(document_id)
    allowed |= await _document_class_ids(session, class_grants)
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
    query = _search_sort(select(Document).where(Document.id.in_(allowed)), Document, q, sort)
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
