"""Tenant provisioning, users and memberships (section 5)."""

import json
import uuid
from importlib import resources
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.auth import passwords
from mhvp.core.auth.permissions import SYSTEM_ROLES
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import (
    Membership,
    MembershipRole,
    Role,
    RolePermission,
    Tenant,
    TenantDomain,
    TenantSettings,
    User,
)
from mhvp.platform.schemas import Branding, CompanyData
from mhvp.properties.defaults import ensure_tenant_defaults

SEED_FILES = ("hausverwaltung-mueller.json", "timo-mueller.json")


def load_seed(name: str) -> dict[str, Any]:
    text = resources.files("mhvp.tenant").joinpath("seeds", name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    CompanyData.model_validate(data["company"])
    Branding.model_validate(data["branding"])
    return data


async def ensure_system_roles(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    for template in SYSTEM_ROLES:
        role = await session.scalar(
            select(Role).where(Role.tenant_id == tenant_id, Role.code == template.code)
        )
        if role is None:
            role = Role(tenant_id=tenant_id, code=template.code, name=template.name, is_system=True)
            session.add(role)
            await session.flush()
        existing = set(
            (
                await session.execute(
                    select(RolePermission.resource, RolePermission.action).where(
                        RolePermission.role_id == role.id
                    )
                )
            ).tuples()
        )
        for permission in sorted(template.permissions):
            resource, action = permission.split(":")
            if (resource, action) not in existing:
                session.add(
                    RolePermission(
                        tenant_id=tenant_id, role_id=role.id, resource=resource, action=action
                    )
                )
    await session.flush()


async def provision_tenant(
    factory: async_sessionmaker[AsyncSession],
    *,
    slug: str,
    name: str,
    company: dict[str, Any] | None = None,
    branding: dict[str, Any] | None = None,
    sources: dict[str, str] | None = None,
    domains: list[str] | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, bool]:
    """Create or complete a tenant idempotently. Returns (tenant id, created)."""
    async with platform_transaction(factory) as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
        created = tenant is None
        if tenant is None:
            tenant = Tenant(slug=slug, name=name, created_by=actor_user_id)
            session.add(tenant)
            await session.flush()
        tenant_id = tenant.id
        for host in domains or []:
            if await session.scalar(select(TenantDomain).where(TenantDomain.host == host)) is None:
                session.add(TenantDomain(tenant_id=tenant_id, host=host.lower()))
    async with tenant_transaction(factory, tenant_id) as session:
        settings = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
        if settings is None:
            session.add(
                TenantSettings(
                    tenant_id=tenant_id,
                    company=CompanyData.model_validate(company or {"name": name}).model_dump(
                        mode="json"
                    ),
                    branding=Branding.model_validate(branding or {}).model_dump(mode="json"),
                    sources=sources or {},
                    created_by=actor_user_id,
                )
            )
        await ensure_system_roles(session, tenant_id)
        await ensure_tenant_defaults(session, tenant_id)
        if created:
            await emit(
                session,
                tenant_id=tenant_id,
                type="tenant.created",
                entity_type="tenant",
                entity_id=tenant_id,
                actor_user_id=actor_user_id,
                payload={"slug": slug},
            )
    return tenant_id, created


async def seed_tenants(factory: async_sessionmaker[AsyncSession]) -> dict[str, uuid.UUID]:
    result: dict[str, uuid.UUID] = {}
    for name in SEED_FILES:
        data = load_seed(name)
        tenant_id, _ = await provision_tenant(
            factory,
            slug=data["slug"],
            name=data["name"],
            company=data["company"],
            branding=data["branding"],
            sources=data["sources"],
            domains=data["domains"],
        )
        result[data["slug"]] = tenant_id
    return result


async def create_user(
    factory: async_sessionmaker[AsyncSession],
    *,
    email: str,
    display_name: str,
    password: str,
    is_platform_admin: bool = False,
) -> uuid.UUID:
    violation = passwords.policy_violation(password)
    if violation:
        raise ProblemError(ErrorCodes.PASSWORD_POLICY, detail=violation)
    async with platform_transaction(factory) as session:
        normalised = email.strip().lower()
        if await session.scalar(select(User.id).where(User.email == normalised)) is not None:
            raise ProblemError(ErrorCodes.CONFLICT, developer_message="E-mail already registered.")
        user = User(
            email=normalised,
            display_name=display_name,
            password_hash=passwords.hash_password(password),
            is_platform_admin=is_platform_admin,
        )
        session.add(user)
        await session.flush()
        return user.id


async def _role_ids(
    session: AsyncSession, tenant_id: uuid.UUID, codes: list[str]
) -> list[uuid.UUID]:
    rows = (
        await session.execute(
            select(Role.id, Role.code).where(Role.tenant_id == tenant_id, Role.code.in_(codes))
        )
    ).all()
    found = {row.code: row.id for row in rows}
    missing = sorted(set(codes) - set(found))
    if missing:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Rollen: {', '.join(missing)}."
        )
    return [found[code] for code in codes]


async def add_member(
    factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role_codes: list[str],
    actor_user_id: uuid.UUID | None,
) -> uuid.UUID:
    async with platform_transaction(factory) as session:
        if await session.get(User, user_id) is None or await session.get(Tenant, tenant_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        membership = await session.scalar(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        )
        if membership is None:
            membership = Membership(tenant_id=tenant_id, user_id=user_id, created_by=actor_user_id)
            session.add(membership)
            await session.flush()
        membership_id = membership.id
    await set_member_roles(
        factory,
        tenant_id=tenant_id,
        membership_id=membership_id,
        role_codes=role_codes,
        actor_user_id=actor_user_id,
        event="membership.created",
    )
    return membership_id


async def set_member_roles(
    factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    role_codes: list[str],
    actor_user_id: uuid.UUID | None,
    event: str = "membership.roles_changed",
) -> None:
    async with tenant_transaction(factory, tenant_id) as session:
        role_ids = await _role_ids(session, tenant_id, role_codes)
        before = sorted(
            (
                await session.scalars(
                    select(Role.code)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(MembershipRole.membership_id == membership_id)
                )
            ).all()
        )
        await session.execute(
            delete(MembershipRole).where(MembershipRole.membership_id == membership_id)
        )
        for role_id in role_ids:
            session.add(
                MembershipRole(tenant_id=tenant_id, membership_id=membership_id, role_id=role_id)
            )
        await emit(
            session,
            tenant_id=tenant_id,
            type=event,
            entity_type="membership",
            entity_id=membership_id,
            actor_user_id=actor_user_id,
            payload={"roles": sorted(role_codes)},
            changes={"roles": {"old": before, "new": sorted(role_codes)}},
        )
