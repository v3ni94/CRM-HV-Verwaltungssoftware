# mhvp.banking

Bank connectors (EBICS, aggregator, FinTS fallback, file import), transactions, rules, matching.

* Milestone: M11, M12 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.4, 6.9.7, 7.4, 8.
* Status: M11 file import (CAMT.053), statements, reconciliation, sync protocol implemented; connectors pending V2/V3. See docs/plans/M11.md.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/banking/`. Register models in `mhvp/models.py` for Alembic autogenerate.
