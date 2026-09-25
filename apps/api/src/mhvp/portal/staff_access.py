"""Portal access for staff (tenant members), operator decision 25.09.2026, M2-08 entschieden
(docs/rules/M2-07.md): every staff membership gets a mandatory portal account with a tenant
wide access grant. Which portal functions that grant actually unlocks is a small permission
catalogue, configured per CRM system role and stored per tenant on
``TenantSettings.portal_role_permissions`` (overrides only; unset roles use the built in
default below). This is a Produktschutz configuration, not a legal rule.
"""

from mhvp.core.auth.permissions import SYSTEM_ROLES

# The portal functions a staff grant can unlock. Kept separate from the CRM permission
# catalogue (mhvp.core.auth.permissions): the portal only offers a narrow read/participate
# surface (documents, tickets, work orders, handover protocols), never CRM write access.
PORTAL_STAFF_PERMISSIONS: tuple[str, ...] = (
    "documents:read",
    "tickets:read",
    "tickets:create",
    "tickets:comment",
    "work_orders:read",
    "handover:read",
)
_ALL = frozenset(PORTAL_STAFF_PERMISSIONS)
_READ_ONLY = frozenset({"documents:read", "tickets:read", "work_orders:read", "handover:read"})
_STAFF_STANDARD = _READ_ONLY | {"tickets:create", "tickets:comment"}

# System roles that are never staff portal accounts: portal_user is the external portal role
# itself; read_only, read_only_master_data, tax_advisor and insurance_broker are excluded by
# operator decision 25.09.2026 (limited or advisory roles, no operational portal need).
EXEMPT_ROLE_CODES: frozenset[str] = frozenset(
    {"portal_user", "read_only", "read_only_master_data", "tax_advisor", "insurance_broker"}
)

DEFAULT_STAFF_PORTAL_PERMISSIONS: dict[str, frozenset[str]] = {
    "tenant_admin": _ALL,
    "administrator": _ALL,
    "support": _READ_ONLY,
}
for _role in SYSTEM_ROLES:
    if _role.code in EXEMPT_ROLE_CODES or _role.code in DEFAULT_STAFF_PORTAL_PERMISSIONS:
        continue
    # standard, clerk_*, technical_clerk, caretaker, accountant_* (operator 25.09.2026):
    # read on documents, tickets, work orders and handover protocols, plus create tickets
    # and comment.
    DEFAULT_STAFF_PORTAL_PERMISSIONS[_role.code] = _STAFF_STANDARD


def is_staff_role_exempt(role_codes: list[str]) -> bool:
    """True if none of the member's roles should ever get a mandatory portal grant."""
    codes = set(role_codes)
    return not codes or codes <= EXEMPT_ROLE_CODES


def effective_permissions_for_role_codes(
    portal_role_permissions: dict[str, list[str]], role_codes: list[str]
) -> frozenset[str]:
    """Union of the tenant's configured (or default) portal permissions for these roles."""
    out: set[str] = set()
    for code in role_codes:
        override = portal_role_permissions.get(code)
        if override is not None:
            out |= {p for p in override if p in _ALL}
        else:
            out |= DEFAULT_STAFF_PORTAL_PERMISSIONS.get(code, frozenset())
    return frozenset(out)


def role_matrix(portal_role_permissions: dict[str, list[str]]) -> dict[str, list[str]]:
    """The full matrix (every non exempt system role, override or default) for the settings UI."""
    codes = sorted({r.code for r in SYSTEM_ROLES} - EXEMPT_ROLE_CODES)
    return {
        code: sorted(effective_permissions_for_role_codes(portal_role_permissions, [code]))
        for code in codes
    }
