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
- Die Entscheidung über Partitionierung hängt an diesen Werten (ADR 0018, ergänzt durch ADR 0021).

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

## Detailseiten und wiederholbarer Nachweis (GA12-07)

Vorgabe aus Abschnitt 16: Detailseiten unter 500 ms (P95). Der Test `apps/api/tests/integration/test_ga12_perf.py` misst die Detailendpunkte eines Objekts (`/properties/{id}`, 30 Einheiten), eines Eigentümervertrags (`/contracts/{id}`) und eines Tickets (`/tickets/{id}`, 12 Tickets im Mandanten) mit je 40 Abrufen nach einem Vorlauf. Aufruf:

```
cd apps/api
MHVP_PERF=1 uv run pytest tests/integration/test_ga12_perf.py -m slow -s --no-cov
```

Jede Messung schreibt eine Zeile `PERF property_detail|contract_detail|ticket_detail ... p95=...ms target=500ms`.

Wiederholung in CI: der Workflow `.github/workflows/perf.yml` läuft wöchentlich (montags 03:17 UTC) und manuell (`workflow_dispatch`, Eingabe Schwelle in Sekunden). Er setzt `MHVP_PERF=1`, führt diesen Test und `test_p15_perf.py` aus und schreibt die `PERF`-Zeilen in die Job-Zusammenfassung. Die Regressionsschwelle ist mit 1 Sekunde (Variable `MHVP_PERF_DETAIL_LIMIT`) bewusst großzügig, weil geteilte Runner schwanken; sie fängt grobe Rückschritte ab (zum Beispiel N+1 Abfragen), nicht den Wert von 500 ms. Die Prüfung gegen 500 ms erfolgt auf dem Staging-Server mit `MHVP_PERF_DETAIL_LIMIT=0.5`.

Messwerte 01.10.2026 (Entwicklungsumgebung, 4 Kerne, mit etwa 20 gleichzeitigen Läufen geteilt, nicht repräsentativ):

```
PERF property_detail samples=40 median=36ms p95=48ms target=500ms
PERF contract_detail samples=40 median=67ms p95=96ms target=500ms
PERF ticket_detail samples=40 median=81ms p95=125ms target=500ms
```

Offen: Messung mit produktionsnahem Bestand (Betreiber, Staging), siehe oben.

## Große Listen: Journal und Bankumsätze bei 100.000 Zeilen (GA12-08)

Grundlage für ADR 0021 (Jahrespartitionierung von `journal_entry` und `bank_transaction`). Der Test
`test_large_journal_and_bank_lists_p95` in `apps/api/tests/integration/test_ga12_perf.py` erzeugt in einem
Mandanten 100.000 gebuchte Buchungen mit 200.000 Zeilen (fünf Buchungsjahre 2022 bis 2026) und 100.000
Bankumsätze (`perf_seed.py`: `seed_journal_entries`, `seed_bank_transactions`) und misst je acht Listenabfragen
in zwei Runden: direkt nach dem Massenimport (Statistik nicht erneuert) und nach `ANALYZE`. Aufruf:

```
cd apps/api
MHVP_PERF=1 uv run pytest tests/integration/test_ga12_perf.py -m slow -s --no-cov -k large
```

Die CI-Schwelle ist 1 Sekunde (`MHVP_PERF_LIST_LIMIT`), der Zielwert 300 ms (P95) wird auf dem Staging-Server
mit `MHVP_PERF_LIST_LIMIT=0.3` geprüft. Der Wächter `journal_line_guard` wird vom Generator auf der
Testdatenbank für die Dauer des Ladens deaktiviert und im `finally` wieder eingeschaltet (Begründung im
ADR 0021, Befund 3). Nie gegen eine produktive Datenbank verwenden.

Messwerte 01.10.2026 (Entwicklungsumgebung, 4 Kerne, mit anderen Läufen geteilt, nicht repräsentativ; je 20
Abrufe, Datenbank mhvp_p09; Laden von 100.000 Buchungen, 200.000 Zeilen und 100.000 Umsätzen in 14,2 s):

| Abfrage | Median ohne frische Statistik | P95 ohne frische Statistik | Median nach ANALYZE | P95 nach ANALYZE |
| --- | --- | --- | --- | --- |
| Journal Seite 1 (100 je Seite) | 64 ms | 133 ms | 28 ms | 31 ms |
| Journal Seite 900 | 109 ms | 119 ms | 86 ms | 94 ms |
| Journal Jahresfilter 2024 (gebucht) | 42 ms | 100 ms | 40 ms | 63 ms |
| Journal Monatsfilter 03.2024 | 88 ms | 194 ms | 24 ms | 26 ms |
| Bankumsätze Seite 1 (200 je Seite) | 99 ms | 111 ms | 80 ms | 91 ms |
| Bankumsätze Offset 90.000 | 347 ms | 404 ms | 180 ms | 201 ms |
| Bankumsätze Jahresfilter 2024 | 84 ms | 111 ms | 46 ms | 55 ms |
| Bankumsätze Status neu (10 Prozent) | 85 ms | 96 ms | 68 ms | 84 ms |

