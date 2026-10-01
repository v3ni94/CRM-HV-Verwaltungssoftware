# ADR 0021: Skalierung Phase 4, Jahrespartitionierung von journal_entry und bank_transaction

- Status: Proposed, Entscheidung des Betreibers zu Zielgrößen und Zeitpunkt offen (AC09-01)
- Date: 01.10.2026

## Context

Abschnitt 16 (Skalierung) nennt als Zielgröße Phase 4 50 Mandanten, 50.000 Einheiten und
10 Millionen Buchungszeilen sowie eine für Jahrespartitionierung vorbereitete Datenbank.
ADR 0018 legt die Entwurfsregeln fest und verschiebt den Umbau. Dieses ADR ergänzt ADR 0018
um die Ist-Analyse des Schemas, die Messwerte bei 100.000 Zeilen je Tabelle (Befund GA12-08),
die Alternativen und die Auslöser. Es ändert kein Schema; Migration 0342 ist ein Platzhalter.

Gegenüber ADR 0018 verschiebt sich der Blick: Die Liste der Buchungen liest `journal_entry`
(Kopfzeile mit `booking_date`), nicht `journal_line`. `journal_line` trägt kein Datum. Eine
Partitionierung der Kopfzeile ist die Voraussetzung für jede Jahresablage der Buchungen, die
Zeilen müssten ihr folgen.

### Ist-Analyse (Stand Migration 0333, Datenbank mhvp_p09)

Messung mit 100.000 Buchungen (200.000 Zeilen) und 100.000 Bankumsätzen in einem Mandanten,
verteilt auf fünf Buchungsjahre (Generator `tests/integration/perf_seed.py`):

| Tabelle | Daten | Indizes |
| --- | --- | --- |
| `journal_entry` | 33 MB | 58 MB |
| `journal_line` | 45 MB | 37 MB |
| `bank_transaction` | 21 MB | 28 MB |

Hochrechnung linear auf 10 Millionen Buchungszeilen (etwa 5 Millionen Buchungen bei zwei
Zeilen je Buchung, Annahme des Generators): `journal_entry` rund 1,6 GB Daten und 2,9 GB
Indizes, `journal_line` rund 2,2 GB und 1,9 GB. Das ist für PostgreSQL keine Größe, die allein
eine Partitionierung erzwingt; die Hochrechnung ist eine Annahme und kein Messwert.

Indizes `journal_entry`: Primärschlüssel `id`, Unique `(ledger_id, id)`, Unique
`(tenant_id, ledger_id, fiscal_year, number)`, Unique `reverses_id` (teilweise), Unique
`(tenant_id, ledger_id, idempotency_key)` (teilweise), `(tenant_id, ledger_id, status)`,
`(tenant_id, ledger_id, booking_date)`, `(tenant_id, bank_transaction_id)` (teilweise),
`(tenant_id, ledger_id)` bei `auto_review_pending`. `journal_line`: Primärschlüssel, `journal_entry_id`,
`account_id`. `bank_transaction`: Primärschlüssel, Unique `(tenant_id, property_bank_account_id,
bank_reference)` (teilweise), `(tenant_id, property_bank_account_id, hash)`,
`counterpart_iban_fingerprint`. Es gibt keinen Index auf `bank_transaction(tenant_id,
booking_date)`; die Standardliste sortiert aber nach `booking_date`.

Fremdschlüssel auf die Tabellen (aus `pg_constraint`, 01.10.2026):

- auf `journal_entry(id)`: 22 Fremdschlüssel aus 19 Tabellen (Offene Posten und Tilgungen,
  Rechnungen, Zahlungsaufträge, Mahnfälle, Verwaltergebühren, WEG-Kostenpositionen, Darlehen,
  Rücklagenbewegungen, Schadenpositionen, Sollstellungspositionen, Migration, Buchungsnotizen,
  Prüfpunkte, Kontierungsentscheidungen, `journal_line` und die Selbstbezüge `reverses_id`,
  `reversed_by_id`);
