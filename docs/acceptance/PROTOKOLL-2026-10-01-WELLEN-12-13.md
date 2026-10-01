# Abnahmeprotokoll der Wellen 12 und 13

Stand: 01.10.2026. Grundlage: Ergebnisberichte der Pakete AA01 bis AA17 (Welle 12, Release 1.57.0) und AB01 bis AB14 (Welle 13, Release 1.58.0) der zweiten Lückenanalyse (`docs/plans/LUECKENLISTE-2026-10-01.md`, Befund GA13-59). Das Protokoll gibt die gemeldeten Testläufe und offenen Punkte unverändert wieder; es behauptet keine Abnahme und ersetzt keine fachliche Abnahme durch den Betreiber (Abschnitt 0.1 Regel 14). Die Freigabestufen G1 bis G5 bleiben geschlossen. Offene Entscheidungen sind in `docs/OPEN_QUESTIONS.md` (AA01-01 bis AB12-01) geführt.

Hinweis zur Lesart: "Ausgeführte Tests" sind die vom Paket gemeldeten Befehle mit Ergebnis. Teilläufe einzelner Testdateien sind keine Gesamtsuite. "Nicht ausgeführt" ist ausdrücklich nicht bestanden. Anhang D Bezug: aus den Berichten maschinell entnommene Fallnummern; fehlt eine Nennung, hat das Paket keinen Rechenfall aus Anhang D berührt. Der Fall D24 bleibt strikter xfail (M17-03, Entscheidung offen).

## Ergänzung KoSIT-Lauf (GA14-05, Paket AC11, 01.10.2026)

Der KoSIT-Validator 1.5.0 und die XRechnung-Konfiguration 3.0.2 (31.10.2024) wurden über den Agent-Proxy mit CA-Bundle geladen (Prüfsummen in `docs/runbooks/xrechnung-kosit.md`). Mit OpenJDK 21.0.10 lief `tests/unit/test_aa02_kosit_validator.py` lokal: 1 passed. Geprüft wurden zwei vom Generator erzeugte Dateien (regelbesteuert, Kleinunternehmer nach § 19 UStG). Beide Berichte: Szenario "EN16931 XRechnung (UBL Invoice)", Bewertung accept, "weder Fehler noch Warnungen". Einschränkung: nur diese zwei Testvarianten mit synthetischen Daten, keine Echtdaten; der CI-Job ist ohne Betreiber-Variablen weiter inaktiv (AA02-03); Pins sind aus dem Download berechnet und nicht mit der Herausgeberseite abgeglichen. Das ist ein technischer Nachweis, keine steuerliche Freigabe (P05, G1).

## Felder für die Betreiberfreigabe

| Release | Freigabe erteilt (ja/nein) | Datum (TT.MM.JJJJ) | Name |
| --- | --- | --- | --- |
| 1.57.0 (Welle 12) |  |  |  |
| 1.58.0 (Welle 13) |  |  |  |

Anmerkungen des Betreibers:


## Release 1.57.0 (Welle 12)

