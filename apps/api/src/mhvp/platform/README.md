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

## Freigabestufen: Umfang, Checklisten, Nachweis (AA02, GA14-02 bis GA14-04)

- `gate_checklists.py`: Checklisten G2 bis G4 aus 18.0, Funktionscodes, Umfangsprüfung.
- `GET /api/v1/tenant/release-gates/checklists`; der Antrag nimmt `scope_property_ids`,
  `scope_legal_entity_ids`, `scope_functions`, `checklist` und `evidence_document_id`.
- `_decide` lehnt G2 bis G4 ohne vollständige Checkliste und Nachweisdokument ab
  (`MHVP-GATE-0006`); ungültige Codes `MHVP-GATE-0007`.
- `DbReleaseGateResolver.is_open` zählt nur unbegrenzte Freigaben, `is_open_for` prüft Kontext.
- Migration 0304: `opened_by/at`, `revoked_by/at`, `revoke_comment`, `evidence_document_id`,
  Umfangsspalten, `checklist`. Details: `docs/plans/GATE-CHECKLISTEN.md`.
* AA17 (GA01-07, 08, 10, 12): `admin_routers.py` holds `/tenant/delivery-default`, `/tenant/number-formats` (+ `/preview`), `/platform/tenants/{id}/domains`, `PATCH /platform/tenants/{id}` (status) and `/platform/oidc-clients` (create, rotate-secret, activate, deactivate; reuses `core.auth.oidc_clients`). Number formats live in `mhvp.core.number_format` (invoice scope locked, OPEN_QUESTIONS AA17-01). Migration 0319 is a no-op. Rule `docs/rules/AA17-tenant-config.md`.
* AB02 (GA14-02, GA14-04): `core.release_gates.ensure_release_gate_open_for` reicht Objekt, Rechtsträger und Funktion an `is_open_for` (Fallback `is_open`, fail closed); genutzt in `accounting/routers.py` (`_ensure_gate_for_ledger`) und `banking/routers.py` (`_ensure_g2_for_batch`). `GET /platform/tenants/{id}/release-gates` liefert Stand und Anträge eines Mandanten für die CRM-Seite `/plattform/freigabestufen`. Migration 0321 noop.
* AB13 (GA01-10, GA01-12): Plattformaktionen ohne Mandantenkontext (Kundendomain, Mandantenstatus, OIDC-Client) schreiben zusätzlich zum Log einen Eintrag in `platform_audit_event` (Migration 0332, ohne RLS, Trigger `forbid_mutation`, Payload ohne Secrets); `GET /platform/audit-events` listet paginiert (nur Plattformadmin). Tests: `tests/integration/test_ab13_platform_audit_numbers.py`.

## DNS-Prüfung der Kundendomains (AD07, GA01-10)

`POST /platform/domains/{id}/verify` (Plattformadmin) löst CNAME (nur mit installiertem dnspython) und Adressen der Kundendomain auf (`domain_dns.py`) und vergleicht sie mit dem Plattformhost (Hosts aus `web_crm_url`, `web_portal_url`, `api_public_url`, `jwt_issuer`). Gespeichert werden `verification_status` (unverified, verified, failed), `verification_checked_at` und `verification_finding` (Migration 0352); Plattformaudit `tenant_domain_verified`. Der Status wirkt nicht auf die Anmeldung (AA17-03 offen). Tests mit gepatchtem Resolver, kein echtes DNS.

## Wartungsfenster und Verfügbarkeit (AD10, GB16-01, GB16-02)

`maintenance.py`, Migration 0355 (Plattformtabellen `platform_maintenance_window` und `platform_availability_measurement`, ohne RLS). Plattformadministratoren legen Wartungsfenster an, ändern und sagen sie ab (`/platform/maintenance-windows`, kein Löschen); alles im Plattformaudit. `GET /platform/maintenance/current` ist öffentlich und liefert Status und die Fenster ab der Vorlaufzeit (`MHVP_MAINTENANCE_NOTICE_HOURS`, Standard 48, je Fenster überschreibbar); CRM und Portal zeigen daraus ein Banner, die Statusseite kann den Feed lesen. `PUT /platform/availability` importiert die Monatszahl je Messpunkt (api, crm, portal) aus Uptime Kuma, `GET /platform/availability` wertet gegen das Ziel 99,5 Prozent aus und weist die geplante Ausfallzeit der Fenster getrennt aus (Regel PL-AVAIL-01, Runbook `docs/runbooks/verfuegbarkeit.md`). Offen: AD10-02.

### Eigenmessung (AE35, GB16-02)

`availability_probe.py`, Migration 0391 (Tabellen `platform_availability_probe_point` und `platform_availability_month`, Spalte `platform_settings.maintenance_counts_as_downtime`, ohne RLS). Der Beat Job `mhvp.platform.availability_probe` prüft jede Minute die URLs aus `MHVP_AVAILABILITY_API_URL`, `_CRM_URL`, `_PORTAL_URL` (leer = aus; ohne gesetzte URL wird der Minutentakt nicht eingeplant) und schreibt je Messpunkt und Minute einen Messpunkt (eindeutig je `probe` und `slot`, wiederholter Lauf ändert nichts). Der HTTP Client ist in `run_probes_once(settings, client=...)` injizierbar, Tests nutzen `httpx.MockTransport`. `availability_evaluate` (täglich 03:25) rechnet je Messpunkt und Monat brutto und netto (ohne Prüfungen in nicht abgesagten Wartungsfenstern), der laufende Monat ist vorläufig, beendete Monate werden festgeschrieben (`final`). `availability_purge` (täglich 03:55) wertet beendete Monate nach und löscht Minutenwerte nach `MHVP_AVAILABILITY_RETENTION_DAYS` nur für festgeschriebene Monate. `GET /platform/availability` enthält die Eigenmessung in den Feldern `self_*`, `GET /platform/availability/live` den Stand der Prüfungen, `PUT /platform/availability/settings` den Schalter (auditiert). Regel PL-AVAIL-01 Punkte 7 bis 11, Fragen AE35-01 (AD10-02) und AE35-02.