- auf `bank_transaction(id)`: 9 Fremdschlüssel aus 8 Tabellen (Klärungsfälle, Lastschriftaufträge,
  Rechnungsverknüpfung, Zahlungsaufträge, Kontierungsentscheidungen, Prüfpunkte der
  Automatik, Migration, Selbstbezüge für Doppelumsatz und Umbuchungspaar);
- auf `journal_line(id)`: keiner. `journal_entry.bank_transaction_id` ist bewusst ohne
  Fremdschlüssel angelegt.

Trigger: `journal_entry_guard` (Unveränderbarkeit gebuchter Buchungen), `journal_entry_balanced`
(verzögert, Soll gleich Haben), `journal_line_guard` (Zeilen gebuchter Buchungen, Konto des
Buchungskreises). Sie müssen je Partition vorhanden sein (Trigger auf der Elterntabelle wirken
bei Partitionierung für Zeilentrigger seit PostgreSQL 13 auf die Partitionen; vor dem Umbau
auf der eingesetzten Version zu prüfen).

RLS: beide Tabellen tragen die Richtlinien `tenant_access` und `tenant_isolation` mit FORCE
(`tenant_rls_statements()`, ADR 0002). Bei einer partitionierten Tabelle gelten die
Richtlinien der Elterntabelle nur für Zugriffe über die Elterntabelle; Zugriffe direkt auf eine
Partition prüfen sie nicht. Die Laufzeitrolle darf deshalb keine Rechte auf Partitionen
erhalten, oder jede Partition erhält dieselben Richtlinien. `tenant_rls_statements()` ist dafür
noch nicht geprüft (offen aus ADR 0018).

### Messwerte bei 100.000 Zeilen

Entwicklungsumgebung, 4 Kerne, geteilt mit weiteren Läufen, nicht repräsentativ. Aufruf und
Tabelle siehe `docs/runbooks/leistungsmessung.md` (Abschnitt GA12-08). Zusammenfassung P95:

- Journal (100 Zeilen je Seite): erste Seite 31 ms, Seite 900 (Tiefenzugriff) 94 ms, Jahresfilter
  63 ms, Monatsfilter 26 ms, jeweils nach ANALYZE; ohne frische Statistik (direkt nach einem
  Massenimport) 100 bis 194 ms.
- Bankumsätze (200 Zeilen je Seite): erste Seite 91 ms, Offset 90.000 201 ms, Jahresfilter 55 ms,
  Statusfilter 84 ms nach ANALYZE; ohne frische Statistik Offset 90.000 404 ms.

Die Vorgabe von 300 ms (P95) wird bei 100.000 Zeilen je Tabelle im Mandanten eingehalten, mit
Ausnahme des tiefen Offsets bei Bankumsätzen ohne aktuelle Statistik. Die Messung belegt nicht,
dass 10 Millionen Zeilen ohne Partitionierung genügen; sie liefert die Basis für die Auslöser.

Befunde der Planausgaben (EXPLAIN ANALYZE, 100.000 Zeilen):

1. Journal: Mit aktueller Statistik nutzt der Planer den Unique-Index
   `(tenant_id, ledger_id, fiscal_year, number)` für die Sortierung (0,3 ms für die erste
   Seite, 78 ms für Zeilen 90.000 bis 90.100). Ohne aktuelle Statistik (Schätzung 1 Zeile)
   liest er alle Zeilen des Buchungskreises und sortiert (172 ms). Die Gesamtzahl für
   `X-Total-Count` kostet 22 bis 104 ms und wächst linear mit der Zeilenzahl des
   Buchungskreises.
2. Bankumsätze: Es gibt keinen Index, der `ORDER BY booking_date DESC, created_at DESC, id DESC`
   bedient. Der Planer liest alle Umsätze des Mandanten und sortiert (43 ms erste Seite, 189 ms
   bei Offset 90.000, bei Speichermangel mit externer Sortierung). Die Kosten wachsen linear mit
   der Zahl der Umsätze je Mandant.
