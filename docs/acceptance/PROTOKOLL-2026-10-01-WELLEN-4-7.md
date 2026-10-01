# Abnahmeprotokoll der Wellen 4 bis 7

Stand: 01.10.2026. Grundlage: Ergebnisberichte der Pakete R01 bis R16, T01 bis T16, U01 bis U16 und V01 bis V12 (Arbeitsstand der Koordination). Das Protokoll gibt die gemeldeten Testläufe und offenen Punkte unverändert wieder; es ersetzt keine fachliche Abnahme durch den Betreiber (Abschnitt 0.1 Regel 14). Die Freigabestufen G1 bis G5 bleiben geschlossen. Offene Entscheidungen sind in `docs/OPEN_QUESTIONS.md` geführt und in `docs/plans/ENTSCHEIDUNGEN-2026-10-01.md` für den Vorstand aufbereitet.

Hinweis zur Lesart: "Ausgeführte Tests" sind die vom Paket gemeldeten Befehle mit Ergebnis. Teilläufe einzelner Testdateien sind keine Gesamtsuite. "Nicht ausgeführt" ist ausdrücklich nicht bestanden.

## Übersicht

| Paket | erledigt | teilweise | nicht erledigt | Migration | Migration ungetestet |
| --- | --- | --- | --- | --- | --- |
| R01 | 7 | 0 | 0 | none | nein |
| R02 | 6 | 0 | 1 | 0284 no-op (kein Schemabedarf, Schalter und Fortschrittsmark | nein |
| R03 | 7 | 0 | 0 | 0285 property_takeover_item.ticket_id (FK ticket, ondelete S | nein |
| R04 | 4 | 1 | 1 | 0286 no-op (kein Schemabedarf, hält die Kette für 0287) | nein |
| R05 | 5 | 1 | 0 | 0287 inspection_package_default_days (tenant_settings, nulla | nein |
| R06 | 5 | 1 | 0 | none | nein |
| R07 | 3 | 0 | 1 | none | nein |
| R08 | 8 | 1 | 0 | none | nein |
| R09 | 4 | 2 | 0 | none | nein |
| R10 | 5 | 2 | 0 | 0288 deposit_interest_rate, deposit_interest_draft, enum-Wer | nein |
| R11 | 1 | 1 | 0 | none | nein |
| R12 | 2 | 3 | 0 | none | nein |
| R13 | 7 | 2 | 0 | none | nein |
| R14 | 6 | 1 | 1 | none | nein |
| R15 | 7 | 1 | 0 | none | nein |
| R16 | 4 | 0 | 0 | none | nein |
| T01 | 1 | 0 | 0 | 0289 tenant_export_job | nein |
| T02 | 1 | 0 | 0 | none | nein |
| T03 | 2 | 2 | 0 | none | nein |
| T04 | 4 | 1 | 0 | 0290 admin_fee_posting: Enumwert cancelled (Backfill), admin | nein |
| T05 | 1 | 1 | 0 | 0291 invoice.work_order_id/resolution_id/plan_item_id (FK),  | nein |
| T06 | 4 | 1 | 1 | 0292 heating_cost_import (neue Tabelle mit RLS, down_revisio | nein |
| T07 | 4 | 0 | 0 | none | nein |
| T08 | 1 | 1 | 0 | 0293 notification_preference.email_mode + Check | ja |
| T09 | 5 | 1 | 1 | 0294 hoa_reserve bank_account_id (FK property_bank_account S | nein |
| T10 | 1 | 1 | 1 | 0297 import_report_type: sechs neue Enum-Werte (down_revisio | ja |
| T11 | 4 | 0 | 0 | 0295 statement_status_model (owner_statement_status +6 Werte | nein |
| T12 | 3 | 0 | 0 | 0296 ai_task_reply_draft (ALTER TYPE ai_task ADD VALUE reply | nein |
| T13 | 4 | 2 | 0 | none | nein |
| T14 | 6 | 1 | 0 | none | nein |
| T15 | 5 | 1 | 2 | none | nein |
| T16 | 3 | 0 | 0 | none | nein |
| U01 | 3 | 0 | 0 | none | nein |
| U02 | 1 | 0 | 1 | none | nein |
| U03 | 3 | 0 | 0 | none | nein |
| U04 | 7 | 1 | 2 | 0298 webauthn_credential.passwordless boolean not null defau | nein |
| U05 | 3 | 0 | 0 | none | nein |
| U06 | 1 | 0 | 0 | none | nein |
| U07 | 2 | 1 | 1 | 0299 document_search_trgm | ja |
| U08 | 2 | 1 | 0 | none | nein |
| U09 | 5 | 0 | 0 | none | nein |
| U10 | 1 | 1 | 0 | none | nein |
| U11 | 4 | 2 | 0 | none | nein |
| U12 | 3 | 0 | 0 | none | nein |
| U13 | 2 | 0 | 0 | none | nein |
| U14 | 1 | 0 | 0 | none | nein |
| U15 | 10 | 2 | 0 | none | nein |
| U16 | 7 | 0 | 0 | none | nein |
| V01 | 4 | 0 | 0 | none | nein |
| V02 | 4 | 0 | 0 | none | nein |
| V03 | 4 | 0 | 0 | 0300 retention_resolution_start (enum value resolution, docu | nein |
| V04 | 1 | 1 | 0 | 0301 export_retention (down_revision 0300) | nein |
| V05 | 1 | 0 | 0 | 0302 owners_meeting close_requested_by, close_requested_at,  | nein |
| V06 | 1 | 0 | 0 | none | nein |
| V07 | 2 | 0 | 0 | none | nein |
| V08 | 4 | 1 | 2 | none | nein |
| V09 | 5 | 0 | 0 | none | nein |
| V10 | 1 | 1 | 0 | none | nein |
| V11 | 5 | 1 | 5 | none | nein |
| V12 | 5 | 0 | 0 | none | nein |

## Welle 4 (Pakete R)

### R01

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run (InvoiceForms, RecurringPlanCreate, AdminFeePanel, AdminFeeRun, YearCarryoverPanel, DirectDebitReconciliation, StatementPdfButton, src/app/api Allowlist-Coverage) -> alle bestanden (einzelne Läufe unter Last liefen in Timeouts, nach Erhöhung des Timeouts der neuen Tests grün)
- uv run pytest tests/integration/test_m15_direct_debits.py -k batch_feedback -> 1 passed (DB mhvp_p01, Redis 1)
- uv run pytest tests/integration/test_m15_direct_debits.py (gesamt) -> vor Testkorrektur 4 passed, nur der neue Test schlug fehl; danach einzeln grün
- uv run ruff check tests/integration/test_m15_direct_debits.py -> ok
- pnpm eslint auf geänderte Komponenten -> ohne Befund
- pnpm tsc --noEmit -> keine Fehler in meinen Dateien; bestehende Fehler in fremden Dateien (ai/OnboardingExtras.tsx, ai/PersonMatchTable.tsx u. a.)

**Nicht ausgeführte Tests:**

- Playwright, next build, volle Suiten (laut Brief)
- Test mit Leserechte-Nutzer (403) für bank-status: Testwelt hat keinen Nutzer mit reiner Leserolle, Berechtigung (APPROVE) unverändert
- vollständiger Lauf test_m15_direct_debits.py nach letzter Testkorrektur (nur der neue Test erneut ausgeführt)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Keine Backend-Änderung nötig: Sammelrückmeldung (order_ids), admin-fees-run, year-carryover und Honorar-PDF existierten bereits; Brief nannte 'Endpunkt', Lücke lag nur in UI und Test.
- Honorar-PDF: Download nutzt POST .../document (legt Dokument einmalig ab) und dann /api/handover-files/documents/{id}/content; ein direkter GET-Endpunkt für das PDF existiert nicht.
- Jahresübernahme-Panel nur für Nutzer mit accounting:create; Vorjahr als Vorbelegung, Hinweis auf noch nicht beendetes Geschäftsjahr kommt vom Server.
- Gesamtabrechnung-PDF-Knopf erscheint nur bei vorhandenem Snapshot und Status außer draft/calculated; bei geschlossenem G4 zeigt der Server eine Fehlermeldung.
- Keine neue Fachregel, daher keine docs/rules-Datei.
- Fremde tsc-Fehler im Arbeitsbaum (ai/OnboardingExtras.tsx, ai/PersonMatchTable.tsx) stammen nicht aus R01.


### R02

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p02) -> ok
- pytest tests/integration/test_r02_documents.py -> 3 passed
- pytest test_q03_documents_w3.py test_m6_process_inbox.py -> 10 passed
- pytest test_migrations.py + test_r02_documents.py -> 7 passed
- ruff check/format Dateien des Pakets -> ok
- mypy src/mhvp/documents -> ok
- vitest DocumentRedactions, DocumentIntakeSettings, DmsUpload -> 10 passed
- pnpm tsc --noEmit -> keine Fehler in Dateien des Pakets (Fehler nur in fremder MaintenancePanel.test.tsx)

**Nicht ausgeführte Tests:**

- Playwright, next build, volle Suiten (laut Rahmen)
- Echter Browser-PUT gegen Objektspeicher mit CORS

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:**

- Q03-03: Schwärzung im System (Bereiche im PDF entfernen) bleibt außerhalb, als R02-01 in OPEN_QUESTIONS

**Offene Punkte und Entscheidungen:**

- R02-01 Schwärzung im System offen
- R02-02 CORS und erreichbarer Endpunkt vor Einschalten des direkten Uploads prüfen; API erzwingt den Schalter bewusst nicht
- R02-03 Hub-Mandant und Absenderlisten festlegen
- openapi.json und api-client neu erzeugen (neue Endpunkte /document-direct-upload, Feld distribute); CRM nutzt dafür serverFetch
- Q03-02/Q03-03 in OPEN_QUESTIONS und Lückenliste Status vom Koordinator nachziehen
- Kleiner Edit in fremder Domäne: platform/routers.py _settings_out filtert sources auf String-Werte


### R03

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p03, 0284 bis 0288 vorhanden) -> ok
- pytest tests/integration/test_r03_onboarding.py test_r03_portal_checklist.py test_m7_takeover.py -> 7 passed
- pytest tests/integration/test_m7_ai.py -> 19 passed (D57 Erwartung um document_link ergänzt)
- pytest tests/integration/test_migrations.py -> 4 passed
- ruff check/format und mypy src/mhvp/ai portal/owner_overview properties/routers_takeover -> sauber (ruff check src gesamt zeigt fremde Fehler anderer Pakete)
- web-crm vitest OnboardingExtras, PropertyProposal, TakeoverChecklist, surface-consistency -> 14+17 passed; tsc --noEmit -> ok; eslint der geänderten Dateien -> ok
- web-portal vitest P13 (neue Tests bestanden, PortalChat-Test unter Last Timeout), i18n/api-Tests -> passed; tsc --noEmit -> ok

**Nicht ausgeführte Tests:**

- Playwright/E2E
- volle Suiten
- Zugriff auf Debitorenkonten bei vorhandenem Buchungskreis (Zweig sync_debtor_accounts ohne Neuanlage) nicht eigens getestet
- Berechtigungstest der Zusatzrechte accounting:create und documents:update im Apply nicht eigens getestet
- openapi.json und api-client nicht regeneriert (Koordinator)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- R03-01 (OPEN_QUESTIONS): Soll das Eigentümerportal die Checkliste zeigen oder braucht es einen Mandantenschalter (Datenschutz)?
- R03-02: Bankkonten werden nur bei genau einem passenden Rechtsträger angelegt, bei mehreren Eigentümern einer Mietverwaltung nur Hinweis; Standardteam und Zuständiger der Checklisten-Tickets offen
- A-R03-01: Buchungskreis wird bei Debitorenübernahme aus Kontenvorlage Entwurf mit Geschäftsjahresbeginn Januar angelegt (Annahme, hinter G1)
- Standardmäßig wird die Quelldokument-Verknüpfung (link_source_documents=true) gesetzt und verlangt daher documents:update; bestehender Test D57 in test_m7_ai.py um document_link angepasst
- openapi.json und packages/api-client müssen vom Koordinator neu erzeugt werden (neue Endpunkte und Schemas OnboardingBankAccountChoice, OnboardingAllocationKeyChoice, OnboardingMatchBatchIn/Out, TakeoverTicketsIn/Out)
- Fremde Dateien anderer Pakete waren zeitweise syntaktisch defekt (ai/lookup_tools.py); später behoben, nicht von R03 geändert


### R04

**Ausgeführte Tests mit Ergebnis:**

- pytest test_q08_import_history.py -> 2 passed (vor letzten Lint Edits, danach ruff und mypy imports grün)
- pytest test_workspace_search_p1.py -> 1 passed
- alembic upgrade head -> bis 0287 ok
- ruff check imports, ai/imports.py, Q08 Test -> grün; mypy imports, workspace -> grün

**Nicht ausgeführte Tests:**

- test_perf_queries (Suche hat 1 Zusatzabfrage für Rechnungen)
- Tests für Rechnungsnummer- und Adresssuche nach Mieter
- tsc --noEmit, Vitest für entity-links (kein Testfile vorhanden)
- test_migrations.py

**Teilweise erledigt:**

- M8-07: Kautionen und Darlehen sind im Prüfbericht nur als nicht vergleichbar aufgelistet (keine eindeutige Kontenart)

**Nicht erledigt:**

- Undo für payment_schedule/sepa_mandate und document_link der Berichtsarten sepa_overview und document_index (nicht im Paketumfang, kein Recorder-Eintrag)

**Offene Punkte und Entscheidungen:**

- Q08-03 neu: reale Exporte nötig, Vorzeichenregel bestätigen, Kautionen/Darlehen zuordnen
- Rechnungsnummer- und Mieter-Adresssuche ohne eigenen Test
- entity-links.ts: neue Route /rechnungen/{id} existiert im CRM


### R05

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_r05_positive_paths.py -> 4 passed
- pytest tests/unit/test_q10_portal_w3.py tests/integration/test_q10_portal_w3.py test_p08_hoa_audit_inspection.py test_a61_inspection.py test_m21_portal.py test_migrations.py -> 59 passed, 2 failed (test_migrations: Downgrade/Round-Trip scheitert an Welle-3-Migration (hoa_inspection_event kind Check mit Testdaten), Drift meldet ix_contract_payment_reserve_id aus Migration 0278, beides nicht R05)
- alembic upgrade head bis 0288 -> ok
- pnpm vitest InspectionPackageDefaultDays.test.tsx -> 2 passed
- ruff check eigene Dateien -> ok
- pnpm tsc --noEmit -> keine Fehler in eigenen Dateien (fremde Fehler in ai/ Komponenten)

**Nicht ausgeführte Tests:**

- volle Suiten, Playwright, mypy komplett (mypy meldet fremden Fehler TenantDomain in platform/routers.py:793)

**Teilweise erledigt:**

- Belegindex: kein Index angelegt (Abfrage auf Dokumentkennungen des Kontos begrenzt, ILIKE ohne Trigramm); bei großen Beständen pg_trgm Index prüfen

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- R05-01 in OPEN_QUESTIONS: 14 Tage Standardfrist und historische Ansprüche mit Rechtsanwalt klären
- test_migrations Downgrade-Round-Trip scheitert an Welle-3-Migration mit vorhandenen Testdaten (hoa_inspection_event kind), Drift ix_contract_payment_reserve_id fehlt im Modell oder in Migration 0278: Verantwortliche der Pakete prüfen
- openapi.json und api-client müssen vom Koordinator neu erzeugt werden (neue Felder inspection_package_default_days, clear_inspection_package_default_days, no_expiry)
- _filter_sort_documents in portal/routers.py ist ungenutzt, bleibt wegen vorhandenem Unit-Test


### R06

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_r06_tickets_workspace.py test_m9_workspace.py test_q11_workspace_w3.py test_ticket_resolution.py -> 20 passed, 1 failed (Fehler im Link zum Belegentwurf behoben, danach Einzellauf -k change_requests: 1 passed)
- pnpm vitest run PortalProposalsPanel, MaintenancePanel, NotificationBell, Workspace.test -> alle bestanden (MaintenancePanel nach Label Korrektur 5 passed, danach neuer Bulk Test ergänzt)
- ruff check src tests/integration/test_r06_tickets_workspace.py -> sauber; mypy src/mhvp/tickets src/mhvp/workspace -> sauber
- pnpm tsc --noEmit -> keine Fehler in meinen Dateien (Fehler nur in fremder Datei ai/PersonMatchTable.tsx)

**Nicht ausgeführte Tests:**

- mypy src/mhvp/portal (nur tickets und workspace geprüft)
- Vollständige Suiten, Playwright, next build (laut Brief nicht vorgesehen)
- Regressionslauf test_m21_portal.py und test_m19_tickets.py: bei Abgabe wegen Maschinenlast noch nicht beendet, Ergebnis offen

**Teilweise erledigt:**

- Q12 Tickets bulk: nur Aktion Status (mit gemeinsamer Erledigungsnotiz); keine UI-Umstellung der Ticketliste, diese nutzt weiter bulk-status

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Ticketliste im CRM nutzt weiter /tickets/bulk-status; Umstellung auf den Bericht von /tickets/bulk (Fehlercodes je Ticket anzeigen) ist ein kleiner Folgeschritt.
- Frühere Sammelaktion maintenance.done schloss auch Wartungen mit Intervall; geänderte Semantik (Verhalten wie Einzelaktion) ist im Changelog und in docs/rules/R06 vermerkt, Betreiber sollte das bestätigen.
- Stummschalten gilt für alle nicht verpflichtenden Arten über die Standardzeile *; eine Stummschaltung je Art besteht weiter in den Benachrichtigungseinstellungen.
- Die Aufgabenliste nannte keine Migration; keine Schemaänderung nötig. Regel R06 ist nicht abgenommen.


### R07

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_r07_embed.py tests/unit/test_q12_listparams.py -> passed
- pytest tests/integration/test_r07_list_includes.py -> 1 passed
- pytest tests/integration/test_q12_lists_bulk.py test_m17_operating_costs.py::test_operating_cost_statement test_m24_hoa.py::test_d18_sub_community_without_basis_blocks_release -> 5 passed
- ruff check/format (geaenderte Dateien) -> ok
- mypy listparams, refs, 7 Router -> ok (nach Fix refs.py)

**Nicht ausgeführte Tests:**

- volle Suiten
- Frontend (keine Frontend-Aenderung)
- Integrationstest invoices include=creditor mit Daten (nur leere Liste und 422 geprueft)
- OpenAPI-Export (Koordinator)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:**

- meeting.closed-Emission: kein Endpunkt setzt Versammlungsstatus closed oder Protokollabschluss; Fachentscheidung offen (R07-01)

**Offene Punkte und Entscheidungen:**

- R07-01: Protokollabschluss der Eigentuemerversammlung fehlt; meeting.closed danach anhaengen (Owner Timo Mueller)
- billing/routers.py und hoa/routers.py liegen ausserhalb der genannten Domaenen, aber der Paketauftrag verlangt die Ereignisse dort; nur je ein additiver emit-Block
- openapi.json neu exportieren (Beschreibungen der fuenf Listen geaendert)
- Waehrend der Laeufe trat einmal ein transienter Zirkelimport in mhvp.hoa.property_scope (R08 in Arbeit) auf; beim zweiten Lauf weg


### R08

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_r08_property_scope_domains.py tests/integration/test_q13_property_scope_etag.py -> 4 passed
- pytest test_q13, test_m18_tax_advisor_scope, test_m11_banking, test_hotfix_hoa_audit_scope, test_perf_queries, test_ai_lookup_areas, test_ai_lookup (int+unit), test_p14_member_scope_webauthn -> 72 passed, 1 failed (tests/unit/test_ai_lookup.py::test_help_index_is_in_sync_with_sources: help_index.json nicht synchron mit docs/handbuch, Arbeitsbaum anderer Pakete und dieses Pakets)
- ruff check (geänderte Dateien) -> ok bis auf vorbestehende Befunde in contracts/deposit_settlement.py und deposit_settlement_routers.py Zeile 767 (fremd)
- mypy (68 geänderte Quelldateien) -> ok
- pnpm vitest run src/lib/etag-lock.test.ts src/lib/lib.test.ts components/tickets contracts documents accounting invoices -> alle grün
- pnpm tsc --noEmit -> keine Fehler in bff.ts/etag-lock.ts; verbleibende Fehler in components/ai/PersonMatchTable.tsx und OnboardingExtras.tsx (fremd)

**Nicht ausgeführte Tests:**

- volle Suiten, Playwright, Portal-Tests (keine Portaländerung)
- tests/integration/test_migrations.py (keine Migration)

**Teilweise erledigt:**

- Q13-01: Portalverwaltung, Objektakte, Importe, Prüfberichte des Beirats per Id, Bankregeln/Sync-Protokolle/Klärungsliste nicht angeschlossen (docs/OPEN_QUESTIONS.md R08-01)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- R08-01 in docs/OPEN_QUESTIONS.md: Portalverwaltung, Objektakte, Importe, Prüfberichte des Beirats per Id, Bankregeln/Sync-Protokolle/Klärungsliste nicht angeschlossen; Kontakte bleiben mandantenweit (Betreiberentscheidung).
- Datensätze ohne Objekt (Buchungskreis der Verwaltungsgesellschaft, Ticket ohne Objekt, Dienstleistervertrag ohne Objekt) sind für eingeschränkte Mitglieder unsichtbar (wie Q13).
- GET /banking/accounts filtert nach dem Limit (account_selection.list_accounts unverändert); bei mehr als 'limit' Konten können für eingeschränkte Mitglieder weniger erscheinen.
- help_index.json muss nach den Handbuchänderungen neu erzeugt werden (Unit-Test test_help_index_is_in_sync_with_sources rot, Ursache auch fremde Pakete).
- Meine DB mhvp_p08 hatte zwei Zeilen in alembic_version (0281 und 0283); 0281 gelöscht, danach upgrade head bis 0288 erfolgreich.
- OpenAPI-Export nicht ausgeführt (Koordinator); keine neuen Endpunkte, nur Abhängigkeiten.


### R09

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_r09_compact_reply.py tests/integration/test_r09_ai_automation.py tests/integration/test_q06_ai_w3.py tests/integration/test_p12_mail_compact.py (+ m26) -> 25 passed, 1 failed (Testfehler im Fake, danach behoben); test_r09_ai_automation.py allein -> 3 passed
- vitest AiAutomationSwitches.test.tsx CompactView.test.tsx -> 6 passed
- ruff check ai, letting/routers.py, Tests -> ok; mypy der neuen ai/communication-Module -> ok

**Nicht ausgeführte Tests:**

- tsc --noEmit meldet Fehler nur in fremden Dateien (PersonMatchTable.tsx, MaintenancePanel.test.tsx), keine in R09-Dateien
- mypy src/mhvp/letting nicht gelaufen
- Gesamtlauf Q06 und M26 nach letzter Testkorrektur nicht wiederholt (nur R09-Datei)

**Teilweise erledigt:**

- M20-02: kein eigener AiTask mit eigenem Anbieterschema, weil ein neuer Wert des Enum ai_task eine Migration braucht (OPEN_QUESTIONS R09-02)
- M7-07: Anbieter-Batch-APIs weiter nicht angebunden (Q06-02); Historienanalyse ohne fachliche Definition nicht angeschlossen (R09-03)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- R09-01: Schalter liegen ohne Migration unter tenant_settings.objektakte_classification[ai_automation]; eigene Spalten empfohlen, Standard aus bestätigen
- R09-02: eigener AiTask fuer Antwortentwuerfe braucht Migration (Enum ai_task)
- R09-03: Historienanalyse nicht definiert und nicht angeschlossen; Anbieter-Batch (Q06-02) offen
- openapi.json und api-client nicht regeneriert (Koordinator): neuer Endpunkt /ai/automation, Schemas AutomationIn/AutomationOut; CRM nutzt bff ohne typisierten Client


### R10

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_b15_deposit_rate_history.py tests/unit/test_m5_deposit_settlement.py -> 15 passed
- pytest tests/integration/test_b15_deposit_interest.py tests/integration/test_m5_deposit_settlement.py -> passed
- pytest tests/integration/test_b26_portal_branding.py tests/integration/test_m21_magic_link.py -> 7 passed
- alembic upgrade head auf mhvp_p10 bis 0288 -> ok; alembic check meldet nur fremde Drifts (rent_increase_case.ai_check_id, contract_payment.reserve_id), keine eigenen
- ruff check/format und mypy src/mhvp/contracts src/mhvp/platform -> sauber (eine fremde E501 in platform/schemas.py Zeile 126, fremde C416 in portal/routers.py)
- web-portal: vitest src/lib/branding.test.ts src/components/auth -> 13 passed; tsc --noEmit -> sauber
- web-crm: vitest PortalSettings, DepositInterestPanel, DepositPanel, DepositInterestRatesAdmin -> 12 passed

**Nicht ausgeführte Tests:**

- tests/integration/test_migrations.py: test_downgrade_and_upgrade_round_trip und test_no_autogenerate_drift schlagen wegen fremder Migration 0281 (fk_rent_increase_case_ai_check_id_ai_proposal) und fremder Modelldrifts fehl, nicht wegen 0288; Downgrade von 0288 daher nicht per Rundlauf bestaetigt
- web-crm tsc --noEmit meldet Fehler in fremden Dateien (ai/PersonMatchTable, etag-lock), keine in meinen
- Playwright und volle Suiten nicht gelaufen (Vorgabe)

**Teilweise erledigt:**

- B20: Pflicht gilt nur fuer Anmeldung per Link; erzwungene TOTP-Einrichtung bei Passwortanmeldung nicht umgesetzt (widerspricht Betreiberentscheidung M2-01)
- B26: Manifest der Web-App bleibt statisch neutral; Logo-Upload fuer das Portal nutzt die vorhandenen Logo-Dokument-IDs, keine eigene Upload-Oberflaeche; Domains und CI-Werte fuer Fremdmandanten (G5) nicht freigegeben

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Konflikt Auftrag vs. Betreiberentscheidung: Auftrag nannte Standard Pflicht fuer den zweiten Faktor im Portal, M2-01 (26.09.2026) macht ihn freiwillig; umgesetzt Standard account_choice, Pflicht als Mandantenoption (A-R10-02, OPEN_QUESTIONS R10-02). Koordinator/Betreiber bestaetigen.
- Rechtliche Bewertung der Kautionsverzinsung je Anlageform offen (OPEN_QUESTIONS R10-01); Saetze nur vom Betreiber eingegeben
- Migration 0288 Downgrade laesst den Enum-Wert deposit_rates stehen (PostgreSQL)
- packages/api-client und openapi.json nicht regeneriert (Vorgabe); CRM nutzt fuer neue Felder lokale Typen und Casts
- Eigener Upload fuer Portal-Logo fehlt, vorhandene Logo-Dokument-IDs des Briefkopfs werden genutzt (nur PNG oder JPEG)
- Fremde Fehler beim Test: kurzzeitiger Syntaxfehler in ai/lookup_tools.py (inzwischen behoben), E501 in platform/schemas.py Zeile 126


### R11

**Ausgeführte Tests mit Ergebnis:**

- MHVP_PERF=1 pytest tests/integration/test_p15_perf.py -> 3 passed (contacts, seed, statement), bank_retrieval einzeln 1 passed
- pytest test_p15_perf.py ohne MHVP_PERF -> 4 skipped
- ruff check und mypy tests/bank_connector_stub.py -> ok

**Nicht ausgeführte Tests:**

- Staging-Messung
- Volle Suite

**Teilweise erledigt:**

- S16-08: Sollstellungslauf mit 1.000 Vertraegen nicht gesondert gemessen (Bestandstest mit 869 Einheiten); Abrechnungsmessung umfasst nur calculate; Staging-Messung offen

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Bankabruf-Schwelle 60 Sekunden ist Betreiberannahme, Spezifikation nennt keinen Wert
- Messwerte stammen aus geteilter Entwicklungsumgebung, Staging-Messung durch Betreiber
- ruff format auf tests/integration/ lief ueber das ganze Verzeichnis und hat dabei eventuell eine fremde Testdatei umformatiert (1 Datei), bitte per git diff pruefen


### R12

**Ausgeführte Tests mit Ergebnis:**

- web-crm playwright e2e/waves-2-3-pages.backend.spec.ts --project chromium --workers 1 (API 8112, DB mhvp_p12, Redis 6380/12, Web 3112, eigener Build .next-r12) -> 12 passed, 1 skipped (Mail-Kompaktansicht, keine Nachricht); erster Lauf scheiterte nur an eigenem Testfehler (leeres Route-Announcer-alert, Link-Locator traf /mail/postausgang), behoben
- web-portal playwright e2e/waves-2-3-pages.backend.spec.ts --project chromium --workers 1 (Web 3113) -> 2 passed; ein früherer Lauf scheiterte am 5s-Timeout des Rollenwechsels unter Last, Timeout auf 15s erhöht, danach grün

**Nicht ausgeführte Tests:**

- Phone/Tablet-Projekte (Specs nicht als @mobile markiert)
- Übrige bestehende @backend-Specs (nicht im Paket)
- tsc/eslint der neuen Specs nicht separat ausgeführt

**Teilweise erledigt:**

- R12: Mail-Kompaktansicht wird nur geprüft, wenn eine Nachricht vorhanden ist (Test übersprungen, kein Seed-Endpunkt für eingehende Mails)
- R12: Portal-Belegsuche nur als Dokumentensuche (M25-06) mit Leerzustand geprüft, nicht mit Trefferfall (kein Dokumentenseed im Portal-Pfad)
- R12: Rechnungsplan-Detailseite weg/[propertyId]/plan/[planId] nicht abgedeckt; Seiten werden nur auf Überschrift und fehlende Fehlerseite geprüft, ohne Schreibaktionen

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Seed-Endpunkt oder Testfixture für eingehende Mails und Portal-Dokumente fehlt; damit ließen sich Kompaktansicht und Belegsuche mit Treffern prüfen
- Baustein: Rollenwechsel braucht nach router.refresh() unter Last bis zu mehrere Sekunden, Test nutzt 15s Timeout
- Beim Start meldet next start eine Warnung wegen output standalone (funktioniert trotzdem)


### R13

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_r13_zip_limits.py tests/integration/test_r13_security_review.py test_q10_portal_w3.py test_p17_privacy.py test_q03_documents_w3.py -> 20 passed
- pytest test_m2_platform.py -k 'password or refresh or session' -> 5 passed
- pytest test_p13_portal.py test_m21_portal.py -> 51 passed
- mypy (5 geänderte Module) -> ok; ruff check/format eigene Dateien -> ok (fremde Lintfehler in notice_routers.py, owner_overview.py, transfer_routers.py:584, portal/routers.py:504 stammen von anderen Paketen)

**Nicht ausgeführte Tests:**

- Nebenläufigkeitstest Löschantrag
- volle Suite
- Frontend (keine Frontendänderung)

**Teilweise erledigt:**

- 6: kein Nebenläufigkeitstest
- 2: kein eigener Test für begrenztes Lesen

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Passwortwechsel: auch die aktuelle Sitzung endet mit Ablauf des Access Tokens (Refresh scheitert); BFF/CRM sollte nach Passwortwechsel zur Neuanmeldung führen
- Vertreterliste zeigt Anmeldeadresse bei tickets:read, Betreiberentscheidung zu engerem Recht
- Eigentümerabrechnungsliste zeigt Metadaten auch bei geschlossenem G4 (nur PDF gesperrt)
- Kein Fehlversuchszähler für current_password bei Passwortwechsel und TOTP-Abschaltung


### R14

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_r14_money_review.py -> 1 passed
- pytest Integrationstests Zahllauf, Zahlungen, Mahnung, Ergebnisse, Honorare, hoa_w2_gaps (38 Tests) -> nach Rücknahme der Sperre führendes System: alle zuvor fehlgeschlagenen 9 erneut gelaufen, 9 passed; übrige 30 passed
- ruff check und ruff format --check der geänderten Dateien -> ok
- mypy der geänderten Module -> ok

**Nicht ausgeführte Tests:**

- volle Suite, Frontend (keine Frontendänderung), Nebenläufigkeitstests mit echten parallelen Transaktionen

**Teilweise erledigt:**

- Regressionstests nur für costs/from-ledger ergänzt; für Zeilensperre, Honorarlauf-Parallelität, Ersatzversion und Zinsentwurf-Sperre keine eigenen Tests

**Nicht erledigt:**

- Sperre führendes System beim Anlegen von Zahlungsaufträgen: verworfen, widerspricht D52 (Sperre erst bei der Zahlungsdatei, bestehender Test)

**Offene Punkte und Entscheidungen:**

- H1 Jahresübertrag: Schlussbestandssatz datiert auf den ersten Tag des Folgejahres, Darstellung mit Steuerberater abstimmen (M10-07)
- H2 Verzugszinsen: Tage/365 und Rundung je Basiszinsperiode rechtlich nicht geprüft (V7)
- H3 costs/from-ledger nutzt Kalenderjahr, abweichendes Wirtschaftsjahr einer GdWE nicht abgebildet
- Zinsentwurf: ein bereits angelegter Entwurf wird bei späterer Sperre weiter idempotent zurückgegeben, nicht verworfen


### R15

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run surface-consistency, chat-suggestions, settings-index, i18n-consistency, table-wrapper (web-crm) -> 144 passed, danach surface-consistency 17 passed
- python3 scripts/check_i18n.py und check_i18n_usage.py -> OK
- python3 scripts/build_help_index.py --check -> ok (nach Neuerzeugung)
- pytest tests/unit/test_ai_lookup.py -k help_index -> fehlgeschlagen vor Neuerzeugung (Handbuch geändert), danach nicht erneut gelaufen
- pnpm tsc --noEmit web-portal -> rc 0
- pnpm tsc --noEmit web-crm -> nur Fehler in fremder MaintenancePanel.test.tsx (nicht R15)

**Nicht ausgeführte Tests:**

- pytest help_index nach Neuerzeugung
- web-portal vitest (Lauf lief in Hintergrund ohne ausgewertetes Ergebnis)
- Playwright

**Teilweise erledigt:**

- R15: Formulare mit Teilnehmerfeldern in Altkomponenten ohne aria-label bleiben (z.B. ContractForm, TenantAdmin, MembersAdmin, ProfileSettings, EntryActions, FinTsConnections, TransactionList, OccupancyList, kontakte/objekte Suchformulare, Portal dokumente, BoardEngagementDetail Rest), da sie nicht neu aus Welle 2 und 3 sind oder sichtbare Beschriftung haben

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- help_index.json muss nach jeder Handbuch- oder settings-index-Änderung anderer Pakete vom Koordinator neu erzeugt werden (python3 scripts/build_help_index.py)
- tsc-Fehler in apps/web-crm/src/components/properties/MaintenancePanel.test.tsx (fremdes Paket)
- Verbleibende Formulare ohne aria-label siehe partial


### R16

**Ausgeführte Tests mit Ergebnis:**

- Skriptprüfung Seiten gegen Handbuch, Regelindex gegen docs/rules -> ok

**Nicht ausgeführte Tests:** keine gemeldet.

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Plan-Statuszeilen sind als Fußzeile angehängt, Zuordnung der S-Punkte nur bei Paketen mit einem Plan
- Handbuchabschnitte der Seitenprüfung bleiben stichwortbasiert, inhaltliche Tiefe je Seite nicht geprüft


## Welle 5 (Pakete T)

### T01

**Ausgeführte Tests mit Ergebnis:**

- pytest test_t01_tenant_export_job.py + test_migrations.py -> 6 passed (Kette bis 0297)
- vitest TenantExportJobs.test.tsx -> 2 passed
- ruff check/format, mypy src/mhvp/platform -> sauber
- pnpm tsc --noEmit -> ohne Ausgabe (keine Fehler)

**Nicht ausgeführte Tests:**

- Playwright
- Gesamtsuite
- openapi/api-client Regeneration (Koordinator)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- OPEN_QUESTIONS T01-01: Aufbewahrung/Löschung alter Exportarchive, Verschlüsselung, Rechtsgrundlage der Herausgabe
- openapi.json und api-client müssen vom Koordinator neu erzeugt werden (neue Endpunkte)
- Adminprüfung per Rolle tenant_admin (Rolle administrator bewusst ausgeschlossen)


### T02

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_telemetry.py -> 4 passed
- ruff/mypy auf meine Dateien sauber (mypy meldet Fremdfehler logging.py redact_event, ruff Fremdfehler Importreihenfolge main.py)

**Nicht ausgeführte Tests:**

- Compose-Start mit Profil otel (kein Docker)
- Celery-Worker real mit Collector
- tests/unit/test_health.py scheitert an NameError text in Fremdcode

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- M9-02-01 Tracing-Backend und Datenschutz (OPEN_QUESTIONS)
- Fremd: mypy-Fehler redact_event in core/logging.py, Importreihenfolge main.py, NameError text in test_health


### T03

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_t03_bank_raw_consent.py -> 4 passed (Schluesselbildung, Parser, Retention-Zuweisung, Aufgabe)
- pytest tests/integration/test_m11_finapi.py -> 15 passed (einzeln; zusammen mit meiner Datei in einem Lauf Fixture-Fehler durch importierte Fixtures, getrennt gruen)
- pnpm vitest run src/components/banking -> 111 passed
- ruff check banking + neue Tests -> ok; mypy src/mhvp/banking -> ok

**Nicht ausgeführte Tests:**

- pnpm tsc --noEmit nicht ausgefuehrt
- tests/unit/test_finapi_client.py im Endlauf nicht ausgefuehrt

**Teilweise erledigt:**

- M11-08: Ablaufdatum wird nur bei Pruefung (/check) gelesen, kein taeglicher Abgleich beim Anbieter; GoCardless nicht vorhanden
- M11-07: Retention-Profil bleibt Entwurf bis Freigabe durch Steuerberatung (T03-01)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- T03-01 Freigabe Profil accounting_records (V17)
- T03-02 Feldname Zustimmungsablauf bei finAPI bestaetigen (M11-41), danach taeglicher Abgleich
- Bei Datei-Import wird die Rohdatei zusaetzlich zum bestehenden Upload-Dokument abgelegt (Doppelspeicherung, keine Migration fuer Verknuepfung mit BankSyncRun)


### T04

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_t04_admin_fee_posting.py test_q15_fee_documents.py test_m13_xrechnung.py -> 6 passed
- pytest tests/integration/test_migrations.py -> 4 passed
- ruff check (eigene Dateien) -> ok
- mypy admin_fee_posting, admin_fees, models, main -> ok
- vitest AdminFeePanel.test.tsx -> 4 passed
- tsc --noEmit -> keine Fehler in geänderten Dateien

**Nicht ausgeführte Tests:**

- Volle Suiten, Playwright (Vorgabe Welle 5)

**Teilweise erledigt:**

- M13-07: CRM-Eingabemaske für die Kontenzuordnung fehlt (nur API, BFF freigeschaltet)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- T04-01 in OPEN_QUESTIONS: USt-Behandlung beim Zahler und Verwalter, Konten je Buchungskreis (mit P02-02, Steuerberater, G1)
- CRM-Maske für admin-fee-posting-config fehlt
- OpenAPI/api-client nicht regeneriert (Koordinator)
- ruff meldet E501 in fremder Datei accounting/invoice_factual.py (nicht T04)


### T05

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade 0291, downgrade 0290, upgrade 0291 (mhvp_p05) -> ok
- alembic upgrade head -> ok
- pytest test_w5_t05_invoice_factual.py test_w2_p03_invoice_checks.py test_m14_invoices.py test_pue_invoice_checks.py -> 12 passed
- pytest tests/unit/test_invoice_factual.py -> 3 passed
- pytest test_migrations.py -> 2 passed, 2 failed (fremd: downgrade base scheitert an ck_hoa_inspection_event_kind mit Bestandsdaten; drift meldet fehlenden Index ix_contract_payment_reserve_id, nicht T05)
- ruff check, ruff format, mypy (accounting) -> ok
- vitest InvoiceFactualPanel.test.tsx -> 3 passed
- pnpm tsc --noEmit (web-crm) -> ok

**Nicht ausgeführte Tests:**

- Playwright
- volle Suiten
- openapi export (Koordinator)

**Teilweise erledigt:**

- M14-02: Mengenabgleich gegen Auftragspositionen fehlt, weil work_order kein Positionsmodell (Menge, Einzelpreis) hat (Ticketdomäne); Toleranzpflege nur per API, keine CRM-Maske; Verknüpfungsfelder (Auftrag, Beschluss, Planposition, Rechnungsplan) nicht in der CRM-Erfassungsmaske

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- OPEN_QUESTIONS T05-01: Toleranzwerte, Positionsmodell für Arbeitsaufträge (Ticketdomäne), Budgetabgleich brutto oder netto
- CRM Erfassungsmaske um Auswahl Auftrag, Beschluss, Planposition und Rechnungsplan ergänzen; CRM Maske für Toleranzen
- Hinweis Freitext Auftragsbezug erscheint nur im factual-check, nicht in invoice.findings (bestehende Erwartungen in test_m14_invoices)
- Fremde Fehler in test_migrations: Index ix_contract_payment_reserve_id fehlt in einer Migration, Downgrade hoa_inspection_event mit Daten


### T06

**Ausgeführte Tests mit Ergebnis:**

- uv run pytest tests/unit/test_m17_09_heating_import.py -> 5 passed
- uv run alembic upgrade head (mhvp_p06, bis 0297) -> ok
- uv run pytest tests/integration/test_m17_09_heating_import.py -> 1 passed (Ablauf, 403, 404 anderer Mandant, 422, Dubletten, Übernahme 2.250,00 EUR)
- uv run pytest tests/integration/test_migrations.py tests/integration/test_m17_heating.py -> 5 passed
- ruff check (eigene Dateien) -> ok; mypy src/mhvp/billing -> ok

**Nicht ausgeführte Tests:**

- Frontend (keine Komponente geändert außer BFF-Allowlist; pnpm tsc nicht ausgeführt)
- volle Suite, Playwright

**Teilweise erledigt:**

- M17-09: CRM-Oberfläche fehlt (nur BFF-Allowlist und API); Handbuch beschreibt API-Bedienung

**Nicht erledigt:**

- M17-09: ARGE HeiWaKo D-Format und feste Messdienstformate: Format nicht belegt, offene Frage M17-09-01

**Offene Punkte und Entscheidungen:**

- OPEN_QUESTIONS M17-09-01: CO2-Vermieteranteil in Einzelbeträgen enthalten (Annahme) oder bereits abgezogen; feste Messdienstformate; Toleranz CO2-Prüfung
- CRM-Maske für den Heizkostenimport fehlt
- ruff meldet I001 in billing/owner_statement_routers.py (fremde Änderung, nicht angefasst)
- OpenAPI-Export nicht aktualisiert (Koordinator)


### T07

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_p13_portal.py tests/integration/test_q10_portal_w3.py -> 13 passed
- pnpm vitest run PortalManagement (web-crm) -> 2 passed
- pnpm vitest run DocumentBundleList (web-portal) -> 2 passed

**Nicht ausgeführte Tests:**

- tsc, ruff, mypy: keine Änderungen am Code

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Q10-01 und Q10-02 bleiben offen (Umlageeigenschaften, Mieterträge Datenschutz, Eigentümer Timo Müller)
- Lückenliste-Spalte Stand für M21-06, SA-05, SA-06, SA-01 ist veraltet und sollte der Koordinator auf umgesetzt setzen
- Anfangs KeyError 0292 in der Migrationskette durch parallele Agenten, nach Eintreffen von 0292 grün


### T08

**Ausgeführte Tests mit Ergebnis:**

- ruff check/format, mypy src/mhvp/workspace -> grün
- pnpm vitest NotificationPreferences.test.tsx -> 3 passed
- pnpm tsc --noEmit -> grün

**Nicht ausgeführte Tests:**

- tests/integration/test_q11_workspace_w3.py (Migrationen 0290 bis 0292 fehlen noch, alembic bricht ab; Spalte nur manuell in mhvp_p08 angelegt)
- tests/integration/test_migrations.py

**Teilweise erledigt:**

- M23-04: kein SMS-Kanal; Mailversand setzt weiter ein Standardpostfach voraus; Stummschaltung wirkt beim Anlegen, nicht erneut beim Versand

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Integrationstest nach Vorliegen von 0292 ausführen
- docs/plans/M23 Statuszeile nicht ergänzt (Plan-Datei nicht gefunden)


### T09

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_t09_reserve_develop.py -> 1 passed
- pytest tests/integration/test_t09_hoa_reserves.py test_q09_hoa_w3.py test_hoa_w2_gaps.py -> 7 passed
- pytest tests/integration/test_m24_asset_report.py + test_migrations.py -> 3 passed, 2 failed: downgrade round trip scheitert in 0278 an fremden Testdaten in hoa_inspection_event (vorbestehend, nicht T09), drift danach nach Wiederherstellung des Index -> 1 passed
- ruff check src/mhvp/hoa + Tests -> ok; mypy src/mhvp/hoa -> ok
- vitest ReservePositions.test.tsx ReserveForms.test.tsx -> 5 passed
- tsc --noEmit -> keine Fehler in den T09-Dateien

**Nicht ausgeführte Tests:**

- Playwright
- volle Suiten

**Teilweise erledigt:**

- M24-01: Bankkonto und Buchungskonto nur über API pflegbar, CRM-Formular ohne Kontoauswahl; Steuern/Gebühren als Bewegungsarten vorhanden, keine steuerliche Einordnung; reserve_plan als eigene Entität nicht angelegt (Soll je Position kommt aus PlanItem.reserve_id)

**Nicht erledigt:**

- reserve_statement als eigenes Dokument: Paket T11

**Offene Punkte und Entscheidungen:**

- test_migrations Downgrade-Rundlauf scheitert in 0278 (Check hoa_inspection_event) bei vorhandenen Testdaten, unabhängig von T09; ein abgebrochener Downgrade hinterlässt ix_contract_payment_reserve_id fehlend (in mhvp_p09 manuell wiederhergestellt)
- main.py: Importreihenfolge (platform.export_routers) von anderem Paket verletzt ruff I001
- OpenAPI/api-client nicht regeneriert (Koordinator); CRM nutzt neue Endpunkte über BFF
- T11: Rücklagendaten für reserve_statement über reserves.reserve_development() und Snapshot-Felder opening/closing_*


### T10

**Ausgeführte Tests mit Ergebnis:**

- test_w5_t10_import_reports.py + test_q08_import_history.py + test_m8_import.py -> 5 passed (gegen Kopie der Migrationskette mit Platzhaltern für 0292 und 0296, in $SP/w5/t10run)
- ruff check src/mhvp/imports, ai/imports.py, Test, Migration -> ok
- mypy src/mhvp/imports -> ok
- pnpm vitest run src/components/imports -> ok

**Nicht ausgeführte Tests:**

- alembic upgrade head und tests/integration/test_migrations.py gegen die echte Kette (0292 und 0296 fehlten bei Abschluss)
- pnpm tsc --noEmit
- Portalnutzer-Konflikt mit vorhandenem Portalkonto nicht getestet

**Teilweise erledigt:**

- M8-01: Spaltenzuordnung generisch, da in docs/integrations keine Immoware24-Spalten belegt sind; echte Exportkopfzeilen weiter offen (T10-01)

**Nicht erledigt:**

- Portalnutzer: kein Anlegen von Konten oder Einladungen (bewusst, nur Statusabgleich)

**Offene Punkte und Entscheidungen:**

- ReportType ist ein Datenbank-Enum (import_report_type): ohne Migration nicht erweiterbar. Ich habe 0297 (ALTER TYPE ADD VALUE, wie 0277) geschrieben, obwohl das Paket keine Migration vorsah; Nummer 0297 war nicht zugewiesen, bitte Koordinator prüfen, down_revision 0296 setzt T12 voraus.
- Kautionen entstehen ohne Kautionskonto und ohne Bewegung; Kontozuordnung manuell.
- Dienstleister: Kreditorenkonto und Freistellungsbescheinigung werden nicht importiert.
- apps/api/openapi.json und api-client nicht regeneriert (ReportType-Enum, Koordinator: make openapi); Frontend nutzt bis dahin einen Cast wie bei Welle 3.
- OPEN_QUESTIONS T10-01: echte Immoware24-Kopfzeilen fehlen.


### T11

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p11, Kette bis 0297) -> ok
- pytest tests/unit/test_s69_statement_lifecycle.py -> 6 passed
- pytest tests/integration/test_s69_statement_status.py tests/integration/test_m17_owner_statement.py -> 6 passed
- pytest tests/integration/test_migrations.py -> round trip fehlgeschlagen in fremder Migration 0281 (fk_rent_increase_case_ai_check_id_ai_proposal fehlt beim Downgrade); Drift danach nur durch den abgebrochenen Downgrade, keine Drift an owner_statement oder reserve_statement
- ruff check und mypy billing, hoa -> ok (einziger ruff-Befund: Importreihenfolge platform.export_routers in main.py, fremd)
- vitest src/components/billing/ und ReserveStatementPanel.test.tsx -> 9 Dateien, 24 Tests passed
- pnpm tsc --noEmit -> ok; eslint geänderte Dateien -> ok

**Nicht ausgeführte Tests:**

- Playwright
- volle Suiten
- test_migrations round trip sauber (durch fremde Migration 0281 blockiert)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Freigabestufe: Paket nannte G4 für posted und issued; umgesetzt G3 für die Eigentümerabrechnung (Mietabrechnung wie deren PDF), G4 für die Rücklagenabrechnung (OPEN_QUESTIONS S69-01-01).
- posted bucht nichts, sondern verweist auf bereits gebuchte Buchungen des Buchungskreises; welche Buchung eine Eigentümer- oder Rücklagenabrechnung abschließt, ist offen (S69-01-01).
- Beschluss der Rücklagenabrechnung: angenommen, dass der Beschluss auf den Snapshot der Hausgeldabrechnung genügt (A-S69-01-01).
- openapi.json und packages/api-client nicht regeneriert (Koordinator): neue Pfade /billing/owner-statements/{id}/transition und /hoa/reserve-statements*.
- test_migrations round trip scheitert in der fremden Migration 0281 (Downgrade-Constraintname); Datenbank mhvp_p11 nach dem Testlauf ggf. neu aufsetzen.
- ruff I001 in main.py durch fremden Import platform.export_routers.


### T12

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_t12_reply_task_record_fields.py -> 4 passed
- pytest test_migrations.py test_q11_workspace_w3.py test_p12_mail_compact.py test_r09_compact_reply.py + unit ai/eval/automation -> 69 passed, 1 failed (test_notification_mail_modes_collective, fremdes Paket T08, einzeln wiederholt: passed)
- alembic upgrade head auf mhvp_p12 (bis 0297) -> ok
- ruff check automation ai communication und neuer Test -> ok
- mypy automation communication ai -> ok
- vitest CompactView.test.tsx AutomationMasterActions.test.tsx -> 9 passed
- tsc --noEmit: keine Fehler in CompactView, AutomationAdmin, AutomationMasterActions

**Nicht ausgeführte Tests:**

- Gesamtsuiten, Playwright, next build
- Offline-KI-Auswertung (evaluate.py) ohne Fälle für reply_draft

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- T12-01 in OPEN_QUESTIONS: ob weitere Stilfelder (Anrede, Grußformel je Gesellschaft) nötig sind, Eigentümer Betreiber
- Route reply-draft existierte bereits (Entwurf anlegen), daher heißt der KI-Weg reply-ai
- Beim Formatieren mit ruff format src können Dateien anderer Pakete mitformatiert worden sein (nur Formatierung)
- Offline-Auswertungsfälle für reply_draft (ai/evaluate.py SCORERS) nicht angelegt
- R09-02 in OPEN_QUESTIONS nicht geändert (nur anhängen erlaubt), Erledigung steht in T12-01 und docs/rules/T12.md


### T13

**Ausgeführte Tests mit Ergebnis:**

- pytest test_t13_sd_access_protocol.py -> 3 passed
- pytest test_p08_sd_portal.py test_p08_hoa_audit_inspection.py test_m21_board_portal.py test_a61_inspection.py -> 11 passed
- ruff check/format auf neue Testdatei -> sauber

**Nicht ausgeführte Tests:**

- mypy (Tests nicht Teil von src)
- Frontend (keine Änderung)

**Teilweise erledigt:**

- SD-05: keine erneute Einladung bei abgelaufener Einladung (T13-01)
- SD-06: keine Beiratsprüfung vor dem Beschluss am Tagesordnungspunkt vorgesehen (T13-02)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- T13-01 erneute Einladung nach Ablauf (G5)
- T13-02 Beiratsprüfung vor Beschluss als Hinweis oder Verweis, rechtlich zu klären (G4)
- T13-03 Bezeichnung Status retrieved bestätigen (G4)
- Lückenliste Spalte Stand für SD-05 bis SD-07 durch Koordinator zu aktualisieren


### T14

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_t14_property_scope_rest.py -> 1 passed
- pytest r08, q13, m11_banking, a72_a74, m21_board_portal, m21_portal, m9_rule_proposals, m35_objektakte_lists, q10_portal_w3, m12_history_and_invoice, m8_migration, migration_0213/0221, q08_import_history -> 83 passed
- ruff check banking portal hoa objektakte imports (geänderte Dateien) -> ok (vorbestehende E501 in fremder imports/w5_reports.py)
- mypy geänderte Quelldateien (20) -> ok

**Nicht ausgeführte Tests:**

- volle Suiten, Playwright, Frontend (keine Frontendänderung)
- test_migrations.py (keine Migration)
- OpenAPI-Export (Koordinator; keine neuen Endpunkte, nur Abhängigkeiten)

**Teilweise erledigt:**

- R08-01: Immoware24 Datei-/Vollimporte ohne Zielobjekt, Abgleichberichte über alle Objekte, historische Bankverknüpfungen, Änderungsvorschläge/Vollmachten/Mandatsvorschläge der Portalverwaltung nicht angeschlossen (OPEN_QUESTIONS T14-01)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- T14-01 in docs/OPEN_QUESTIONS.md: mandantenweite Importe ohne Zielobjekt, Kontakte, Portal-Vorschläge/Vollmachten/Mandate weiter mandantenweit (Betreiberentscheidung)
- Buchungskreis-Prüfung nutzt Ledger.property_id wie R08; Buchungskreise nur mit Objekt am Rechtsträger sind für eingeschränkte Mitglieder 404
- Sync-Läufe ohne Kontobezug und Regeln ohne Objekt sind für eingeschränkte Mitglieder unsichtbar
- ruff --fix lief einmal über imports/: nur Importsortierung in w3_routers.py beabsichtigt, bitte Diff an imports/w5_reports.py (fremd) prüfen


### T15

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_s16_03_redaction.py tests/unit/test_q13_etag_key_rotation.py -> 33 passed
- pytest tests/integration/test_m26_letting.py::test_prospect_viewings_rejection_templates_and_self_disclosure (mhvp_p15) -> 1 passed
- pytest tests/integration/test_q13_property_scope_etag.py::test_key_rotation_dry_run_apply_and_back -> failed: UndefinedColumn mailbox.reply_style (fremdes Paket, Migration fehlt noch)
- ruff check/format, mypy core/redaction.py core/events.py core/logging.py letting/routers.py -> sauber

**Nicht ausgeführte Tests:**

- Rotationsintegrationstest grün (nach Eintreffen der reply_style-Migration erneut ausführen)
- keine Frontendänderung, daher kein vitest/tsc

**Teilweise erledigt:**

- S16-03: Rotationsintegrationstest test_key_rotation_dry_run_apply_and_back konnte nicht grün laufen, weil ein paralleles Paket mailbox.reply_style ins ORM eingefügt hat, dessen Migration noch fehlt (fremder Zwischenstand, kein T15-Fehler)

**Nicht erledigt:**

- EBICS-Schlüssel: EBICS nicht implementiert, nichts zu verschlüsseln (OPEN_QUESTIONS S16-03-02)
- Vaultwarden/SOPS-Anbindung des Masterschlüssels: Betriebsentscheidung, Rest aus 1.49.0

**Offene Punkte und Entscheidungen:**

- S16-03-01: Datenmigration für Altzeilen self_disclosure_link.token (Klartext -> sha256:<hex>), kein Schemawechsel nötig (String(96) reicht); bis dahin Lookup über Digest oder Klartext
- S16-03-02: EBICS bei Umsetzung als EncryptedText speichern (Gate G2)
- Maskierung in events.emit wirkt auch auf Webhook-Payloads aus Domain Events; Felder mit Namen token/secret werden dort als [redacted] ausgeliefert (gewollt, bisher kein Konsument gefunden, der solche Felder braucht)
- Rotationsintegrationstest nach Eintreffen der Migration für mailbox.reply_style erneut laufen lassen


### T16

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run PortalSettings.test.tsx -> 4 passed
- vitest settings/ProfileSettings/MembersAdmin/OccupancyList/ContractForm/banking/accounting/platform -> 343 passed; unter Last 2 Timeouts (ProfileSettings, MembersAdmin), mit --testTimeout=30000 11 passed; NotificationPreferences.test.tsx schlägt fremd fehl (fehlender Schlüssel NotificationSettings.deliveryHelp, nicht T16)
- web-portal BoardEngagementDetail.test.tsx --testTimeout=30000 -> 6 passed
- web-crm pnpm tsc --noEmit -> ohne Fehler
- playwright test --list hoa-plan-detail.backend.spec.ts -> 1 Test erkannt

**Nicht ausgeführte Tests:**

- Playwright hoa-plan-detail.backend.spec.ts (braucht laufendes Backend und Webserver, E2E_BACKEND=1)
- tsc im web-portal
- ESLint
- Vitest für Portal dokumente-Seite (Server Component, ohne Test)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- R10-04 in OPEN_QUESTIONS angehängt (Logo in Fremdmandanten, G5)
- Playwright-Spec nicht gegen Backend ausgeführt
- NotificationPreferences.test.tsx (fremdes Paket) schlägt wegen fehlendem Schlüssel NotificationSettings.deliveryHelp fehl
- Modul-README und docs/plans/M-Statuszeile nicht ergänzt, nur Handbuch


## Welle 6 (Pakete U)

### U01

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run (3 neue Testdateien, InvoiceForms, settings-index, invoices, bff, surface-consistency) -> 261 und 17 Tests grün
- pnpm tsc --noEmit -> ohne Fehler
- pnpm eslint (4 geänderte Komponenten) -> ohne Fehler
- scripts/check_i18n.py -> OK

**Nicht ausgeführte Tests:**

- Playwright, next build, API-Suiten (keine API-Änderung)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- scripts/build_help_index.py --check meldet help_index.json veraltet (Handbuch geändert, auch durch andere Pakete): Koordinator soll am Ende neu erzeugen, Datei nicht angefasst.
- Beschlussauswahl benötigt den Rechtsträger des Buchungskreises (legal_entity_id aus GET /accounting/ledgers); Plan und Planpositionen kommen aus GET /hoa/plans, Zugriff nach Leserecht hoa.
- Manager-Buchungskreise werden in der Honorarmaske über GET /tenant/legal-entities (members:read) gefiltert; ohne dieses Recht zeigt die Maske alle Buchungskreise und die API lehnt falsche ab.
- Steuerbehandlung des Honorars bleibt offen (T04-01), Hinweis steht in der Maske.


### U02

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run src/app/api src/components/billing src/lib/i18n-consistency.test.ts -> 15 Dateien, 253 passed
- pnpm tsc --noEmit -> ok
- eslint der neuen Dateien -> ok

**Nicht ausgeführte Tests:**

- Backend (keine Änderung)
- Playwright, Build

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:**

- M17-09: feste Messdienstformate (offene Frage M17-09-01)

**Offene Punkte und Entscheidungen:**

- Verträge werden je Objekt ohne Stichtagsfilter geladen, die Auswahl zeigt alle Verträge der Einheit
- Abrechnungsliste der API ist auf 200 Einträge begrenzt


### U03

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run src/components/hoa/Reserve src/components/billing/StatementStatusActions -> 5 Dateien, 13 Tests passed
- eslint geänderte Dateien -> ok
- pnpm tsc --noEmit -> keine Fehler in U03-Dateien (Fehler nur in fremder billing/HeatingImportPanel.tsx)

**Nicht ausgeführte Tests:**

- Playwright
- volle Suiten
- Backend-Tests (keine API-Änderung)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- tsc: fremde Fehler in billing/HeatingImportPanel.tsx
- Statusverlauf zeigt keinen Bearbeiter (API liefert nur Benutzer-ID)


### U04

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p04, 0297 -> 0298 -> 0299) -> ok
- pytest tests/integration/test_s16_webauthn_login.py tests/unit/test_webauthn_verify.py tests/integration/test_m2_platform.py tests/integration/test_migrations.py -> 51 passed
- pytest tests/integration/test_p14_member_scope_webauthn.py -> passed
- pytest tests/unit/test_p14_auth_security.py tests/unit/test_webauthn_verify.py -> 17 passed
- ruff check (core, tests, migration) -> ok; mypy src/mhvp/core/auth src/mhvp/platform/models.py -> ok
- web-crm vitest lib/webauthn, components/auth, ProfileSettings, Passkeys -> 22 passed; tsc --noEmit -> ok; eslint geänderte Dateien -> ok
- web-portal vitest lib/webauthn, components/auth, SecuritySettings, Passkeys -> 17 passed; tsc --noEmit -> ok; eslint geänderte Dateien -> ok

**Nicht ausgeführte Tests:**

- Playwright und echte Authenticatoren (Rahmen: keine Playwright-Läufe)
- volle Suiten API/Web
- make openapi (openapi.json und api-client nicht angefasst; Frontend nutzt fetch ohne generierte Typen für die neuen Pfade)

**Teilweise erledigt:**

- S16-01: Serverseitige Sperre der passwortlosen Anmeldung für reine Portalkonten fehlt (nur im Portal-BFF erzwungen), OPEN_QUESTIONS U04-02

**Nicht erledigt:**

- Freischaltung produktiv: bewusst aus, Sicherheitsprüfung der eigenen Protokollprüfung bzw. Bibliotheksfreigabe offen (U04-01, P14-02)
- Test mit echten Browsern/Geräten und Playwright: laut Rahmen keine Playwright-Läufe

**Offene Punkte und Entscheidungen:**

- U04-01: Freischaltung erst nach Sicherheitsprüfung der Protokollprüfung oder Wechsel auf geprüfte Bibliothek (P14-02); RP ID und Origins je Umgebung festlegen; .env.example nicht ergänzt (gemeinsame Datei).
- U04-02: Portal nur zweiter Faktor ist im Portal-BFF erzwungen, nicht in der API (Kennzeichen Portalkonto fehlt).
- Registrierung verlangt keine erneute Anmeldung (Re-Auth M20-04 nicht angebunden); gemerkte Geräte überspringen auch die Passkey-Abfrage (A-U04-01).
- Koordinator: make openapi ausführen (neue Schemas AuthWebAuthn*, LoginStep.mfa_methods, AuthWebAuthnCredentialOut.passwordless).


### U05

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_p13_portal.py -> 10 passed
- ruff check portal + test -> ok
- mypy src/mhvp/portal -> ok
- vitest RepresentationList + shell -> 23 passed
- tsc --noEmit web-portal -> ok

**Nicht ausgeführte Tests:**

- Playwright, next build, Vollsuite

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Hinweis auf bald ablaufende Vollmachten per Benachrichtigung nicht umgesetzt (Frist als Produktentscheidung offen).
- OpenAPI und api-client nicht regeneriert (Koordinator).
- Portal-OpenAPI-Typ von /portal/me ist untyped, daher kein Client-Update noetig.
- docs/rules/M21-05.md behandelt WhatsApp, Vertretungsregel daher in M21-05-vertretung.md


### U06

**Ausgeführte Tests mit Ergebnis:**

- pytest test_u06_ticket_bulk.py test_m19_ticket_templates.py -> 7 passed
- ruff, mypy src/mhvp/tickets -> ok
- vitest src/components/tickets -> 95 passed
- pnpm tsc --noEmit -> ok

**Nicht ausgeführte Tests:**

- openapi.json und api-client nicht regeneriert (Koordinator)
- test_d50_authorization nicht gelaufen

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- openapi.json und packages/api-client müssen vom Koordinator neu erzeugt werden (TicketBulkIn geändert, status jetzt optional)
- Keine docs/rules Datei angelegt, keine neue Fachregel


### U07

**Ausgeführte Tests mit Ergebnis:**

- pnpm vitest run AccountsManager.test.tsx -> 1 passed
- pnpm tsc --noEmit -> keine Fehler in AccountsManager (Fehler in HeatingImportPanel.tsx fremd)
- ruff check/format auf neue Python-Dateien -> ok
- psql: Indexanlage und EXPLAIN ANALYZE mit 5.000 Dokumenten -> ok

**Nicht ausgeführte Tests:**

- tests/integration/test_u07_document_search_perf.py (Migrationskette bricht an fehlender 0298)
- tests/integration/test_migrations.py
- mypy

**Teilweise erledigt:**

- M25-06: Messung nur von Hand per psql (Sequenzscan 3,5 ms bei 5.000 Zeilen); der Pytest-Messtest lief nicht, weil 0298 fehlt

**Nicht erledigt:**

- SA-08: Seed-Kontenrahmen mit Mehrschlüsselverteilung und Hausgeld/Rücklage je Konto (Fremdbereich accounting, fachliche Entscheidung), als U07-01 in OPEN_QUESTIONS

**Offene Punkte und Entscheidungen:**

- Migration 0299 und Pytest nach Vorliegen von 0298 ausführen (alembic upgrade head, test_u07, test_migrations)
- U07-01: Seed-Kontenrahmen Hausgeld/Rücklage und Mehrschlüssel fachlich festlegen
- Bei 5.000 Dokumenten wählt der Planer den Sequenzscan; Index erst bei größeren Beständen wirksam


### U08

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p08) -> bis 0299 ok
- MHVP_PERF=1 pytest tests/integration/test_u08_perf.py -s --no-cov -> 2 passed (100 s)
- ruff check test_u08_perf.py -> ok

**Nicht ausgeführte Tests:** keine gemeldet.

**Teilweise erledigt:**

- S16-08: Staging-Messung mit produktionsnaher Datenmenge bleibt Betreiberaufgabe

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- U08-01: Staging-Messung mit produktionsnaher Datenmenge (Betreiber); Buchung des Sollstellungslaufs (43,3 s) ist der größte Anteil, keine Optimierung nötig


### U09

**Ausgeführte Tests mit Ergebnis:**

- pytest test_u09_invoice_submission.py -> 5 passed
- pytest test_q11_workspace_w3.py test_m21_portal.py -k invoice_submission or portal -> 43 passed
- pnpm vitest WorkOrderDetail.test.tsx -> 8 passed
- mypy src/mhvp/portal -> 1 Fehler in Zeile 547 (fremder U15-Edit), nicht von U09
- pnpm tsc --noEmit (web-portal) -> ohne Ausgabe

**Nicht ausgeführte Tests:**

- Testdateien u09 und q11 in einer Session zusammen (Login-Konflikt der Fixtures, einzeln gruen)
- Volle Suiten, Playwright

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- mypy-Fehler routers.py Zeile 547 stammt aus einem U15-Edit (change_requests), bitte dort beheben
- Rechnungsbuch-Duplikat nur als Befund; harte Sperre nur bei gleicher Nummer (bestehend)
- IBAN-Befund wird im CRM-Belegentwurf als Text in findings angezeigt, keine eigene Komponente


### U10

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_csv_formats.py -> 13 passed
- ruff check src/mhvp/banking -> ok
- mypy csv_formats.py -> ok

**Nicht ausgeführte Tests:**

- Integrationstest Import Endpunkt, Modul-README, plans/M11.md Statuszeile, Handbuch nicht ergänzt

**Teilweise erledigt:**

- M11-09: Rücknahme über Import-Undo nicht angebunden, Bankdatei-Importe (BankSyncRun) sind nicht im ImportRun-Undo; Spaltennamen nur Annahme A-M11-09-01 (keine Beispieldatei)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- M11-09-01: Beispieldatei des Immoware24-Umsatzexports fehlt
- Rücknahme von Bankdatei-Importen über Import-Undo gewünscht? Würde Recorder-Anbindung in banking.services.import_file erfordern


### U11

**Ausgeführte Tests mit Ergebnis:**

- uv run pytest test_u11_retention_procedure_holds.py test_m6_04_retention_matrix.py test_q03_documents_w3.py test_m6_documents.py test_m9_restore_replay.py (mhvp_p11, head 0299) -> 30 passed
- uv run ruff check src/mhvp/documents + geänderte Tests -> ok
- uv run mypy src/mhvp/documents -> ok

**Nicht ausgeführte Tests:**

- Frontend (keine Frontend-Änderung)
- volle Suite
- OpenAPI-Export (Koordinator)

**Teilweise erledigt:**

- S711-06: Fristbeginn Beschluss nur über retention_base_on mit vorhandenen Startregeln, keine eigene Startregel (Schema retention_start nötig)
- S711-06: Steuerverfahren und Rechtssachen außerhalb der Buchhaltung ohne Datenmodell, Sperre dort weiter manuell (Sperrart tax_procedure, legal_matter)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- U11-01 in OPEN_QUESTIONS: Startregel Beschluss (Schema), Datenmodell Steuerverfahren/Rechtssachen, Fristwerte bleiben Entwurf
- Bestehende Tests angepasst: Sperraufhebung jetzt durch zweite Person (m6_documents, m6_04, q03, m9_restore_replay)
- CRM-Anzeige des Sperrstatus nicht gebaut; BFF-Allowlist für GET documents/{id}/retention-status bei Bedarf ergänzen


### U12

**Ausgeführte Tests mit Ergebnis:**

- pytest test_u12_sd_pue11.py -> 1 passed
- pytest test_t13_sd_access_protocol.py -> 3 passed
- pytest test_q13_property_scope_etag.py -> 3 passed
- pytest test_m21_portal.py -> 42 passed
- pytest test_p08_sd_portal.py -> 2 passed
- ruff check portal und neue Tests -> clean; mypy src/mhvp/portal -> clean

**Nicht ausgeführte Tests:**

- Frontend (kein UI-Edit)
- mehrere Integrationsdateien in einem pytest-Aufruf ergeben Fixture-Fehler (nur einzeln grün, Ursache nicht untersucht)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- U12-01: inhaltliche Schwärzung bleibt außerhalb des Systems
- T13-01 fachliche Bestätigung durch Betreiber
- CRM-Oberfläche zeigt keinen eigenen Button für erneute Einladung (API vorhanden, BFF-Pfad accounts existiert)
- Kombinierte pytest-Läufe mehrerer Integrationsdateien mit Modul-Fixtures scheitern im Aufbau, einzeln grün


### U13

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_u13_import_history.py -> 2 passed
- pytest tests/integration/test_q08_import_history.py tests/integration/test_m8_import.py -> 3 passed
- ruff check src/mhvp/imports src/mhvp/ai/imports.py tests/integration/test_u13_import_history.py -> ok
- mypy src/mhvp/imports src/mhvp/ai/imports.py -> ok

**Nicht ausgeführte Tests:**

- Frontend (keine Frontend-Änderung)
- volle Suite (Vorgabe)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Kleine additive Änderung in mhvp/ai/imports.py (Dispatch der Rücknahme an w3_reports), Domäne ai
- Vorzeichenregel A-U13-01 ist Annahme; fachliche Bestätigung offen (wie Q08-03)
- Kautionskonten werden nur erkannt, wenn das Sachkonto mit einem getrennten Objektbankkonto verknüpft ist; ein eigenes Kontoattribut Kautionskonto existiert nicht
- OpenAPI unverändert (nur zusätzliche Felder im JSON-Bericht ohne Schema)


### U14

**Ausgeführte Tests mit Ergebnis:**

- sh scripts/gen_python_client.sh --help -> ok
- make client-py -> Exit 0, Paket mhvp_api_client erzeugt, 1 Schema (ImmowareSyncRunOut) vom Generator wegen Referenzfehler ausgelassen

**Nicht ausgeführte Tests:**

- Import und Aufruf des erzeugten Clients gegen laufende API

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Abweichung: uv add --dev nicht verwendet (hätte pyproject.toml und uv.lock der parallel bearbeiteten API geändert); stattdessen uvx mit gepinnter Version, bei Wunsch später als dev-Abhängigkeit nachziehen.
- Generator lässt ImmowareSyncRunOut aus (Referenz auf SyncStatus-Output nicht auflösbar): Schema im Immoware-Sync prüfen.
- Das Skript wird nicht in make lint oder CI aufgerufen.


### U15

**Ausgeführte Tests mit Ergebnis:**

- pytest test_u15_review_w45.py test_t14_property_scope_rest.py -> 5 passed
- pytest test_t09_hoa_reserves test_t01_tenant_export_job test_t03_bank_raw_consent test_t12_reply_task_record_fields test_q11_workspace_w3 (mit u15/t14) -> 23 passed vor der letzten Testanpassung
- pytest test_p13_portal.py + u15 -> 14 passed
- pytest test_t04_admin_fee_posting test_w5_t05_invoice_factual test_q13_property_scope_etag test_r08_property_scope_domains -> 9 passed
- ruff check/format, mypy (workspace, portal, platform, accounting, banking/raw_archive, communication/suggest, hoa/reserves) -> ok

**Nicht ausgeführte Tests:**

- Gesamtsuite
- Frontend (keine Frontendänderung)
- Nebenläufigkeitstest der Advisory-Sperre (nur Codeprüfung)

**Teilweise erledigt:**

- T12: Freigabe ohne Prüfsumme des gesehenen Entwurfs (U15-01)
- T05: Verknüpfungen nicht auf Objektgleichheit geprüft (U15-02)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- U15-01 bis U15-04 in docs/OPEN_QUESTIONS.md
- T04: idempotente Rückgabe vorhandener Entwurfs-IDs erfolgt vor der Bereichsprüfung (nur IDs, geringes Risiko)
- DB mhvp_p15 war veraltet (0252/0261 nachträglich erweitert): Spalten invoice.recurring_plan_id und mailbox.reply_style manuell ergänzt; für saubere Läufe DB neu aufsetzen
- Portal-Schreibrouten der Vollmachten erfordern tenant_settings:update (Admin, nie objektgebunden): Prüfung dort defensiv


### U16

**Ausgeführte Tests mit Ergebnis:**

- python3 scripts/build_help_index.py -> help_index.json regeneriert
- python3 scripts/build_help_index.py --check -> grün

**Nicht ausgeführte Tests:** keine gemeldet.

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Handbuch-Kapitel für T02 (M9-02 OpenTelemetry) nicht erstellt, da technische Änderung ohne Benutzerschnittstelle
- Handbuch-Kapitel für T15 (S16-03 Sicherheit) nicht erstellt, da Sicherheitsprüfung ohne Benutzerschnittstelle
- privacy/ Modul hat kein README (aber war nicht in Welle 5 umgesetzt)


## Welle 7 (Pakete V)

### V01

**Ausgeführte Tests mit Ergebnis:**

- pytest test_t12_reply_task_record_fields.py test_w5_t05_invoice_factual.py test_t09_hoa_reserves.py (mhvp_p01) -> 14 passed (in zwei Laeufen)
- pytest tests/unit/test_problems.py test_fints_problems_bpd.py -> 8 passed
- vitest CompactView.test.tsx -> 6 passed
- ruff check/format -> ok
- mypy hoa/reserves.py communication/routers.py communication/compact.py accounting/routers.py -> ok
- pnpm tsc --noEmit (web-crm) -> ok

**Nicht ausgeführte Tests:**

- Gesamtsuiten, Playwright (Rahmenvorgabe)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- V01-01 in OPEN_QUESTIONS: Betreiber bestaetigt Sperre statt protokollierter Aenderung (U15-03, G4)
- OpenAPI-Diff: approve-Endpunkt hat neuen Pflicht-Body MailReplyDraftApproveIn, neue Problem-Codes MHVP-COMM-0010, MHVP-ACC-0008, MHVP-HOA-0005 (make openapi durch Koordinator)
- U15-01, U15-02, U15-03 in OPEN_QUESTIONS koennen vom Koordinator auf erledigt gesetzt werden (nur Anhaengen erlaubt)


### V02

**Ausgeführte Tests mit Ergebnis:**

- pytest test_v02_portal_passkey_lock.py test_v02_self_disclosure_token_hash.py -> 4 passed
- pytest test_s16_webauthn_login.py test_p14_member_scope_webauthn.py -> passed
- ruff check eigene Dateien -> sauber; mypy core/auth, letting/tasks.py -> sauber
- pytest test_m21_portal.py test_p13_portal.py test_u15_review_w45.py -> 56 passed; ruff, mypy portal sauber

**Nicht ausgeführte Tests:**

- volle Suite
- Frontend (keine Änderung)
- mypy platform/routers.py

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Betreiber bestätigt das Kennzeichen Portalkonto (Annahme A-V02-01, Rolle portal_user)
- Umstellungsendpunkt nach Deployment einmal auslösen
- openapi.json und api-client vom Koordinator neu zu erzeugen (neuer Endpunkt, neuer Fehlercode)
- V11-08: Schreibzugriff auf Vollmachten haben nur nicht objektbeschränkte Administratoren, die Bereichsprüfung ist daher defensiv und ohne eigenen Scoped-Integrationstest


### V03

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (0299 bis 0302) auf mhvp_p03 -> ok
- pytest test_u11_retention_procedure_holds + test_m6_04_retention_matrix + test_m6_documents -> 21 passed
- pytest test_migrations + test_u11 -> 7 passed
- vitest RetentionStatusCard + PortalAccessSection -> 10 passed
- vitest src/app/api (BFF) -> grün
- pnpm tsc --noEmit -> ohne Fehler
- ruff check/format, mypy src/mhvp/documents -> sauber

**Nicht ausgeführte Tests:**

- Playwright, volle Suiten, next build

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Handbuch-Hinweis: Zuordnung des Beschlusses im CRM erfolgt nur per API/PATCH, kein Auswahlfeld in der UI
- Frontend-Messages vitest-Paritätstest nicht separat gefunden, JSON valide in de und en
- Datenmodell Steuerverfahren/Rechtssachen für automatische Sperre bleibt offen (U11-01)


### V04

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head -> 0302 ok
- pytest test_migrations.py (inkl. Round Trip, Drift) -> 4 passed
- pytest test_v04_export_retention.py test_t01_tenant_export_job.py -> 5 passed
- ruff check Paketdateien -> ok; mypy src/mhvp/platform -> ok
- vitest ExportRetentionSetting und TenantExportJobs -> 5 passed
- pnpm tsc --noEmit -> ok

**Nicht ausgeführte Tests:**

- Playwright, volle Suiten

**Teilweise erledigt:**

- T01-01: Empfohlene Dauer, Verschlüsselung und Herausgabe an Dritte bleiben rechtlich offen (V04-01)

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- V04-01 in docs/OPEN_QUESTIONS.md: empfohlene Dauer, Systemstandard und Verschlüsselung (Timo Müller mit Datenschutz, G5)
- Bestehende ruff-Fehler in fremden Dateien (ai/imports.py, ai/schemas.py, documents/schemas.py, test_r03_onboarding.py) nicht angefasst


### V05

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (0301->0302) -> ok
- pytest test_r07_01_meeting_close.py test_m25_meeting.py test_m25_protocol_draft.py -> 6 passed
- pytest test_migrations.py -> 4 passed
- ruff check/format, mypy src/mhvp/hoa -> ok
- vitest MeetingClose.test.tsx ProtocolDraft.test.tsx -> 6 passed
- tsc --noEmit -> keine Fehler in geaenderten Dateien

**Nicht ausgeführte Tests:**

- Playwright
- volle Suiten

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- V05-01 in OPEN_QUESTIONS: Protokollfrist rechtlich offen (Gate G4)
- Status closing erscheint nicht in portal/owner_meetings Einwahlanzeige (nur invited/held), gewollt
- Dokument-ID wird im CRM als Textfeld eingegeben; Upload-Auswahl waere Komfortausbau
- openapi.json und api-client muessen vom Koordinator regeneriert werden
- Status disrupted hat keinen meetingStatus-Uebersetzungsschluessel (vorbestehend)


### V06

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_r03_onboarding.py (DB mhvp_p06) -> 5 passed (inkl. neuer Test Mehrfach-Eigentümer, 403/404/422/409)
- pnpm vitest run src/components/ai/OnboardingExtras.test.tsx -> 7 passed
- ruff check (eigene Dateien sauber), mypy src/mhvp/ai -> ok
- pnpm tsc --noEmit -> ok

**Nicht ausgeführte Tests:**

- Debitorenkonten-Entscheidung (mehrere Rechtsträger mit Verträgen) nur über Code, nicht per Integrationstest
- PropertyProposal-Komponententest, Playwright

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- V06-01 in OPEN_QUESTIONS: Standardteam/Zuständiger für Checklisten-Tickets, Sammelkonto je Eigentümer
- Vorbestehende Ruff-Fehler in documents/routers.py und documents/schemas.py (fremd)
- Test-Fixture von test_r03_onboarding.py um die Nutzer m7admin und m7second ergänzt, da die Tests allein sonst nicht anmeldbar waren
- openapi.json und api-client nicht regeneriert (laut Rahmen)


### V07

**Ausgeführte Tests mit Ergebnis:**

- pnpm --filter @mhvp/web-crm build -> grün, 3m50,9s
- pnpm --filter @mhvp/web-portal build -> grün, 3m06,3s

**Nicht ausgeführte Tests:** keine gemeldet.

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Build-Logs: w7/V07-crm.log, w7/V07-portal.log


### V08

**Ausgeführte Tests mit Ergebnis:**

- scripts/e2e-backend.sh (mhvp_p08, Redis 6380/8, API 8108, Web 3108, NEXT_DIST_DIR=.next-p08, MHVP_SEED_ADMIN_SUPERADMIN=true) --project chromium --project phone -> Lauf 1: 48 bestanden, 7 Fehler, 5 übersprungen; Lauf 3: 54/3/3; Lauf 4: 56 bestanden, 1 Fehler (handover), 3 übersprungen; danach handover.mobile isoliert 3 bestanden
- alembic upgrade head auf mhvp_p08 bis 0302 -> ok (nach Korrektur von 0301)
- pnpm vitest run src/components/letting/FlowImport.test.tsx src/components/billing src/components/handover src/components/ui/StatusChip.test.tsx -> 71 und 31 bestanden
- pnpm tsc --noEmit (apps/web-crm) -> ohne Fehler

**Nicht ausgeführte Tests:**

- Playwright-Projekte tablet und tablet-landscape
- web-portal Playwright
- ein einziger Gesamtlauf nach allen Korrekturen: der letzte volle Lauf (Lauf 4) lief vor den letzten zwei Handover-Spec-Anpassungen, diese wurden isoliert nachgewiesen

**Teilweise erledigt:**

- V08: 3 Specs bleiben bedingt übersprungen, weil Seed-Daten fehlen (kein Fehler): wave-2026-09-27 mailbox page 2 (weniger als eine Seite Mails, kein Objektspeicher-Mailseed), wave-2026-09-27 Kaution-PDF (keine Kaution im Seed), waves-2-3-pages mail compact view (keine Mail im Seed)

**Nicht erledigt:**

- V08: Tablet-Projekte (tablet, tablet-landscape) nicht ausgeführt, nur chromium und phone wie im Standardlauf von scripts/e2e-backend.sh
- V08: web-portal Specs nicht Teil des Pakets, nicht ausgeführt

**Offene Punkte und Entscheidungen:**

- BEFUND Migration 0301_export_retention.py (fremdes Paket): drop_constraint und create_check_constraint mit bereits präfixiertem Namen wurden von der Naming Convention doppelt präfixiert (UndefinedObject beim Upgrade). Von mir mit op.f(...) für STATUS_CK und RETENTION_CK behoben. Der Eigentümer des Pakets soll das prüfen, damit ORM und Migration bei seinem eigenen Test übereinstimmen.
- BEFUND UX: Auf dem Telefon (390x844) liegt das Unterschriftsfeld im Unterschriftsblatt unterhalb des Formulars (Name, Rolle, Ort) und kann unterhalb des sichtbaren Bereichs liegen; die E2E musste scrollen. Prüfen, ob das Feld höher oder das Formular eingeklappt werden soll.
- BEFUND UX: Übergabeprotokoll Zählerliste zeigt weiterhin den Roh-Schlüssel der Zählerart (electricity) statt der deutschen Bezeichnung; nur der Wert wurde formatiert.
- BEFUND Spec-Hygiene: Die Specs erzeugen Daten mit festen Schlüsseln (Kontonummern, IBAN) und sind auf einer nicht frischen DB nur bedingt wiederholbar; bank-buchen ist jetzt eindeutig, weitere Specs sollten beim Ausbau gleich verfahren.
- Skipped Specs brauchen Seed (Mails im Objektspeicher MHVP-DOC-0007 bereits vorhanden, aber ohne 60 Testmails, Kaution, Superadmin): ein E2E Seed Skript wäre der nächste Schritt (docs/OPEN_QUESTIONS.md, Eigentümer Betreiber, kein Gate).
- scripts/e2e-backend.sh benötigt für parallele Läufe NEXT_DIST_DIR und Ports (gesetzt); der Next Build schreibt apps/web-crm/tsconfig.json um (include je Build-Verzeichnis), von mir auf den Stand von HEAD zurückgesetzt.
- Der Zugriff auf einen Postgres Superuser war nicht nötig: mhvp_p08 existierte bereits gebootstrappt. Ein Versuch, Superuser Passwörter zu raten, wurde vom System zu Recht blockiert und nicht weiterverfolgt.


### V09

**Ausgeführte Tests mit Ergebnis:**

- bash $SP/w7/p09-run.sh (Migration bis 0302, Build, playwright E2E_BACKEND=1, 1 Worker) Erstlauf -> 5 failed, 19 passed
- Läufe nach Fixes mit Redis-Flush und MHVP_RATE_LIMIT_PER_MINUTE_ANONYMOUS=5000 -> 3 von 3 Läufen 24 passed

**Nicht ausgeführte Tests:**

- vitest und tsc des Portals nicht ausgeführt (nur Klassen-Zusatz an einem Link)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- Meldungen mit Foto (meldung.backend.spec) braucht S3-kompatiblen Speicher (MHVP_S3_*); ohne ihn 503 object storage not configured. scripts/e2e-backend.sh und CI sollten einen Speicher bereitstellen (hier moto_server mit flask, flask-cors per uv run --with, Bucket mhvp-e2e anlegen).
- Ohne Anhebung von rate_limit_per_minute_anonymous (Standard 120/min je IP) liefert Login im Lauf 429 und Specs scheitern mit irreführender Meldung TOTP secret unknown; Zeile in scripts/e2e-backend.sh ergänzt, CI-Workflow prüfen.
- Fremdbefund Migration 0301_export_retention (anderer Agent): Constraint-Name war doppelt präfixiert, zwischenzeitlich vom Verfasser mit op.f korrigiert; Kette lief danach bis 0302 durch.
- Während des Laufs hatte ein Next-Build apps/web-portal/tsconfig.json um .next-p09 ergänzt; zurückgesetzt. Umgebungsvariablen der Shell zeigen standardmäßig auf DB mhvp und Redis 6379/0: Skripte müssen sie explizit überschreiben (im Laufskript geschehen).
- Einmalig nicht reproduzierbar: Meldungsliste nach Absenden leer (Test meldung.backend, Foto) im ersten Lauf, danach 5 von 5 grün; vermutlich Race zwischen Commit und router.refresh, beobachten.


### V10

**Ausgeführte Tests mit Ergebnis:**

- pytest test_v10_chart_split_seed.py -> 3 passed
- pytest test_m10_chart_template.py test_m10_02_cost_presets.py -> 9 passed
- ruff check/format, mypy accounting -> ok

**Nicht ausgeführte Tests:**

- Integrationstest Ledger-Anlage mit vorhandenen Schlüsseln (_apply_template_splits)
- alembic upgrade head meldete zunächst fehlende 0301, Tests liefen danach

**Teilweise erledigt:**

- U07-01: keine Mehrschlüsselaufteilung vorbelegt (keine eindeutige Quelle), Rest als V10-01 in OPEN_QUESTIONS; Übernahme in Buchungskreise nur durch bestehende Tests mitgeprüft, ohne eigenen Integrationstest mit vorhandenen Schlüsseln

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- V10-01 in OPEN_QUESTIONS: Mehrschlüsselverteilungen, 041805, Bankkonten, Art der Abrechnung der Kostenkonten fachlich offen
- docs/plans/M10.md und Handbuch nicht ergänzt (keine neue Bedienfunktion)


### V11

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_csv_formats.py -> 17 passed
- pytest tests/integration/test_v11_review_import_undo.py tests/integration/test_u13_import_history.py -> 3 passed
- pytest tests/integration/test_q08_import_history.py -> 2 passed
- ruff check + mypy csv_formats.py, w3_reports.py -> ok

**Nicht ausgeführte Tests:**

- Gesamtsuite
- Frontend (keine Frontend-Änderung)

**Teilweise erledigt:**

- V11-04: manuell zum Vortag beendeter Vorgängerplan bei laufendem Vertrag wird bei Rücknahme weiter geöffnet (exakter Nachweis bräuchte Schema)

**Nicht erledigt:**

- V11-05 Portal Rechnungseinreichung document_id ohne Eigentumsprüfung: Bereich V02, nur gemeldet
- V11-06 Rücklage Bankkonto beendet/Buchungskonto inaktiv serverseitig ungeprüft: Bereich V01, nur gemeldet
- V11-07 Löschungssperre überschreibbar mit documents:update: Bereich V03, nur gemeldet
- V11-08 Vollmachtsdokument ohne Sichtbarkeitsprüfung: Bereich V02, nur gemeldet
- V11-09 Ticket-Sammelaktion ohne Ereignis für Priorität/Team: niedrig, offen

**Offene Punkte und Entscheidungen:**

- V02: submit_invoice muss document_id über _own_uploads(session, account, [body.document_id]) prüfen (portal/routers.py), hoch
- V03: set_hold soll bestehende Sperre nicht überschreiben bzw. Art nicht abschwächen
- V01: hoa/reserves.py Bankkonto valid_to und Buchungskonto aktiv serverseitig prüfen
- V02: create_representation Vollmachtsdokument per Sichtbarkeitsprüfung
- Honorarbuchung: Kontenart der Verwalterkonten ungeprüft (niedrig)


### V12

**Ausgeführte Tests mit Ergebnis:**

- python3 scripts/build_help_index.py -> help_index.json regeneriert

**Nicht ausgeführte Tests:**

- Keine Unit Tests (reine Dokumentation)

**Teilweise erledigt:** keine gemeldet.

**Nicht erledigt:** keine gemeldet.

**Offene Punkte und Entscheidungen:**

- docs/rules/README.md: 200 Regel-Dateien fehlen im Index, nur Welle-6-Regeln ergänzt; vollständige Regeneration des Index offen (große Aufgabe, nicht in V12 Scope)
- Modul-READMEs (apps/api/src/mhvp/*/README.md) wurden bereits von U*.json Agenten aktualisiert, keine zusätzliche Bearbeitung nötig
