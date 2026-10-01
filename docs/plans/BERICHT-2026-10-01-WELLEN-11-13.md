# Ergebnisbericht Wellen 11 bis 13, Stand 01.10.2026

Adressat: Vorstand (Timo Müller). Gegenstand: zweite Lückenanalyse des Master-Prompts (Befunde GA01 bis GA14) und die Versionen 1.57.0 und 1.58.0 der MH Verwaltungsplattform. Die Gates G1 bis G5 bleiben geschlossen, keine Version öffnet ein Gate. Dieser Bericht ist keine rechtliche oder steuerliche Abnahme.

## Ergebnis in Kürze

- Die zweite Lückenanalyse ergab 80 Befunde. Nach Welle 13 sind 52 erledigt, 18 teilweise erledigt und 10 offen (docs/plans/LUECKENLISTE-2026-10-01.md).
- Version 1.57.0 (Welle 12, 17 Pakete) und 1.58.0 (Welle 13, 14 Pakete) sind im Repository abgeschlossen. Migrationen 0303 bis 0333. Ob und wann beide Versionen in Produktion deployt wurden, ist aus den Unterlagen nicht ersichtlich. Letzter dokumentierter Produktionsstand ist 1.55.0 (Bericht Wellen 4 bis 10).
- Alle neuen Schalter stehen im Auslieferungszustand aus. Es wurden keine Rechtsregeln entschieden. 38 neue Entscheidungsfragen (AA01-01 bis AB12-01) liegen beim Betreiber und sind in docs/plans/ENTSCHEIDUNGEN-2026-10-01.md mit Empfehlung eingearbeitet.
- Die Tests liefen als Gesamtsuite in vier Teilläufen (Shards) mit grünem Ergebnis. Einzelheiten siehe Testnachweise.

## Vorgehen

1. Welle 11: Abschlussverifikation der Wellen 4 bis 10 (Builds, Playwright, Gesamtsuite, siehe Bericht Wellen 4 bis 10) und zweite Prüfung des Master-Prompts gegen den Code. Grundlage waren 14 Prüfpakete GA01 bis GA14 zu den Abschnitten 3 bis 19 und den Anhängen A bis E. Befunde der ersten Lückenliste vom 30.09.2026 wurden nicht erneut aufgeführt. Ergebnis: docs/plans/LUECKENLISTE-2026-10-01.md mit 80 Befunden. Anhang D: 57 von 58 Fällen mit Test und vorgerechnetem Sollwert, D24 bleibt xfail (M17-03).
2. Welle 12 (AA01 bis AA17): je Paket eine Fachdomäne, eigene Migration, Paketergebnis als JSON. Befunde mit Entscheidungsbedarf wurden nur technisch vorbereitet (Schalter aus, Gate geschlossen) und als Frage mit Eigentümer und Gate in docs/OPEN_QUESTIONS.md eingetragen.
3. Welle 13 (AB01 bis AB14): Abschluss der in Welle 12 teilweise erledigten Befunde. Entscheidungsfragen waren ausdrücklich nicht Teil der Welle.
4. Integration durch den Koordinator: Zusammenführen der Pakete im gemeinsamen Arbeitsbaum, Behebung von Kollisionen, Gesamtsuite, Migrationsrundlauf, Linting.

## Pakete

### Welle 12, Version 1.57.0 (Migrationen 0303 bis 0319)

