# mhvp.imports

Immoware24 import assistant (M8). Plan: `docs/plans/M8.md`.

* Specification: docs/MASTER-PROMPT.md 13.1, 6.9.10.
* Files: `models.py` (mappings, source files, staging rows), `fields.py` (target fields and
  parsing), `services.py` (stage, validate, test run, apply, reconcile), `routers.py`.
* Import runs and undo come from `mhvp.ai` (`import_run`, `import_run_item`).
* Tests: `apps/api/tests/integration/test_m8_import.py`, `apps/api/tests/unit/test_m8_fields.py`.
