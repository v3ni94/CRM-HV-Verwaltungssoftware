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

## Superadmin und Freigabe ohne zweite Person (ADR 0011, 26.09.2026)

* `User.is_superadmin` (Migration 0135, höchstens ein Benutzer, Teilindex `uq_app_user_superadmin`),
  Vergabe nur über `services.set_superadmin` (Seed mit `MHVP_SEED_ADMIN_SUPERADMIN=true` oder
  `PUT`/`DELETE /platform/users/{id}/superadmin`, `GET /platform/superadmin`).
* `platform_settings` (eine Zeile, keine Mandantenbindung): `GET`/`PATCH /platform/settings`,
  Flag `gate_superadmin_bypass`, Standard aus. Nur mit Flag an darf der Superadmin einen eigenen
  Freigabeantrag genehmigen; der Antrag trägt dann `four_eyes = false`, das Ereignis
  `release_gate.opened` die Nutzlast `superadmin_bypass = true` und das Änderungsprotokoll den
  Eintrag `four_eyes true -> false`. Das schwächt das Vier-Augen-Prinzip aus ADR 0003 und bleibt
  aus, bis der Betreiber es einschaltet. Ablehnungen und alle anderen Plattformadministratoren
  bleiben beim Vier-Augen-Prinzip (`MHVP-GATE-0002`).

## API-Schlüssel der Überwachung (M9-04a, 26.09.2026)

* Recht `platform:metrics:read` (`mhvp.core.auth.permissions.PLATFORM_PERMISSIONS`), bewusst
  nicht Teil von `ALL_PERMISSIONS`: keine Mandantenrolle und kein über `/tenant/api-keys`
  erzeugter Schlüssel kann es tragen (`validate_permission` weist es ab).
* Endpunkte `GET`/`POST /platform/ops/metrics-keys`, `DELETE /platform/ops/metrics-keys/{id}`
  (`mhvp.workspace.ops`, nur `require_platform_admin`, also Sitzung eines
  Plattformadministrators). Der Schlüssel nutzt das vorhandene Modell `ApiKey` und liegt im
  angegebenen Mandanten (`tenant_id` im Body, ersatzweise der Mandant des Mandantenwechsels),
  weil Schlüsselformat und RLS einen Mandanten brauchen; er trägt genau `platform:metrics:read`
  und keine Mandantenrechte. Geheimnis nur einmal in der Antwort; Ereignisse `api_key.created`
  und `api_key.revoked` im Speichermandanten; Ratenlimit wie jeder API-Schlüssel.
* `require_platform_metrics_read` (`mhvp.core.auth.principal`) lässt eine
  Plattformadministrator-Sitzung oder einen Schlüssel mit genau diesem Recht zu und schützt
  `GET /platform/ops/metrics` (JSON und Prometheus). Alle anderen Endpunkte weisen den
  Schlüssel mit 403 ab. Kein Schema, keine Migration. Tests:
  `tests/integration/test_m9_ops_metrics_key.py`; Runbook `docs/runbooks/monitoring.md` 3.1.
