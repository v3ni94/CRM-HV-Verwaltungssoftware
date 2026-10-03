# ADR 0039: Tenant scoped foreign keys by trigger guard

- Status: Accepted
- Date: 2026-10-03

## Context

Section 5.3 and 6.9.1 (B01) require that a row only references rows of the same tenant.
PostgreSQL checks foreign keys without row level security: a plain `REFERENCES x(id)` accepts
the UUID of a row of another tenant (finding GAL-103, example `hoa/routers.py` taking
`allocation_key_id`, `basis_resolution_id`, `basis_document_id` from the request unchecked).
Measurement at 0458 (`python -m mhvp.core.db.tenant_fk`): 784 single column foreign keys
between tenant tables, none tenant scoped.

## Decision

1. Migration 0460 installs the generic trigger function `mhvp_tenant_fk_guard` and attaches it
   as `BEFORE INSERT OR UPDATE OF tenant_id, <columns>` to every table of the money and WEG
   domains (accounting, banking, billing, contracts, hoa): 409 foreign keys on 133 tables,
   frozen in `mhvp.core.db.tenant_fk.TENANT_FK_GUARDED` and in the migration. The referenced
   row must exist with the same `tenant_id`; otherwise SQLSTATE 23503 with constraint name
   `mhvp_tenant_fk`. Under RLS a row of another tenant is invisible and is rejected the same
   way; without RLS filtering the explicit tenant comparison rejects it.
2. Existing data is checked before the triggers are created (FORCE RLS lifted inside the
   migration transaction for the check only, pattern 0398). Any cross tenant reference aborts
   the migration with the list of affected columns. Data is never deleted or repaired by the
   migration.
3. Ratchet: `tests/unit/test_ap03_tenant_fk_ratchet.py` compares all tenant foreign keys of the
   ORM metadata with the guarded list and `tests/unit/data/ap03_tenant_fk_ratchet.json`
   (376 unguarded foreign keys of the other domains). The list only shrinks; a new tenant
   foreign key must be guarded via `tenant_fk.guard_statements` in its migration.

## Consequences

- An API request with a foreign tenant id in a guarded column can no longer be stored, also
  through jobs, imports and integrations (rule 0.1.4). Without router validation the request
  currently ends as an unhandled integrity error (no data written); routers should validate
  referenced ids before writing and answer with 404 or 422 (open point AP03).
- The guard checks the tenant axis only. The legal entity axis (for example a resolution of
  another GdWE of the same tenant, E01) stays a domain check in the routers.
- One indexed primary key lookup per changed reference on insert and update.
- Integration test `tests/integration/test_ap03_tenant_fk_guard.py` reproduces the attack path
  (ledger of tenant B used as `hoa_reserve.ledger_id` in tenant A) for the app role, without
  RLS filtering and on update.

## Alternatives considered

- Composite foreign keys `(tenant_id, id)`: needs an additional unique constraint on every
  referenced table and rewriting 784 constraints plus ORM declarations; no difference in the
  guarantee, much larger migration and drift risk. Can replace the trigger table by table later.
- Router validation only (`ensure_visible`): necessary for clean error answers but leaves jobs,
  imports and raw SQL unprotected.

## References

- `docs/MASTER-PROMPT.md` section 5.3, 6.9.1 (B01), rule 0.1.4, 0.1.5
- ADR 0002 (RLS), ADR 0033 (tenant index guard)
- Finding GAL-103 (Welle 25 gap analysis)
