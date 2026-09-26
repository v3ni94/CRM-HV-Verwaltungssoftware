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

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/billing/`. Register models in `mhvp/models.py` for Alembic autogenerate.