3. Wächterfunktion `journal_line_guard`: Sie sucht die Buchung mit
   `WHERE id = COALESCE(NEW.journal_entry_id, OLD.journal_entry_id)`. Diese Bedingung wurde
   im Versuch nicht als Indexbedingung verwendet (Plan: Seq Scan, mit `enable_seqscan = off`
   Volldurchlauf des Primärschlüsselindex). Gemessen: 3,4 ms je eingefügter Zeile bei 20.000
   Buchungen im Mandanten, 0,8 ms bei 100.000 Buchungen anderer Mandanten, linear wachsend mit
   der Tabellengröße. Ein Massenimport von 200.000 Zeilen ist damit nicht möglich (Abbruch nach
   mehr als 9 Minuten), und jede einzelne Buchung wird bei großen Beständen langsamer. Das ist
   unabhängig von der Partitionierung und der wichtigste Einzelbefund; ein Lasttest mit
   realer Zeilenmenge hätte ihn früher gezeigt. Die Ursache (Parameterauswertung der
   Datensatzfelder in PL/pgSQL) ist nur durch die Messung belegt, nicht durch Dokumentation.
   Eine Korrektur (zum Beispiel getrennte Abfragen je Operation im Triggertext) ändert eine
   Datenbankwache der Buchungsinvarianten B02 und B03, braucht deshalb eine eigene Migration,
   Tests der Wache und die Freigabe der Geschäftsführung; sie ist nicht Teil dieses ADR.

## Decision

1. Es wird in dieser Welle nicht partitioniert und keine Migration mit Schemawirkung angelegt.
   Migration 0342 ist ein Platzhalter. Empfehlung des Entwurfs: zuerst die Maßnahmen ohne
   Datenumbau (Abschnitt Alternativen, Stufe 1), erst bei Eintreten der Auslöser die
   Partitionierung (Stufe 2).
2. Bei Umsetzung wird `journal_entry` nach `RANGE (booking_date)` und `bank_transaction` nach
   `RANGE (booking_date)` partitioniert, je Kalenderjahr eine Partition plus Default-Partition.
   `journal_line` folgt über eine aus der Kopfzeile übernommene Spalte `booking_date`
   (ADR 0018, Punkt 2); sie wird erst mit dem Umbau angelegt. Der Schlüssel `fiscal_year` wurde
   verworfen, weil Entwürfe keinen Wert tragen (`fiscal_year` ist bis zur Buchung leer).
3. Folgen des Partitionsschlüssels, die vor einer Umsetzung gelöst sein müssen:
   - Primärschlüssel und jeder Unique-Index müssen `booking_date` enthalten. Betroffen sind
     `pk_journal_entry` (`id`), `(ledger_id, id)`, `reverses_id`, die Idempotenzschlüssel und die
     Belegnummer `(tenant_id, ledger_id, fiscal_year, number)`. Die Eindeutigkeit der
     Belegnummer über Jahre hinweg bleibt gewahrt, weil `fiscal_year` Teil des Schlüssels ist;
     das Buchungsdatum eines Satzes kann aber in einem anderen Jahr liegen als das
     Geschäftsjahr. Zwischen Buchungsdatum und Geschäftsjahr ist die Regel nicht ohne weiteres
     deckungsgleich und mit Steuerberater zu klären (keine Annahme).
   - Die 22 und 9 Fremdschlüssel auf `id` sind nicht mehr möglich, weil ein Fremdschlüssel einen
     Unique-Index auf `id` allein braucht. Zwei Wege: (a) Fremdschlüssel entfernen und die
     Integrität über Trigger oder Prüfläufe (B02, B07, B09 `checks`) sichern, (b) das
     Buchungsdatum in alle referenzierenden Tabellen übernehmen und zusammengesetzte
     Fremdschlüssel verwenden. Weg (a) schwächt die Datenbankgarantie, Weg (b) verändert bis zu 27
     Tabellen. Beides ist ein größerer Eingriff als in ADR 0018 angenommen und braucht eine
     eigene Planung je Weg.
   - Trigger und RLS werden je Partition geprüft (siehe Ist-Analyse).
