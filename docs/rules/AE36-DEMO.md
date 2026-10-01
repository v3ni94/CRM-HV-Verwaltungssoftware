# AE36-DEMO: Demo-Mandant mit Kennzeichen und Ausschluss (AA15-01)

- **ID:** AE36-DEMO
- **Geltungsbereich:** Mandanten mit `tenant.is_demo` (Migration 0392), insbesondere der Demo-Mandant `demo-muster` aus `make seed-demo`. Alle anderen Mandanten sind unverändert.
- **Art:** Produktschutz (strengerer interner Standard, keine Rechtspflicht). Die Entscheidung, ob ein dauerhafter Demo-Mandant in Staging gewünscht ist, bleibt offen (AA15-01, Eigentümer Betreiber).
- **Quellenstatus (Anhang C):** keine Rechtsnorm. Die Behandlung steuerlicher Aufzeichnungen aus einem Demo-Mandanten ist keine Rechtsfrage dieser Regel, weil der Mandant nur erfundene Daten enthält.
- **Abnahmefall:** kein Fall aus Anhang D; Tests `apps/api/tests/integration/test_ae36_demo_scale.py`, `test_ga12_demo_seed.py`, `test_ae40_review_w16.py`, `apps/api/tests/unit/test_ae36_scale.py`.

## Regel

1. Ein Demo-Mandant enthält nur erfundene Daten. `make seed-demo` erzeugt sie mit erfundenen Namen (Max Beispiel, Musterstraße) und rein synthetischen IBANs der Bankleitzahl 00000000 mit gültigen Prüfziffern. Die Selbstprüfung `assert_synthetic_ibans` bricht vor dem Schreiben ab, wenn eine andere IBAN auftaucht. Es gibt keine Gleitkommabeträge, es wird nichts gebucht (nur Entwürfe), kein Gate wird geöffnet.
2. Das Kennzeichen wird beim Anlegen gesetzt (`POST /platform/tenants` mit `is_demo`, `make seed-demo`) oder nachträglich durch einen Plattformadministrator (`PUT /platform/tenants/{id}/demo`, Oberfläche Plattform). Setzen ist nur möglich, solange keine Freigabestufe G1 bis G5 des Mandanten geöffnet ist (`MHVP-DEMO-0002`): Ein Mandant mit geöffneter Stufe arbeitet mit echten Daten. Jede Änderung steht im Plattformaudit (`tenant_demo_flag_changed`).
3. Ausgeschlossen aus der Plattformabrechnung: keine Lizenz (`POST /platform/licenses`), keine Nutzungszählung (`POST /platform/tenants/{id}/usage`, nächtlicher Job `platform-usage-daily` und Monatsjob), keine Abrechnungsvorschau; die Bereitschaftsansicht zeigt Nullwerte und `demo: true`. Ein Demo-Mandant zählt nicht als produktiver Mandant.
4. Ausgeschlossen aus Exporten: vollständiger Mandantenexport (`POST /tenant/export-jobs`), Mandantenexport-Antrag der Plattform, Journal-Export, DATEV-Buchungsstapel und Prüfexport. Antwort 409 `MHVP-DEMO-0001`, bevor ein Buchungskreis geprüft wird.
5. Ausgeschlossen aus Statistiken: die Betriebskennzahlen (`/platform/ops/metrics`) zählen Mandanten und Fachwerte ohne Demo-Mandanten (`tenants_active`, Fehlerzähler), `tenants_demo` weist sie getrennt aus; die mandantenübergreifende Arbeitsansicht der Plattformadministratoren (`/platform/overview`) liest keinen Demo-Mandanten. Die Zeilen- und Größenwerte der Skalierung sind physisch und enthalten die Tabellen des Demo-Mandanten (Regel AE36-SCALE).
6. Nicht ausgeschlossen: Anmeldung, Oberfläche, Fachfunktionen innerhalb des Mandanten, nächtliche Mandantenjobs. Gate-Regeln (G1 bis G5) gelten unverändert; der Demo-Mandant hat sie geschlossen.
7. Eine Freigabestufe eines Demo-Mandanten wird nicht geöffnet: Die Genehmigung eines Antrags (`POST /platform/tenants/{id}/release-gates/requests/{rid}/approve`) antwortet 409 `MHVP-DEMO-0001`, der Antrag bleibt beantragt (Review W16, AE40-1). Für echten Betrieb ist zuerst das Kennzeichen zu entfernen.

## Offene Punkte

- Dauerhafter Demo-Mandant in Staging und Einsatzort: Betreiberentscheidung AA15-01 (Vermerk: technisch vorbereitet, Welle 16, AE36).
- Die Bankleitzahl 00000000 ist keinem Institut zugeordnet (Annahme A-AE36-03, gegen die Bankleitzahlendatei der Bundesbank zu prüfen).

## Änderungsgrund

Betreiberliste vom 01.10.2026, Punkt 27 (AA15-01): Demo-Mandant mit Kennzeichen, Ausschluss aus Abrechnungen, Exporten, DATEV und Statistiken; `make seed-demo` ohne reale Namen und IBANs.
