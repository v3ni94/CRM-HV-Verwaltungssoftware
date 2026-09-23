# mhvp.documents

Documents, categories, DMS adapters (Paperless, Google Drive, S3), templates, retention profiles.

* Milestone: M6 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.7, 6.9.5, 11.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/documents/`. Register models in `mhvp/models.py` for Alembic autogenerate.
