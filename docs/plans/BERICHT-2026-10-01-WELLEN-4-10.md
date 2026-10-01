# Abschlussbericht Wellen 4 bis 10, Stand 01.10.2026

Adressat: Vorstand (Timo Müller). Gegenstand: Versionen 1.50.0 bis 1.56.0 der MH Verwaltungsplattform. Die Gates G1 bis G5 bleiben geschlossen, keine Version öffnet ein Gate. Dieser Bericht ist keine rechtliche oder steuerliche Abnahme.

## Ergebnis in Kürze

- Produktionsstand: Am 01.10.2026 um 11:45 Uhr wurde Produktion von 1.46.0 auf 1.55.0 deployt (Migrationen 0248 bis 0302). Sicherung vor dem Deploy: /srv/mhvp-backup/vor-1.55.0-20261001-114035.dump. Dauer 4 min 53 s, API nach dem Deploy gesund.
- Version 1.56.0 ist gepusht und noch nicht deployt. Sie enthält keine Migration.
- Alle neuen Schalter stehen im Auslieferungszustand auf aus (Einzelheiten unten). Ausnahme ist der Mailinhalt der Benachrichtigungen, dort bleibt der bisherige Zustand voll.
- Die Tests wurden je Paket mit Teilläufen einzelner Dateien ausgeführt. Gesamtsuiten, Playwright-Läufe und Staging-Messungen sind je Paket als nicht ausgeführt zu lesen, soweit unten nicht ausdrücklich genannt. Nachweise: docs/acceptance/PROTOKOLL-2026-10-01-WELLEN-4-7.md und die Paketergebnisse unter $SP/w4 bis $SP/w10.

## Betreiberentscheidung B27 (01.10.2026, Timo Müller)

Immoware24 ist nicht das führende Buchhaltungssystem. Die Daten aus Immoware24 werden einmalig als Grundlage ins CRM übernommen (Migrationsjournal, Eröffnungssalden, Stammdaten, Berichte). Die Buchhaltung wird später ausschließlich im CRM geführt.

Folgen: Kein Parallelbetrieb mit Rückschreiben nach Immoware24. Eine Rücknahme von Bankdatei-Importen über Immoware24 ist nicht nötig (M11-09-01 Alternative A bestätigt). Der Zustand leading_system = immoware24 am Buchungskreis bedeutet nur, dass der Buchungskreis noch nicht produktiv im CRM geführt wird, bis zur Umstellung nach Abgleich und G1 (6.9.10, D52). Offen bleibt der Zeitpunkt der Umstellung je Buchungskreis. Eigentümer: Timo Müller. Gate: G1. Quelle: docs/OPEN_QUESTIONS.md, Zeile B27.

## Versionen

### 1.50.0 (Welle 4, 16 Pakete, Migrationen 0284 bis 0288)

Inhalt: Belegmaske mit Anlagen, Erfassungsmaske für Rechnungspläne, Sammelrückmeldung bei Lastschriften, Honorarlauf mit Vorschau und PDF, Jahresübernahme der Schlussbestände als Entwurf, PDF der Gesamtabrechnung (hinter G4), geschwärzte Kopien mit Freigabe durch eine zweite Person. Zusätzlich Tickets aus der Übernahme-Checkliste, Prüfbericht und Rücknahme des Altdatenimports sowie die Korrektur der Rücknahme der Migrationen 0257 und 0278.

Tests: Je Paket Integrationstests der betroffenen Dateien (zum Beispiel Lastschriften, Dokumente, Onboarding, Positivpfade, Tickets, Sicherheits- und Geldprüfung) und Komponententests, Migrationskette bis 0288 geprüft. Nicht ausgeführt: Gesamtsuiten, Playwright, next build, einzelne Prüfungen mit Leserechten (403) und Nebenläufigkeitstests, mypy nicht vollständig.

### 1.51.0 (Welle 5, 16 Pakete, Migrationen 0289 bis 0297)

Inhalt: Mandantenexport als Hintergrundjob, optionales OpenTelemetry-Tracing, unveränderte Ablage der Bankrohdaten mit Zustimmungsablauf der finAPI-Verbindung, Honorarrechnungen mit Storno und Buchungsentwürfen hinter G1, sachliche Rechnungsprüfung mit Toleranzen je Mandant, Heizkostenimport des Messdiensts, Benachrichtigungen sofort oder täglich, Rücklagen mit Entwicklung je Jahr, Statusmodell der Abrechnungen, neue Berichtsarten des Altdatenimports.

