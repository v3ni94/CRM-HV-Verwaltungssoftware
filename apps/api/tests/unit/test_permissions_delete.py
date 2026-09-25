"""Rule M2-07 "Löschen nur Administrator" (docs/rules/M2-07.md, Produktschutz):

only tenant_admin (and administrator, the platform admin alias) may hold any `*:delete`
permission. Every other system role must not.
"""

from mhvp.core.auth.permissions import SYSTEM_ROLES

_ADMIN_CODES = {"tenant_admin", "administrator"}


def test_only_admin_roles_hold_delete_permissions() -> None:
    for role in SYSTEM_ROLES:
        deletes = {p for p in role.permissions if p.endswith(":delete")}
        if role.code in _ADMIN_CODES:
            assert deletes, f"{role.code} should keep delete rights"
        else:
            assert not deletes, f"{role.code} must not hold delete rights: {sorted(deletes)}"
