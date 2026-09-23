"""Row level security statements for tenant tables (ADR 0002).

Each tenant table gets RLS enabled and forced (the owning migrator role is bound too) and two
policies on ``tenant_id = app_current_tenant_id()``:

* ``tenant_access`` (permissive) grants access within the current tenant;
* ``tenant_isolation`` (restrictive) is ANDed with every other policy, so a later permissive
  policy (for example portal access) can never widen access across tenants.

Use in migrations: ``for statement in tenant_rls_statements("contact"): op.execute(statement)``.
"""

import re

ACCESS_POLICY = "tenant_access"
ISOLATION_POLICY = "tenant_isolation"
CURRENT_TENANT_FUNCTION = "app_current_tenant_id"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_CONDITION = f"tenant_id = {CURRENT_TENANT_FUNCTION}()"


def _qualified(table: str, schema: str) -> str:
    for name in (table, schema):
        if not _IDENTIFIER.fullmatch(name):
            raise ValueError(f"invalid SQL identifier: {name!r}")
    return f'"{schema}"."{table}"'


def tenant_rls_statements(table: str, *, schema: str = "public") -> list[str]:
    qualified = _qualified(table, schema)
    return [
        f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY {ACCESS_POLICY} ON {qualified} AS PERMISSIVE FOR ALL "
        f"USING ({_CONDITION}) WITH CHECK ({_CONDITION})",
        f"CREATE POLICY {ISOLATION_POLICY} ON {qualified} AS RESTRICTIVE FOR ALL "
        f"USING ({_CONDITION}) WITH CHECK ({_CONDITION})",
    ]


def drop_tenant_rls_statements(table: str, *, schema: str = "public") -> list[str]:
    qualified = _qualified(table, schema)
    return [
        f"DROP POLICY IF EXISTS {ISOLATION_POLICY} ON {qualified}",
        f"DROP POLICY IF EXISTS {ACCESS_POLICY} ON {qualified}",
        f"ALTER TABLE {qualified} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {qualified} DISABLE ROW LEVEL SECURITY",
    ]