Tests: Je Paket Teilläufe der neuen Testdateien, Migrationsrundlauf mit Kette bis 0297, einzelne Komponententests. Nicht ausgeführt: Playwright, Gesamtsuiten, Compose-Start mit Profil otel (kein Docker), Celery mit echtem Collector, in einzelnen Paketen tsc und Migrationstests.

### 1.52.0 (Welle 6, 16 Pakete, Migrationen 0298 und 0299)

Inhalt: CRM-Masken für Honorarbuchung, Rechnungsprüfung, Heizkostenimport und Rücklagen. Anmeldung mit Passkey (WebAuthn) hinter Schalter, Vertreterrolle im Portal, Sammelaktionen für Tickets, Suchindizes der Portal-Belegsuche, Messtests (Sollstellungslauf mit 1.000 Verträgen 48,3 s, Abrechnungs-PDF 1,7 s, Messwerte unter Last), erweiterte Dokumentsperren, Prüfbericht der Wellen 4 und 5.

Tests: Frontend-Läufe (vitest, tsc, eslint) mit grünem Ergebnis in den Masken-Paketen, Integrationstests für Passkey, Tickets, Portal, Dokumente und Import, Messtests mit MHVP_PERF. Nicht ausgeführt: Playwright, echte Authenticatoren, Gesamtsuiten, openapi- und api-client-Regeneration (Koordinator).

### 1.53.0 (Welle 7, 12 Pakete, Migrationen 0300 bis 0302)

Inhalt: Hash-Prüfung bei der Freigabe des KI-Antwortentwurfs, Objektprüfung der Rechnungsverknüpfungen, Sperre des Rücklagen-Anfangsbestands, serverseitige Passkey-Sperre für Portalkonten, Umstellung der Selbstauskunft-Token auf SHA-256, Aufbewahrung der Mandantenexporte, Protokollabschluss der Eigentümerversammlung im Vier-Augen-Prinzip, Entscheidungspunkt bei mehreren Rechtsträgern im Onboarding, Verifikation von Build und Playwright.

Tests: Integrationstests je Paket, Migrationstests bis 0302 (4 passed), Produktionsbuild von CRM und Portal grün, Playwright gegen das echte Backend: 3 von 3 Läufen mit 24 bestandenen Tests im Portal; CRM-Lauf mit 56 bestanden, 1 Fehler (Übergabe, isoliert danach bestanden), 3 übersprungen. Nicht ausgeführt: Playwright-Projekte Tablet und Tablet quer, Portal-vitest, Gesamtsuiten.

### 1.54.0 (Welle 8, 6 Pakete, keine Migration)

Inhalt: Sicherheitsprüfung der Passkey-Implementierung mit sieben Behebungen (docs/reviews/WEBAUTHN-2026-10-01.md), Ticket-Ereignisse bei Einzel- und Sammelaktionen, Dokumentauswahl beim Protokollabschluss, Beschlussauswahl bei der Aufbewahrung, Messung der Portal-Belegsuche, Abnahmeprotokoll der Wellen 4 bis 7 und Entscheidungsliste für den Vorstand.

Tests: Passkey-Prüfung (25 Unit-Tests, 9 Integrationstests), Tickets, Dokumente und Honorarbuchung mit Teilläufen, Messtest der Belegsuche. Nicht ausgeführt: Playwright, next build, Gesamtsuiten, echte Geräte und FIDO-Konformitätstests.

### 1.55.0 (Welle 9, 2 Pakete, keine Migration)

Inhalt: Mengenbegrenzung der Passkey-Endpunkte (429 mit Retry-After) und Einstellungsseite für Standardteam und Zuständigen der Übernahme-Tickets.

Tests: 8 Integrationstests Auth, 4 Komponententests der Einstellungskarte, 15 Tests des Einstellungsindex, tsc ohne Fehler. Nicht ausgeführt: Gesamtsuite, Playwright, next build.

### 1.56.0 (Welle 10, 5 Pakete, keine Migration, nicht deployt)

Inhalt: Objektzuordnung in den Restbereichen (Mandatsvorschläge, Abgleichberichte, Bankverknüpfungen, Immoware24-Importe), täglicher finAPI-Zustimmungsabgleich hinter Mandantenschalter, Inhaltsmodus der Benachrichtigungsmails, Sicherheits- und Geldflussprüfung der Wellen 7 bis 9 (docs/reviews/REVIEW-W79-2026-10-01.md) mit Härtungen bei Rücklagen, Exporten, Protokollabschluss und Honorarbuchung, Handbuch und Regelindex.

