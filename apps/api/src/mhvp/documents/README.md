# mhvp.documents

Documents, links, categories, retention profiles, DMS mirrors (Paperless-ngx, Google Drive),
letter templates, PDF letters and serial letters.

* Milestone: M6, plan and decisions in `docs/plans/M6.md`.
* Specification: docs/MASTER-PROMPT.md 6.7, 6.9.5, 7.11, 11.
* Files: `models.py`, `schemas.py`, `routers.py`, `services.py` (store, link, retention,
  letter context), `blobs.py` (S3 originals), `text.py` (text layer, type checks), `dms.py`
  (store protocol and adapters), `tasks.py` (mirror job), `letters.py` (placeholders, DIN 5008
  PDF), `defaults.py` (categories, free letter).
* Tests: `apps/api/tests/integration/test_m6_documents.py`, `apps/api/tests/unit/test_m6_documents.py`.
* Locks: deletion only with a released retention profile; nothing is sent from here.