4. Alembic-Vorgehen für Bestandstabellen (PostgreSQL kann eine bestehende Tabelle nicht in
   eine partitionierte umwandeln):
   1. Wartungsfenster ankündigen, Schreibzugriff über den Feature-Schalter der Buchung
      sperren, Sicherung und Wiederherstellungstest (`backup.md`).
   2. Neue Tabelle `journal_entry_p` mit `PARTITION BY RANGE (booking_date)` anlegen, Partitionen
      je Jahr und Default, Indizes, Trigger und RLS je Partition (`tenant_rls_statements()`).
   3. Daten je Jahr per `INSERT ... SELECT` kopieren, Zeilenzahl und Summe Soll und Haben je
      Mandant, Buchungskreis und Jahr gegen den Altbestand prüfen; Belegnummern, Zeitstempel,
      Ersteller bleiben identisch (B01).
   4. In einer Transaktion Namen tauschen (`ALTER TABLE ... RENAME`), Fremdschlüssel nach
      Weg (a) oder (b) umstellen, Sequenzen prüfen, Statistik mit `ANALYZE` erneuern.
   5. Altbestand bis zur Abnahme behalten (nicht löschen), dann eigene Migration zum Entfernen.
   Gleiches Vorgehen für `bank_transaction` (nur 9 Fremdschlüssel).
5. Downtime: für 5 Millionen Buchungen und 10 Millionen Zeilen ist das Kopieren je nach
   Hardware eine Frage von Minuten bis Stunden. Der Betrag ist aus den Ladezeiten des
   Generators (200.000 Zeilen in unter 15 Sekunden ohne Wächter) nur grob ableitbar und wird
   vor dem Umbau auf dem Staging-Server mit Produktionsmenge gemessen. Das Wartungsfenster
   wird erst danach festgelegt. Eine Variante ohne Wartungsfenster (logische Replikation oder
   Doppelschreiben) wird nicht empfohlen, weil sie die Buchungsinvarianten B01 bis B03 über zwei
   Tabellen verteilt.
6. Rollback: bis zur Abnahme bleibt die Ausgangstabelle mit unverändertem Inhalt erhalten. Ein
   Rückbau ist das Zurücktauschen der Namen und das Wiederherstellen der Fremdschlüssel in
   derselben Transaktionsform; nach der Abnahme nur über Wiederherstellung aus der Sicherung
   plus Nachspielen der WAL. Neue Buchungen nach dem Tausch müssen im Rollbackfall
   zurückkopiert werden; das Skript dafür gehört zum Umbauplan.
7. Der Umbau gilt als Änderung von Buchungsdaten der Mandanten: Freigabe durch die
   Geschäftsführung, Information des Steuerberaters zum Prüfexport, Gate G1 bleibt Voraussetzung
   jeder produktiven Nutzung. Er wird nicht vor G5 (Drittmandanten) benötigt, wenn die
   Messungen unter den Schwellen bleiben.

## Consequences

- Kein Eingriff in Buchungsdaten und kein Schemarisiko in dieser Welle.
- Der Lasttest (`test_large_journal_and_bank_lists_p95`) ist wiederholbar und läuft nur mit
  `MHVP_PERF=1`; die Wächterfunktion verhindert aktuell einen Massenimport über die normale
  Schreibstrecke, der Generator schaltet sie auf der Testdatenbank für die Dauer des Ladens ab.
- Neue Aufgaben, die aus der Analyse folgen und nicht Teil dieses ADR sind: Korrektur der
  Wächterfunktion (Befund 3), Index für die Bankumsatzliste (Befund 2), ANALYZE nach
  Massenimporten (Befund 1). Sie sind in `docs/runbooks/leistungsmessung.md` und als Hinweis an
  die Verantwortlichen der Buchhaltung und des Bankings vermerkt.
- Nicht belegt sind: horizontale Worker-Skalierung (mehrere Celery-Worker gegen dieselbe
  Queue), 50 Mandanten gleichzeitig, 10 Millionen Zeilen. Der Messplan unten benennt sie.
- Offene Frage AC09-01 (Zielgrößen und Zeitpunkt, Eigentümer Betreiber, Gate G5).

## Alternatives considered

Stufe 1, ohne Datenumbau (Empfehlung als erster Schritt, jeweils mit Messung vor und nach):