Tests: Teilläufe je Paket (unter anderem Zustimmungsabgleich 3 passed, Benachrichtigungsinhalt 2 Komponententests, Prüfbefunde 5 passed, Hilfeindex geprüft). Nicht ausgeführt: Gesamtsuiten, Playwright, Frontend-Tests in den Paketen ohne Frontendänderung, openapi- und api-client-Regeneration (Koordinator).

## Deploy-Hinweise

Stand: Produktion läuft auf 1.55.0 mit allen Migrationen bis 0302. Die Migrationen 0284 bis 0302 sind damit eingespielt. Für den Betrieb gilt:

- Migrationen 0284 bis 0302 (1.50.0 bis 1.53.0): 0284, 0286 sind ohne Schemaänderung (noop), 0297 ergänzt Enum-Werte, 0299 legt Trigramm-Indizes an. Rücksprung nur über die Sicherung vor dem Deploy, nicht über Downgrade im laufenden Betrieb.
- Version 1.56.0: keine Migration, Deploy ohne Schemaänderung. Vor dem Deploy neue Sicherung nach Betriebsablauf (docs/runbooks/deploy.md).
- Neue Schalter, alle im Auslieferungszustand aus:
  - Passkeys: MHVP_WEBAUTHN_ENABLED (Standard aus) mit MHVP_WEBAUTHN_RP_ID und MHVP_WEBAUTHN_ORIGINS. Freigabe bleibt Betreiberentscheidung.
  - Tracing: MHVP_OTEL_ENDPOINT (Standard aus), Compose-Profil otel.
  - finAPI-Zustimmungsabgleich: Mandantenschalter, Standard aus (ab 1.56.0).
  - Aufbewahrung der Mandantenexporte: Standard keine automatische Löschung.
  - Honorarbuchung: Buchungsentwürfe nur hinter G1 und nur mit hinterlegter Kontenzuordnung je Mandant, ohne Vorgabe.
  - Mailinhalt der Benachrichtigungen (ab 1.56.0): Standard voll, also unverändertes Verhalten. Umstellung auf Hinweis ohne Inhalt ist eine bewusste Einstellung unter Einstellungen, Benachrichtigungen.
- Einmaliger Nachlauf: Umstellung der Selbstauskunft-Token aus Altzeilen auf SHA-256. Auslösung über den idempotenten Task mhvp.letting.hash_self_disclosure_tokens oder den Plattform-Admin-Endpunkt POST /api/v1/platform/maintenance/self-disclosure-token-hash. Bereits versandte Links bleiben gültig. Wiederholung ist unschädlich. Ob der Lauf in Produktion bereits erfolgt ist, ist aus den Unterlagen nicht ersichtlich und zu prüfen.
- Weitere einmalige Nachläufe sind in den Unterlagen nicht benannt.

## Verweise

- Entscheidungsliste mit Empfehlung und drei Alternativen je Frage: docs/plans/ENTSCHEIDUNGEN-2026-10-01.md. Die vier Prioritäten für die nächste Sitzung stehen dort am Anfang.
- Offene Fragen mit Eigentümer und Gate: docs/OPEN_QUESTIONS.md.
- Testnachweise Wellen 4 bis 7: docs/acceptance/PROTOKOLL-2026-10-01-WELLEN-4-7.md.
- Prüfberichte unter docs/reviews:
  - SECURITY-2026-10-01.md (Sicherheit Wellen 2 und 3)
  - MONEY-2026-10-01.md (Geldpfade Wellen 2 und 3)
  - SECRETS-2026-10-01.md (Feldverschlüsselung)
  - REVIEW-W45-2026-10-01.md (Wellen 4 und 5)
  - REVIEW-W6-2026-10-01.md (Welle 6)
  - WEBAUTHN-2026-10-01.md (Passkey-Protokollprüfung)
  - REVIEW-W79-2026-10-01.md (Wellen 7 bis 9)

## Abschlussverifikation 01.10.2026 (Welle 11)

- Builds: web-crm und web-portal fehlerfrei (170 s und 65 s).
- Playwright Portal gegen Backend: 24 von 24 Specs grün, keine Korrektur nötig.
- Playwright CRM gegen Backend: 51 grün, 6 bedingt übersprungen (fehlende Seed-Daten), bank-buchen.spec.ts rot wegen eines Fehlers der Testumgebung (GET /banking/accounts 500 CryptoError, mutmaßlich Konten mit abweichendem Masterschlüssel in der Testdatenbank). Derselbe Spec lief am Vormittag in Welle 7 grün; die Ursache ist nicht abschließend bewiesen und als Prüfpunkt offen. Kein Code geändert.
- Gesamtsuite der API für 1.56.0: 3.795 Tests grün; Vitest CRM 1.865, Portal 179 grün.
