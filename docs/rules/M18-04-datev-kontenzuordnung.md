# M18-04 DATEV-Kontenzuordnung je Mandant: Betreiberpflege, kein vorbelegter Kontenrahmen, Export nur mit vollständiger Zuordnung

| Field | Content |
| --- | --- |
| ID | `M18-04` |
| Title | Zuordnung CRM-Konto zu DATEV-Sachkonto je Mandant (optional je Buchungskreis, gültig ab Datum); der Buchungsstapel-Export schreibt ausschließlich zugeordnete DATEV-Konten und bricht bei fehlender Zuordnung ab |
| Scope | `mhvp.accounting.models.DatevAccountMapping` (Migration 0099), `mhvp.accounting.datev_mapping` (Auflösung, Prüfbericht, CSV-Import), `mhvp.accounting.datev_mapping_routers` (`/api/v1/accounting/datev-mappings`), `mhvp.accounting.reports.datev_csv`, CRM-Seite Einstellungen, Buchhaltung, DATEV |
| Source status | Fachliche Umsetzung nach Betreiberauftrag (Aufgabe A36, M18-01). Keine Rechtsnorm zitiert. Es wird kein DATEV-Kontenrahmen (SKR03/SKR04) vorbelegt; die Zuordnung ist reine Betreiberpflege nach Abstimmung mit dem Steuerberater. Beraternummer, Mandantennummer und Kontenrahmenkennung stammen weiterhin ausschließlich aus `TenantBillingSettings` (M18-03) |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_m18_datev_mapping.py` (CRUD, Import mit Vorschau, Prüfbericht, Export mit und ohne vollständige Zuordnung, Rechte, Mandantentrennung) und `test_m18_reports.py::test_reports_and_exports` (Export erst nach Zuordnung) |
| Implementation | Tabelle `datev_account_mapping` (RLS, eindeutig je Mandant, Buchungskreis oder mandantenweit, CRM-Konto und Gültig ab), Fehlercode `MHVP-BILL-0008`, `ExportRun.note = "Kontenzuordnung angewendet"` |
| Change reason | A36: der bisherige Export gab CRM-Kontonummern unverändert aus (M18-03, Vermerk "Kontenzuordnung zu prüfen"); eine stille Ausgabe roher Nummern ist für den Steuerberater nicht verwertbar |

## Regeln

- Eine Zuordnung besteht aus CRM-Kontonummer (`account_code`), DATEV-Sachkonto (`datev_account`,
  nur Ziffern, bis 16 Stellen), Bezeichnung, Aktiv-Kennzeichen, optional Buchungskreis und
  optional Gültig ab. Ohne Buchungskreis gilt sie für alle Buchungskreise des Mandanten.
- Auflösung je Buchungszeile und Buchungstag: aktive Zeilen des Buchungskreises vor
  mandantenweiten Zeilen; darunter die Zeile mit dem spätesten Gültig ab, das nicht nach dem
  Buchungstag liegt; ohne Gültig ab gilt die Zeile seit jeher.
- `POST /accounting/ledgers/{id}/exports/datev` schreibt im Feld "Konto" das aufgelöste
  DATEV-Sachkonto. Fehlt für eine gebuchte Zeile im Zeitraum die Zuordnung, bricht der Export
  mit `409 MHVP-BILL-0008` ab; die Antwort enthält unter `missing` je Konto Nummer,
  Bezeichnung, Anzahl Zeilen sowie ersten und letzten Buchungstag. Rohe CRM-Nummern werden nie
  ausgegeben. Die Prüfung der Beraterdaten (`MHVP-BILL-0004`, M18-03) bleibt vorgeschaltet.
- Prüfbericht `GET /accounting/datev-mappings/report?ledger_id&start&end`: alle Konten des
  Buchungskreises mit aufgelöstem DATEV-Konto zum Zeitraumende, Buchungszeilen im Zeitraum und
  Kennzeichen `unmapped` (Zeile ohne Zuordnung am Buchungstag oder Konto ohne Zuordnung zum
  Zeitraumende). `used_unmapped_count` entspricht der Sperre des Exports.
- CSV-Import `POST /accounting/datev-mappings/import`: Kopfzeile `account_code;datev_account;
  label;valid_from` (deutsche Aliasse Konto, DATEV-Konto, Bezeichnung, Gültig ab; Semikolon
  oder Komma; Datum TT.MM.JJJJ oder JJJJ-MM-TT). `dry_run=true` liefert die Vorschau mit
  Aktion je Zeile (neu, ändern, unverändert, Fehler). Eine Datei mit fehlerhaften Zeilen wird
  nicht übernommen (422 mit den fehlerhaften Zeilen). Der Import gilt je Zielbereich
  (Buchungskreis oder mandantenweit) und ändert bestehende Zeilen desselben Kontos und Gültig
  ab, statt Duplikate anzulegen.
- Rechte: Pflege (Anlegen, Ändern, Löschen, Import) `accounting:update`; Liste und Bericht
  `accounting:read` (Steuerberaterrolle liest, pflegt nicht). Mandantentrennung über RLS.
- Bereits geschriebene Exporte bleiben mit Prüfsumme unverändert; eine spätere Änderung der
  Zuordnung wirkt nur auf neue Exporte (B03 sinngemäß, Exporte sind keine Buchungen).
- Ob der Steuerberater das erzeugte Feld "Konto" ohne weitere DATEV-Felder (Gegenkonto,
  BU-Schlüssel) verarbeiten kann, bleibt Teil von M18-01 (Abnahme mit dem Steuerberater).
