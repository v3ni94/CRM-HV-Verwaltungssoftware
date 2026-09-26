# mhvp.contracts

Tenancy and ownership contracts, payments, schedules, SEPA mandates, deposits, versioning and
debtor account reservation.

* Milestone: M5 (docs/MASTER-PROMPT.md section 18), plan and decisions in `docs/plans/M5.md`.
* Specification: docs/MASTER-PROMPT.md 6.3, 6.9.1, 6.9.2, 6.9.11, 7.2, annex A.1, A.3.
* Files: `models.py`, `schemas.py`, `services.py` (creditor entity, debtor accounts, periods,
  plausibility), `validation.py` (SEPA creditor id, mandate reference), `routers.py`.
* Tests: `apps/api/tests/integration/test_m5_contracts.py`, `apps/api/tests/unit/test_m5_rules.py`.
* Locks: no postings (M10, G1), no direct debit collection (G2).

## Dienstleisterverträge (M9-06)

`service_contracts.py` (model `ServiceContract`, orientation calculation of next possible end and
latest notice date), `service_contract_routers.py` (`/api/v1/service-contracts`). The notice
date feeds the deadline list (`mhvp.workspace.jobs`, kind `service_contract_notice`, 14 days
lead time). Plan: `docs/plans/M9-06-dienstleistervertraege.md`.
