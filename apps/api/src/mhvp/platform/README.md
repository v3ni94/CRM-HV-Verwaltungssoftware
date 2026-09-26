# mhvp.platform

Tenants, users, memberships, roles, licenses, usage, release gate persistence.

* Milestone: M2 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 5, 18.0.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/platform/`. Register models in `mhvp/models.py` for Alembic autogenerate.

Zugriffsbereich je Rechtsträger (A37, docs/rules/M18-05-steuerberaterzugang.md):
`Membership.legal_entity_ids` (Migration 0102), Pflege über
`PUT /tenant/members/{id}/legal-entities` (`tenant_settings:update`), Auswahlliste
`GET /tenant/legal-entities` (`members:read`); die Prüfung selbst liegt in
`mhvp.core.auth.scope` und wirkt nur für Steuerberater-Mitgliedschaften.