| Paket | Inhalt |
| --- | --- |
| AA01 | Gate-Auflösung der Hintergrundjobs je Mandant, Buchungsprüfungen (Nummernfolge, Nebenbuch), Buchungsvermerke mit unveränderlichem Trigger (0303), Abdeckungstest der Gate-Routen |
| AA02 | Freigabestufen: Umfang, Checklisten, Nachweisdokument, Widerruf (0304), CI-Job für XRechnung-Prüfung |
| AA03 | Ereignisse (ticket.commented, bank_transaction.imported, contract.changed und andere) und Nachrichtenfelder (0305) |
| AA04 | Listenparameter (ListSpec) und ETags (0306, ohne Schema) |
| AA05 | Auftragsworkflow, Vorlagenkontext, erzeugte Dokumente, Einbettung von Lernbeispielen (0307) |
| AA06 | Versammlungsmodell: Wiederholung, Fortsetzung, Umlauf, Ergebnis je TOP, Stimmkanal (0308) |
| AA07 | Vermögensbericht im Eigentümerportal, Freigabeschritt für Sonderfälle beim Eigentümerwechsel (0309) |
| AA08 | Abrechnungszeiträume mit Status, Dokumente an Objekten, Portalkonto-Statusmodell (0310) |
| AA09 | Schwarzes Brett nach Abschnitt 6.2 (0311) |
| AA10 | Verwalterhonorar, Rechnungsplan mit Automatikkennzeichen, Standard-Bankregel, ADR 0020 (0312) |
| AA11 | Abrechnung: Informationsblatt, Belegmappe, Zeitanteilsregel (0313) |
| AA12 | Regelversionen und Prüfpunkte, § 13b UStG als Freigabepunkt (0314, ohne Schema) |
| AA13 | Dokumenteingang: Zuordnung, Folgeprozess, Direktablage hinter Schalter (0315, ohne Schema) |
| AA14 | Portal: Sprache, Formulare, Dienstleisterinformationen, Freigabe je Unterlagenklasse (0316) |
| AA15 | Zeitpläne der Jobs, Demo-Mandant, Incident-Runbook (0317, ohne Schema) |
| AA16 | HeiWaKo-Export Satzart A, Integrationsdokumentation (0318, ohne Schema) |
| AA17 | Mandantenvorgaben, Kundendomains, OIDC-Clients, Ende-zu-Ende-Pfade (0319, ohne Schema) |

### Welle 13, Version 1.58.0 (Migrationen 0320 bis 0333)

| Paket | Inhalt |
| --- | --- |
| AB01 | Laufzeitnachweis des Gate-Schutzes je Route, Nebenbuchabgleich im CRM und im Prüfexport |
| AB02 | Gate-Umfang mit Objektbezug an Buchungs- und Zahlungsrouten, Freigabestufen im CRM |
| AB03 | Nachrichten: delivered_at und read_at, Erzeugungstests der Ereignisse |
| AB04 | strict_query an allen GET-Listen, ListSpec auf zehn weiteren Listen, ETags an sieben Ressourcen |
| AB05 | Erzeugte Dokumente, Vorlagenkontext, Workflow-Verweis am Auftrag |
| AB06 | Versammlung im CRM, Beschluss-Sammlung, Hinweis zum Grundlagenbeschluss |
| AB07 | Vermögensbericht per Brief, Sonderfälle Eigentümerwechsel, Informationsblatt und § 35a-Nachweis hinter G3 |
| AB08 | Portalkonto-Status mit Beat-Job, Anlage ohne Einladung |
| AB09 | CRM für Kreditoren und Honorarfelder, Planflag, Standard-Bankregel |
| AB10 | Registerversion im Abrechnungs-Snapshot, Prüfpunkte, § 13b-Freigabepunkt |
| AB11 | Direktablage-Tests, Parallellaufsperren für Dokumenteingang und Verbrauchsinformation |
| AB12 | Portalsprache am Konto (0331), CRM-Seite Dienstleister im Portal |
| AB13 | Plattformaudit (0332), Mandantenkonfigurationstests |
| AB14 | HeiWaKo-Satzarten L und M, Dossiers mit Faktenstand |

Die Migrationen 0331 (portal_account.locale) und 0332 (platform_audit_event) sind in Welle 13 die einzigen echten. Die übrigen Nummern 0320 bis 0330 und 0333 sind Platzhalter ohne Schemaänderung.

## Stand der Lückenliste

Quelle: docs/plans/LUECKENLISTE-2026-10-01.md, Zählung nach Welle 13.

| Stand | Anzahl |
| --- | --- |
| erledigt | 52 |
| teilweise | 18 |
| offen | 10 |
| Summe | 80 |

Teilweise erledigt: GA03-03, GA04-06, GA04-07, GA04-09, GA04-10, GA06-02, GA06-03, GA07-01, GA07-03, GA08-02, GA09-02, GA09-04, GA10-03, GA11-02, GA11-04, GA12-04, GA14-02, GA14-05.
Offen: GA02-06, GA08-04, GA08-06, GA08-08, GA10-06, GA10-07, GA11-03, GA12-08, GA13-24, GA13-59.

Nach Gate verteilen sich die 80 Befunde so: ohne Gate 40, G1 18, G3 9, G4 8, G2 2, G5 2, G1 bis G4 1. Die teilweise und offenen Befunde sind entweder Entscheidungen von Betreiber oder Rechtsberatung oder Folgearbeiten (Welle 14).

## Testnachweise

Zahlen aus den Commit-Meldungen (git log):

