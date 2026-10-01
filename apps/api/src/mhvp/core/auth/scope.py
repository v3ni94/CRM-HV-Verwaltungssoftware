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
from typing import Any

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


# Property assignment (3.4 "optionale Objektzuordnung", M2-02/S16-02,
# docs/rules/M2-02-objektzuordnung.md). Produktschutz, not a legal duty:
#
# * ``Membership.property_ids`` empty: no restriction (default, existing behaviour).
# * non empty: the member sees only these properties, whatever the other roles, unless one of
#   the roles is an administrator role (``PROPERTY_UNSCOPED_ROLES``).
# * API keys and platform administrators after a recorded switch are not restricted.
#
# Foreign properties answer 404 like foreign legal entities. Domains filter their lists and
# detail reads with ``property_allowed``/``session_allowed_property_ids``; the axis sits next to
# tenant RLS and the legal entity scope, never replaces them.
PROPERTY_UNSCOPED_ROLES: frozenset[str] = frozenset({"tenant_admin", "administrator"})


def allowed_property_ids(principal: Principal | None) -> frozenset[uuid.UUID] | None:
    """Properties the principal may access, or ``None`` when unrestricted."""
    if principal is None or principal.api_key_id is not None:
        return None
    if principal.is_platform_admin and principal.platform_access_reason:
        return None
    if not principal.property_ids:
        return None
    if any(role in PROPERTY_UNSCOPED_ROLES for role in principal.roles):
        return None
    return frozenset(principal.property_ids)


def property_allowed(principal: Principal | None, property_id: uuid.UUID | None) -> bool:
    """``property_id`` ``None`` (record without property) is visible only when unrestricted."""
    allowed = allowed_property_ids(principal)
    return allowed is None or (property_id is not None and property_id in allowed)


def ensure_property_allowed(principal: Principal | None, property_id: uuid.UUID | None) -> None:
    """Raises 404 (never 403: the existence of a foreign property is not disclosed)."""
    if not property_allowed(principal, property_id):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def session_allowed_property_ids(session: AsyncSession) -> frozenset[uuid.UUID] | None:
    return allowed_property_ids(session_principal(session))


def ensure_session_property_allowed(session: AsyncSession, property_id: uuid.UUID | None) -> None:
    ensure_property_allowed(session_principal(session), property_id)


async def property_path_guard(request: Request) -> None:
    """Router dependency: a ``{property_id}`` path parameter outside the membership's property
    assignment answers 404 before the endpoint runs (M2-02/S16-02). Paths without the
    parameter or with an unparsable value (the endpoint answers 422) pass unchanged."""
    raw = request.path_params.get("property_id")
    if raw is None:
        return
    try:
        property_id = uuid.UUID(str(raw))
    except ValueError:
        return
    ensure_property_allowed(await get_principal(request), property_id)


def _property_of(column: Any, value: uuid.UUID) -> Any:
    """Select of the property id of the row ``value`` of ``column``'s table."""
    from sqlalchemy import select

    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity

    owner = column.class_
    if column.key == "legal_entity_id":
        return (
            select(LegalEntity.property_id)
            .join(owner, column == LegalEntity.id)
            .where(owner.id == value)
        )
    if column.key == "ledger_id":
        return select(Ledger.property_id).join(owner, column == Ledger.id).where(owner.id == value)
    return select(column).where(owner.id == value)


def property_column_guard(
    columns: dict[str, Any],
) -> Callable[[Request], Awaitable[None]]:
    """Router dependency factory (M2-02/S16-02, Q13-01): ``columns`` maps a path or query
    parameter (``statement_id``) to the ORM column holding the property of that row
    (``Statement.property_id``); a ``legal_entity_id`` or ``ledger_id`` column resolves the
    property through the legal entity or the ledger. A row outside the membership's property
    assignment answers 404 before the endpoint runs; unknown ids and unparsable values pass
    through, so the endpoint keeps its own 404 or 422. Unrestricted members cost no query."""

    async def dependency(request: Request) -> None:
        params = {**request.query_params, **request.path_params}
        names = [name for name in columns if name in params]
        if not names:
            return
        principal = await get_principal(request)
        if principal.tenant_id is None or allowed_property_ids(principal) is None:
            return
        from mhvp.core.auth.principal import tenant_tx

        async with tenant_tx(request, principal) as session:
            for name in names:
                try:
                    value = uuid.UUID(str(params[name]))
                except ValueError:
                    continue
                column = columns[name]
                found = (await session.execute(_property_of(column, value))).first()
                if found is None:
                    continue
                ensure_property_allowed(principal, found[0])

    return dependency


__all__ = [
    "PROPERTY_UNSCOPED_ROLES",
    "SCOPED_ROLES",
    "SESSION_PRINCIPAL_KEY",
    "TenantPrincipal",
    "allowed_legal_entity_ids",
    "allowed_property_ids",
    "ensure_legal_entity_allowed",
    "ensure_property_allowed",
    "ensure_session_legal_entity_allowed",
    "ensure_session_property_allowed",
    "is_restricted",
    "legal_entity_allowed",
    "legal_entity_scope",
    "property_allowed",
    "property_column_guard",
    "property_path_guard",
    "session_allowed_legal_entity_ids",
    "session_allowed_property_ids",
    "session_principal",
]
