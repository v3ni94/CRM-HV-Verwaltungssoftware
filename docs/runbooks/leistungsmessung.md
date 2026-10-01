# Runbook: Leistungsmessung (S16-08)

Vorgaben aus Abschnitt 16: P95 unter 300 ms bei einer Liste mit 10.000 Zeilen,
Sollstellungslauf mit 1.000 Verträgen unter 2 Minuten, Abrechnung mit 100 Einheiten unter
1 Minute, Bankabruf mit 100 Konten. Die Messungen sind Betreiberschwellen, keine Rechtsregeln.

## Durchführung

Die Tests sind mit `slow` markiert und laufen nur mit `MHVP_PERF=1`. Sie gehören nicht in den
regulären CI-Lauf, weil das Ergebnis eine ruhige Maschine mit der produktionsnahen
PostgreSQL-Version voraussetzt.

```
cd apps/api
MHVP_PERF=1 uv run pytest tests/integration/test_p15_perf.py -m slow -s --no-cov
uv run pytest tests/integration/test_m13_receivables.py -m slow -s --no-cov
```

Jede Messung schreibt eine Zeile `PERF ...` in die Ausgabe. Die Zeilen werden unten mit Datum,
Maschine und Commit eingetragen. Ein Wert aus einer geteilten Entwicklungsumgebung gilt nur
als Plausibilitätsprüfung.

## Stand der Messungen

| Vorgabe | Test | Stand |
| --- | --- | --- |
| Liste 10.000 Kontakte, P95 unter 300 ms | `test_p15_perf.py::test_list_of_10000_contacts_p95_below_300_ms` | umgesetzt, Ergebnis siehe Protokoll |
| Sollstellungslauf, 67 Objekte, 869 Einheiten, unter 2 Minuten | `test_m13_receivables.py::test_a27_receivable_run_runtime_67_properties_869_units` | vorhanden (Bestand), 1.000 Verträge nicht gesondert |
| Abrechnung mit 100 Einheiten unter 1 Minute | `test_p15_perf.py::test_statement_of_100_units_below_one_minute` | übersprungen, Lastdaten-Seed fehlt |
| Bankabruf mit 100 Konten | `test_p15_perf.py::test_bank_retrieval_of_100_accounts` | übersprungen, Lastdaten-Seed fehlt |

## Protokoll

| Datum | Maschine | Commit | Zeile |
| --- | --- | --- | --- |
| 30.09.2026 | Entwicklungsumgebung, 4 Kerne, mit 20 gleichzeitigen Läufen geteilt, nicht repräsentativ | Arbeitsstand Welle 2 | siehe unten |

`PERF contacts_list rows=10000 samples=40 median=43ms p95=73ms` (Vorgabe: P95 unter 300 ms). Die übrigen Tests sind übersprungen (Lastdaten fehlen).

## Offen

- Lastdaten-Seed für Abrechnung (100 Einheiten) und Bankabruf (100 Konten mit Konnektor-Attrappe).
- Messung auf dem Staging-Server mit produktionsnaher Datenmenge (Betreiber).
- Die Entscheidung über Partitionierung hängt an diesen Werten (ADR 0018).

## Lastdaten-Seed (S16-08)

`apps/api/tests/integration/perf_seed.py` erzeugt synthetische Daten über die öffentliche API: eine WEG mit 100 Einheiten (`seed_units`) und 100 Objekte mit je einem Bankkonto (`seed_bank_accounts`, IBAN mit gültiger Prüfziffer, fiktive Bankleitzahl). Der Test `test_seed_of_100_units_and_100_bank_accounts` schreibt die Zeile `PERF seed ...`. Die Tests für Abrechnung und Bankabruf bleiben übersprungen, bis Abrechnungsdaten (Wirtschaftsplan, Kosten) und eine Konnektor-Attrappe ergänzt sind.