| Version | API-Suite | CRM vitest | Portal vitest |
| --- | --- | --- | --- |
| 1.56.0 (Basis, Bericht Wellen 4 bis 10) | 3.795 grün | 1.865 | 179 |
| 1.57.0 | 3.927 grün in 4 Shards | 1.886 | 189 |
| 1.58.0 | 4.015 grün in 4 Shards | 1.920 | 198 |

Zusätzlich je Release laut Commit-Meldung: Migrationsrundlauf und Drift, RLS, OpenAPI, mypy, ruff, eslint, tsc, i18n, Hilfeindex, Abgleich der Agentendokumente.

Nicht nachgewiesen sind in den Unterlagen: Playwright-Läufe gegen das Backend für 1.57.0 und 1.58.0 (der Kernpfad-Spec core-paths-ga01 war als Aufgabe offen), Staging-Messungen, Tests mit echten Authenticatoren. Diese sind als nicht ausgeführt zu lesen. Einzelne Paketprüfungen, die bei den Agenten nicht liefen, standen in der Integrationsliste (unter anderem test_aa12_rule_checkpoints.py, test_m17_operating_costs.py, GA09-04-Test) und sind durch die Gesamtsuite abgedeckt, soweit diese sie enthält.

## Integrationskorrekturen

- Portalkonto-Status: Das Paket AA08 führte zunächst den Wert disabled ein. Nach Integration gilt revoked (entzogen). Migration 0310 bereinigt Bestandsdaten: jeder Status außerhalb der erlaubten Werte (not_invited, invited, active, locked, expired, revoked), insbesondere der Altwert disabled, wird auf revoked gesetzt, bevor die Prüfbedingung ck_portal_account_status angelegt wird. Der Downgrade der Migration entfernt die Bedingung, stellt aber disabled nicht wieder her.
- Celery: Tests dürfen die gemeinsame Anwendung nicht umbinden. create_celery(set_as_current=False) verhindert, dass Konfigurationstests gemeinsame Tasks auf eine andere Instanz setzen. Regel für künftige Pakete: Konstruktoren mit globaler Wirkung nie ohne Rücksetzung.
- Testweltkollisionen: Pakete AA04 und GA04 teilten Mandanten und Benutzer anderer Module. Ergebnis: eigene Testwelten mit Paketpräfix (Slug und Benutzername mit Paketkürzel und Lauf-ID), keine Importe fremder Welten. AB02 nutzt noch die Welt von M2 (Kollisionsrisiko im Shard zu beobachten).
- strict_query: Alle 323 GET-Listen lehnen unbekannte Abfrageparameter mit 422 ab (core/listparams.py). Folgefehler aus der Einführung: die Objektsuche im Zuordnungsassistenten des Messdienstes sendete einen unzulässigen Parameter und nutzt nun page_size. /tenant/events akzeptiert limit als Alias für page_size.
- Weitere Korrekturen 1.57.0: doppelter Schlüssel im Webhook-Ereigniskatalog, optionales merge_fields in Kontaktauswahlen, Portal-Sprachwächter, ICU-Maskierung eines DMS-Hinweises, Chatseitenkontext und Einstellungsindex für neue Seiten.
- Weitere Korrekturen 1.58.0: Registerverweis im Snapshot verträgt ungespeicherte Regelversionen, Neuberechnung AB10 über eine neue Abrechnungsversion, Marker für IBAN-sichere KI-Tests, Tabellenhülle für neue Seiten.

## Deployment-Hinweise