- Zusammengesetzte Indizes für die Listensortierung, zum Beispiel
  `bank_transaction (tenant_id, booking_date DESC, created_at DESC, id DESC)`. Gewinn: bedient
  die Standardliste ohne Sortierung der gesamten Tabelle. Aufwand: eine Migration pro Tabelle,
  Speicher der Indexgröße. Risiko gering.
- Autovacuum und Analyse für die großen Tabellen enger einstellen (Schwelle je Tabelle) und
  nach Massenimporten `ANALYZE` im Importlauf. Kostet nichts am Schema; die Messung zeigt den
  Unterschied zwischen 133 und 31 ms (erste Seite des Journals).
- BRIN-Index auf `booking_date`: klein (wenige Seiten je Million Zeilen) und für die zeitlich
  geordnet eingefügten Zeilen geeignet; er hilft bei Bereichsfiltern, nicht bei
  `ORDER BY ... LIMIT` über die ganze Tabelle, und nicht bei mandantenweise gemischten Zeilen,
  weil die Korrelation zur physischen Reihenfolge fehlt, sobald mehrere Mandanten parallel
  einfügen. Als Ergänzung für Jahresberichte denkbar, nicht als Ersatz. Wird mit dem Messplan
  geprüft.
- Keyset-Paginierung (Cursor statt Offset) für die Listen: beseitigt das Tiefenproblem der
  Offsets (201 ms bei Offset 90.000). Das ist eine API-Änderung und gehört in einen eigenen
  Plan; der Gesamtzähler `X-Total-Count` bleibt ein linearer Aufwand.

Stufe 2 und Alternativen zur Partitionierung:

- Archivtabellen (abgeschlossene Jahre in `journal_entry_archive`): einfacher als
  Partitionierung beim Schreiben, aber Auswertungen über Jahre brauchen `UNION`, die Wächter
  und Prüfläufe (B02 bis B09) müssen beide Tabellen kennen, und eine Verschiebung gebuchter
  Sätze widerspricht dem Grundsatz, dass Buchungen nach der Buchung nicht bewegt werden (B01,
  Beleg- und Nachweiskette). Nicht empfohlen.
- Partitionierung nach `tenant_id` (Hash): trennt Mandanten, erfüllt nicht die Jahresablage
  (ADR 0018).
- Datenbank je Mandant: starke Trennung, aber 50 Datenbanken Betrieb, Migrationen und
  Auswertung über Mandanten (Konzernsicht) unverhältnismäßig.
- Sofortige Partitionierung: Fremdschlüssel (31 auf zwei Tabellen) und Unique-Schlüssel
  müssen umgebaut werden, ohne dass die Messung einen Nutzen belegt.

## Auslöser

Die Partitionierung (Stufe 2) wird erst geplant, wenn eine der Bedingungen auf dem
Staging-Server oder in Produktion eintritt. Alle Werte sind Vorschläge für die Entscheidung
AC09-01, keine Rechtsregeln:

- eine der Tabellen `journal_entry`, `journal_line`, `bank_transaction` erreicht 20 Millionen
  Zeilen (Wert aus ADR 0018) oder 50 GB einschließlich Indizes;
- P95 der Journal- oder Bankumsatzliste liegt nach Umsetzung der Stufe 1 und aktueller
  Statistik an drei aufeinanderfolgenden Wochenmessungen über 300 ms bei 10.000 Zeilen je Liste
  (Abschnitt 16) oder über 1 Sekunde bei Tiefenzugriff;
- Die Dauer der Sicherung oder der Wiederherstellung überschreitet das Ziel (RTO unter 4 Stunden,
  Abschnitt 16 Backup) wegen der Größe dieser Tabellen;
- 20 Mandanten produktiv (Zwischenmarke auf dem Weg zu 50) lösen die Wiederholung der Messung
  aus, nicht den Umbau.

## Messplan

1. Reproduktion: `MHVP_PERF=1 uv run pytest tests/integration/test_ga12_perf.py -m slow -s --no-cov`
   mit 100.000 Zeilen (Stand dieses ADR).