## Rechtstexte des Portals (AE29, M21-04, R10-03/R10-04)

`legal_texts.py` nutzt die Tabelle `legal_text_block` (AE16, Freigabe mit zweiter Person) mit den Codes `impressum`, `datenschutz`, `nutzungsbedingungen` (`TEXT_BLOCK_CODES` in `documents/models.py`); keine Parallelstruktur, Migration 0385 ist ein noop. Öffentlich nach Portal-Host (wie `/tenant/branding`): `GET /tenant/legal-texts` (Freigabestand) und `GET /tenant/legal-texts/{code}` (nur die freigegebene Fassung, sonst `released=false` und der Vermerk "Text nicht freigegeben", dazu der externe https-Link aus dem Branding). `GET /tenant/branding` nennt zusätzlich `legal_texts_released`. Intern: `GET /tenant/legal-texts-config` (tenant_settings:read) mit Abgleich zur Fassung der Einwilligungsrichtlinie (`NB-<Version>`), `PUT /tenant/legal-texts-config` (Schalter `terms_version_mode` manual oder follow_text, `tenant_settings.sources["legal_texts"]`, contacts:approve) und `POST /tenant/legal-texts-config/apply-terms-version` (ausdrückliche Übernahme, `confirm=true`, nur mit freigegebenem Text, contacts:approve). Im Modus follow_text setzt `follow_terms_version` (Aufruf in `text_block_routers.approve_block`) die Fassung bei der Freigabe. Änderungen der Richtlinie schreiben das Ereignis `consent_policy.updated` mit Herkunft. Regel docs/rules/AE29-01.md.

## Demo-Mandant und Skalierungsmessung (AE36, Welle 16, Migration 0392)

* `Tenant.is_demo`: Kennzeichen des Demo-Mandanten (Regel `docs/rules/AE36-DEMO.md`). `demo.py`: `is_demo_tenant`, `ensure_not_demo` (409 `MHVP-DEMO-0001`), `active_productive_tenants`. `demo_routers.py`: `PUT /platform/tenants/{id}/demo` (Plattformadministrator, nur ohne geöffnete Freigabestufe, Plattformaudit `tenant_demo_flag_changed`). `TenantCreate.is_demo` und `TenantOut.is_demo`; `provision_tenant(..., is_demo=True)`.
* Ausschluss: Lizenz, `count_usage` (Nutzungszählung, Abrechnungsvorschau), Nutzungsjobs, Mandantenexport (Job und Antrag), dazu Journal-, DATEV- und Prüfexport in `mhvp.accounting`. Die Bereitschaftsansicht (`/platform/tenants/{id}/readiness`) zeigt `demo: true` und Nullwerte.
* `scale_models.py`: `PlatformScaleSetting` (eine Zeile, Schwellen aus ADR 0021) und `PlatformScaleSnapshot` (eine Messung je ISO-Woche), Plattformtabellen ohne RLS. Logik und API: `mhvp.workspace.scale`, `mhvp.workspace.scale_routers`.
* `demo_seed.py`: setzt das Kennzeichen, erzeugt nur synthetische IBANs (Bankleitzahl 00000000, `assert_synthetic_ibans`) und gibt dem Demo-Mandanten die Zweitfaktor-Richtlinie freiwillig (Runbook `docs/runbooks/demo-mandant.md`).

### Eigenmessung: Deploy-Variablen und HTTP-Test (AF24, GAE-33)

`warn_missing_probe_urls` schreibt beim Start der API und beim ersten Messlauf je Prozess eine Logzeile mit den nicht gesetzten Variablen `MHVP_AVAILABILITY_{API,CRM,PORTAL}_URL` (Warnung in staging und prod, Info in dev und test). `tests/integration/test_af24_availability_http.py` prüft `check_url` gegen einen echten uvicorn Server in einem Thread, ausschließlich auf 127.0.0.1 (Status 200, 503, Weiterleitung, Zeitüberschreitung, geschlossener Port).

### Demo-Kennzeichen in /auth/me (AF19-R, AG13)

`MeOut.is_demo` (core/auth/routers.py) liest `tenant.is_demo` des Mandanten des Principals über `platform.demo.is_demo_tenant` (Tabelle `tenant` ohne RLS); ohne Mandant false. Das CRM-Demo-Band (`DemoBanner`) wertet das Feld aus. Test: `tests/integration/test_ag13_me_is_demo.py`.

## AG03: Schalter insurance_broker_access (GAC-07)

`PATCH /tenant/settings` kennt `insurance_broker_access` (Standard aus, gespeichert in
`tenant_settings.sources`, keine Migration). Nur bei gesetztem Schalter erhält die Systemrolle
`insurance_broker` die Rechte `insurance:read` und `claims:read` (Regel GAC-07).

### Mandantenvollexport und Zahlungsdateien (AN08)

Bei geschlossenem G2 enthält das Export-ZIP keinen Inhalt von Zahlungsdateien (GAJ-301); die Metadaten bleiben in `data/documents.jsonl`, das Manifest listet sie unter `documents.withheld`.
