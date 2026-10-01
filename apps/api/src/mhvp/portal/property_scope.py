"""Property assignment of the membership in the portal administration (M2-02, R08-01).

A portal account belongs to a contact; the contact reaches properties through the contracts
of its parties (``PartyMember`` to ``Contract.party_id``, ``Contract.property_id``). For a
member with a property assignment (``Membership.property_ids``) a contact, and its portal
account, is visible when at least one such contract lies inside the assignment. Outside it
single objects answer 404, lists are empty and invitations are refused with 404.
Produktschutz, not a legal duty; next to tenant RLS and the legal entity scope (A37).
"""

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import get_principal, tenant_tx
from mhvp.core.auth.scope import allowed_property_ids, session_allowed_property_ids
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal.models import PortalAccount


def contact_property_query(contact_id: Any, allowed: frozenset[uuid.UUID]) -> Any:
    """Select of one contract id of ``contact_id`` inside ``allowed`` (existence check)."""
    from mhvp.contacts.models import PartyMember
    from mhvp.contracts.models import Contract

    return (
        select(Contract.id)
        .join(PartyMember, PartyMember.party_id == Contract.party_id)
        .where(PartyMember.contact_id == contact_id, Contract.property_id.in_(allowed))
        .limit(1)
    )


async def contact_visible(session: AsyncSession, contact_id: uuid.UUID) -> bool:
    allowed = session_allowed_property_ids(session)
    if allowed is None:
        return True
    return await session.scalar(contact_property_query(contact_id, allowed)) is not None


async def ensure_contact_visible(session: AsyncSession, contact_id: uuid.UUID) -> None:
    if not await contact_visible(session, contact_id):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def portal_admin_guard(request: Request) -> None:
    """Router dependency of ``/portal-admin``: an ``{account_id}`` path parameter whose
    contact has no contract inside the member's property assignment answers 404 before the
    endpoint runs. Unknown or unparsable ids pass through (the endpoint answers 404 or 422)."""
    raw = request.path_params.get("account_id")
    if raw is None:
        return
    try:
        account_id = uuid.UUID(str(raw))
    except ValueError:
        return
    principal = await get_principal(request)
    if principal.tenant_id is None:
        return
    allowed = allowed_property_ids(principal)
    if allowed is None:
        return
    async with tenant_tx(request, principal) as session:
        contact_id = await session.scalar(
            select(PortalAccount.contact_id).where(PortalAccount.id == account_id)
        )
        if contact_id is None:
            return
        if await session.scalar(contact_property_query(contact_id, allowed)) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
