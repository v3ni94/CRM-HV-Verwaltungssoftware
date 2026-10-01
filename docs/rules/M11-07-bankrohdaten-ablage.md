# Regel M11-07: Ablage der Bankrohdaten und Aufbewahrung

* ID: M11-07
* Geltungsbereich: Mandant, Banking (Dateiimport CAMT.053/MT940, finAPI-Abruf), `mhvp.banking.raw_archive`.
* Quellenstatus: Spezifikation 8.2 (10 Jahre) als Fachliche Umsetzung; die maßgebliche Aufbewahrungsklasse bleibt Offene Entscheidung (V17, OPEN_QUESTIONS M11-03, P09-01, T03-01). Keine Rechtsnorm als verifiziert zitiert.
* Regel: Jede Bankdatei und jede finAPI-Antwort eines Abrufs wird unverändert unter `bank/<mandant>/<konto>/<datum>.<ext>` abgelegt (Konto: Bankkonto der Plattform, Datum: Abrufdatum, Erweiterung aus xml, json, csv, sta, mt940, txt) und als Dokument (Quelle bank_raw) mit dem Aufbewahrungsprofil der Klasse `accounting_records` (10 Jahre, Fristbeginn Ende des Anlagejahres) indiziert. Zweite Ablage am selben Tag: Suffix `-2`, `-3`. Nie überschreiben. Ein Speicherfehler wird protokolliert und bricht den Import nicht ab.
* Abnahmefall: Anhang D D39 (Bankimport mit Nachweis); Test `tests/integration/test_t03_bank_raw_consent.py`.
* Änderungsgrund: Lückenliste 30.09.2026, M11-07.
