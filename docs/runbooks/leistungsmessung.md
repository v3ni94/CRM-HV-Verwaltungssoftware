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
| Abrechnung mit 100 Einheiten unter 1 Minute | `test_p15_perf.py::test_statement_of_100_units_below_one_minute` | umgesetzt mit Seed `seed_statement_data` (100 Eigentümereinheiten, Kostenbuchung), gemessen wird die Berechnung |
| Bankabruf mit 100 Konten | `test_p15_perf.py::test_bank_retrieval_of_100_accounts` | umgesetzt mit Konnektor-Attrappe (`tests/bank_connector_stub.py`, 20 Umsätze je Konto, Import über `import_finapi_transactions`); Schwelle 60 Sekunden ist eine Betreiberannahme, die Spezifikation nennt keinen Wert |

## Protokoll

| Datum | Maschine | Commit | Zeile |
| --- | --- | --- | --- |
| 30.09.2026 | Entwicklungsumgebung, 4 Kerne, mit 20 gleichzeitigen Läufen geteilt, nicht repräsentativ | Arbeitsstand Welle 2 | siehe unten |

`PERF contacts_list rows=10000 samples=40 median=43ms p95=73ms` (Vorgabe: P95 unter 300 ms). 

## Offen

- Messung auf dem Staging-Server mit produktionsnaher Datenmenge (Betreiber).
- Die Entscheidung über Partitionierung hängt an diesen Werten (ADR 0018).

## Lastdaten-Seed (S16-08)

`apps/api/tests/integration/perf_seed.py` erzeugt synthetische Daten über die öffentliche API: eine WEG mit 100 Einheiten (`seed_units`) und 100 Objekte mit je einem Bankkonto (`seed_bank_accounts`, IBAN mit gültiger Prüfziffer, fiktive Bankleitzahl). Der Test `test_seed_of_100_units_and_100_bank_accounts` schreibt die Zeile `PERF seed ...`. `seed_statement_data` ergänzt eine WEG mit 100 Eigentümern, Ertrags und Kostenkonto, einer gebuchten Kostenzahlung und dem Abrechnungsentwurf 2025. Die Attrappe `StubBankConnector` erfüllt das Protokoll `BankConnector` ohne Netzwerkzugriff.

## Messwerte Welle 4 (01.10.2026)

Entwicklungsumgebung, 4 Kerne, mit 20 gleichzeitigen Läufen geteilt, nicht repräsentativ. Aufruf: `MHVP_PERF=1 uv run pytest tests/integration/test_p15_perf.py -s --no-cov`.

```
PERF contacts_list rows=10000 samples=40 median=75ms p95=129ms
PERF seed units=100 bank_accounts=100 seconds=22.1
PERF statement_calculate units=100 seconds=1.8
PERF bank_retrieval accounts=100 transactions=2000 seconds=18.3
```

Die Abrechnungsmessung umfasst nur die Berechnung des Entwurfs (ohne Sollstellungen und Zahlungen je Einheit) und ersetzt keine Messung mit produktionsnahen Daten. Der Sollstellungslauf mit 1.000 Verträgen ist weiterhin nicht gesondert gemessen.

## Welle 6, Paket U08: Sollstellungslauf mit 1.000 Verträgen und Abrechnungsausgabe

Neue Messtests in `apps/api/tests/integration/test_u08_perf.py` (nur mit `MHVP_PERF=1`):

| Vorgabe | Test | Stand |
| --- | --- | --- |
| Sollstellungslauf mit genau 1.000 Verträgen (10 Objekte, 2 Komponenten je Vertrag, 2.000 Positionen), Vorschau und Buchung unter 2 Minuten | `test_receivable_run_with_1000_contracts_below_two_minutes` | gemessen, siehe unten |
| Abrechnung über `calculate` hinaus: interne Freigabe, Gesamtabrechnung als PDF auf dem Briefbogen und 100 Einzelabrechnungen als PDF, zusammen unter 1 Minute (Betreiberannahme) | `test_statement_output_of_100_units_below_one_minute` | gemessen, siehe unten |

Aufruf: `MHVP_PERF=1 uv run pytest tests/integration/test_u08_perf.py -s --no-cov`. Der Bestand wird mit
dem Seed aus `test_m13_receivables.py::_load_world` aufgebaut (Konstanten per Patch auf 1.000 und 10).

Messwerte 01.10.2026 (unter Last: 4 Kerne, gleichzeitig durch etwa 16 Agenten belegt, nicht repräsentativ):

```
PERF receivable_seed contracts=1000 seconds=7.4
PERF receivable_run contracts=1000 items=2000 preview=4.9s post=43.3s total=48.3s
PERF statement_output units=100 total_pdf=0.1s unit_pdfs=1.5s unit_pages=100 all=1.7s
```

Beide Vorgaben sind eingehalten (Lauf 48,3 s gegen 120 s, Ausgabe 1,7 s gegen 60 s). Es wurde kein Engpass
über 2 Minuten festgestellt, daher keine Index- oder Abfrageänderung. Die Buchung (43,3 s) ist der
größere Anteil und der erste Kandidat, falls die Staging-Messung höhere Werte zeigt.

## Welle 8, Paket W04: Portal-Belegsuche (U07, M25-06)

Aufruf: `MHVP_PERF=1 uv run pytest tests/integration/test_u07_document_search_perf.py -s --no-cov` gegen die vollständige Migrationskette.

Messwert 01.10.2026 (Entwicklungsumgebung, 4 Kerne, geteilt, nicht repräsentativ): `PERF portal_receipt_search docs=5000 median=3.6ms max=9.5ms` (Schwelle 300 ms).

Befund zur Indexnutzung (EXPLAIN im Test): Unter Row Level Security nutzt die Abfrage den Mandantenindex `ix_document_tenant_created_at`, nicht die Trigramm-Indizes. Ursache: `lower()` und `LIKE` sind in PostgreSQL nicht als leakproof markiert, daher dürfen sie bei aktiver Mandantenrichtlinie nicht als Indexbedingung vorgezogen werden. Ohne diese Schranke (Probe auf einer temporären Kopie mit denselben Indizes) wählt der Planer einen BitmapOr über beide Trigramm-Indizes, sie sind also korrekt definiert. Die Abfrage lässt sich ohne Schemaänderung nicht anpassen; bei 5.000 Belegen je Mandant genügt der Mandantenindex mit Filter. Ob bei deutlich größeren Beständen eine Anpassung nötig wird (zum Beispiel leakproof-Wrapperfunktion, Betreiberentscheidung mit Superuser-Rechten), ist mit Staging-Daten zu klären.
