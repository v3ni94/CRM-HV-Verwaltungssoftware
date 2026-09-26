# mhvp.tenant

Tenant seeds (section 5.2) and tenant setup steps.

* `seeds/`: tenants Hausverwaltung Müller GmbH and Timo Müller (`make seed`).
* `manager_entity.py`, `routers.py`: own legal entity and ledger of the managing company
  (`LegalEntityKind.MANAGER`, A32, docs/plans/M16.md), `GET/POST /api/v1/tenant/manager-entity`,
  idempotent, name from the tenant company data, default chart of accounts. The tenant
  settings endpoints themselves live in `mhvp.platform.routers` (`tenant_router`).
