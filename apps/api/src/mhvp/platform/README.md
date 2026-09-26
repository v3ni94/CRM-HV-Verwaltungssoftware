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

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `gates.py`: persistent release gates (ADR 0003): four eyes opening, revocation, resolver
* `licensing.py`: licence model, usage counters, price list, onboarding and G5 readiness (M27); router registered in `main.py`
* `seed.py`: `python -m mhvp.platform.seed`: tenants from seeds (5.2), optional initial administrator
* `sync_roles.py`: `python -m mhvp.platform.sync_roles`: add new template permissions to system roles