1. Vorbedingung: Sicherung vor dem Deploy nach Betriebsablauf (docs/runbooks/deploy.md). Rücksprung nur über die Sicherung, nicht über Downgrade im laufenden Betrieb.
2. Migrationen 0303 bis 0333 einspielen (bei Produktionsstand 1.55.0 zusätzlich keine Migration aus 1.56.0). Echte Schemaänderungen: 0303 (Buchungsvermerke mit Trigger gegen Änderung), 0304 (Freigabenachweis, Umfang), 0305 (Nachrichtenfelder, Ticketkategorie), 0307, 0308, 0309, 0310 (mit Datenbereinigung des Portalstatus), 0311, 0312, 0313, 0316, 0331, 0332 (unveränderliche Plattformaudit-Tabelle). Platzhalter ohne Schema: 0306, 0314, 0315, 0317 bis 0330, 0333.
3. Datenbereinigung in 0310: Portalkonten mit Status disabled oder anderen unbekannten Werten werden auf revoked gesetzt. Vor dem Deploy zählen, wie viele Konten betroffen sind, und dem Fachbereich mitteilen, dass diese Zugänge als entzogen geführt werden.
4. Post-Deploy: Der einmalige Nachlauf zur Umstellung der Selbstauskunft-Token auf SHA-256 (Task mhvp.letting.hash_self_disclosure_tokens oder Plattform-Admin-Endpunkt POST /api/v1/platform/maintenance/self-disclosure-token-hash) ist idempotent und unschädlich bei Wiederholung. Ob er in Produktion bereits lief, ist aus den Unterlagen nicht ersichtlich und nach dem Deploy zu prüfen oder zu wiederholen.
5. Externe API-Nutzer: Seit 1.58.0 antworten alle GET-Listen auf unbekannte Abfrageparameter mit 422 statt sie zu ignorieren. Betrifft Integrationen, Skripte und Webhook-Abnehmer, die zusätzliche Parameter senden. Vor dem Deploy Betreiber externer Clients informieren, Zugriffsprotokolle auf unbekannte Parameter prüfen. Das CRM und das Portal sind angepasst.
6. Schalter im Auslieferungszustand aus: Direktablage des Dokumenteingangs (document_intake_auto_file), automatische Buchung des Rechnungsplans (auto_posting_enabled), Sperre für virtuelle Versammlungen (hoa_virtual_basis_term_lock_enabled), Rechnungsnummernformat (INVOICE_FORMAT_RELEASED), Demo-Mandant (MHVP_DEMO_SEED), XRechnung-Prüfung im CI (MHVP_KOSIT_ENABLED). Weiterhin offen bleiben die Schalter der Wellen 4 bis 10 (unter anderem MHVP_WEBAUTHN_ENABLED).
7. Neuer Beat-Job: Portalkonto-Status (abgelaufene Einladungen auf expired, gesperrte auf locked). Prüfen, dass der Worker die neuen Beat-Einträge geladen hat.
8. Die Commit-Meldung nennt einen OpenAPI-Test als grün. Externe Clients, die gegen die Schnittstelle bauen, sollten den Client nach dem Deploy neu erzeugen.

## Offene Punkte

- Entscheidungen des Betreibers: 38 Fragen, siehe docs/plans/ENTSCHEIDUNGEN-2026-10-01.md. Wichtigste Hebel: AA01-01 (Einstufung der Routen ohne Gate), AA02-01 und AA02-02 (Gate-Zuschnitt), AA12-01 und AA17-01 (Steuerberater), AA07-01, AA07-02, AA06-01, AA06-02 (Rechtsanwalt).
- Teilweise und offene Befunde, soweit keine Entscheidung nötig: Folgearbeiten Welle 14 laut Rückmeldungen. Dazu gehören CRM-Fälligkeitsliste der Prüfpunkte, Schalter send_invitation im CRM-Formular des Portalzugangs, Erlöskonto als Kontenauswahl, Workflow-Auswahl am Auftrag, Objektbezug an die übrigen G1- und G2-Routen, Plattformaudit-Seite im CRM mit BFF, Vitest für den Versand des Vermögensberichts, Leserecht für die Rechtsträger-Auswahl, Anhang-B-Läufe der Dossiers (V1).
- Prüfpunkte aus der Integration: mypy-Hinweis in portal/routers.py (provision_account), Importreihenfolge in portal/routers.py, Zeilenlänge in accounting/creditor_routers.py. Die Platzhalter-Datei zz_ab08tmp ist in alembic/versions nicht mehr vorhanden.
- Nicht belegt: Playwright-Lauf für 1.57.0 und 1.58.0, Staging-Messungen, Prüfung mit echten Geräten für Passkeys.
- Der Prüfpunkt aus Welle 11 (bank-buchen.spec.ts, CryptoError bei abweichendem Masterschlüssel in der Testdatenbank) ist weiterhin nicht abschließend geklärt.

## Verweise

- Entscheidungsliste: docs/plans/ENTSCHEIDUNGEN-2026-10-01.md
- Lückenliste: docs/plans/LUECKENLISTE-2026-10-01.md
- Offene Fragen mit Eigentümer und Gate: docs/OPEN_QUESTIONS.md (Zeilen AA01-01 bis AB12-01)
- Bericht Wellen 4 bis 10: docs/plans/BERICHT-2026-10-01-WELLEN-4-10.md