Auswertung: Mit aktueller Statistik liegen alle Abfragen unter 300 ms (P95). Ohne aktuelle Statistik
überschreitet nur der tiefe Offset der Bankumsatzliste die Vorgabe (404 ms). Die Pläne (EXPLAIN ANALYZE, 100.000
Zeilen) zeigen: Das Journal nutzt nach `ANALYZE` den Unique-Index `(tenant_id, ledger_id, fiscal_year,
number)` für die Sortierung (erste Seite 0,3 ms, Zeilen 90.000 bis 90.100 78 ms, Gesamtzähler 22 ms);
die Bankumsatzliste sortiert mangels passenden Index alle Umsätze des Mandanten (43 ms erste Seite, 189 ms bei
Offset 90.000). Die Kosten wachsen bei beiden linear mit der Zeilenzahl; die Messung belegt keine Aussage für
10 Millionen Zeilen.

Hinweise für den Betrieb:

- Nach Massenimporten (Immoware24-Übernahme, Kontoauszugsimport) `ANALYZE` auf `journal_entry`,
  `journal_line` und `bank_transaction` ausführen, bis Autovacuum nachgezogen hat.
- Befund Wächterfunktion: `journal_line_guard` verbraucht je eingefügter Zeile Zeit proportional zur Größe von
  `journal_entry` (3,4 ms je Zeile bei 20.000 Buchungen im Mandanten, gemessen). Ein Massenimport von 200.000
  Zeilen über die normale Schreibstrecke ist damit nicht praktikabel. Korrektur nur über eine eigene Migration
  mit Tests der Wache und Freigabe der Geschäftsführung (ADR 0021, Folgen).
- Offen: Messung mit 1, 5 und 10 Millionen Zeilen, mit 10 und 50 Mandanten und mit mehreren Celery-Workern
  gegen dieselbe Queue (Messplan in ADR 0021, Zeitpunkt vor G5, Frage AC09-01). Bis dahin ist die Zielgröße
  Phase 4 aus Abschnitt 16 nicht nachgewiesen.

## Welle 15, Paket AD01: Wächterfunktion und Index der Bankumsatzliste

- Migration 0346 ersetzt den Rumpf von `mhvp_journal_line_guard` (gleiche Regeln B02 und B03, getrennte Zweige für INSERT, UPDATE und DELETE, kein `COALESCE` im WHERE) und legt `ix_bank_transaction_booking_date (tenant_id, booking_date)` an. Downgrade stellt den Rumpf aus 0010 wieder her.
- Nachweis Plan (Test `test_ad01_line_guard.py::test_guard_lookup_uses_primary_key_index`, generischer Plan wie in PL/pgSQL, App-Rolle mit RLS): neu `Index Scan using pk_journal_entry`, `Index Cond: (id = $1)`; alt `Index Cond` nur auf `tenant_id`, `id = COALESCE($1, $2)` als Filter. Das bestätigt die Ursache des Befunds aus ADR 0021.
- Der Generator `seed_journal_entries` schaltet den Wächter nicht mehr ab (Entwürfe, Zeilen, dann eine Buchung aller Entwürfe). Lasttest `test_bulk_load_200k_lines_with_guard_active` (nur `MHVP_PERF=1`, Schwelle `MHVP_PERF_GUARD_LIMIT`, Vorgabe 300 s). Messwert nachher: in Welle 15 nicht abgeschlossen (Lauf auf geteilter Maschine nach Fristende abgebrochen). Vorher: 3,4 ms je Zeile bei 20.000 Buchungen, 200.000 Zeilen nach mehr als 9 Minuten abgebrochen.
- ANALYZE nach Massenimporten: Die App-Rolle darf `ANALYZE` nicht ausführen (geprüft: `WARNING: permission denied to analyze "bank_transaction", skipping it`; Eigentümer ist `mhvp_migrator`). Keine Rechteausweitung. Vorgesehen ist ein Wartungsjob über eine Wartungsverbindung mit Eigentümerrechten außerhalb des Workers (zum Beispiel zeitgesteuert auf dem Datenbankhost: `ANALYZE journal_entry, journal_line, bank_transaction` nach CAMT-Import und Immoware24-Vollimport mit mehr als 10.000 geschriebenen Zeilen, sonst nächtlich). Bis zur Umsetzung manuell durch den Betreiber; Autovacuum zieht ohnehin nach.
