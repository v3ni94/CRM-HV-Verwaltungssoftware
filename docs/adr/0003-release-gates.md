# ADR 0003: Release gates G1 to G5

- Status: Accepted
- Date: 2026-09-23

## Context

Rule 0.1.1 and section 18.0 define release gates: G1 productive bookkeeping, G2 payment
initiation, G3 rental statements, G4 WEG statements, G5 third party tenants. Section 19.2
requires feature flags per tenant, default off. Rule 0.1.4 extends gates to jobs, imports,
bulk actions and integrations.

## Decision

1. `mhvp.core.release_gates` defines `ReleaseGate` G1 to G5 as per tenant flags, default
   closed.
2. No environment variable, setting or global switch can open a gate.
3. Guards: a FastAPI dependency (`require_release_gate`) for endpoints and a job guard
   (`ensure_release_gate_open`) for imports, bulk actions, Celery jobs and integrations.
   A closed gate yields problem `MHVP-GATE-0001` with HTTP 403 (ADR 0004).
4. M1 ships only the fail closed resolver: every gate is closed for every tenant, and a
   missing tenant context is treated as closed.
5. M2 adds persistence per tenant with: tenant, gate, scope, `opened_by`, `opened_at`,
   evidence document, `revoked_at`. A gate covers only the documented functional scope and
   object group (section 18.0). Proposal for M2: opening requires two distinct persons.
6. A gate never replaces domain checks (resolution, four eyes principle, duplicates).

## Consequences

- Money related functions can be developed and tested while remaining unusable in
  production.
- Opening a gate becomes an auditable act with evidence.

## Alternatives considered

- Global environment flag: rejected, a single misconfiguration would open all tenants.
- UI only hiding: rejected by rule 0.1.4 and D50.

## References

- `docs/MASTER-PROMPT.md` sections 0.1 (rules 1, 3, 4), 18.0, 19.2; annex D (D50)
- `docs/plans/M1.md` section 4.4
