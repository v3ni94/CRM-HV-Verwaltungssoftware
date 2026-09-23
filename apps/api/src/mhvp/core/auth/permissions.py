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
    "contacts",
    "contracts",
    "documents",
    "properties",
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
_SETTINGS_R = frozenset({"tenant_settings:read"})


def _rw(resource: str, *, delete: bool = False) -> frozenset[str]:
    actions = ["read", "create", "update"] + (["delete"] if delete else [])
    return frozenset(f"{resource}:{a}" for a in actions)


def _r(resource: str) -> frozenset[str]:
    return frozenset({f"{resource}:read"})


_MASTER_RWD = (
    _rw("contacts", delete=True)
    | _rw("properties", delete=True)
    | _rw("contracts", delete=True)
    | _rw("documents", delete=True)
)
_MASTER_RW = _rw("contacts") | _rw("properties") | _rw("contracts") | _rw("documents")
_MASTER_R = _r("contacts") | _r("properties") | _r("contracts") | _r("documents")

SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole("tenant_admin", "Mandantenadministrator", _ADMIN),
    SystemRole("administrator", "Administrator", _ADMIN),
    SystemRole("standard", "Standard", _SETTINGS_R | _MASTER_RWD),
    SystemRole("read_only", "Nur Lesezugriff", READ_ALL),
    SystemRole("read_only_master_data", "Nur Lesezugriff Stammdaten", _SETTINGS_R | _MASTER_R),
    SystemRole("clerk_no_delete", "Sachbearbeiter ohne Löschen", _SETTINGS_R | _MASTER_RW),
    SystemRole("clerk_no_accounting", "Sachbearbeiter ohne Buchhaltung", _SETTINGS_R | _MASTER_RWD),
    SystemRole(
        "accountant_no_banking",
        "Buchhalter ohne Onlinebanking",
        _SETTINGS_R | _rw("contacts") | _r("properties") | _r("contracts") | _rw("documents"),
    ),
    SystemRole(
        "accountant_banking",
        "Buchhalter mit Onlinebanking",
        _SETTINGS_R | _rw("contacts") | _r("properties") | _r("contracts") | _rw("documents"),
    ),
    # Caretakers see objects, not contracts or personal data of residents (data minimisation).
    SystemRole("caretaker", "Hausmeister", _r("properties")),
    SystemRole(
        "technical_clerk",
        "Technischer Sachbearbeiter",
        _SETTINGS_R | _r("contacts") | _rw("properties") | _rw("documents"),
    ),
    SystemRole("support", "Support", _SETTINGS_R | _MASTER_R | {"audit:read"}),
    SystemRole("insurance_broker", "Versicherungsmakler", frozenset()),
    SystemRole("tax_advisor", "Steuerberater", _SETTINGS_R),
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
