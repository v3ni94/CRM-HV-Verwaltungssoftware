"""Legal entity access scope per membership (A37, M18-02, docs/rules/M18-05-steuerberaterzugang.md).

Permissions of the role matrix apply per tenant (3.4). Some roles must additionally be limited
to individual legal entities of the tenant (the tax advisor of one WEG must not read the
ledgers of the other communities). The scope is stored per membership
(``Membership.legal_entity_ids``) and is only effective for the roles in ``SCOPED_ROLES``.

Semantics (Produktschutz, not a legal duty):

* A membership whose roles are all scoped roles (today only ``tax_advisor``) sees exactly the
  legal entities listed in ``legal_entity_ids``. An empty list means no legal entity at all:
  a tax advisor without an assignment sees nothing until the administrator assigns one.
* A membership with at least one unscoped role (administrator, standard, accountant, ...) is
  not limited by the list; the list is ignored.
* API keys and platform administrators after a recorded tenant switch carry no membership and
  are not limited.

Foreign legal entities never leak through error codes: single objects answer 404, lists are
filtered. The check is a second axis next to tenant RLS, never a replacement for it.
"""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import Principal, TenantPrincipal, get_principal
from mhvp.core.problems import ErrorCodes, ProblemError

# Roles whose membership scope (``Membership.legal_entity_ids``) limits data access.
SCOPED_ROLES: frozenset[str] = frozenset({"tax_advisor"})

# Key under which ``tenant_tx`` stores the request principal on ``AsyncSession.info``.
SESSION_PRINCIPAL_KEY = "mhvp.principal"


def allowed_legal_entity_ids(principal: Principal | None) -> frozenset[uuid.UUID] | None:
    """Legal entities the principal may access, or ``None`` when unrestricted.

    ``frozenset()`` (empty) means: restricted and nothing assigned, i.e. no access.
    """
    if principal is None or principal.api_key_id is not None:
        return None
    if principal.is_platform_admin and principal.platform_access_reason:
        return None
    if not principal.roles or any(role not in SCOPED_ROLES for role in principal.roles):
        return None
    return frozenset(principal.legal_entity_ids)


def is_restricted(principal: Principal | None) -> bool:
    return allowed_legal_entity_ids(principal) is not None


def legal_entity_allowed(principal: Principal | None, legal_entity_id: uuid.UUID) -> bool:
    allowed = allowed_legal_entity_ids(principal)
    return allowed is None or legal_entity_id in allowed


def ensure_legal_entity_allowed(principal: Principal | None, legal_entity_id: uuid.UUID) -> None:
    """Raises 404 (never 403: the existence of a foreign legal entity is not disclosed)."""
    if not legal_entity_allowed(principal, legal_entity_id):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def session_principal(session: AsyncSession) -> Principal | None:
    """The request principal attached by ``tenant_tx`` (``None`` on worker or seed sessions)."""
    value = session.info.get(SESSION_PRINCIPAL_KEY)
    return value if isinstance(value, Principal) else None


def session_allowed_legal_entity_ids(session: AsyncSession) -> frozenset[uuid.UUID] | None:
    """Scope of the session's principal; ``None`` when unrestricted or no principal attached."""
    return allowed_legal_entity_ids(session_principal(session))


def ensure_session_legal_entity_allowed(session: AsyncSession, legal_entity_id: uuid.UUID) -> None:
    ensure_legal_entity_allowed(session_principal(session), legal_entity_id)


def legal_entity_scope(
    permission: str,
) -> Callable[[Request], Awaitable[frozenset[uuid.UUID] | None]]:
    """Dependency: the permission guard of ``require_permission`` plus the allowed legal
    entity ids (``None`` = unrestricted) for endpoints that filter lists themselves."""

    async def dependency(request: Request) -> frozenset[uuid.UUID] | None:
        principal = await get_principal(request)
        if principal.tenant_id is None or not principal.has(permission):
            raise ProblemError(
                ErrorCodes.FORBIDDEN, developer_message=f"Missing permission {permission}."
            )
        return allowed_legal_entity_ids(principal)

    return dependency


__all__ = [
    "SCOPED_ROLES",
    "SESSION_PRINCIPAL_KEY",
    "TenantPrincipal",
    "allowed_legal_entity_ids",
    "ensure_legal_entity_allowed",
    "ensure_session_legal_entity_allowed",
    "is_restricted",
    "legal_entity_allowed",
    "legal_entity_scope",
    "session_allowed_legal_entity_ids",
    "session_principal",
]
