"""Permission filter of the portal assistant (AE28, M7-06, 14 "Chat liest ausschließlich den für
die Person freigegebenen Inhalt", 9.1 RAG "Berechtigungsfilter vor der Ähnlichkeitssuche").

The filter is security critical and has one source: the access matrix of the account
(``mhvp.portal.access``, table ``access_grant``). The assistant reads exactly the documents the
account sees in the portal document list, optionally narrowed to one unit or one document, never
more. Rules:

* no active grant: the scope is empty, the assistant has nothing to read and calls no provider;
* a unit or a document outside the grants answers 404 (the existence is not revealed);
* a locked, revoked or unknown account has an empty scope;
* the AI path derives the scope again from the account at execution time (``audience_scope``),
  the id list handed over with a run can only narrow it, never widen it.

Produktschutz and access control, no legal rule."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal import access
from mhvp.portal.models import PortalAccount
from mhvp.portal.status import LOGIN_STATUSES


@dataclass(frozen=True)
class AssistantScope:
    """What the assistant may read for one question."""

    unit_ids: frozenset[uuid.UUID]  # units with an active grant of the account
    document_ids: frozenset[uuid.UUID]  # readable documents after the optional focus
    readable_documents: int  # readable documents before the focus (status display)
    focus_unit_id: uuid.UUID | None = None
    focus_document_id: uuid.UUID | None = None

    @property
    def empty(self) -> bool:
        return not self.document_ids


async def granted_unit_ids(
    session: AsyncSession, account: PortalAccount, today: date
) -> set[uuid.UUID]:
    """Units of the active grants: unit grants and the unit of every granted contract."""
    from mhvp.contracts.models import Contract

    active = await access.grants(session, account, today)
    units = {g.scope_id for g in active if g.scope_type == "unit"}
    contract_ids = {g.scope_id for g in active if g.scope_type == "contract"}
    if contract_ids:
        units |= set(
            await session.scalars(select(Contract.unit_id).where(Contract.id.in_(contract_ids)))
        )
    return units


async def unit_document_ids(session: AsyncSession, unit_id: uuid.UUID) -> set[uuid.UUID]:
    """Documents linked to the unit, its property, its contracts or the legal entities of its
    property. Only a narrowing: the result is always intersected with the readable documents."""
    from mhvp.contracts.models import Contract
    from mhvp.documents.models import DocumentLink
    from mhvp.properties.models import LegalEntity, Unit

    unit = await session.get(Unit, unit_id)
    if unit is None:
        return set()
    contract_ids = select(Contract.id).where(Contract.unit_id == unit_id)
    entity_ids = select(LegalEntity.id).where(LegalEntity.property_id == unit.property_id)
    rows = await session.scalars(
        select(DocumentLink.document_id).where(
            or_(
                (DocumentLink.entity_type == "unit") & (DocumentLink.entity_id == unit_id),
                (DocumentLink.entity_type == "property")
                & (DocumentLink.entity_id == unit.property_id),
                (DocumentLink.entity_type == "contract")
                & (DocumentLink.entity_id.in_(contract_ids)),
                (DocumentLink.entity_type == "legal_entity")
                & (DocumentLink.entity_id.in_(entity_ids)),
            )
        )
    )
    return set(rows)


async def build_scope(
    session: AsyncSession,
    account: PortalAccount,
    today: date,
    *,
    unit_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
) -> AssistantScope:
    """Scope of one question. A unit without grant and a document outside the readable set
    answer 404; an account without any grant gets an empty scope."""
    if account.status not in LOGIN_STATUSES:
        return AssistantScope(frozenset(), frozenset(), 0)
    units = await granted_unit_ids(session, account, today)
    readable = await access.visible_document_ids(session, account, today)
    documents = set(readable)
    if unit_id is not None:
        if unit_id not in units:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        documents &= await unit_document_ids(session, unit_id)
    if document_id is not None:
        if document_id not in readable:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        documents &= {document_id}
    return AssistantScope(
        unit_ids=frozenset(units),
        document_ids=frozenset(documents),
        readable_documents=len(readable),
        focus_unit_id=unit_id,
        focus_document_id=document_id,
    )


async def audience_scope(
    session: AsyncSession, account_id: uuid.UUID | None, today: date
) -> set[uuid.UUID]:
    """Readable documents of a portal account for the AI gateway; never ``None``. An unknown,
    locked or revoked account yields the empty set (nothing is read)."""
    if account_id is None:
        return set()
    account = await session.get(PortalAccount, account_id)
    if account is None or account.status not in LOGIN_STATUSES:
        return set()
    return await access.visible_document_ids(session, account, today)


def narrow(scope: set[uuid.UUID], focus_ids: object) -> set[uuid.UUID]:
    """Intersection with the optional focus list of the run (a narrowing only). A missing list
    keeps the scope, a malformed list yields the empty set."""
    if focus_ids is None:
        return scope
    if not isinstance(focus_ids, list):
        return set()
    allowed: set[uuid.UUID] = set()
    for raw in focus_ids:
        try:
            allowed.add(uuid.UUID(str(raw)))
        except ValueError:
            return set()
    return scope & allowed
