# mhvp.hoa

Owners' meetings, resolutions, board audits (audit_engagement).

* Milestone: M25 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.5, 6.9.12, 7.8 W13, 7.9.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/hoa/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Implemented parts (M24, M25; see docs/plans/M24.md, M25.md)

* `models.py`, `calc.py`, `routers.py`: economic plan, resolutions, annual statement.
* `package.py`: statement package and blocking checks (W12), including the W03 partial scope
  check (D18) and the resolution validity block (D54).
* `levies.py`: special levies with instalments, amendments and earmarked report (W09, D20).
* `meetings.py`: owners' meeting, circular resolutions, board audit (M25).
* `protocol.py`: minutes draft of a meeting from a placeholder template as PDF on the tenant
  letterhead (A62); a draft without legal effect, the signed minutes stay linked separately.
* Reserve block of the statement: Soll, Ist, open contributions, bank balance and explained
  difference, never a settlement entry (W08, D19).
* `board.py`: board access per audit engagement, revocation and the management answer to a
  board question (A52, docs/rules/M21-07.md); the board itself works in `mhvp.portal.board`.
* `finance.py`: loans, insurance claims and larger measures (W10, A59); items count only with
  a posted journal entry, documents via DocumentLink, no posting.
* `calc.cash_flow_reconciliation`: Gesamtgeldfluss and Überleitung of the statement year (W04,
  A60); an unexplained difference blocks the package.