| Paket | erledigt | teilweise | nicht erledigt | Migration | Migration ungetestet |
| --- | --- | --- | --- | --- | --- |
| AA01 | 4 | 1 | 0 | 0303 journal_entry_note (down_revision 0302) | nein |
| AA02 | 4 | 2 | 1 | 0304 release_gate_request: opened_by/at, revoked_by/at, revoke_comment | nein |
| AA03 | 5 | 1 | 0 | 0305 message-Spalten, ticket.category_id mit Trigger | nein |
| AA04 | 2 | 2 | 0 | 0306 noop (down_revision 0305) | nein |
| AA05 | 2 | 2 | 0 | 0307 work_order.approval_workflow_id, document_template (master_templa | nein |
| AA06 | 5 | 3 | 0 | 0308 owners_meeting (ends_at, origin_meeting_id, 3 template FKs, publi | nein |
| AA07 | 1 | 1 | 0 | 0309 hoa_asset_report_provision und hoa_acquisition_release (RLS, Cons | nein |
| AA08 | 5 | 1 | 0 | 0310 Abrechnungszeitraum status/locked_at, building.energy_certificate | nein |
| AA09 | 1 | 0 | 0 | 0311 notice_board_6_2 (property_notice: category, type, audiences, doc | nein |
| AA10 | 2 | 2 | 1 | 0312 admin_fee_setting Felder, recurring_invoice_plan.auto_post (down_ | nein |
| AA11 | 3 | 2 | 0 | 0313 statement.deadline_exception_document_id (FK document RESTRICT, f | nein |
| AA12 | 2 | 3 | 0 | 0314 noop (down_revision 0313) | ja |
| AA13 | 5 | 0 | 0 | 0315 noop (down_revision 0314) | nein |
| AA14 | 5 | 3 | 0 | 0316 access_grant.document_class + Check ck_access_grant_document_clas | nein |
| AA15 | 5 | 2 | 0 | 0317 noop (down_revision 0316) | nein |
| AA16 | 2 | 3 | 0 | 0318 noop (down_revision 0317) | ja |
| AA17 | 4 | 2 | 0 | 0319 noop (down_revision 0318) | nein |

### AA01

**Befunde (gemeldet):** GA14-01: done, GA14-06: partial, GA05-01: done, GA05-02: done, GA05-03: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA14-01: JobDbReleaseGateResolver (eigene NullPool-Verbindung je Prüfung, RLS, Fehler = geschlossen) und install_job_release_gate_resolver in core/release_gates.py; Worker setzt ihn bei worker_init/worker_process_init; Test mit G1 offen/geschlossen je Mandant, B bleibt zu, G2 bleibt zu, nach Widerruf zu, banking.tasks._g1_open und release_gated
- GA05-01: checks() meldet Nummernlücken je Geschäftsjahr (generate_series) und Abweichung Zählerstand gegen höchste Nummer; Test mit manipulierter Nummer
- GA05-02: Tabelle journal_entry_note (append only Trigger, RLS, Versionskette note_key/supersedes_id), GET/POST /accounting/ledgers/{id}/entries/{id}/notes, Codes MHVP-ACC-0009/0010, CRM-Komponente EntryNotes im Journal, BFF-Allowlist
- GA05-03: checks() harte Nebenbuchinvarianten; Endpoint checks liefert subledger und subledger_differences je Debitor/Kreditor zum Stichtag as_of; Test mit Teilausgleich, nicht zugeordneter Zahlung und Storno

**Teilweise erledigt:**

- GA14-06: Register GATED_ROUTES (29 Routen) mit statischem Nachweis der Gate-Prüfung und Fangnetz für neue ungegatete Geld-/Abrechnungs-/Versandrouten (Bestandsaufnahme REVIEWED_UNGATED, Einstufung offen AA01-01); kein Laufzeitaufruf jeder Route mit 403 MHVP-GATE-0001 (bestehende Laufzeitprüfung nur in test_d50); Zwei-Mandanten-Test mit echtem Resolver in test_ga14_job_gates.py

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- Kette im Hauptbaum unvollständig (KeyError 0308, fremde Pakete); daher Kopie von alembic bis 0303 in $SP/w12/aa01api gegen mhvp_p01, fremde Modell-Drift per lokaler Hilfsrevision 9999 nur in dieser Kopie ausgeglichen
- alembic upgrade 0302 -> 0303 -> ok; compare_metadata: keine Drift für journal_entry_note
- pytest tests/integration/test_migrations.py -> übrige Tests grün, test_no_autogenerate_drift rot nur wegen fremder Modelle ohne Migration (0304 ff.), nicht journal_entry_note
- pytest test_ga05_ledger_checks.py test_m10_ledger.py test_d50_authorization.py -> 364 passed
- pytest test_m15_payments.py test_annex_d_money.py test_m13_receivables.py test_ga14_job_gates.py -> 14 passed
- pytest tests/unit/test_ga14_gate_coverage.py tests/unit/test_release_gates.py -> passed
- ruff check src tests -> nur 3 fremde Befunde in core/webhooks.py; mypy accounting, release_gates, worker -> ok
- pnpm vitest run EntryNotes.test.tsx Bookkeeping.test.tsx -> 9 passed; pnpm tsc --noEmit -> keine Fehler in geänderten Dateien

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py::test_no_autogenerate_drift gegen die vollständige Kette (Vorgänger 0304 bis 0308 fehlen im Arbeitsbaum)
- Playwright
- volle Suiten

**Offene Punkte und Entscheidungen:**

- AA01-01 (OPEN_QUESTIONS): Einstufung der Bestandsaufnahme REVIEWED_UNGATED (u. a. Buchen/Stornieren von Sätzen, Zahlungsaufträge, dispatches, SEPA-Mandate) je Route, Eigentümer Timo Müller, G1 bis G4.
- Hinweis AA05 zur Drift an journal_entry_note: gegen mhvp_p01 nach 0303 keine Drift für die Tabelle; vermutlich lief deren DB ohne 0303 (Modell vorhanden, Migration damals noch nicht angewendet). Bitte nach upgrade head erneut prüfen.
- Wenn GA14-02 (Umfang je Objekt) den DbReleaseGateResolver um Kontext erweitert, delegiert JobDbReleaseGateResolver weiter an is_open(tenant, gate) ohne Kontext.
- Nebenbuchdifferenzen erscheinen nur in der API-Antwort von checks, noch nicht im CRM oder Prüfexport.

### AA02

**Befunde (gemeldet):** GA14-02: partial, GA14-03: done, GA14-04: done, GA14-05: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA14-03: Checklisten G2 bis G4 aus 18.0 als Codes (platform/gate_checklists.py), GET /tenant/release-gates/checklists, _decide verlangt vollständige Checkliste und Nachweisdokument (MHVP-GATE-0006), docs/plans/GATE-CHECKLISTEN.md
- GA14-04: Spalten opened_by/opened_at, revoked_by/revoked_at/revoke_comment, evidence_document_id (FK document RESTRICT, Mandantenprüfung, MHVP-GATE-0007); Widerruf überschreibt die Öffnung nicht mehr; Backfill opened_* aus decided_*
- GA14-02 (technisch): strukturierter Umfang scope_property_ids, scope_legal_entity_ids, scope_functions (NULL = alle), DbReleaseGateResolver.is_open zählt nur unbegrenzte Freigaben, is_open_for(property_id, legal_entity_id, function) prüft Kontext; GateStateOut.partially_open
- GA14-05: optionaler CI-Job xrechnung-kosit (nur mit Repo-Variable und gepinnten SHA-256, continue-on-error) und überspringbarer Test tests/unit/test_aa02_kosit_validator.py

**Teilweise erledigt:**

- GA14-02: Router reichen property_id/legal_entity_id noch nicht an is_open_for durch (Granularität offen, AA02-02); core/release_gates Protocol unverändert gelassen wegen AA01
- GA14-05: Validator lokal nicht ausgeführt (kein Jar/Java-Setup), Prüfsummen und Version offen (AA02-03, P05)

**Nicht erledigt:**

- GA14-04 Anzeige in einer CRM-Gate-Übersicht: im CRM existiert keine Gate-Oberfläche, nur API

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p02, bis 0319) -> ok
- pytest tests/unit/test_aa02_gate_checklists.py -> 4 passed
- pytest tests/unit/test_aa02_kosit_validator.py -> 1 skipped (kein Validator)
- pytest test_aa02_gate_scope_evidence, test_m2_gate_superadmin, test_m2_platform, test_m27_market_readiness, test_g1_opening -> 48 passed, 1 failed (test_m2_platform::test_role_change_into_exempt_role_revokes_staff_portal_access: IntegrityError Check-Constraint bei Mitgliedsrollen, nicht Gate-bezogen, fremdes Paket)
- test_migrations::test_no_autogenerate_drift -> failed nur wegen fremdem Index ix_building_energy_certificate_document_id, release_gate_request ohne Drift
- test_migrations::test_downgrade_and_upgrade_round_trip -> failed in fremder Migration (ck_property_notice_audiences fehlt beim Downgrade)
- ruff check/format, mypy src/mhvp/platform -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- KoSIT-Validator real (kein Jar, kein Netz)
- Frontend (keine Änderung)
- openapi export (Koordinator)

**Offene Punkte und Entscheidungen:**

- AA02-01 Mindestumfang Checklisten G2 bis G4 (Betreiber)
- AA02-02 Granularität des Freigabeumfangs, Durchreichen des Objektbezugs in Routern und Jobs; AA01 könnte job resolver auf is_open_for erweitern
- AA02-03 KoSIT Version, Lizenz, SHA-256 als Repo-Variablen
- Neue Codes MHVP-GATE-0006/0007 und neue Felder erfordern OpenAPI-Export und api-client durch Koordinator
- Fremde Fehler: test_role_change_into_exempt_role_revokes_staff_portal_access, Drift-Index building, Downgrade property_notice

### AA03

**Befunde (gemeldet):** GA04-01: done, GA04-02: done, GA04-03: done, GA04-04: done, GA04-08: done, GA04-09: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-01: ticket.commented im Kommentar-Endpunkt (Payload ohne Text)
- GA04-02: bank_transaction.imported gebündelt je Importlauf und Konto (Datei- und finAPI-Import)
- GA04-03: contract.changed und contract_payment.changed zusätzlich zu den detaillierten Typen (Annahme A-AA03-01, Frage AA03-01)
- GA04-04: portal_account.activated bei Einladungseinlösung
- GA04-08: ticket.category_id auf ticket_template per Trigger, Freitext bleibt Fallback

**Teilweise erledigt:**

- GA04-09: Spalten delivered_at, read_at, provider_message_id angelegt (provider_message_id aus gmail_message_id nachgefüllt) und in der Nachrichtenliste ausgegeben; Befüllung aus Gmail-Push, Zustellstatus und Portal-Lesebestätigung fehlt; ai_classification entspricht classification/suggestion (A-AA03-02)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- test_ga04_events.py (2 Tests) -> bestanden, gegen temporär umgehängte Kette (0308 fehlte, Spalte manuell in mhvp_p03 ergänzt)
- test_a69_webhooks.py -> 4 bestanden
- ruff, mypy tickets/banking.services/contracts -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py gegen echte Kette: 0308 fehlt, und 0316 Downgrade schlägt fehl (Fremdmigration, ck_access_grant_..._document_class_scope)
- Test für bank_transaction.imported und portal_account.activated (nur Code, kein Test)

**Offene Punkte und Entscheidungen:**

- Befüllung delivered_at/read_at aus Gmail-Push, Zustellstatus, Portal-Lesebestätigung
- Tests für bank_transaction.imported und portal_account.activated ergänzen
- Migrationskette: 0308 fehlt, 0316-Downgrade defekt (Fremdpaket)
- Frage AA03-01 Vereinheitlichung der Vertragsereignistypen

### AA04

**Befunde (gemeldet):** GA04-05: partial, GA04-06: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-05: core/listparams.ListSpec (Filter, Sortierung, include, as_of mit valid_from/valid_to, 422 für jeden nicht deklarierten Query-Parameter) und Anbindung an GET /banking/transactions (filter, sort, fields), /hoa/resolutions (filter, sort, fields), /accounting/dunning-runs (filter, sort), /mail/messages (filter, fields; eigene Ordnung bleibt)
- GA04-06: ETag und If-Match (412 bei veraltetem Token) an PATCH /hoa/resolutions/{id}, ETag an GET /mail/messages/{id}, If-Match und ETag an PATCH /mail/messages/{id}

**Teilweise erledigt:**

- GA04-05: weitere Listen (übrige banking-GETs, letting, portal, metering, sla, ai, automation, immoware, handover, work orders) noch ohne ListSpec; Querschnittstest prüft nur die umgestellten Listen (LISTS im Test), kein Gesamtinventar aller GET-Listen
- GA04-06: übrige PATCH/PUT-Ressourcen (banking rules, letting, portal, automation, work orders, ai, sla, playbooks, mailboxes) noch ohne ETag; Pflicht-If-Match für Geldflüsse nicht umgesetzt (needs_decision, AA04-01)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_aa04_listspec.py -> 3 passed
- pytest tests/integration/test_aa04_listspec_etag.py (mhvp_p04, Kette bis 0312 in Scratch-Kopie, da 0313/0315 im Arbeitsbaum fehlten) -> 6 passed
- pytest test_annex_d_hoa.py test_m16_dunning.py test_m9_automation_stage2.py -> 12 passed, 1 failed (test_dunning_preview_and_locks: Job-Fehlerzählung M9-01 mit monkeypatch, betrifft nicht den geänderten Listenendpunkt, vermutlich parallele Änderung)
- ruff check/format geänderte Dateien -> ok
- mypy core/listparams + 4 Router -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py (Kette im Arbeitsbaum lückenhaft: 0313, 0315 fehlen)
- Frontend (keine Änderung)
- volle Suite

**Offene Punkte und Entscheidungen:**

- AA04-01 in OPEN_QUESTIONS: Pflicht-If-Match für Geldflüsse per Mandantenschalter, Entscheidung Timo Müller
- Restliche Listen- und Änderungsendpunkte nach demselben Muster umstellen (Folgepaket)
- Migrationskette im Arbeitsbaum hatte bei Testlauf Lücken (0313, 0315); Koordinator prüft linear
- test_m16_dunning::test_dunning_preview_and_locks schlägt fehl, Ursache außerhalb dieses Pakets prüfen

### AA05

**Befunde (gemeldet):** GA04-07: partial, GA04-10: partial, GA04-11: done, GA04-12: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-11: Tabelle generated_document (Vorlage, Version, Kontext, Empfänger, Dispatch) wird bei Vorlagenbriefen und über store_letter/record_dispatch für alle bestehenden Briefe gefüllt, GET /generated-documents mit Kanal und Nachweis
- GA04-12: Lernbeispiele werden eingebettet (Quelle ai_example, Indexjob) und im Gateway per Kosinusabstand als Few-Shot gewählt, nur mit freigegebener Einbettungsroute, sonst Reihenfolge nach Datum

**Teilweise erledigt:**

- GA04-07: Spalte work_order.approval_workflow_id (ohne FK, in POST /work-orders und Ausgabe); Entscheidung Ersatz durch Beiratsabstimmung oder Workflow-Entität offen (AA05-01)
- GA04-10: master_template_id, context_types, placeholders_used (berechnet), Kontextfilter und Kontextprüfung beim Brief; Tabelle template_block fehlt (AA05-02)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa05_templates_generated.py -> 4 passed (Endstand)
- pytest test_aa05, test_m7_ai_embeddings, test_m6_documents, test_migrations -> 26 passed, 2 failed (test_migrations: Downgrade-Rundlauf scheitert an Migration building_energy_certificate eines anderen Pakets, Drift-Test Folgefehler; alembic check zeigt Drift nur für journal_entry_note (0303, fremd), nicht für 0307)
- alembic upgrade 0307, downgrade 0306, upgrade 0307 -> ok
- ruff check und format, mypy src/mhvp/documents -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- mypy für ai und tickets nach letzter Änderung (nur documents erneut), Frontend (keine UI-Änderung), volle Suiten

**Offene Punkte und Entscheidungen:**

- AA05-01 Freigabe-Workflow vs. Beiratsabstimmung (OPEN_QUESTIONS)
- AA05-02 template_block nicht angelegt
- AA05-03 Abstandsgrenzwert für Lernbeispiele
- Keine CRM-Oberfläche für Kontextfilter und Herkunftsliste, nur API
- test_migrations scheitert derzeit an fremder Migration (building_energy_certificate Index-Drop im Downgrade) und fremdem Drift journal_entry_note

### AA06

**Befunde (gemeldet):** GA03-01: done, GA03-02: done, GA03-03: partial, GA03-04: done, GA07-01: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA03-01: Meeting.kind um repeat, continuation, partial, circular_resolution erweitert; origin_meeting_id (Pflicht bei Wiederholung/Fortsetzung, frühere Versammlung derselben GdWE), ends_at, drei Vorlagenbezüge auf document_template, public_description (Portal) und internal_description; PATCH /hoa/meetings ergänzt; CRM-Formular MeetingDetailsForm und Artauswahl beim Anlegen
- GA03-02: AgendaItem.result (accepted/rejected aus Verkündung, deferred/no_vote per PATCH /hoa/agenda/{id}, sperrt Stimmen und Verkündung), minutes_text (Protokollentwurf), voting_principle je TOP mit Grundlage (Vorrang vor Versammlung), Regel all_owners in der Auszählung; CRM AgendaResultForm und Regelauswahl
- GA03-04: Vote.channel presence/online aus Anwesenheit, circular im Umlaufverfahren; Auszählung liefert channels, Mitgliederliste vote_channels
- GA03-03: Resolution.location, court_notes, entered_at (Backfill aus created_at), Status deleted und irrelevant; PATCH mit Vermerken und Ereignis; Anzeige in ResolutionTable
- GA07-01: Prüfung Gültigkeitsende <= Beschlussdatum + 3 Jahre: Hinweis virtual_basis_term_notice, Sperre MHVP-HOA-0030 nur mit tenant_settings.hoa_virtual_basis_term_lock_enabled (Standard aus), Schalter in den Versammlungseinstellungen

**Teilweise erledigt:**

- GA03-03: void bleibt zulässig, keine Datenübernahme void zu deleted/irrelevant bis Entscheidung AA06-01
- GA07-01: Übergangsregel § 48 Abs. 6 WEG nicht umgesetzt, offene Frage AA06-02; Hinweis nur in der Antwort beim Anlegen, nicht dauerhaft in GET /meetings/{id}
- GA03-01: Wiederholung/Fortsetzung im CRM-Anlegeformular nicht wählbar (Ursprungsversammlung nur per API); Vorlagen als ID-Eingabe statt Auswahlliste; Portal-UI zeigt public_description noch nicht an (nur API-Feld)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade 0307->0308, downgrade 0308->0307, upgrade (isolierte Kette bis 0308) -> ok
- alembic upgrade head (volle Kette bis 0319) -> ok
- pytest tests/integration/test_aa06_meeting_resolution.py -> 5 passed
- pytest test_m25_02_circular, test_m25_03_meeting_invitation_virtual, test_m25_meeting, test_m25_protocol_draft, test_r07_01_meeting_close, unit test_m25_meeting_rules, test_m9_meeting_resolution_deadline -> 24 passed (nach Anpassung der erwarteten Settings-Antwort in test_m25_03)
- pytest tests/unit/test_aa06_virtual_basis_term.py -> 2 passed
- pytest tests/integration/test_migrations.py -> round trip und drift failed wegen fremder Migration 0310 (DROP INDEX ix_building_energy_certificate_document_id fehlt / Index-Drift building), nicht 0308
- ruff check (geänderte Dateien) -> ok; mypy src/mhvp/hoa -> ok
- pnpm vitest run MeetingDetailsForm, HoaForms, ResolutionTable, MeetingFormPanel, bff route -> 223 passed
- pnpm tsc --noEmit -> keine Fehler
- eslint geänderte Komponenten -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- Playwright (Vorgabe)
- volle Suiten (Vorgabe)
- web-portal (keine Portal-UI-Änderung)
- make openapi (Koordinator)

**Offene Punkte und Entscheidungen:**

- AA06-01 (OPEN_QUESTIONS): Abbildung des Status void, G4
- AA06-02 (OPEN_QUESTIONS): Dreijahresgrenze und § 48 Abs. 6 WEG, G4
- Problemcode MHVP-HOA-0030 gewählt (0006 bis 0019 frei gelassen, da AA07 parallel 0020 nutzt); Koordinator bitte Nummernlücke prüfen
- Fremddomain-Edits additiv: platform/models.py (TenantSettings.hoa_virtual_basis_term_lock_enabled), portal/owner_meetings.py (public_description, ends_at in der Portalantwort)
- Migration 0310 (fremd): downgrade bricht ab (Index ix_building_energy_certificate_document_id fehlt) und Autogenerate-Drift am Index building; test_migrations rot bis zur Korrektur
- openapi.json und api-client neu erzeugen (neuer Endpunkt PATCH /hoa/agenda/{item_id}, neue Felder)
- Portal-UI zeigt public_description noch nicht an; CRM ohne Auswahl der Ursprungsversammlung und ohne Vorlagenauswahlliste

### AA07

**Befunde (gemeldet):** GA07-02: done, GA07-03: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA07-02: Vermögensbericht (Status issued) im Eigentümerportal (Liste und PDF hinter G4), Bereitstellungsprotokoll je Eigentumsvertrag in hoa_asset_report_provision, CRM-Protokollansicht, Portal-Seite Abrechnungen

**Teilweise erledigt:**

- GA07-03: Freigabeschritt für Sondererwerbe (Antrag und Freigabe durch zweite Person, Sperre im Abrechnungspaket, Zuordnungsvorschlag als Text) umgesetzt; die Zuordnung in calc.py bleibt unverändert, weil die Rechtsregel je Erwerbsart offen ist (AA07-01); Testabdeckung für Erbfall, Zwangsversteigerung und Sondernachfolge nur über Erbfall exemplarisch

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa07_asset_provision_acquisition.py -> 2 passed
- pytest test_m24_hoa, test_m24_asset_report, test_ownership_transfer, test_q10_portal_w3 -> 11 passed (vor Constraint-Namensanpassung); test_aa07 + test_r05_positive_paths nach Anpassung -> 6 passed
- test_migrations.py -k drift -> nur Drift fremder Migration 0310 (ix_building_energy_certificate_document_id), keiner von 0309
- ruff check/format und mypy src/mhvp/hoa und portal/owner_assets.py -> sauber
- pnpm tsc --noEmit web-crm -> keine Fehler in meinen Dateien; web-portal -> nur fremde Fehler (rahmenvertraege/page.tsx, lib/locale.ts)

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py::test_downgrade_and_upgrade_round_trip scheitert an fremder Migration 0310 (Downgrade, Index building); 0309 Downgrade daher nicht separat ausgeführt
- vitest und Playwright nicht ausgeführt, keine Frontend-Komponententests ergänzt

**Offene Punkte und Entscheidungen:**

- AA07-01 und AA07-02 in OPEN_QUESTIONS angelegt (Zuordnung je Erwerbsart, Genügen des Portalabrufs; Gate G4)
- Brief-Versandpfad für Eigentümer ohne Portal nicht umgesetzt (hängt an AA07-02)
- Freigabe gilt je Abrechnungsversion (A-AA07-01)
- test_downgrade_and_upgrade_round_trip und Autogenerate-Drift fremder Migration 0310 (Index building.energy_certificate_document_id) müssen dort behoben werden
- OpenAPI und api-client nicht regeneriert (Koordinator)

### AA08

**Befunde (gemeldet):** GA02-01: done, GA02-03: done, GA02-04: done, GA02-07: partial, GA02-08: done, GA02-09: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA02-01: property_billing_period.status (open, results_created, confirmed, closed) und locked_at, POST .../billing-periods/{id}/status (ein Schritt vor/zurück, closed final, Prüfung gegen Abrechnungen bei Betriebskosten), Löschen nach closed 409, Panel mit Status und Schaltfläche, BFF-Eintrag, Codes MHVP-PROP-0006/0007
- GA02-03: building.energy_certificate_document_id (FK document, SET NULL, Index), Prüfung in POST/PUT/PATCH
- GA02-04: documents (JSONB-Liste) an maintenance_item und service_provider_relation, Mandantenprüfung, in Create/Patch
- GA02-08: Test Folgefälligkeit done_on plus Intervall, remind_before bleibt, zweiter Zyklus
- GA02-09: Test Überlappung 409, Wechsel Leerstand zu Vertrag, Historie, 403/404/422

**Teilweise erledigt:**

- GA02-07: roles, invited_at, CHECK mit allen Statuswerten, expired und locked abgeleitet beim Lesen; not_invited zugelassen aber nicht gesetzt, revoked bleibt (A-AA08-01), kein Job der expired speichert

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa08_property_status_docs.py -> 5 passed
- pytest test_aa08_portal_account.py test_a86_portal_accounts.py test_t13_sd_access_protocol.py test_p16_w2.py test_property_masterdata_c2.py test_migrations.py (Lauf vor Indexkorrektur) -> 26 passed
- pytest test_aa08_portal_account.py (nach Korrektur der Fixture-Importe) -> 3 passed im Lauf mit test_migrations (5 passed gesamt)
- pytest test_migrations.py -> 3 passed, 1 failed (test_no_autogenerate_drift: nur hoa_acquisition_release Unique aus Migration 0309, nicht AA08)
- pnpm vitest BillingPeriodsPanel.test.tsx MasterData.test.tsx PortalAccessSection.test.tsx -> alle grün
- pnpm tsc --noEmit -> ohne Fehler
- ruff check/format auf geänderten Dateien -> sauber
- mypy src/mhvp/properties src/mhvp/portal -> 2 Fehler nur in portal/notice_routers.py (fremdes Paket)

**Nicht ausgeführte Tests (nicht bestanden):**

- Playwright, volle Suite, next build (Vorgabe)

**Offene Punkte und Entscheidungen:**

- AA08-01 (OPEN_QUESTIONS): Wiederöffnung abgeschlossener Zeiträume und Verbindung mit Periodensperre P06-02
- A-AA08-01/02 (ASSUMPTIONS): Statuswerte Portalzugang und Prüfumfang des Periodenwechsels nur bei Betriebskosten
- test_no_autogenerate_drift schlägt wegen hoa_acquisition_release (Migration 0309, anderes Paket) fehl: UniqueConstraint Modell und Migration weichen ab
- mypy-Fehler in portal/notice_routers.py (arg-type _audiences) aus fremdem Paket
- Kein Job setzt expired dauerhaft; Anzeige ist abgeleitet
- Dokumentverweise haben noch keine Auswahl im Formular der Oberfläche (nur API)
- openapi.json und api-client nicht regeneriert (Vorgabe)

### AA09

**Befunde (gemeldet):** GA02-02: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA02-02: Schwarzes Brett nach 6.2: category (Katalog notice_category), type (neutral, info, warning, danger, CHECK), audiences als Liste (tenant, owner, provider; Altwert audience weiter akzeptiert), document_ids als Mehrfachanhänge mit Sichtbarkeitsprüfung je Zielgruppe, Tabelle notice_board_read mit idempotenter Lesebestätigung (POST /portal/notices/{id}/read), Lesequote im CRM (read_count, recipient_count, GET /notices/{id}/reads), Portalanzeige mit farbiger Stufe, Mehrfachdownload und Bestätigungsknopf, Dienstleister sehen Aushänge zu Objekten mit Auftrag

**Teilweise erledigt:**

- keine gemeldet

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_ga02_02_notice_board.py test_m21_notices.py (-k notice) in temporärer Kette 0001-0315 (Stubs für 0308, 0313-0315 nur im Scratchpad) -> 4 passed
- pytest test_r08_property_scope_domains.py -k scope/notice -> passed (6 passed gesamt mit Migrationstests)
- Migration 0311 isoliert (Kette bis 0302 + 0311) upgrade, downgrade 0302, upgrade -> ok
- test_migrations.py::test_no_autogenerate_drift -> Drift nur durch fremde, noch nicht geschriebene Migrationen (Energieausweis, Versammlung, Abrechnung), keine Abweichung bei property_notice/notice_board_read
- uv run mypy src/mhvp/portal -> sauber
- uv run ruff check/format Portal, Test, Migration -> sauber
- pnpm vitest PropertyNotices.test.tsx (web-crm) -> 6 passed
- pnpm vitest NoticeList, StartTiles, Accessibility.axe (web-portal) -> 31 passed
- pnpm tsc --noEmit web-crm -> keine Fehler; web-portal ohne Notice-Fehler
- Rückmeldung AA02 geprüft: 0311 nutzt nun kurze CHECK-Namen (type, audiences, Namenskonvention ergibt ck_property_notice_type und ck_property_notice_audiences), Modell identisch; upgrade, downgrade 0302, upgrade, downgrade 0302 auf frischer Kette bis 0302 plus 0311 fehlerfrei (Drop Constraint vor Spaltenänderung, RLS vor drop_table). Der frühere Fehler kam von doppelt präfixierten Namen der ersten Fassung.

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py::test_downgrade_and_upgrade_round_trip gegen die Gesamtkette: scheitert an der Downgrade-Funktion von 0316 (Constraint-Name ck_access_grant_ck_access_grant_document_class_scope doppelt präfixiert), fremdes Paket
- Gesamtkette alembic upgrade head im Repo: Lücken 0308, 0313-0315 noch nicht geschrieben
- Playwright, next build, volle Suiten (Vorgabe)

**Offene Punkte und Entscheidungen:**

- Migration 0311 hängt an 0310 (vorhanden); die Gesamtkette im Repo hat noch Lücken (0308, 0313 bis 0315), Test daher in temporärer Kette im Scratchpad.
- Fehler in Migration 0316 (fremdes Paket): downgrade nutzt doppelt präfixierten Constraint-Namen; Hinweis: Bei CHECK-Constraints in Migrationen kurze Namen verwenden (Namenskonvention präfixiert), 0311 tut das.
- Dokumente werden im CRM als Dokument-IDs (kommagetrennt) erfasst, eine Auswahl aus der Objektakte wäre ein Komfortschritt.
- Altspalten audience und document_id sind entfernt; API liefert beide Altwerte weiter als abgeleitete Felder (audience: all, tenant, owner, custom; document_id: erste Anlage).
- Recipient-Zählung der Lesequote berücksichtigt aktive Freigaben (Einheit, GdWE) und Dienstleister mit Auftrag zum heutigen Tag; Zugriff über Vollmacht oder Beirat ist nicht gesondert gezählt.
- Rundlauf von 0311 wurde ohne Beispieldaten in property_notice geprüft (Datenumsetzung audience zu audiences und document_id zu document_ids per einfachem UPDATE); im Gesamtlauf test_downgrade_and_upgrade_round_trip bleibt 0316 (fremd) der Blocker.

### AA10

**Befunde (gemeldet):** GA02-05: partial, GA03-06: done, GA03-07: partial, GA03-09: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** D58. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA03-06: admin_fee_setting um manager_contact_id, termination_date, due_day_rule, due_day, account_id, sev_fee_amount erweitert (Migration 0312, Schema, POST/PATCH/GET, Fälligkeit in Rechnungsausstellung, Kündigungsdatum begrenzt Lauf, SE-Betrag je Einheit)
- GA03-09: ADR 0020 Formatversionen mit Pin- und Kompatibilitätstest der pain-Versionen (tests/unit/test_format_versions_pin.py)

**Teilweise erledigt:**

- GA02-05: Standard-Bankregel (proposed, Priorität 900, idempotent) wird beim Anlegen des Dienstleisterverhältnisses erzeugt; Integrationstest und Oberflächenhinweis nicht erstellt
- GA03-07: auto_post am Plan (Standard aus, nur mit auto_posting_enabled setzbar, bucht nichts, OPEN_QUESTIONS AA10-01); Integrationstest und UI nicht erstellt

**Nicht erledigt:**

- GA03-06: sev_fee_recipient und vat_option bewusst nicht umgesetzt (D58: Partei nie Zahlungsempfänger; vat_percent vorhanden)

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_format_versions_pin.py test_aa10_fee_plan.py test_pain001_versions.py test_pain008_versions.py -> 29 passed, danach test_aa10_fee_plan.py 8 passed
- ruff check/format auf geänderte Dateien -> sauber
- mypy src/mhvp/accounting src/mhvp/properties/routers.py -> Success

**Nicht ausgeführte Tests (nicht bestanden):**

- Integrationstests (RLS 404, Leserecht 403, Validierung 422) für admin-fees Felder, auto_post, Standard-Bankregel: nicht geschrieben bzw. nicht ausgeführt, weil Bash nach einem abgelehnten DB-Reset gesperrt wurde
- tests/integration/test_migrations.py
- Frontend-Tests (keine UI-Änderung)

**Offene Punkte und Entscheidungen:**

- AA10-01 bis AA10-03 in docs/OPEN_QUESTIONS.md
- Bash war nach einem abgelehnten DROP SCHEMA auf mhvp_p10 gesperrt; die DB mhvp_p10 steht auf 0319 mit Stub-Inhalt für 0308, 0313, 0314, 0315 und muss vor Integrationstests neu aufgebaut werden
- Integrationstests und CRM-Oberfläche für Honorarfelder, auto_post und Standardregel fehlen
- docs/handbuch und docs/plans Statuszeile nicht ergänzt

### AA11

**Befunde (gemeldet):** GA06-01: done, GA06-02: partial, GA06-03: partial, GA06-04: done, GA03-08: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA06-01: Eigentumsverträge mit Beginn, Ende oder Betragswechsel im Monat werden auch bei receivable_rules.enabled nicht tageweise berechnet, sondern als manueller Posten OWNERSHIP_CHANGE ausgewiesen; Integrationstest Eigentümerwechsel zum 15.03.; Regel M13-01 korrigiert
- GA06-04: Statement.deadline_exception_document_id/_set_by/_set_at (Migration 0313); Nachforderung nach Fristablauf nur mit Grund UND Nachweisdokument (deadline_exception_effective in services.py und results.py); Setzen protokolliert (Ereignis statement.deadline_exception_set); CRM-Abschnitt DeadlineExceptionPanel in der Abrechnungsansicht
- GA03-08: Belegliste der gebuchten Ausgaben im Snapshot (results.receipts, Hinweis RECEIPT_MISSING), Option attach_receipts (Anlage und PATCH /billing/owner-statements/{id}/options), PDF-Ausgabe mit angehängten PDF-Belegen und Schlussseite der fehlenden Belege, CRM-Schalter und Block Belegmappe

**Teilweise erledigt:**

- GA06-02: Informationsblatt als eigene PDF-Ausgabe (POST /statements/{id}/info-sheet/preview) und im Bündel (include_info_sheet) umgesetzt; Texte zu Belegeinsicht und Einwendungen bleiben Platzhalter bis zur Freigabe durch den Betreiber (AA11-01); kein Ablegen als Dokument
- GA06-03: Anschreiben (DIN-5008-Brief) war bereits vorhanden; § 35a-Block übernimmt die belegten Lohnanteile der WEG-Einzelabrechnung für SEV-Eigentümer als Information in Snapshot, PDF und CRM; für Mietverwaltung keine freigegebene Quelle, Mustertext mit Steuerberatung offen (AA11-02)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p11) -> ok; alembic downgrade 0312 und upgrade head -> ok
- pytest tests/integration/test_migrations.py -> 2 failed wegen fremder Migration (ix_building_energy_certificate_document_id, Drift und Round-Trip, nicht AA11); eigene Tabellen ohne Drift
- pytest tests/integration/test_m17_results.py -k result_entries -> 1 passed
- pytest tests/integration/test_m17_owner_statement.py -> 2 passed
- pytest tests/integration/test_m17_operating_costs.py -k a07 -> 1 passed
- pytest tests/integration/test_m13_receivable_rules.py -> alle passed (5); test_m13_receivables.py::test_receivable_run -> passed
- pytest tests/unit/test_m17_owner_statement_calc.py tests/unit/test_aa11_owner_statement_info_sheet.py -> 11 passed
- ruff check und format (billing, receivables, Tests, Migration) -> ok; mypy src/mhvp/billing src/mhvp/accounting/receivables.py -> ok
- vitest DeadlineExceptionPanel, StatementLettersPanel, OwnerStatementPanel -> 9 passed; tsc --noEmit (web-crm) -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- Übrige Tests von test_m17_results.py und test_m13_receivables.py (nur die betroffenen Tests einzeln gelaufen)
- Playwright, volle Suiten (Vorgabe)
- OpenAPI-Export (nicht erlaubt, Koordinator)

**Offene Punkte und Entscheidungen:**

- AA11-01 (G3): Texte des Informationsblatts durch Betreiber mit Rechtsanwalt freigeben; danach als Mandanteneinstellung hinterlegen (info_sheet.build nimmt texts bereits an)
- AA11-02 (G3): § 35a für Mietverwaltung und Mustertext Anschreiben mit Steuerberatung entscheiden
- AA11-03 (G1): eigene WEG-Regel für den Eigentümerwechsel in der Sollstellung
- Fristausnahme: keine Prüfung durch zweite Person umgesetzt (Befund erwähnt sie, Vorschlag nicht); CRM erfasst Nachweis per Dokument-ID statt Auswahldialog
- test_migrations.py scheitert an fremder Migration (Index ix_building_energy_certificate_document_id, vermutlich 0310), nicht AA11
- OpenAPI und api-client neu erzeugen (neue Felder und Endpunkte: info-sheet/preview, owner-statements/{id}/options, attach_receipts, deadline_exception_*)

### AA12

**Befunde (gemeldet):** GA08-01: partial, GA08-02: partial, GA08-03: done, GA08-05: partial, GA08-07: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA08-03: H05 CO2KostAufG 5a bis 5d als Entwurfseinträge (2028, 2029) im Regelregister mit Hinweistext
- GA08-07: Block E-Rechnung (Profil, Prüfer, Version, Ergebnis, Meldungen) im CRM-Belegeingang mit Test

**Teilweise erledigt:**

- GA08-01: Prüfbefund und Steuerwarnung an der Reverse-Charge-Kennzeichnung (Beleg), keine Zeilenkennzeichnung, keine verbindliche Sperre/zweite Person (Fallkatalog offen, AA12-01)
- GA08-02: Prüfpunkte HeizkostenV 5 und 12 als Entwurf im Register; keine objektbezogene Tabelle, keine Fälligkeitsliste im CRM (AA12-02)
- GA08-05: Registerversion nach Abrechnungsbeginn gewählt (select_version) und im Snapshot festgehalten; Berechnung weiter an Codetabelle gebunden, keine CRM-Registerseite (AA12-04)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_aa12_rule_register.py tests/unit/test_w2_p03_checks.py -> 9 passed
- pnpm vitest run ReceiptIntake.test.tsx -> 14 passed
- pnpm tsc --noEmit -> ohne Fehler
- ruff check/format auf geänderten Dateien, mypy accounting/rule_register.py und billing/services.py -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_aa12_rule_checkpoints.py (Kette bricht: 0313 fehlt noch, alembic upgrade KeyError 0313)
- bestehende Integrationstests Abrechnung/Rechnungen (gleicher Grund)

**Offene Punkte und Entscheidungen:**

- AA12-01 bis AA12-04 in docs/OPEN_QUESTIONS.md
- Integrationstest nach Existenz von 0313 ausführen
- CRM-Registerseite und Fälligkeitsliste der Prüfpunkte nicht umgesetzt
- RuleVersion-Einträge erfordern aufsteigende Wirksamkeitsdaten; Prüfpunkte HeizkostenV nutzen das Anlegedatum

### AA13

**Befunde (gemeldet):** GA10-01: done, GA10-02: done, GA10-03: partial, GA10-04: done, GA10-05: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA10-01: match_units, match_contracts (am Dokumentdatum gültig), IBAN per Fingerabdruck und Kundennummer in match_contacts; unit_id/contract_id im Vorschlag und beim Bestätigen als DocumentLink
- GA10-02: intake_followup.suggest (Rechnung, Schadensfoto, Vertrag, Protokoll) als Vorschläge in final.followups, Bestätigung per POST followups/{kind}/confirm verknüpft nur Ticket oder Vertrag
- GA10-03: Direktablage hinter Mandantenschalter document_intake_auto_file (Standard aus), nur Objektverknüpfung, Meldung final.auto_filed, Rücknahme revert-auto; Entscheidung AA13-01 offen
- GA10-04: Protokoll um get, search, list_changes erweitert; Paperless- und Drive-Adapter angeglichen; MinioStore-Adapter über BlobStore
- GA10-05: Rolle je Zeile und optionale Feldübernahme (merge_fields) in ContactProposal und apply_contacts

**Teilweise erledigt:**

- keine gemeldet

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p13) -> ok bis 0319
- pytest test_aa13_intake_match.py test_m6_process_inbox.py test_aa13_document_store.py -> 7 passed
- pytest test_m6_dms_delete_and_inbox.py -> passed
- pnpm vitest run ContactProposal.test.tsx -> 4 passed
- ruff check eigene Dateien -> ok
- mypy documents ai -> nur 2 vorhandene Fehler in letters.py und routers.py (fremd)
- pnpm tsc --noEmit -> nur Fehler in TenantDefaultsAdmin.test.tsx (fremd)

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_migrations.py
- Playwright, volle Suiten

**Offene Punkte und Entscheidungen:**

- AA13-01 (OPEN_QUESTIONS): Freigabe und Schwelle der Direktablage, Abweichung von Regel 0.1.6 bis zur Entscheidung
- BFF-Allowlist und CRM-Oberfläche für intake-proposals (accept, followups/confirm, revert-auto) fehlen weiterhin, kein bestehender Verbraucher; Schalter document_intake_auto_file hat noch keinen Settings-Endpunkt (Setzen nur über TenantSettings.sources)
- OpenAPI und api-client müssen zentral neu erzeugt werden (ContactChoice.role/merge_fields, neue Endpunkte); ContactProposal weitet den Typ lokal
- Paperless list_changes erkennt keine Löschungen; MinioStore.search liefert leer
- Konfidenz der Einheit/Vertrag fließt nicht in die Gesamtkonfidenz ein (bewusst, bestehende Tests)

### AA14

**Befunde (gemeldet):** GA03-05: done, GA11-01: partial, GA11-02: partial, GA11-04: partial, GA11-05: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA03-05: access_grant scope_type document_class mit Spalte document_class, Auswertung in visible_documents, Endpunkte GET/POST document-class-grants, Migration 0316
- GA11-05: Zugriffspfadprotokoll-Test (Liste, Detail, Download, Sammel-Download, Suche, Export, CRM-API, Datenschutz, KI-Scope und KI-Input) vor und nach Freigabe, abgelaufene Freigabe
- GA11-01: Sprachwahl (Cookie, Accept-Language, Fallback de), LanguageSwitch im Kopf, Schlüsselgleichheitstest de/en, weitere Sprachen nur per Datei
- GA11-02: 20 Elementtypen (address, location, signature, consent, amount, divider ergänzt), Backend, Portal-Rendering, CRM-Baukasten
- GA11-04: Rahmenverträge und Verfügbarkeit des Dienstleisters lesend im Portal (Seite /rahmenvertraege), Verwaltung erfasst Zeitfenster, Tabelle provider_availability

**Teilweise erledigt:**

- GA11-01: Sprache nicht am PortalAccount gespeichert, nur Cookie (A-AA14-02); keine Sprachwahl auf der Anmeldeseite
- GA11-02: Typenliste der 20 Typen nicht in der Spezifikation belegt, sechs Typen abgeleitet (A-AA14-01, AA14-01)
- GA11-04: Bewertungen nicht im Portal angezeigt (Entscheidung AA14-02); Verfügbarkeit wird nur von der Verwaltung gepflegt, keine CRM-Oberfläche dafür (nur API)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa14_access_paths.py -> 2 passed
- pytest test_p13_portal.py test_m21_portal.py test_t13_sd_access_protocol.py -> 55 passed
- pytest unit/test_p13_portal_forms.py -> 14 passed
- alembic upgrade/downgrade 0315/upgrade -> ok
- pytest test_migrations.py -> round trip ok, test_no_autogenerate_drift FAILED wegen fremder Tabelle hoa_acquisition_release (UniqueConstraint, nicht AA14)
- web-portal vitest locale, shell, ProviderInfo, PortalForms -> passed
- web-crm vitest PortalFormsAdmin -> 4 passed
- web-portal pnpm tsc --noEmit -> ohne Fehler
- ruff check/format auf eigenen Dateien -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- web-crm tsc
- volle Suiten
- Playwright

**Offene Punkte und Entscheidungen:**

- AA14-01 bis AA14-03 in OPEN_QUESTIONS.md
- openapi.json und api-client müssen neu erzeugt werden (neue Endpunkte provider-availability, document-class-grants, provider/*)
- test_no_autogenerate_drift schlägt wegen hoa_acquisition_release (anderes Paket) fehl
- ruff format auf src/mhvp/portal hat versehentlich notice_routers.py, notices.py, owner_meetings.py mit formatiert (nur Formatierung, fremde Änderungen unberührt)
- Freigaben document_class sind nicht hinter G5 geschaltet (reine Konfiguration, Portal selbst bereits vorhanden)
- CRM-Oberfläche für Verfügbarkeit und Klassenfreigabe fehlt (nur API)

### AA15

**Befunde (gemeldet):** GA12-01: done, GA12-02: done, GA12-03: done, GA12-04: partial, GA12-05: done, GA12-06: partial, GA12-07: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA12-01: job_allowed in documents.process_inbox, geplantem Abstimmungsbericht und Zahllauf Vorschau; payments-payment-run-preview im JOB_CATALOG, ops-backup-verify (plattformweit) entfernt; Tests je Job
- GA12-02: Tabelle Standardjobs (Schalter, Uhrzeit HH:MM) in /einstellungen/automatisierung (JobSchedulesAdmin), Komponententest
- GA12-03: Schalter Testmodus im Regelformular, Kennzeichnung in der Regelliste, Ergebnisfilter im Protokoll, dry_run neutral statt Fehler dargestellt, Komponententest
- GA12-05: docs/runbooks/incident.md (Klassen, Erkennung, Eindämmung, Beweissicherung, Meldepflichten allgemein mit Fristen zu verifizieren, Kommunikation, Protokollvorlage)
- GA12-07: test_ga12_perf.py (Objekt, Vertrag, Ticket, P95), Workflow .github/workflows/perf.yml (wöchentlich und manuell, MHVP_PERF=1), Runbook leistungsmessung.md ergänzt; gemessen p95 48/96/125 ms

**Teilweise erledigt:**

- GA12-04: make seed-demo und mhvp.platform.demo_seed vorhanden und getestet (3 Objekte, 40 Einheiten, 60 Kontakte, 36 Entwürfe, 200 Umsätze, nichts gebucht, nur dev/test/staging); Entscheidung ob Demo-Mandant gewünscht und Kennzeichen demo (Schema) offen: AA15-01
- GA12-06: Tests für Sommerzeit (29.03. und 25.10.2026), Beat-Einträge, Wiederholung und parallelen Lauf von Zahllauf Vorschau, Mahnlauf, Digest, Fristen, Erinnerungen; für Verbrauchsinformation und Dokumenteneingang nur Schalter, kein Parallellauftest. Fix in in_window (Herbst: Fenster zweimal) und Tageslauf-Wächter für Mahnlauf und Zahllauf

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_ga12_jobs.py test_ga12_demo_seed.py test_p21_core.py test_m16_dunning.py test_m15_payment_run.py (DB mhvp_p15) -> erster Lauf 33 passed, 2 failed (Wächter vs. m16 Test, Testfilter), danach angepasst; test_ga12_jobs.py + test_m16_dunning.py -> 24 passed
- MHVP_PERF=1 pytest test_ga12_perf.py -> 1 passed
- alembic upgrade head (0316 -> 0317 -> 0319) -> ok
- pnpm vitest run AutomationAdmin JobSchedulesAdmin -> 12 passed (bei Last einmal 5s Timeout, mit --testTimeout=30000 grün)
- pnpm tsc --noEmit -> keine Fehler; scripts/check_i18n.py -> OK
- ruff check/format und mypy auf geänderte Module -> grün

**Nicht ausgeführte Tests (nicht bestanden):**

- volle Suiten, Playwright, make seed-demo gegen laufende API per httpx (nur über TestClient getestet), perf.yml in GitHub Actions, check_i18n_usage meldet 1 fremden Befund (DmsSettings.folderSchemeHint)

**Offene Punkte und Entscheidungen:**

- AA15-01 (Betreiber): Demo-Mandant gewünscht, Kennzeichen demo im Schema, Einsatz in Staging
- AA15-02 (Betreiber, Rechtsanwalt): Ansprechpartner und rechtliche Prüfung von incident.md, Meldefristen zu verifizieren
- GA12-06: kein Parallellauftest für Verbrauchsinformation (Tag 3 Wächter) und Dokumenteneingang; Sollstellungslauf war bereits getestet
- test_m16_dunning.py (Domäne accounting) angepasst: zweiter geplanter Lauf am selben Tag wird jetzt übersprungen, Fehlerlauf-Test nutzt Folgetag
- Fremde ruff-Befunde in core/webhooks.py (F601, E501) und portal/notice_routers.py (E501) nicht von AA15
- Version, CHANGELOG und changelog.ts nicht angefasst (Koordinator)

### AA16

**Befunde (gemeldet):** GA09-01: partial, GA09-02: partial, GA09-03: done, GA09-04: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA09-03: Entscheidung Hub-Parser verbleiben bis zur Ablösung im Hub als Abschnitt 8 in immoware-hub.md dokumentiert, Bestätigung als AA16-02 offen
- GA09-01: Writer write_a_records (Satzart A, nur belegte Felder) mit Roundtrip-Test gegen den Parser, 12 Unit-Tests grün

**Teilweise erledigt:**

- GA09-01: nur A-Satz geschrieben, L und M nicht belegt für Schreibpfad, Bedarf der Anbieter offen (AA16-01)
- GA09-02: Übersichtstabelle je Bestandstool (Zweck, Schnittstelle, Status, offene Punkte) in docs/integrations/README.md; mueller-flow.md und uebergabeprotokoll.md sowie Wissensdatenbank-Nachweis hängen an V1 (AA16-03)
- GA09-04: Integrationstest test_ga09_smart_einzug_contact_updated.py geschrieben (Owner-Kontakt, Fehlzustellung, Neuzustellung, Signatur, Idempotency-Key, keine Klardaten), aber nicht ausgeführt, weil die Migrationskette unvollständig ist (0308, 0313 bis 0315 fehlen noch)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_m40_metering_heiwako.py -> 12 passed
- ruff check/format und mypy src/mhvp/metering -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_ga09_smart_einzug_contact_updated.py (Kette 0308, 0313 bis 0315 fehlt, alembic upgrade head scheitert)
- tests/integration/test_migrations.py

**Offene Punkte und Entscheidungen:**

- AA16-01 HeiWaKo Stammdatenformat der Anbieter
- AA16-02 Bestätigung Hub-Parser
- AA16-03 Anhang-B-Läufe und Wissensdatenbank-Nachweis
- Integrationstest nach Vollständigkeit der Kette ausführen, Feldnamen der Deliveries-Antwort (status, attempts, id) und Status pending nach Fehlversuch dabei prüfen

### AA17

**Befunde (gemeldet):** GA01-06: done, GA01-07: partial, GA01-08: done, GA01-09: done, GA01-10: partial, GA01-12: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA01-06: Playwright-Spec e2e/core-paths-ga01.backend.spec.ts (Objekt-Formular, Vertragsformular, Dokument-Upload), per --list geprüft, nicht ausgeführt
- GA01-08: GET/PUT /tenant/delivery-default, Vorbelegung in communication/dispatch.py, CRM-Seite einstellungen/nummernkreise
- GA01-09: Ordnerschema folder_scheme (Validierung, Rendering, Direktablage, PUT-Validierung, CRM-Feld in DMS-Maske); Paperless-URL/Token und Drive-Konto waren vorhanden
- GA01-12: /platform/oidc-clients (Liste, Anlage, Secret erneuern, aktivieren/deaktivieren) und CRM-Seite plattform/oidc-clients

**Teilweise erledigt:**

- GA01-07: Konfiguration, Vorschau, Validierung, Standard wie heute, CRM-Maske; angewendet nur bei Vertragsnummern, Rechnung gesperrt (AA17-01), Objekt/Beleg/Ticket Erzeugung unverändert (AA17-02)
- GA01-10: Domains hinzufügen/entfernen/auflisten, CNAME-Hinweis, Mandantenstatus PATCH, CRM-Seite plattform/domains; keine DNS-Prüfung, Sperre wird in der Anmeldung nicht ausgewertet (AA17-03); kein Ändern des Zwecks einer bestehenden Domain (Entfernen und neu anlegen)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head auf mhvp_p17 (0318 -> 0319) -> ok
- pytest tests/unit/test_aa17_formats.py tests/integration/test_aa17_tenant_admin.py tests/integration/test_m30_oidc_clients.py -> 21 passed
- ruff check/mypy auf neue und geänderte Dateien -> sauber (mypy: nur fremde Fehler in platform/routers.py GATE_*)
- pnpm vitest run TenantDefaultsAdmin.test.tsx und src/components/documents -> grün
- pnpm tsc --noEmit -> nur fremder Fehler in PropertyNotices.test.tsx
- playwright test e2e/core-paths-ga01.backend.spec.ts --list -> 3 Tests gelistet

**Nicht ausgeführte Tests (nicht bestanden):**

- Playwright-Specs (nur --list, Vorgabe)
- Test der konfigurierten Vertragsnummer in contracts/services.contract_number und des Mandantenstandards in dispatch (kein eigener Integrationstest)
- Seitentests der neuen CRM-Seiten domains und oidc-clients (nur tsc)

**Offene Punkte und Entscheidungen:**

- AA17-01 Rechnungsnummernkreis (G1, Steuerberater)
- AA17-02 Objekt-/Beleg-/Ticketnummern über Konfiguration formatieren
- AA17-03 DNS-Prüfung der Kundendomain und Auswertung des Mandantenstatus suspended in der Anmeldung
- Playwright-Selektoren der neuen Spec ungeprüft (nicht ausgeführt)
- Frage an Koordinator: Platform-Audit nutzt Logger-Warnung (wie platform_settings), kein DomainEvent, da ohne Mandantenkontext

## Release 1.58.0 (Welle 13)

| Paket | erledigt | teilweise | nicht erledigt | Migration | Migration ungetestet |
| --- | --- | --- | --- | --- | --- |
| AB01 | 3 | 0 | 0 | 0320 ab01_noop (down_revision 0319) | nein |
| AB02 | 2 | 1 | 0 | 0321 noop (down_revision 0320) | nein |
| AB03 | 2 | 1 | 0 | 0322 noop (down_revision 0321) | nein |
| AB04 | 6 | 2 | 0 | 0323 noop (down_revision 0322) | nein |
| AB05 | 1 | 2 | 0 | 0324 noop (down_revision 0323) | nein |
| AB06 | 3 | 2 | 0 | 0325 noop (down_revision 0324) | ja |
| AB07 | 1 | 3 | 0 | 0326 noop (down_revision 0325), kein Schemabedarf: Verknüpfung über be | nein |
| AB08 | 1 | 0 | 0 | 0327 noop (down_revision 0326) | nein |
| AB09 | 5 | 0 | 0 | 0328 noop (down_revision 0327) | ja |
| AB10 | 2 | 1 | 0 | 0329 noop (down_revision 0328) | ja |
| AB11 | 2 | 1 | 1 | 0330 noop (down_revision 0329) | nein |
| AB12 | 2 | 2 | 0 | 0331 portal_account.locale String(8) nullable, down_revision 0330; upg | nein |
| AB13 | 4 | 2 | 0 | 0332 platform_audit_event (down_revision 0331) | nein |
| AB14 | 3 | 2 | 0 | 0333 noop (down_revision 0332) | ja |

### AB01

**Befunde (gemeldet):** GA14-06: done, GA05-03: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA14-06: tests/integration/test_ab01_gate_runtime.py ruft jede Route aus GATED_ROUTES (29) als tenant_admin einer eigenen Testwelt (Präfix ab01) mit geschlossenem Gate auf; 22 Routen liefern 403 MHVP-GATE-0001 mit dem registrierten Gate (gültige Bodies wählen den gegateten Zweig: target issued, action send, channel portal); 7 Routen mit Gate erst nach Datensatz oder Bedingung in PRECONDITION_FIRST mit Grund und Nachweis ohne Wirkung (404 bzw. auto-post posted 0, g1-opening/request ist der Öffnungsantrag selbst, 201 requested); REVIEWED_UNGATED nicht berührt
- Nebenbuchdifferenzen CRM: Komponente SubledgerCheck (Debitoren und Kreditoren getrennt, Stichtag, Differenzen hervorgehoben, Zusammenfassung) auf Buchhaltung, Auswertungen, Daten aus GET checks?as_of=Stichtag (serverseitig, keine BFF-Änderung nötig); Vitest
- Nebenbuchdifferenzen Prüfexport: ZIP des Prüfexports enthält nebenbuchabgleich.csv (Stichtag = Zeitraumende, Saldo Hauptbuch, Offene Posten, Differenz, im Index mit SHA-256); Assertion in test_m18_audit_export

**Teilweise erledigt:**

- keine gemeldet

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- Hauptbaum-Kette durch fremde Lücken (0321 ff., KeyError 0330) nicht ladbar; daher Kopie $SP/w13/ab01api mit alembic bis 0320 gegen mhvp_p01: alembic upgrade 0318 -> 0319 -> 0320 ok
- pytest tests/integration/test_ab01_gate_runtime.py -> 30 passed
- pytest tests/integration/test_m18_audit_export.py tests/unit/test_audit_export_csv.py -> 5 passed
- pytest test_m18_tax_advisor_scope.py test_p10_reports.py test_m12_automation_levels.py test_ga05_ledger_checks.py -> 17 passed, 1 failed (fremd: /tenant/events lehnt Parameter limit ab, Listspec eines anderen Pakets, nicht Buchhaltung)
- pytest tests/unit/test_ga14_gate_coverage.py -> passed
- ruff check geänderte Dateien -> ok (src/mhvp/accounting: 1 fremder E501 in creditor_routers.py:93); mypy src/mhvp/accounting -> ok
- pnpm vitest run SubledgerCheck.test.tsx -> 2 passed; pnpm tsc --noEmit -> keine Fehler in geänderten Dateien

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py gegen die vollständige Kette (0321 ff. im Arbeitsbaum unvollständig)
- Playwright
- volle Suiten

**Offene Punkte und Entscheidungen:**

- Laufzeitnachweis mit vorbereitetem Datensatz fehlt für 7 Routen in PRECONDITION_FIRST (switch-requests anlegen/approve/reject, receivable-runs post mit Regelpositionen, rent-invoices und credit-note, settlement-proposal/confirm, postal/jobs mit Mahnfall über externen Dienst); dort greift das Gate erst nach Lookup bzw. Bedingung.
- GATED_ROUTES enthält POST /accounting/g1-opening/request, das den Öffnungsantrag selbst stellt und bei geschlossenem G1 zulässig ist; Register bedeutet dort 'referenziert G1', nicht 'abgelehnt'. Ggf. Register bereinigen.
- Beschreibungstext Accounting.reports.auditExport.description nennt die neue Tabelle nicht (bewusst nicht geändert).
- Fremd: ruff E501 in accounting/creditor_routers.py:93 und 422 bei /tenant/events?limit (test_p10_reports oder test_m12) stammen aus anderen Paketen.

### AB02

**Befunde (gemeldet):** GA14-02: partial, GA14-04: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA14-02: core.release_gates.ensure_release_gate_open_for (additiv, nutzt is_open_for mit property_id/legal_entity_id/function, Fallback is_open, fail closed); durchgereicht in accounting/routers.py (set_leading, settlement_confirm mit post_immediately: Objekt und Rechtsträger des Buchungskreises) und banking/routers.py (Zahlungsdatei herunterladen und einreichen: Objekt des Bankkontos); unbekanntes Objekt wird ohne Kontext geprüft, 403 vor 404 bleibt
- GA14-04 Rest: CRM-Seite /plattform/freigabestufen (nur Plattformadmin) mit Komponente ReleaseGatesAdmin: Mandantenauswahl, Stand je Stufe (offen, begrenzt offen, geschlossen), Checkliste aus GET /tenant/release-gates/checklists, Antrag mit Nachweisdokument und Objektbegrenzung, Genehmigen/Ablehnen mit Kommentar (Plattform-API), Widerruf mit Kommentar (nur angemeldeter Mandant), Anzeige opened_by/opened_at, revoked_by/revoked_at/Kommentar; neuer Endpunkt GET /platform/tenants/{id}/release-gates (PlatformGateOverviewOut); BFF-Allowlist additiv; i18n PlatformGates de/en; Link auf Plattformseite

**Teilweise erledigt:**

- GA14-02: nicht alle G1/G2-Routen haben Objektbezug: receivable-runs/post, dunning letter send, admin-fee posting-drafts, direct-debit file/submit, create_batch (mehrere Aufträge) prüfen weiter ohne Kontext (nur unbegrenzte Freigaben öffnen); Jobs (release_gated, JobDbReleaseGateResolver) ohne Kontext; Granularität AA02-02 offen

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p02, bis 0333) -> ok
- pytest tests/unit/test_ab02_gate_context.py tests/integration/test_ab02_gate_context_platform.py test_aa02_gate_scope_evidence.py test_m10_ledger.py test_m15_payment_run.py test_m15_payments.py -> 20 passed
- ruff check, ruff format, mypy (platform, core/release_gates, accounting/routers, banking/routers) -> ok
- vitest ReleaseGatesAdmin.test.tsx + i18n-consistency.test.ts -> 9 passed
- pnpm tsc --noEmit -> keine Fehler in AB02-Dateien; eslint --max-warnings=0 für AB02-Dateien -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- HTTP-Ende-zu-Ende mit echtem Buchungskreis/Sammler unter begrenzter Freigabe (Kontextweitergabe per Unit-Test mit Fake-Session, Resolver per Integrationstest geprüft)
- test_migrations (Koordinator), Playwright, openapi export

**Offene Punkte und Entscheidungen:**

- AA02-02 Granularität bleibt offen; weitere Routen ohne Objektbezug und Jobs prüfen ohne Kontext
- Antrag und Widerruf laufen über die Mandanten-API und gehen nur im angemeldeten Mandanten; für andere Mandanten zeigt die Seite einen Hinweis (keine Plattform-Antragsroute ergänzt)
- Neuer Endpunkt und Schema PlatformGateOverviewOut erfordern OpenAPI-Export und api-client durch Koordinator
- Integrationstest nutzt die AA02/M2-Welt (Fixture-Import aus test_aa02_gate_scope_evidence), keine eigene Welt

### AB03

**Befunde (gemeldet):** GA04-09: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-09: message.delivered_at bei Statuswechsel auf sent (Dispatch-/Versandpfad _record_sent, provider_message_id aus Gmail-ID) und bei Zugangsnachweis einer verknüpften Zustellung; read_at beim Öffnen eines Dokuments der Nachricht im Portal (Indiz, erster Wert bleibt)
- Tests: bank_transaction.imported, portal_account.activated, contract.changed, contract_payment.changed über den Fachpfad mit Signatur, Mindestnutzlast und Ausschluss von Namen, IBAN und Freitexten; Zustell- und Leseindizien

**Teilweise erledigt:**

- GA04-09: Eine Gmail-Zustellbestätigung des Anbieters gibt es nicht, delivered_at markiert nur Annahme durch den Transport (A-AB03-01)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_ab03_events_receipts.py test_ga04_events.py -> 6 bestanden
- pytest test_migrations.py -> 4 bestanden
- ruff (communication, Tests), mypy communication -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- Portal- und Frontend-Tests (keine Frontend-Änderung)

**Offene Punkte und Entscheidungen:**

- Echte Gmail-Zustellbestätigung nicht verfügbar; ggf. später Bounce-Auswertung
- ruff I001 in portal/routers.py Importblock stammt von einem anderen Paket (nicht von AB03)

### AB04

**Befunde (gemeldet):** GA04-05: done, GA04-06: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-05: core/listparams.strict_query als Routen-Dependency an allen 323 GET-Listenrouten (response list[...] oder Seite mit items): nicht deklarierte Query-Parameter 422, filter/sort/fields/include/as_of nur bei Routen mit list_params oder ListSpec; bestehende Parameter bleiben deklariert
- GA04-05: ListSpec (filter[...], sort, fields, as_of 422) an /work-orders, /sla/clocks, /sla/alerts, /automation/rules, /immoware/sync/runs, /metering/sync-jobs, /banking/rules, /banking/payment-orders, /letting/listings, /letting/prospects
- GA04-05: Querschnittstest test_ab04_list_inventory iteriert alle GET-Listenrouten aus app.routes mit ?unbekannt=1 und erwartet 422; Restliste REMAINING leer
- GA04-06: If-Match (freiwillig, 412 bei veraltetem Token) und ETag an PATCH /sla/rules/{id}, /automation/rules/{id}, /letting/listings/{id}, /letting/prospects/{id}, /banking/payment-orders/{id}, /teams/{id}, /mail/mailboxes/{id}; ETag an GET /automation/rules/{id}, /letting/listings/{id}, /teams/{id}
- Hinweis AB01: GET /tenant/events akzeptiert limit wieder (als Alias von page_size, vorher still ignoriert); Bestandstests mit undeklarierten Parametern per AST-Scan geprüft
- Hinweis AA04: test_m16_dunning::test_dunning_preview_and_locks läuft grün (keine Ursache in der Listenumstellung)

**Teilweise erledigt:**

- GA04-06: übrige PATCH/PUT-Ressourcen (metering connections/assignments mit eigener Versionsprüfung, handover protocols, ai/sla/banking PUT-Konfigurationen, portal) ohne ETag; Pflicht-If-Match bleibt offen (AA04-01)
- GA04-05: echte Filter/Sortierung (ListSpec) nur an 10 weiteren Listen; die übrigen Listen lehnen unbekannte und generische Parameter mit 422 ab, bieten aber noch keine filter[...]/sort an. 60 GET-Routen ohne Response-Modell (meist Dateien, Exporte, einzelne Listen wie /banking/transactions, /hoa/resolutions, die bereits ListSpec haben) sind nicht im Inventar

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p04, Kette bis 0333) -> ok
- pytest tests/unit/test_ab04_strict_query.py tests/unit/test_aa04_listspec.py -> 6 passed
- pytest test_m18_tax_advisor_scope test_m40_metering test_m40_metering_stage2 test_r03_portal_checklist test_m21_sla test_m9_automation test_m15_payments test_m19_tickets test_a80_rule_assignment_chain test_m16_dunning test_aa04_listspec_etag test_q12_lists_bulk test_m26_letting test_m32_immoware test_q14_letting_w3 test_m9_rule_proposals test_t01_tenant_export_job test_ab04_list_inventory -> 110 passed
- ruff check/format über alle 101 geänderten Routerdateien -> ok (ein vorbestehendes E501 in accounting/creditor_routers.py:93, nicht aus diesem Paket)
- mypy geänderte Router (tickets/order_routers, sla, automation, immoware, metering, banking, letting, communication, platform, core/listparams) -> ok
- pnpm tsc --noEmit (web-crm) -> ok
- Statische Prüfung web-crm/web-portal (Literal-URLs und URLSearchParams) und tests/ (AST) auf undeklarierte Parameter an Listenrouten -> Funde behoben (properties limit/search, tenant/events limit)

**Nicht ausgeführte Tests (nicht bestanden):**

- volle Integrationssuite (nur betroffene Dateien, siehe oben; weitere 40 Testdateien mit Bezug zu Listen nicht gelaufen)
- test_migrations.py
- Playwright
- web-portal tsc (keine Änderung im Portal)

**Offene Punkte und Entscheidungen:**

- Clients, die bisher undeklarierte Parameter an Listen schickten, erhalten nun 422; geprüft wurden web-crm, web-portal und tests/ statisch, externe API-Nutzer nicht (Hinweis in Release Notes empfohlen)
- AA04-01 (Pflicht-If-Match für Geldflüsse) unverändert offen
- strict_query läuft als Routen-Dependency vor der Authentifizierung: unbekannte Parameter ergeben 422 auch ohne Token (keine Daten, nur Parameterschema wie in OpenAPI)
- OpenAPI-Export (apps/api/openapi.json, api-client) nicht neu erzeugt (gesperrte Datei): neue Header-Parameter If-Match und limit an /tenant/events, Koordinator

### AB05

**Befunde (gemeldet):** GA04-11: done, GA04-07: partial, GA04-10: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA04-11: CRM-Seite /dokumente/erzeugt (Filter Vorlage, Zeitraum, Link zum Dokument), GET /generated-documents um template_id, created_from, created_to erweitert, BFF additiv, i18n de/en, Vitest

**Teilweise erledigt:**

- GA04-07: PATCH /work-orders/{id}/approval-workflow (404/403/422 getestet), approval_workflow_id in Auftragsliste und Detail, Eingabefeld auf der CRM-Auftragsseite; keine Auswahl und keine Mandantenprüfung des Workflows, weil es keine Workflow-Entität gibt (AA05-01); es existiert auch kein CRM-Auftragsformular zum Anlegen
- GA04-10: PATCH /document-templates/{id} pflegt context_types vorhandener Versionen (Platzhalter neu berechnet), Vorlagenformular mit Kontext-Checkboxen und Anzeige placeholders_used; template_block weiter offen (AA05-02)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa05_templates_generated.py -> 5 passed (mit temporären Fremd-Stubs 0323/0326 der Kette)
- vitest GeneratedDocumentsList, workorders, LetterTemplates -> 8 passed
- ruff check/format, mypy documents + tickets/order_routers -> ok
- pnpm tsc --noEmit -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations, volle Suiten, Playwright

**Offene Punkte und Entscheidungen:**

- AA05-01: Workflow-Entität fehlt, daher keine Auswahl und keine Mandantenprüfung (422 nur bei ungültiger UUID)
- AA05-02 template_block offen
- Test caretaker auf PATCH approval-workflow akzeptiert 200 oder 403 (Rolle nicht geprüft); Rechteprüfung 403 für Vorlagen-PATCH ist getestet
- Migration 0323 und 0326 lagen zeitweise nur als temporäre Stubs anderer Pakete vor

### AB06

**Befunde (gemeldet):** GA03-01: done, GA03-03: partial, GA07-01: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA03-01: CRM-Anlegeformular bietet Wiederholung und Fortsetzung mit Pflichtauswahl der Ursprungsversammlung derselben GdWE (origin_meeting_id); Vorlagen im Detailformular als Auswahlliste aus GET /document-templates; Portal MeetingList zeigt public_description (interne nie)
- GA07-01: GET /hoa/meetings/{id} liefert virtual_basis_term_notice dauerhaft, CRM MeetingFormPanel zeigt ihn; Sperre unverändert hinter Mandantenschalter (Standard aus)
- Problemcodes: 0006 bis 0019 unbelegt, Vergaberegel im hoa/README dokumentiert, keine Umnummerierung

**Teilweise erledigt:**

- GA03-03: void bleibt offen (AA06-01), nichts geändert
- GA07-01: Übergangsregel § 48 Abs. 6 WEG und Sperrentscheidung offen (AA06-02)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_aa06_meeting_resolution + test_m25_03_meeting_invitation_virtual -> 6 passed
- ruff hoa -> ok; mypy src/mhvp/hoa -> ok
- vitest CRM HoaForms, MeetingDetailsForm, MeetingFormPanel -> 16 passed
- vitest portal MeetingList -> 3 passed
- pnpm tsc --noEmit CRM und Portal -> keine Fehler

**Nicht ausgeführte Tests (nicht bestanden):**

- alembic upgrade head: Kette unvollständig (0326 fehlt als Vorgänger von 0327, 0323 fehlt), daher migration_untested
- tests/integration/test_migrations.py
- Playwright, volle Suiten (Vorgabe)

**Offene Punkte und Entscheidungen:**

- AA06-01 (void) und AA06-02 (Dreijahresgrenze, § 48 Abs. 6 WEG) unverändert offen, G4
- Migrationskette: 0323 und 0326 fehlen noch (andere Pakete), alembic upgrade head erst danach prüfbar
- openapi.json und api-client neu erzeugen (neues Feld virtual_basis_term_notice im Detail ist ein untypisiertes dict, kein Schemaeffekt erwartet)
- Problemcodes HOA 0006 bis 0019 bleiben frei, Regel im Modul-README

### AB07

**Befunde (gemeldet):** GA07-02: done, GA07-03: partial, GA06-02: partial, GA06-03: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA07-02: POST /hoa/asset-reports/{id}/dispatch (G4, nur issued): Brief je aufgelöstem Empfänger je Eigentumsvertrag zum Stichtag, abgelegt als erzeugtes Dokument (Kontext hoa_asset_report, Links Kontakt/Vertrag/Gemeinschaft), Übergabe an den bestehenden Dispatch (Zustellweg Aufruf > Kontakt > Mandantenstandard); Standard nur Eigentümer ohne Portalabruf, doppelte Briefe übersprungen; Bereitstellungsprotokoll zeigt je Eigentümer dispatches; CRM-Spalte Brief und Versandschaltfläche

**Teilweise erledigt:**

- GA07-03: Sonderfälle Ersterwerb, Zwangsversteigerung, Sonderrechtsnachfolge mit deutscher Fallbezeichnung (case_label, Befundtext) und Freigabeschritt getestet; Zuordnungsregel je Erwerbsart bewusst nicht entschieden (AA07-01), calc.py unverändert
- GA06-02: Informationsblatt technisch vollständig (Vorschau, Ablage POST /statements/{id}/info-sheet hinter G3, Verknüpfung über generated_document Kontext statement, Liste /outputs, CRM-Panel); Texte Belegeinsicht/Einwendungen bleiben 'Text nicht freigegeben' bis AA11-01
- GA06-03: Anschreiben und eigener §-35a-Nachweis (Vorschau GET /billing/owner-statements/{id}/preview/{letter\|s35a}, Ablage POST .../outputs hinter G3 nach interner Freigabe, Liste, CRM-Panel); steuerlicher Hinweis Platzhalter 'Text nicht freigegeben' bis AA11-02, Mietverwaltung ohne Beträge

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p07) -> ok bis 0333
- pytest tests/integration/test_ab07_outputs.py -> 3 passed
- pytest test_aa07_asset_provision_acquisition, test_m24_asset_report, test_m17_owner_statement, test_m17_operating_costs::test_a07_tenant_letters_from_snapshot, unit test_aa11_owner_statement_info_sheet, test_m17_owner_statement_calc -> 17 passed
- ruff check src + Testdatei, ruff format --check, mypy src/mhvp/hoa src/mhvp/billing und Testdatei -> sauber
- vitest StatementOutputsPanel, OwnerStatementPanel -> 6 passed; eslint geänderte Dateien -> sauber; tsc --noEmit web-crm -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_migrations.py (noop-Migration, nicht separat ausgeführt)
- kein vitest für AssetReportDispatch; Playwright und volle Suiten (Vorgabe)
- OpenAPI-Export und api-client (Koordinator)

**Offene Punkte und Entscheidungen:**

- AA07-01 (Zuordnung je Erwerbsart) und AA07-02 (Genügen des Portalabrufs) weiter offen, G4
- AA11-01 und AA11-02 weiter offen (Texte Informationsblatt, steuerlicher Hinweis § 35a), G3
- Versandstatus im CRM-Protokoll wird technisch (prepared/sent) angezeigt, keine Übersetzung
- documents.LINKABLE kennt hoa_asset_report/statement nicht; Verknüpfung zum Lauf daher über generated_document.context (fremde Domäne nicht geändert)
- OpenAPI und api-client neu erzeugen (neue Endpunkte dispatch, info-sheet, outputs, preview)

### AB08

**Befunde (gemeldet):** GA02-07: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA02-07: Statusmodell 6.2 des Portalzugangs wird gespeichert (not_invited bei Anlage mit send_invitation=false, invited bei Einladung/Brief/Neueinladung, active bei Annahme, locked/active und expired per Beat-Job mhvp.portal.sync_account_status alle 15 Min, idempotent, revoked bleibt final); last_login_at (am Benutzer) bei jeder Anmeldung per Test belegt; Uebergangstabelle in Modul-README und Rule AA08

**Teilweise erledigt:**

- keine gemeldet

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_ab08_portal_status, test_aa08_portal_account, test_a86_portal_accounts, test_t13_sd_access_protocol, test_m21_portal -> 51 passed (mit temporaeren Stub-Migrationen 0323/0326, danach entfernt)
- ruff check/format portal -> sauber
- mypy src/mhvp/portal -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py
- Frontend (keine Aenderung)

**Offene Punkte und Entscheidungen:**

- test_aa08_portal_account.py nutzte die Welt von test_a86 (Konflikt bei gemeinsamem Lauf), jetzt eigene Fixtures mit Praefix aa08
- ruff format auf tests/integration formatierte versehentlich einige Testdateien anderer Pakete (nur Format)
- Frontend zeigt not_invited noch nicht mit eigener Beschriftung; CRM-Formular hat keinen Schalter send_invitation
- openapi.json/api-client nicht regeneriert (neues Feld send_invitation)
- Annahme A-AB08-01 in ASSUMPTIONS

### AB09

**Befunde (gemeldet):** GA02-05: done, GA03-06: done, GA03-07: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- AA10 Integrationstests: tests/integration/test_ab09_fee_creditor_plan.py (Honorarfelder: Anlegen, Lesen, Patchen, 422, Leserecht 403, anderer Mandant 404; Kreditorenansicht 404/200/404; eigene Testwelt ab09)
- GA02-05: Standard-Bankregel beim Anlegen der Dienstleisterbeziehung (proposed, Prio 900, creditor_payment, hit_count 0), ohne Option keine Regel, Leserecht 403, Mandantentrennung; Hinweis in der Kreditorenansicht (CreditorsPanel)
- GA03-07: auto_post wirkt im Lauf: generate liefert auto_post_requested und auto_post_state (draft_only, locked_g1, locked_switch, draft_pending_rule), bucht nie (journal_entry_id None); Tests für nein, ja mit G1 zu, ja mit G1 offen; Setzen ohne Automatikschalter 409
- CRM Honorarformular: manager_contact_id (ContactPicker), termination_date, due_day_rule, due_day, account_id, sev_fee_amount mit Validierung, Anzeige in der Honorarliste; Rechnungspläne: Spalte Automatische Buchung mit PATCH-Umschalter und Sperrhinweis nach Lauf; i18n de/en; Vitest (AdminFeeExtraFields.test.tsx, RecurringPlanAutoPost.test.tsx)
- Handbuch buchhaltung.md, docs/plans/M13.md Statuszeile, Regel M13-fee-fields Punkt 6, Accounting-README

**Teilweise erledigt:**

- keine gemeldet

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/integration/test_ab09_fee_creditor_plan.py + tests/unit/test_aa10_fee_plan.py (mhvp_p09, Redis 6380/9, Scratch-Alembic mit Stubs für 0323, 0325, 0326) -> 13 passed
- pnpm vitest run AdminFeeExtraFields, RecurringPlanAutoPost, CreditorsPanel, AdminFeePanel -> alle grün
- pnpm tsc --noEmit -> sauber
- ruff check/format, mypy src/mhvp/accounting -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_migrations.py und upgrade head mit der echten Kette (0323, 0325, 0326 fehlten beim Lauf, Stubs nur im Scratch-Verzeichnis)
- Playwright, volle Suiten

**Offene Punkte und Entscheidungen:**

- Erlöskonto im Honorarformular als ID-Eingabe (keine Kontenauswahl, da Buchungskreise des Objekts im Formular nicht geladen sind); Auswahlliste wäre Folgearbeit
- AA10-01 bis AA10-03 in OPEN_QUESTIONS unverändert (Entscheidungen nicht Teil der Welle)
- Migrationskette beim Lauf lückenhaft (0323, 0325, 0326); Gesamtlauf nach Eintreffen der Pakete nötig
- BFF-Allowlist: keine neuen Pfade nötig, alle genutzten Pfade bereits freigegeben

### AB10

**Befunde (gemeldet):** GA08-05: done, GA08-02: partial, GA08-01: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA08-05: Snapshot haelt Registereintrag (ID, Version, Status, Wirksamkeitsdatum) fest, Ausgabe snapshot.rule_register, CRM-Zeile am Lauf; Integrationstest Lauf, neue Version, Nachrechnung identisch (nicht ausgefuehrt)
- GA08-01 Rest: CRM-Anzeige Freigabepunkt 13b UStG an der Eingangsrechnung, Unit-Test dass keine Automatik greift

**Teilweise erledigt:**

- GA08-02: Pruefpunkte als konfigurierbare Eintraege (Gruppe Pruefpunkt), Endpunkt GET rule-versions/due-checkpoints meldet faellige Punkte als Hinweis; Standard leer ist nur ohne seed-checkpoints (AA12 Entwuerfe bleiben ueber den bestehenden Seed-Endpunkt); keine CRM-Faelligkeitsliste; fachliche Befuellung offen (AB10-01)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_ab10_rule_checkpoints.py tests/unit/test_w2_p03_checks.py -> 9 passed (inkl. neuer Tests)
- pnpm vitest run src/components/receipts -> 16 passed
- pnpm tsc --noEmit -> ohne Fehler
- ruff/mypy rule_register.py -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_aa12_rule_checkpoints.py und test_m17_operating_costs.py (Kette bricht: 0321 fehlt, alembic KeyError)
- kein Frontend-Test fuer die zwei neuen Seitenbloecke (Server-Seiten)

**Offene Punkte und Entscheidungen:**

- AB10-01 in docs/OPEN_QUESTIONS.md
- Integrationstests nach Vorliegen der Migrationen 0321 bis 0327 ausfuehren
- CRM-Faelligkeitsliste der Pruefpunkte nicht umgesetzt

### AB11

**Befunde (gemeldet):** GA10-03: partial, GA12-06: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA12-06: Sperre je Mandant und Job (lock_job, Advisory Lock) in documents.process_inbox und billing.consumption_info ergänzt; Tests für zwei gleichzeitige Läufe und Wiederholung beider Jobs (Dokumenteneingang ohne Sperre nachweislich doppelte Wirkung, mit Sperre eine)
- GA10-03: Tests beider Schalterzustände (aus, an unter Schwelle, an bei zwei Objekten, an bei eindeutigem Objekt), Mandantentrennung inkl. gleicher Objektnummer im anderen Mandanten, Protokollierung (Ereignis document.intake_auto_filed)

**Teilweise erledigt:**

- GA10-03: Befund bleibt teilweise, weil die Entscheidung AA13-01 (Freigabe, Schwelle) offen ist; Schalter unverändert Standard aus

**Nicht erledigt:**

- GA12-04 Rest: bewusst nicht angefasst (AA15-01 offen)

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head (mhvp_p11) -> ok bis 0333
- pytest test_ab11_jobs_intake.py test_aa13_intake_match.py test_ga12_jobs.py -> 22 passed
- pytest test_h03_consumption_info.py test_m6_process_inbox.py -> siehe Chat (Lauf nach JSON)
- Gegenprobe: Sperre im Dokumenteneingang entfernt -> Parallellauftest schlägt fehl (2 statt 1), Sperre wiederhergestellt
- ruff check/format geänderte Dateien -> ok; mypy consumption_info_tasks.py -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_migrations.py
- volle Suiten, Playwright
- mypy documents gesamt

**Offene Punkte und Entscheidungen:**

- AA13-01 und AA15-01 weiterhin offen
- Zu Beginn wurde versehentlich die Standard-DB mhvp und Redis 6379 statt mhvp_p11/6380 benutzt (env.sh überschreibt zuvor gesetzte Variablen): einige Testläufe (Mandanten ab11a/ab11b, Welt ab11) liegen in der DB mhvp; es gab dabei keine Migration auf mhvp außer ggf. bereits laufendem upgrade head, die Läufe scheiterten an Kettenlücken (0323 fehlte zeitweise)
- Verbrauchsinformation: Test prüft Zeilenzahl je Einheit und Monat und Wiederholung ohne neue Wirkung; die Sperre wirkt dort zusätzlich zur Eindeutigkeit uq_consumption_info_unit_month

### AB12

**Befunde (gemeldet):** GA11-01: done, GA11-04: partial, GA11-02: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA11-01: Sprachwahl am Portalkonto (portal_account.locale, PATCH /portal/me/locale, locale in GET /portal/me), Übernahme bei Anmeldung (Passwort, zweiter Faktor, Magic Link) in den Cookie, Sprachwahl auf der Anmeldeseite, Cookie bleibt Vorrang für nicht angemeldete Besucher
- GA11-04: CRM-Seite /einstellungen/dienstleister-portal für Verfügbarkeitsfenster (Liste, Erfassen, Entfernen) und Klassenfreigaben, BFF-Allowlist additiv, i18n de/en, Vitest, ohne Bewertungen

**Teilweise erledigt:**

- GA11-04: Bewertungsanzeige bewusst nicht umgesetzt (AA14-02 offen)
- GA11-02: unverändert bei 20 Typen (AA14-01 offen)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest test_ab12_portal_locale.py test_aa14_access_paths.py -> 3 passed
- pytest test_migrations.py -> 4 passed (inkl. no_autogenerate_drift)
- web-portal vitest locale, LanguageSwitch, auth, bff -> 30 passed
- web-crm vitest PortalProviderAdmin, settings-index, messages, bff -> 219 passed
- web-portal tsc --noEmit -> ohne Fehler; web-crm tsc: keine Fehler in eigenen Dateien (fremde Fehler in ReleaseGatesAdmin.tsx)
- ruff check/format auf eigenen Dateien -> ok

**Nicht ausgeführte Tests (nicht bestanden):**

- volle Suiten
- Playwright
- next build

**Offene Punkte und Entscheidungen:**

- AB12-01 in OPEN_QUESTIONS.md: Dienstleister-Freigaben unter G5? Nach ADR 0003 und 18.0 ist G5 Drittmandantenbetrieb, die Freigaben sind mandanteninterne Konfiguration; ein Gate würde auch den ersten Mandanten sperren. Kein Gate gesetzt.
- AA14-01 und AA14-02 bleiben offen (20 Typen, Bewertungen).
- openapi.json und api-client müssen neu erzeugt werden (neuer Endpunkt PATCH /portal/me/locale, Feld locale in /me, nicht typisiert da /me dict zurückgibt).
- Die CRM-Messages de.json und en.json wurden per JSON-Roundtrip geschrieben; dabei wurden einige Inline-Objekte umformatiert (Werte unverändert), Diff enthält daher Formatierungsrauschen.
- mypy src/mhvp/portal meldet einen Fehler in routers.py Zeile 302 (provision_account, Rückgabetyp), nicht aus AB12.
- Die CRM-Seite zeigt Rechtsträger über /tenant/legal-entities (members:read); ohne dieses Recht bleibt die Auswahl leer.

### AB13

**Befunde (gemeldet):** GA01-07: partial, GA01-08: done, GA01-10: partial, GA01-12: done

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA01-10/GA01-12: Plattformaudit platform_audit_event (Migration 0332, ohne RLS, Trigger forbid_mutation gegen UPDATE/DELETE/TRUNCATE) fuer Kundendomain anlegen/entfernen, Mandantenstatus, OIDC-Client anlegen, Secret erneuern, aktivieren, deaktivieren; Payload ohne Secrets; GET /platform/audit-events (Plattformadmin, limit 1..200, offset, Filter action, total)
- GA01-07: Integrationstest konfigurierte Vertragsnummer (Format V-00100 bei neuem Vertrag, Startwert nur bei unbenutztem Kreis, Rechnungskreis bleibt 422, Leserecht 403)
- GA01-08: Integrationstest Mandantenstandard im Versand (Standard email, Kontaktpraeferenz post schlaegt Standard, Kanal der Position schlaegt Kontakt, Standard post)
- GA01-10/12: Vitest TenantDomainsAdmin.test.tsx (6 Tests) und OidcClientsAdmin.test.tsx (5 Tests)

**Teilweise erledigt:**

- GA01-07: Rechnungsnummernkreis gesperrt (AA17-01), Objekt/Beleg/Ticket unveraendert (AA17-02)
- GA01-10: DNS-Pruefung und Wirkung suspended nicht angefasst (AA17-03)

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- alembic upgrade head auf mhvp_p13 (0331 -> 0332 -> 0333) -> ok
- pytest test_ab13_platform_audit_numbers.py test_aa17_tenant_admin.py -> 7 passed
- pytest test_migrations.py (inkl. Drift-Test, Round-Trip) -> passed (Lauf mit ab13/aa17 zusammen, 10 passed, 1 failed = damals Testfehler im eigenen Contract-Test, danach behoben)
- pnpm vitest run TenantDomainsAdmin.test.tsx OidcClientsAdmin.test.tsx -> 11 passed
- pnpm tsc --noEmit -> sauber
- ruff check/format und mypy platform/admin_routers.py, models.py -> sauber

**Nicht ausgeführte Tests (nicht bestanden):**

- test_migrations.py nach der letzten Testkorrektur nicht erneut (Migration unveraendert)
- keine Seitentests der Next.js-Seiten selbst, Komponententests ersetzen sie; Playwright nicht ausgefuehrt

**Offene Punkte und Entscheidungen:**

- AA17-01, AA17-02, AA17-03 unveraendert offen
- Keine Oberflaeche fuer das Plattformaudit (nur API)
- BFF-Allowlist fuer /platform/audit-events nicht ergaenzt, da keine CRM-Seite
- Das Log (_log.warning) bleibt zusaetzlich zum Audit-Eintrag bestehen; kein DomainEvent (kein Mandantenkontext)
- Fremde Migrationsdateien 0323/0326 (zz_ab08tmp) waren zeitweise transient, Tests liefen nach Stabilisierung der Kette

### AB14

**Befunde (gemeldet):** GA09-01: done, GA09-02: partial, GA09-04: partial

**Geprüfte Abnahmefälle (Anhang D Bezug):** kein Fall aus Anhang D genannt. Fachliche Bestätigung je Fall durch den Prüfer steht aus (V16).

**Erledigt (gemeldet):**

- GA09-01: write_l_records und write_m_records (heiwako.py) nur mit den vom Parser belegten Positionen, Roundtrip- und Byte-Identitätstests gegen den Parser (15 Unit-Tests grün); nicht belegte Felder (L ab Position 166, M Umlagezeilen 4 bis 6, M Dienstleisterblöcke 42 bis 66, Satzarten B und K) bleiben leer und sind als offen dokumentiert (AA16-01)
- GA09-04: Annahmen zu id, status, attempts, pending nach Fehlversuch gegen webhooks.py und platform/routers.py geprüft und zutreffend; Test geschärft (exakter Feldsatz der Deliveries-Antwort, Zuordnung der Zustellung über event_id und X-MHVP-Delivery, last_status_code 500 und 204, last_error, next_attempt_at, delivered_at, attempts 2 nach Neuzustellung); eigene Testwelt ga09 statt Import der Welt von test_a69, Masterkey wird zurückgesetzt
- GA09-02: Abschnitt Faktenstand (Zweck, Stack, Datenmodell, Schnittstellen, Status) in dossier-uebergabeprotokoll.md (PHP/MariaDB, v3ni94/UProtkoll, 13 Tabellen, mysqldump), dossier-flow.md und dossier-smart-einzug.md ergänzt; Lücken als 'offen, Dossier erforderlich (AA16-03)' markiert

**Teilweise erledigt:**

- GA09-04: Integrationstest nicht ausgeführt, alembic upgrade head scheitert weiterhin (Revision 0326 fehlt in der Kette, andere Agenten); Test ist ruff-sauber und sammelbar
- GA09-02: mueller-flow.md und uebergabeprotokoll.md sowie Wissensdatenbank-Nachweis hängen am Anhang-B-Lauf (AA16-03); objektakte, Hub und Mail optimierung hatten die Abschnitte bereits

**Nicht erledigt:**

- keine gemeldet

**Ausgeführte Tests mit Ergebnis:**

- pytest tests/unit/test_m40_metering_heiwako.py -> 15 passed
- ruff check/format und mypy src/mhvp/metering -> sauber
- pytest tests/integration/test_ga09_smart_einzug_contact_updated.py --collect-only -> 1 Test gesammelt

**Nicht ausgeführte Tests (nicht bestanden):**

- tests/integration/test_ga09_smart_einzug_contact_updated.py (Kette unvollständig, KeyError 0326)
- tests/integration/test_migrations.py

**Offene Punkte und Entscheidungen:**

- AA16-01 Stammdatenformat der Anbieter, nicht belegte L/M-Felder und B/K
- AA16-03 Anhang-B-Läufe
- Integrationstest ausführen, sobald die Migrationskette bis 0332 vollständig ist