2. Staffel: Generator mit 1, 5 und 10 Millionen Zeilen auf dem Staging-Server (Parameter
   `ROWS_LARGE`), je Staffel Tabellengrößen, P95 der acht Listenabfragen, Dauer des
   Gesamtzählers, Dauer von Sicherung und Wiederherstellung. Voraussetzung: Korrektur der
   Wächterfunktion oder Abschalten auf der Staging-Datenbank für den Ladevorgang.
3. Mehrere Mandanten: 10 und 50 Mandanten mit je gleich großem Bestand, gleichzeitige Last
   (zehn bis fünfzig parallele Clients), Messung der Latenz und der Sperren (`pg_stat_activity`).
4. Worker: mehrere Celery-Worker gegen dieselbe Queue (Sollstellungslauf, Bankabruf), Nachweis
   der Durchsatzsteigerung und der Idempotenz bei gleichzeitigen Aufträgen.
5. Vergleich je Maßnahme der Stufe 1 (Index, Statistik, BRIN) mit denselben Abfragen; das
   Ergebnis wird im Runbook `leistungsmessung.md` protokolliert und die Auslöser dort neu bewertet.
6. Zeitpunkt: vor Öffnung von G5 (Drittmandanten), siehe AC09-01.

## References

- `docs/MASTER-PROMPT.md` Abschnitt 16 (Skalierung), 7.1 (Buchungsinvarianten), 18.0 (Gates)
- `docs/adr/0018-jahrespartitionierung.md`, `docs/adr/0002-tenant-isolation.md`,
  `docs/adr/0003-release-gates.md`
- `docs/runbooks/leistungsmessung.md`, `docs/runbooks/backup.md`
- `apps/api/tests/integration/test_ga12_perf.py`, `apps/api/tests/integration/perf_seed.py`
- `docs/OPEN_QUESTIONS.md` AC09-01

## Nachtrag Welle 15 (AD01, 01.10.2026)

Befund 3 behoben mit Migration 0346 (gleiche Fachlogik, indexierbarer Zugriff je Operation; Planbeweis im Test `test_ad01_line_guard.py`), Befund 2 mit dem Index `ix_bank_transaction_booking_date`. Befund 1: Die App-Rolle darf kein ANALYZE ausführen, deshalb Wartungsjob außerhalb des Workers (Runbook `leistungsmessung.md`, Abschnitt AD01). Messwerte nachher für 200.000 Zeilen mit aktivem Wächter stehen noch aus. Die Freigabe der Geschäftsführung nach AC09-01 (4) ist formal weiter offen.

## Nachtrag Welle 16 (AE36, 01.10.2026)

Die Auslöser dieses ADR (Abschnitt Auslöser) werden jetzt als Plattformkennzahlen gemessen und gemeldet, ohne etwas umzubauen (Regel `docs/rules/AE36-SCALE.md`, Runbook `leistungsmessung.md`, Abschnitt AE36): Zeilen und Größe von `journal_entry`, `journal_line` und `bank_transaction`, P95 der Journal- und Bankumsatzliste aus echten Aufrufen (normal und bei tiefem Zugriff ab Versatz 10.000), Dauer des letzten Wiederherstellungstests gegen die RTO und Zahl produktiver Mandanten (ohne Demo-Mandanten). Ein wöchentlicher Job speichert die Messung (Migration 0392, Tabelle `platform_scale_snapshot`); ein neu erreichter Auslöser erzeugt ein Plattformaudit-Ereignis und einen Hinweis an die Plattformadministratoren, bleibt in `/platform/ops/metrics` unter `alerts` stehen und geht über die Überwachung als E-Mail an den Betreiber. Die Schwellen sind die hier genannten Vorschläge und je Plattform einstellbar (`platform_scale_setting`). Die Entscheidung AC09-01 (Zielgrößen, Zeitpunkt, Freigabe der Geschäftsführung) bleibt offen und trägt den Vermerk "technisch vorbereitet (Welle 16, AE36)". Entschieden wird weder der Umbau noch ein Zeitpunkt; Stufe 2 bleibt an die Freigabe der Geschäftsführung gebunden.
