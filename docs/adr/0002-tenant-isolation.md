# ADR 0002: Tenant isolation with PostgreSQL row level security

- Status: Accepted
- Date: 2026-09-23

## Context

Section 5.3 requires `tenant_id` on every tenant table, row level security (RLS) with a policy
`tenant_isolation`, `SET LOCAL app.tenant_id` per request, an application database user that
is neither superuser nor table owner, and a separate user for migrations. Rule 0.1.5 keeps the
technical tenant separation and adds separation by legal entity. E12 requires negative tests
per path.

## Decision

1. Every tenant table runs `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` and gets
   two policies, both with `USING (tenant_id = app_current_tenant_id())` and
   `WITH CHECK (tenant_id = app_current_tenant_id())`:
   - a PERMISSIVE policy `tenant_access`, which grants access within the tenant;
   - a RESTRICTIVE policy `tenant_isolation`, which is ANDed with every other policy.
   PostgreSQL ORs permissive policies, so a later permissive policy (for example portal access
   in M21) could otherwise widen access across tenants; the restrictive policy keeps the tenant
   boundary absolute. The helper `mhvp.core.db.rls.tenant_rls_statements(table)` emits this
   SQL; every tenant table migration must use it.
2. `app_current_tenant_id()` is
   `NULLIF(current_setting('app.tenant_id', true), '')::uuid` (STABLE, created in the Alembic
   baseline). A missing context yields NULL, so no row matches (fail closed); a malformed
   value raises an error.
3. The context is set per transaction with `set_config('app.tenant_id', <id>, true)`. This is
   transaction local, equivalent to `SET LOCAL` but parameterizable, and safe with connection
   pools because it ends with the transaction. All tenant queries run inside a transaction
   opened by the tenant session helper.
4. Roles (created by the idempotent `infra/postgres/sql/bootstrap.sql`, the only step run as
   superuser):
   - `mhvp_app`: runtime role of api and worker; owns nothing and is not a member of any
     role (the bootstrap revokes all memberships), so it cannot assume the migrator.
   - `mhvp_migrator`: owns the schema and all tables; runs Alembic.
   - Both are NOSUPERUSER, NOBYPASSRLS, NOCREATEROLE, NOCREATEDB, NOINHERIT. The bootstrap
     re-asserts these attributes on every explicit run (`make db-bootstrap`, CI); in Docker
     Compose it runs only at first initialisation of the data volume.
5. Because of FORCE RLS even the owner is bound. Cross tenant data migrations therefore
   iterate per tenant and set the context for each.
6. Runtime enforcement: readiness check `database_role` fails if the runtime role is
   superuser, has BYPASSRLS, owns tables, functions or types, or is a member of any role.
   Engines are created with `hide_parameters`, and unhandled database exceptions are logged
   only with exception type and SQLSTATE, so bound values (tenant data) never reach logs.
7. CI guard test: every table with a `tenant_id` column must have RLS enabled, forced and the
   restrictive `tenant_isolation` policy; the policy must apply to role PUBLIC and use exactly
   the expression `(tenant_id = app_current_tenant_id())`.
8. Least privilege around migrations: migration 0001 revokes INSERT, UPDATE, DELETE and
   TRUNCATE on `alembic_version` from the runtime role; the readiness check `migrations`
   compares the database revision with the Alembic head. The `vector` extension is created
   only by the superuser bootstrap; migration 0001 fails with a clear message if it is
   missing.
9. `WITH CHECK`, the restrictive policy and `FORCE` go beyond the literal policy text in 5.3; they are a
   Produktschutz (section 0.2), not a legal requirement.
10. Platform tables (`platform_*`, `tenant`, `user`, `license`) have no RLS and are reachable
   only through platform roles (M2).
11. The check that host header tenant and token tenant match (section 3.3) arrives with M2.
12. Legal entity separation (6.9.1, B01) is a second, orthogonal axis. It is enforced by the
    domain model (ledger per `legal_entity`) from M4, M5 and M10. RLS does not solve it.

## Consequences

- A forgotten tenant context returns empty results instead of foreign data.
- Tests use the real PostgreSQL (`integration` marker; CI sets `MHVP_REQUIRE_INTEGRATION=1`).
- Maintenance across tenants needs explicit per tenant loops.

## Alternatives considered

- Schema or database per tenant: higher operational effort, not in section 5.3.
- Policy without `WITH CHECK`: would allow inserting rows for another tenant.
- Single permissive `tenant_isolation` policy (literal 5.3 text): any later permissive policy
  would be ORed with it and could open other tenants.
- `current_setting('app.tenant_id')` without `missing_ok`: raises on missing context in
  every query instead of failing closed with no rows; NULLIF variant chosen.
- Plain `SET LOCAL` via string formatting: not parameterizable.

## References

- `docs/MASTER-PROMPT.md` sections 0.1 (rules 5, 9), 0.2, 3.3, 5.3, 6.9.1, 7.1 (B01), annex E (E01, E12)
- `infra/postgres/sql/bootstrap.sql`, `docs/plans/M1.md` sections 4.3, 6, 7
