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

## Marktreife: Preisstruktur, G5-Nachweise, Onboarding (M27-01 bis M27-03, 27.09.2026)

* `mhvp.platform.market_readiness`, Migration 0199. Plattformtabelle ohne RLS:
  `pricing_plan_item` (Struktur ohne Beträge, Angebot als PDF-Entwurf). Mandantentabellen mit
  `tenant_id` und RLS (ADR 0002), nur über Plattformrollen im Mandantenkontext erreichbar:
  `g5_evidence` (acht Nachweise je Mandant, `done` nur mit Dokument des Mandanten),
  `tenant_export_request` (Antrag, Freigabe durch zweite Person, Download als ZIP mit JSON je
  Entität, gelesen im RLS-Kontext des Mandanten, ohne Geheimnisspalten).
* G5: `_decide` ruft `ensure_g5_release_allowed` (alle Nachweise erledigt, Genehmigender ist der
  Superadmin), sonst `MHVP-GATE-0005`. `readiness` zeigt die Liste (`g5_evidence`, `g5_ready`).
* `POST /platform/onboarding`: `provision_tenant` plus Rechtsträger (`manager`, `rental_owner`,
  `sev_owner`), erster Administrator (`tenant_admin`), Feature-Flags aus, Gates geschlossen,
  Willkommens-E-Mail nur als Entwurf in der Antwort. Regeln `docs/rules/M27-01.md` bis `M27-03.md`.

## Lizenzen, eine Preisstruktur, Nutzungsverlauf, Exportjob (P15, 30.09.2026, Migration 0264)

* Lizenz: `PATCH /platform/licenses/{id}` (Kontingent, Laufzeit, Preis, Mindestbetrag),
  `POST /platform/licenses/{id}/end`. `license.price_per_unit` ist optional; NULL heißt Preis
  aus der Preisstruktur (`pricing_plan_item`), siehe Regel `M27-04`.
* Preisliste: `PATCH/DELETE /platform/price-list/{id}`; der heute gültige Eintrag eines
  Nicht-Kern-Moduls schreibt den Betrag der Modulzeile.
* Nutzungsverlauf: `usage_counter_daily` (Plattformtabelle ohne RLS), `GET
  /platform/tenants/{id}/usage/history`, täglicher Job `platform-usage-daily`.
* Exportjob: `mhvp.platform.export_job`, `POST .../export-requests/{id}/run`, Regel
  `M27-01-EXPORT`.
* Mandantenexport durch den Mandantenadministrator (T01, M2-01): `mhvp.platform.export_routers`
  (`/tenant/export-jobs`), Tabelle `tenant_export_job`, Job `mhvp.platform.tenant_export_job`,
  Regel `P14-06`. Der Vier-Augen-Weg der Plattformverwaltung bleibt daneben bestehen.
* Aufbewahrung der Exportarchive (V04, T01-01): `tenant_settings.export_retention_days`
  (Standard leer, keine automatische Löschung), `tenant_export_job.expires_at`, Beat-Job
  `mhvp.platform.purge_expired_exports` (`purge_expired_exports_once`), Status `expired`,
  Ereignis `tenant_export.expired`, Migration 0301.

### Wartungsendpunkt (S16-03-01)

`POST /api/v1/platform/maintenance/self-disclosure-token-hash` (nur Plattform-Administrator) führt die Umstellung der Selbstauskunft-Token aus, siehe `letting/README.md`.
