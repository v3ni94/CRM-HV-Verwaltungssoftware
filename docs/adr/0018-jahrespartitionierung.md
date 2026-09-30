# ADR 0018: Vorbereitung der Jahrespartitionierung für journal_line und bank_transaction

- Status: Proposed
- Date: 30.09.2026

## Context

Abschnitt 16 (Skalierung) verlangt die Vorbereitung einer Jahrespartitionierung für die
wachsenden Tabellen `journal_line` und `bank_transaction`. Heute gibt es keine Partitionierung.
Beide Tabellen tragen `tenant_id` mit RLS (ADR 0002). Buchungen sind nach der Buchung
unveränderlich (Regel B01 bis B09), ein Umbau darf keine Buchung verändern und keinen
Nachweis verlieren. Die Zielgröße (869 Einheiten, 67 Objekte) liegt weit unter den Mengen,
ab denen Partitionierung Leistung bringt; die Messung fehlt (S16-08, `leistungsmessung.md`).

## Decision

1. Es wird jetzt nicht partitioniert. Der Umbau erfolgt erst, wenn die Leistungsmessung
   (Schwelle 16: P95 unter 300 ms bei 10.000 Zeilen je Liste) mit Produktivdaten verfehlt wird
   oder eine der Tabellen 20 Millionen Zeilen erreicht. Beide Werte sind Betreiberschwellen,
   keine Rechtsregeln.
2. Schlüssel bei Umsetzung: `PARTITION BY RANGE (booking_date)` für `bank_transaction` (Spalte
   vorhanden) und für `journal_line`. `journal_line` trägt selbst kein Datum, das Buchungsdatum
   steht an `journal_entry.booking_date`. Der Umbau braucht deshalb eine aus der Kopfzeile
   übernommene Spalte `booking_date` an `journal_line` (bei der Buchung gesetzt, danach
   unveränderlich wie die Buchung selbst). Diese Spalte wird erst mit dem Umbau angelegt, nicht
   "auf Vorrat" (CLAUDE.md Regel 4.2). Je Kalenderjahr eine Partition, dazu eine
   Default-Partition, damit kein Insert fehlschlägt.
3. Voraussetzungen, die schon jetzt gelten und bei neuen Migrationen einzuhalten sind:
   - Der Partitionsschlüssel muss Teil jedes Primär- und Unique-Schlüssels sein. Neue
     Unique-Constraints auf diesen Tabellen werden deshalb so entworfen, dass sie den
     Datumsanteil enthalten können, oder sie werden auf `tenant_id` plus fachlichen Schlüssel
     mit Datum gelegt.
   - Fremdschlüssel auf `journal_line.id` und `bank_transaction.id` werden vermieden. Bestehende
     Verweise (Ausgleiche, Belegketten, Klärungsfälle) sind vor dem Umbau zu inventarisieren.
   - RLS-Policies, Indizes und Trigger gegen Änderung (B01) werden je Partition mitgeführt,
     `tenant_rls_statements()` muss partitionierte Tabellen abdecken (vorher zu prüfen).
4. Migrationsweg: neue partitionierte Tabelle anlegen, je Jahr per `INSERT ... SELECT`
   kopieren, Summen und Zeilenzahlen je Mandant und Jahr gegen die Altdaten prüfen,
   umbenennen in einem Wartungsfenster, Altbestand bis zur Abnahme behalten. Kein Löschen und
   Überschreiben von Buchungen, die Belegnummern und Zeitstempel bleiben identisch.
5. Vor dem Umbau ist ein Wiederherstellungstest mit Backup und WAL nötig (`backup.md`), und
   der Steuerberater wird über die Auswirkung auf den Prüfexport informiert (Nachweisbarkeit).

## Consequences

- Kein Schemaaufwand und kein Risiko für Buchungen im Moment; die Vorbereitung besteht aus den
  Entwurfsregeln unter 3 und dem Messprotokoll.
- Bei Eintreten der Schwelle braucht der Umbau einen eigenen Plan und eine Freigabe durch die
  Geschäftsführung, weil er Buchungsdaten der Mandanten bewegt.
- Offene Punkte: Bestätigung der Schwellen durch den Betreiber, Prüfung von
  `tenant_rls_statements()` für partitionierte Tabellen.

## Alternatives considered

- Sofortige Partitionierung: zusätzliche Komplexität bei Unique-Schlüsseln und Verweisen ohne
  messbaren Nutzen bei der heutigen Datenmenge.
- Partitionierung nach `tenant_id` (Hash): trennt Mandanten, erfüllt aber nicht den Zweck
  der Jahresablage und der einfachen Archivierung alter Jahre.
- Keine Vorbereitung: würde bei späterem Bedarf Unique-Schlüssel ohne Datum hinterlassen.

## References

- `docs/MASTER-PROMPT.md` Abschnitt 16 (Skalierung), 7.1 (Buchungsinvarianten)
- `docs/runbooks/leistungsmessung.md`, `docs/runbooks/backup.md`
