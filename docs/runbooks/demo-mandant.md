# Runbook: Demo-Mandant (`make seed-demo`)

Stand: 01.10.2026 (Welle 16, Paket AE36). Quelle: MASTER-PROMPT Abschnitt 17 (Befehle), Regel `docs/rules/AE36-DEMO.md`, Frage AA15-01 in `docs/OPEN_QUESTIONS.md`.

## Zweck

Ein Mandant mit rein erfundenen Daten für Vorführung, Schulung und Tests der Oberfläche. Er enthält keine echte Person, keine echte Firma und kein echtes Konto und ist kein Testmandant für Fachabnahmen: Annex-D-Fälle werden mit eigenen Sollwerten geprüft (`docs/acceptance/`), nicht an diesem Datenbestand.

## Aufruf

```
export MHVP_DEMO_ADMIN_PASSWORD='<Passwort des Demo-Administrators nach Richtlinie, nicht im Repository>'
make seed-demo                  # Compose-Entwicklungsstack, API unter http://api:8000
make seed-demo LOCAL=1          # lokal: uv run python -m mhvp.platform.demo_seed gegen MHVP_DEMO_API_URL
```

Voraussetzungen und Schutz:

- Läuft nur in den Umgebungen `dev`, `test` und `staging` (`MHVP_ENV`) und nur mit `MHVP_DEMO_SEED=1` (das Makefile setzt es). In Produktion bricht der Befehl mit Fehlercode 2 ab.
- Das Passwort des Demo-Administrators `demo-admin@example.org` kommt aus `MHVP_DEMO_ADMIN_PASSWORD`; ohne Passwort bricht der Befehl ab.
- Eine laufende API unter `MHVP_DEMO_API_URL` (Standard `http://localhost:8000`); die Daten entstehen über die öffentliche API und den Importdienst des Bankings.
- Ein zweiter Aufruf ändert nichts: Der Mandant `demo-muster` existiert dann bereits. Hat ein früher angelegter Demo-Mandant das Kennzeichen noch nicht, setzt der Aufruf es nach (Migration 0392 setzt es für `demo-muster` ebenfalls).

## Inhalt

3 Objekte (WEG) mit 40 Einheiten, 60 Kontakte (40 Eigentümer, 20 weitere Personen und Dienstleister), 36 Buchungsentwürfe (12 Monate je Objekt), 200 Bankumsätze. Es wird nichts gebucht, kein Gate G1 bis G5 geöffnet und kein Plattformschalter eingeschaltet.

Erfundene Angaben: Namen "Max Beispiel", "Anna Beispiel007" und Firmen "Muster Hausmeisterdienst"; Anschrift "Musterstraße 10, 20, 30"; E-Mail-Adresse des Administrators unter `example.org`. Alle IBANs (drei eigene Konten, 200 Gegenkonten) werden erzeugt: Bankleitzahl 00000000, laufende Kontonummer, gültige Prüfziffern nach ISO 13616. Dokumentierte Beispiel-IBANs echter Institute kommen nicht vor. Vor dem Schreiben prüft `assert_synthetic_ibans`, dass jede IBAN diesem Muster entspricht, sonst bricht der Aufruf ab. Die Bankleitzahl 00000000 ist nach bestem Wissen keinem Institut zugeordnet (Annahme A-AE36-03, gegen die Bankleitzahlendatei der Bundesbank zu prüfen).

## Kennzeichen und Ausschluss

Der Mandant trägt `tenant.is_demo`. Er erscheint auf der Seite Plattform mit dem Merkmal "Demo-Mandant". Ausgeschlossen sind (Regel AE36-DEMO):

| Bereich | Wirkung für den Demo-Mandanten |
| --- | --- |
| Plattformabrechnung | keine Lizenz, keine Nutzungszählung, keine Abrechnungsvorschau; zählt nicht als produktiver Mandant |
| Exporte | Mandantenexport, Journal-Export, DATEV-Buchungsstapel, Prüfexport: Antwort 409 `MHVP-DEMO-0001` |
| Statistiken | Betriebskennzahlen und Mandantenzahl der Skalierungsmessung ohne Demo-Mandanten |

Kennzeichen nachträglich setzen oder entfernen: Seite Plattform, Schaltfläche am Mandanten, oder `PUT /api/v1/platform/tenants/{id}/demo` mit `{"is_demo": true}`. Setzen ist nicht möglich, solange eine Freigabestufe des Mandanten geöffnet ist (`MHVP-DEMO-0002`).

## Prüfung nach dem Aufruf

1. Anmelden als `demo-admin@example.org`; Objekte, Einheiten, Kontakte und Bankumsätze sind sichtbar, Buchungen stehen im Status Entwurf.
2. Als Plattformadministrator auf der Seite Plattform: "Demo-Mandant" am Mandanten; `GET /api/v1/platform/ops/metrics` weist `tenants_demo` mit mindestens 1 aus und zählt den Mandanten nicht in `tenants_active`.
3. Ein Export im Demo-Mandanten (zum Beispiel DATEV) antwortet mit 409 und Code `MHVP-DEMO-0001`.

## Zurücksetzen und Entfernen

Die Plattform löscht keine Mandanten. Zum Zurücksetzen in Staging die Datenbank aus der Sicherung wiederherstellen (`backup.md`) oder den Mandanten sperren (`PATCH /api/v1/platform/tenants/{id}` mit Status `suspended`) und unter einem neuen Kürzel neu anlegen. Der dauerhafte Betrieb eines Demo-Mandanten in Staging und der Einsatzort sind Betreiberentscheidung (AA15-01, offen).

## Grenzen

- Der Datenbestand ist klein (200 Bankumsätze, 36 Entwürfe) und ersetzt keinen Lasttest; dafür dient der Generator `apps/api/tests/integration/perf_seed.py` (`leistungsmessung.md`).
- Ein Demo-Mandant darf keine echten Daten aufnehmen. Wer echte Daten erfassen will, legt einen neuen Mandanten an.
