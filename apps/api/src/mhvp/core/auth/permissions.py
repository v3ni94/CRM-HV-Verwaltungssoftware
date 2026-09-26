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
    "accounting",
    "ai",
    "contacts",
    "contracts",
    "documents",
    "properties",
    "tenant_settings",
    "tickets",
    "communication",
    "members",
    "roles",
    "api_keys",
    "webhooks",
    "audit",
    "release_gates",
    "sla",
    "immoware",
    "banking",
    # M35 Stufe 4 (docs/rules/M35-03.md): objektakte review and classification. `read` lists
    # review cases, rules, required documents and the AI call history; `update` decides review
    # cases (incl. asking the AI stage); `approve` maintains classification rules and required
    # documents (configuration, the objektakte "settings.write" level); `delete` removes rules
    # or required documents (docs/rules/M2-07.md: tenant_admin only). `create`/`export` are
    # registered by the matrix but not used by any endpoint yet.
    "objektakte",
    # A61 (docs/rules/A61-einsicht.md): inspection requests of the community. `read` lists and
    # downloads the package (logged), `update` records, releases, delivers and builds packages.
    "hoa",
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


_TICKETS = _rw("tickets") | {"tickets:approve"} | _rw("communication")
# SLA und Bereitschaft (M21 Übernahme aus dem Immoware Hub): Regeln, Eskalation, Bereitschaft und
# Kalender teilen sich sla:update ("verwalten"), Uhren/Alarme lesen und quittieren sla:read.
_SLA_MANAGE = _rw("sla") | {"sla:approve"}

# Rule "Löschen nur Administrator" (docs/rules/M2-07.md, Produktschutz): only tenant_admin
# (and platform admin via ALL_PERMISSIONS) hold `*:delete`. Non admin system roles keep the
# former name `_MASTER_RWD` for a minimal diff, but it no longer grants delete.
_MASTER_RW = _rw("contacts") | _rw("properties") | _rw("contracts") | _rw("documents") | _rw("ai")
_MASTER_RWD = _MASTER_RW

# M35 Stufe 4 (docs/rules/M35-03.md): review work (decide cases, ask the AI stage) versus
# maintaining the classification rule set and required documents (`approve`). Delete stays
# with tenant_admin (docs/rules/M2-07.md).
_OBJEKTAKTE_REVIEW = frozenset({"objektakte:read", "objektakte:update"})
_OBJEKTAKTE_MANAGE = _OBJEKTAKTE_REVIEW | {"objektakte:approve"}
_MASTER_R = _r("contacts") | _r("properties") | _r("contracts") | _r("documents")

# Accounting (M10): postings in non-leading ledgers; approve = Festschreibung, opening balances.
_ACC_RW = _rw("accounting")
_ACC_APPROVE = _ACC_RW | {"accounting:approve", "accounting:export"}

# Onlinebanking (M11-finapi): connecting, re-authorizing and disconnecting a bank connection,
# and seeing unassigned accounts, needs banking:approve in addition to accounting rights.
_BANKING_APPROVE = _rw("banking") | {"banking:approve"}

SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole("tenant_admin", "Mandantenadministrator", _ADMIN),
    SystemRole("administrator", "Administrator", _ADMIN),
    SystemRole(
        "standard",
        "Standard",
        _SETTINGS_R
        | _MASTER_RWD
        | _ACC_RW
        | _TICKETS
        | _SLA_MANAGE
        | _OBJEKTAKTE_MANAGE
        | _rw("hoa"),
    ),
    SystemRole("read_only", "Nur Lesezugriff", READ_ALL),
    SystemRole(
        "read_only_master_data",
        "Nur Lesezugriff Stammdaten",
        _SETTINGS_R | _MASTER_R | _r("objektakte"),
    ),
    SystemRole(
        "clerk_no_delete",
        "Sachbearbeiter ohne Löschen",
        _SETTINGS_R | _MASTER_RW | _rw("tickets") | _rw("communication") | _OBJEKTAKTE_REVIEW,
    ),
    SystemRole(
        "clerk_no_accounting",
        "Sachbearbeiter ohne Buchhaltung",
        _SETTINGS_R | _MASTER_RWD | _TICKETS | _SLA_MANAGE | _OBJEKTAKTE_REVIEW | _rw("hoa"),
    ),
    SystemRole(
        "accountant_no_banking",
        "Buchhalter ohne Onlinebanking",
        _SETTINGS_R
        | _rw("contacts")
        | _r("properties")
        | _r("contracts")
        | _rw("documents")
        | _ACC_APPROVE
        | _r("objektakte"),
    ),
    SystemRole(
        "accountant_banking",
        "Buchhalter mit Onlinebanking",
        _SETTINGS_R
        | _rw("contacts")
        | _r("properties")
        | _r("contracts")
        | _rw("documents")
        | _ACC_APPROVE
        | _BANKING_APPROVE
        | _r("objektakte"),
    ),
    # Caretakers see objects, not contracts or personal data of residents (data minimisation).
    SystemRole("caretaker", "Hausmeister", _r("properties") | _rw("tickets")),
    SystemRole(
        "technical_clerk",
        "Technischer Sachbearbeiter",
        _SETTINGS_R
        | _r("contacts")
        | _rw("properties")
        | _rw("documents")
        | _TICKETS
        | _OBJEKTAKTE_REVIEW,
    ),
    SystemRole("support", "Support", _SETTINGS_R | _MASTER_R | {"audit:read"} | _r("objektakte")),
    SystemRole("insurance_broker", "Versicherungsmakler", frozenset()),
    # Portal users (M21, M22): no CRM rights; portal endpoints check the access matrix.
    SystemRole("portal_user", "Portalzugang", frozenset()),
    SystemRole(
        "tax_advisor", "Steuerberater", _SETTINGS_R | _r("accounting") | {"accounting:export"}
    ),
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
