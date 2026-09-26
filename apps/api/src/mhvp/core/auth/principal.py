"""Request principal: bearer token or API key, tenant/host check, permission guard."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.auth import tokens
from mhvp.core.auth.permissions import PLATFORM_SWITCH_PERMISSIONS, effective_permissions
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import ApiKey, Membership, MembershipStatus, TenantDomain, User

API_KEY_HEADER = "x-api-key"
API_KEY_PREFIX = "mhvp"


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID | None
    tenant_id: uuid.UUID | None
    permissions: frozenset[str] = field(default_factory=frozenset)
    roles: tuple[str, ...] = ()
    api_key_id: uuid.UUID | None = None
    is_platform_admin: bool = False
    platform_access_reason: str | None = None
    # Legal entity scope of the membership (A37, ``mhvp.core.auth.scope``): raw list from
    # ``Membership.legal_entity_ids``; only effective for scoped roles (tax_advisor).
    legal_entity_ids: tuple[uuid.UUID, ...] = ()

    def has(self, permission: str) -> bool:
        return permission in self.permissions


@dataclass(frozen=True)
class TenantPrincipal(Principal):
    """Principal guaranteed to act within a tenant (returned by ``require_permission``)."""

    tenant_id: uuid.UUID = field(default=uuid.UUID(int=0))


def sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.resources.session_factory
    return factory


@asynccontextmanager
async def tenant_tx(request: Request, principal: Principal) -> AsyncIterator[AsyncSession]:
    if principal.tenant_id is None:
        raise ProblemError(ErrorCodes.TENANT_SELECTION)
    async with tenant_transaction(sessions(request), principal.tenant_id) as session:
        # Lets domain helpers without a principal argument apply the legal entity scope
        # (``mhvp.core.auth.scope.session_principal``).
        session.info["mhvp.principal"] = principal
        yield session


def format_api_key(tenant_id: uuid.UUID, prefix: str, secret: str) -> str:
    return f"{API_KEY_PREFIX}_{tenant_id.hex}_{prefix}_{secret}"


def parse_api_key(value: str) -> tuple[uuid.UUID, str, str] | None:
    parts = value.split("_", 3)
    if len(parts) != 4 or parts[0] != API_KEY_PREFIX:
        return None
    try:
        return uuid.UUID(hex=parts[1]), parts[2], parts[3]
    except ValueError:
        return None


async def resolve_host_tenant(request: Request) -> uuid.UUID | None:
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if not host:
        return None
    async with platform_transaction(sessions(request)) as session:
        tenant_id: uuid.UUID | None = await session.scalar(
            select(TenantDomain.tenant_id).where(TenantDomain.host == host)
        )
        return tenant_id


async def _from_api_key(request: Request, raw: str) -> Principal:
    parsed = parse_api_key(raw)
    if parsed is None:
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)
    tenant_id, prefix, secret = parsed
    now = datetime.now(UTC)
    async with tenant_transaction(sessions(request), tenant_id) as session:
        key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
        if (
            key is None
            or key.revoked_at is not None
            or (key.expires_at is not None and key.expires_at <= now)
            or not tokens.constant_time_equals(key.secret_hash, tokens.sha256_hex(secret))
        ):
            raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)
        key.last_used_at = now
        return Principal(
            user_id=None, tenant_id=tenant_id, permissions=frozenset(key.scopes), api_key_id=key.id
        )


async def _from_bearer(request: Request, settings: Settings, raw: str) -> Principal:
    try:
        claims = tokens.decode_access_token(settings, raw)
    except tokens.TokenError:
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED) from None
    async with platform_transaction(sessions(request)) as session:
        user = await session.get(User, claims.user_id)
        if user is None or not user.active:
            raise ProblemError(ErrorCodes.NOT_AUTHENTICATED)
        is_admin = user.is_platform_admin
        membership = None
        if claims.tenant_id is not None:
            membership = await session.scalar(
                select(Membership).where(
                    Membership.tenant_id == claims.tenant_id,
                    Membership.user_id == user.id,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
    if claims.tenant_id is None:
        return Principal(user_id=claims.user_id, tenant_id=None, is_platform_admin=is_admin)
    if membership is None:
        # Only a platform administrator after an explicit, recorded switch (5.1).
        if not (is_admin and claims.platform and claims.platform_access_reason):
            raise ProblemError(ErrorCodes.FORBIDDEN)
        return Principal(
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            permissions=PLATFORM_SWITCH_PERMISSIONS,
            is_platform_admin=True,
            platform_access_reason=claims.platform_access_reason,
        )
    async with tenant_transaction(sessions(request), claims.tenant_id) as session:
        permissions, roles = await effective_permissions(session, claims.tenant_id, membership.id)
    return Principal(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        permissions=permissions,
        roles=tuple(roles),
        is_platform_admin=is_admin,
        legal_entity_ids=_scope_ids(membership.legal_entity_ids),
    )


def _scope_ids(raw: object) -> tuple[uuid.UUID, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[uuid.UUID] = []
    for item in raw:
        try:
            out.append(uuid.UUID(str(item)))
        except ValueError:
            continue
    return tuple(out)


async def get_principal(request: Request) -> Principal:
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    settings: Settings = request.app.state.settings
    authorization = request.headers.get("authorization", "")
    api_key = request.headers.get(API_KEY_HEADER)
    if authorization.lower().startswith("bearer "):
        principal = await _from_bearer(request, settings, authorization[7:].strip())
    elif api_key:
        principal = await _from_api_key(request, api_key.strip())
    else:
        raise ProblemError(ErrorCodes.NOT_AUTHENTICATED, extensions={})
    host_tenant = await resolve_host_tenant(request)
    if host_tenant is not None and principal.tenant_id != host_tenant:
        raise ProblemError(ErrorCodes.TENANT_MISMATCH)
    request.state.principal = principal
    request.state.tenant_id = principal.tenant_id
    return principal


def require_permission(permission: str) -> Callable[[Request], Awaitable[TenantPrincipal]]:
    async def dependency(request: Request) -> TenantPrincipal:
        principal = await get_principal(request)
        if principal.tenant_id is None or not principal.has(permission):
            raise ProblemError(
                ErrorCodes.FORBIDDEN, developer_message=f"Missing permission {permission}."
            )
        return TenantPrincipal(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            permissions=principal.permissions,
            roles=principal.roles,
            api_key_id=principal.api_key_id,
            is_platform_admin=principal.is_platform_admin,
            platform_access_reason=principal.platform_access_reason,
            legal_entity_ids=principal.legal_entity_ids,
        )

    return dependency


async def require_platform_admin(request: Request) -> Principal:
    principal = await get_principal(request)
    if not principal.is_platform_admin or principal.api_key_id is not None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Platform administrator only.")
    return principal
