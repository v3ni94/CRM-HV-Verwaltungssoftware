# mhvp.billing

Operating cost statements, economic plans, HOA fee statements, reserves, special levies, heating costs.

* Milestone: M17, M24 (status model schema from M5) (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.5, 6.9.3, 7.6, 7.8, 7.10.
* Status: M17 operating cost statements (drafts, G3 for issuing). See docs/plans/M17.md.
* A35 KI-Plausibilität: `ai_check.py` (input from the snapshot, masking, normalisation) and
  `ai_check_routers.py` (`/statements/{id}/ai-check`, `/hoa/statements/{id}/ai-check`);
  findings with severity as `AiProposal` `statement_check`, no effect on the statement.
* Owner statement (A06, task A25): `owner_statement.py` (model, pure calculation, ledger
  inputs) and `owner_statement_routers.py` (`/billing/owner-statements`); PDF behind G3.
  Rule `docs/rules/A06-owner-statement.md`.
* Tenant letters (A07, task A34): `letters.py` (letter per tenant from the statement
  snapshot only: costs, advances, result, advance proposal = costs / 12 labelled as proposal)
  and `letter_routers.py` (`/statements/{id}/letters/preview`, `/letters`, `/letters/send`
  always refused behind G3). Rule `docs/rules/A07-tenant-letters.md`.
* BetrKV catalogue (M17-01, task 27.09.2026): `betrkv.py` (system catalogue § 2 Nr. 1 to 17
  plus `V`/`I` exclusions, allocability yes/no/agreement_only, review hints) and
  `allocability_routers.py` (`/billing/operating-cost-types`, account mapping via
  `ledger_account.operating_cost_type`, `/statements/{id}/allocability-check`); hints also in
  the snapshot (`allocability_hints`). Rule `docs/rules/M17-01-betrkv-katalog.md`.
* Advance rule (M17-03): `advance_rule.py` (costs / 12 plus optional surcharge per tenant,
  default 0; proposals with confirmation by a second person, letter text block) and
  `advance_routers.py` (`/billing/advance-rule`, `/statements/{id}/advance-proposals`).
  Never changes contract payments (§ 560 BGB, G3). Rule `docs/rules/M17-03-vorschussregel.md`.
* Owner statement output (M17-05): `owner_statement_pdf.py` (payout block `settlement`, letter
  on the tenant's letterhead via `mhvp.documents.letters`); PDF behind G3.
  Rule `docs/rules/M17-05-eigentuemerabrechnung-ausgabe.md`. Migration 0170.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/billing/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Heating statement draft (M17-02)

`heating_calc.py` (pure Decimal calculation, rule version `heating-costs-draft-v1`, JSON trace),
`heating_services.py` (inputs per statement, consumption import from `mhvp.metering`, feed as
one external cost item with `external_amounts` per occupancy, consumption information) and
`heating_routers.py` (`/statements/{id}/heating...`, `/billing/heating-rule-tables`).
Configurable draft values with source status: consumption share 50 to 70 percent (default 70),
hot water method (flat percent, measured energy, formula with draft factor), CO2 step table
(fallback: `calc.CO2_RESIDENTIAL_STEPS`, to be verified) and degree days (default empty, time
share with notice). Missing consumptions stop the calculation; unresolved CO2 facts keep the
status `pruefen` and block the feed (D27). Rule `docs/rules/M17-02-heizkosten.md`, migration
0162, tests `tests/unit/test_m17_heating_calc.py` and `tests/integration/test_m17_heating.py`.

## Consumption information (rule H03)

`consumption_info.py` builds the monthly consumption information per unit (§ 6a HeizkostenV,
D26) from the period consumptions of `mhvp.metering` (kinds `heating` and `hot_water`, calendar
month): values with origin and estimated marking, previous month, same month of the previous
year, property average, missing data flags, a frozen HTML snapshot and a PDF stored as a
generated document (visibility `internal`, retention note in `source_meta`). One row per
tenant, unit and month (`consumption_info`, migration 0238); a rerun never overwrites.
`consumption_info_tasks.py` runs the Celery job `mhvp.billing.consumption_info` on the first
working day for the previous month, per tenant with `consumption_info_enabled`.
`consumption_info_routers.py` serves the CRM (`/properties/{id}/consumption-info`, switch, manual
run); the gated portal endpoints live in `mhvp.portal.consumption_info`. Elements of § 6a
Abs. 3 the spec does not define are listed as `to_verify` for the operator only (never shown to
tenants, `docs/OPEN_QUESTIONS.md` H03). Rule `docs/rules/H03-verbrauchsinformation.md`.
