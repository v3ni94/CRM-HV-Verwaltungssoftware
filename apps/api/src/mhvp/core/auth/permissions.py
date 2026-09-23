"""Permission matrix (section 3.4): resource x action, roles per tenant with inheritance.

Resources are registered with the milestone that introduces them. System roles follow annex
A.4; their permissions cover only the resources that exist so far.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.platform.models import MembershipRole, Role, RolePermission

ACTIONS: tuple[str, ...] = ("read", "create", "update", "delete", "approve", "export")
RESOURCES: tuple[str, ...] = (
    "tenant_settings",
    "members",
    "roles",
    "api_keys",
    "webhooks",
    "audit",
    "release_gates",
)
ALL_PERMISSIONS: frozenset[str] = frozenset(f"{r}:{a}" for r in RESOURCES for a in ACTIONS)
READ_ALL: frozenset[str] = frozenset(f"{r}:read" for r in RESOURCES)


@dataclass(frozen=True)
class SystemRole:
    code: str
    name: str
    permissions: frozenset[str]


# Annex A.4 role templates. Domain permissions are added per milestone (M3 contacts, ...).
_ADMIN = ALL_PERMISSIONS - {"release_gates:approve"}
SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole("tenant_admin", "Mandantenadministrator", _ADMIN),
    SystemRole("administrator", "Administrator", _ADMIN),
    SystemRole("standard", "Standard", frozenset({"tenant_settings:read"})),
    SystemRole("read_only", "Nur Lesezugriff", READ_ALL),
    SystemRole(
        "read_only_master_data", "Nur Lesezugriff Stammdaten", frozenset({"tenant_settings:read"})
    ),
    SystemRole(
        "clerk_no_delete", "Sachbearbeiter ohne Löschen", frozenset({"tenant_settings:read"})
    ),
    SystemRole(
        "clerk_no_accounting",
        "Sachbearbeiter ohne Buchhaltung",
        frozenset({"tenant_settings:read"}),
    ),
    SystemRole(
        "accountant_no_banking",
        "Buchhalter ohne Onlinebanking",
        frozenset({"tenant_settings:read"}),
    ),
    SystemRole(
        "accountant_banking", "Buchhalter mit Onlinebanking", frozenset({"tenant_settings:read"})
    ),
    SystemRole("caretaker", "Hausmeister", frozenset()),
    SystemRole(
        "technical_clerk", "Technischer Sachbearbeiter", frozenset({"tenant_settings:read"})
    ),
    SystemRole("support", "Support", frozenset({"tenant_settings:read", "audit:read"})),
    SystemRole("insurance_broker", "Versicherungsmakler", frozenset()),
    SystemRole("tax_advisor", "Steuerberater", frozenset({"tenant_settings:read"})),
)

# A platform administrator after an explicit, recorded tenant switch (section 5.1).
PLATFORM_SWITCH_PERMISSIONS: frozenset[str] = ALL_PERMISSIONS - {"release_gates:create"}


def validate_permission(permission: str) -> None:
    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"unknown permission: {permission}")


async def effective_permissions(
    session: AsyncSession, tenant_id: uuid.UUID, membership_id: uuid.UUID
) -> tuple[frozenset[str], list[str]]:
    """Permissions and role codes of a membership, including inherited parent roles."""
    role_rows = (
        await session.execute(
            select(Role.id, Role.code, Role.parent_role_id)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == tenant_id, MembershipRole.membership_id == membership_id
            )
        )
    ).all()
    codes = sorted(row.code for row in role_rows)
    role_ids: set[uuid.UUID] = set()
    frontier = [row.id for row in role_rows]
    while frontier:
        role_id = frontier.pop()
        if role_id in role_ids:
            continue  # inheritance cycle protection
        role_ids.add(role_id)
        parent = await session.scalar(select(Role.parent_role_id).where(Role.id == role_id))
        if parent is not None:
            frontier.append(parent)
    if not role_ids:
        return frozenset(), codes
    rows = await session.execute(
        select(RolePermission.resource, RolePermission.action).where(
            RolePermission.tenant_id == tenant_id, RolePermission.role_id.in_(role_ids)
        )
    )
    return frozenset(f"{r.resource}:{r.action}" for r in rows), codes
