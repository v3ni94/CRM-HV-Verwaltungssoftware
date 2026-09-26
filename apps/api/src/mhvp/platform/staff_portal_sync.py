"""Staff portal grant on a role change (M2-08 rest, 26.09.2026, docs/rules/M2-07.md).

The mandatory tenant wide portal grant of a staff member follows the member's CRM roles: when a
membership moves into an exempt role set (``portal_user``, ``read_only``,
``read_only_master_data``, ``tax_advisor``, ``insurance_broker``) the grant is deactivated
(``valid_to`` = yesterday, the row stays for the audit trail); a change back reactivates it or,
if none exists yet, creates it via ``ensure_staff_portal_access``. External grants of the same
account are never touched. Produktschutz, no legal rule."""

import uuid
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.events import emit
from mhvp.platform.models import Membership, User
from mhvp.portal.access import STAFF_ACCESS_LEGAL_BASIS
from mhvp.portal.models import AccessGrant, PortalAccount
from mhvp.portal.staff_access import is_staff_role_exempt
from mhvp.workspace.services import local_today

DEACTIVATED_EVENT = "portal_account.staff_grant_deactivated"
REACTIVATED_EVENT = "portal_account.staff_grant_reactivated"


async def sync_staff_grant_after_role_change(
    request: Request,
    *,
    principal: TenantPrincipal,
    membership_id: uuid.UUID,
    role_codes: list[str],
) -> str:
    """Returns ``"deactivated"``, ``"reactivated"``, ``"granted"``, ``"exempt"``,
    ``"conflict"`` or ``"unchanged"``."""
    from mhvp.core.auth.principal import sessions
    from mhvp.platform.routers import ensure_staff_portal_access

    async with platform_transaction(sessions(request)) as session:
        row = (
            await session.execute(
                select(Membership.contact_id, User.id, User.email, User.display_name)
                .join(User, User.id == Membership.user_id)
                .where(Membership.id == membership_id)
            )
        ).one_or_none()
    if row is None:
        return "unchanged"
    contact_id, user_id, email, display_name = row
    exempt = is_staff_role_exempt(role_codes)
    today = local_today()

    async with tenant_tx(request, principal) as session:
        account = await session.scalar(
            select(PortalAccount).where(
                PortalAccount.tenant_id == principal.tenant_id, PortalAccount.user_id == user_id
            )
        )
        grant = (
            await session.scalar(
                select(AccessGrant).where(
                    AccessGrant.account_id == account.id,
                    AccessGrant.legal_basis == STAFF_ACCESS_LEGAL_BASIS,
                )
            )
            if account is not None
            else None
        )
        active = grant is not None and (grant.valid_to is None or grant.valid_to >= today)
        if exempt:
            if grant is None or not active:
                return "exempt"
            grant.valid_to = today - timedelta(days=1)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type=DEACTIVATED_EVENT,
                entity_type="portal_account",
                entity_id=grant.account_id,
                actor_user_id=principal.user_id,
                payload={"membership_id": str(membership_id), "roles": sorted(role_codes)},
            )
            return "deactivated"
        if grant is not None:
            if active:
                return "unchanged"
            grant.valid_to = None
            grant.valid_from = min(grant.valid_from, today)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type=REACTIVATED_EVENT,
                entity_type="portal_account",
                entity_id=grant.account_id,
                actor_user_id=principal.user_id,
                payload={"membership_id": str(membership_id), "roles": sorted(role_codes)},
            )
            return "reactivated"
    if contact_id is None:
        # Membership without a linked contact (created before M2-08): the resync endpoint
        # of the portal role matrix handles these, nothing is invented here.
        return "unchanged"
    return await ensure_staff_portal_access(
        request,
        principal=principal,
        contact_id=contact_id,
        email=email,
        display_name=display_name,
        role_codes=role_codes,
    )
