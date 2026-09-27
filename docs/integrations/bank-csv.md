# Bank-CSV-Import (M11-02)

Bindendes Dokument für `apps/api/src/mhvp/banking/csv_formats.py`. Ergänzt den bestehenden
CAMT.053/MT940-Datei-Import (`mhvp.banking.camt`, `mhvp.banking.mt940`,
`mhvp.banking.connectors.FileConnector`) um Bank-CSV-Exporte. Beide Wege münden in dieselbe
Struktur (`RawTransaction`/`RawStatement`/`ParsedFile`) und denselben Import
(`mhvp.banking.services.import_file`), damit derselbe Dublettenschutz (Bankreferenz primär,
Inhalts-Hash sekundär, D05) für CSV, CAMT und MT940 gilt.

## Grundsatz Formaterkennung (Regel 0.1.3)

Ein Format wird nur erkannt, wenn die Kopfzeile der Datei tatsächlich zu einer hier
hinterlegten Signatur passt (`BankCsvFormat.signature`, alle Spaltennamen normalisiert
kleingeschrieben). Es wird nie eine Spalte geraten. Jedes erkannte Format trägt zusätzlich
eine Vertrauensangabe:

- `erkannt`: die Kopfzeile wurde gegen eine reale Beispieldatei geprüft.
- `zu_pruefen`: die Kopfzeile folgt einer öffentlich dokumentierten Exportkonvention, ist
  aber nicht gegen ein reales Beispiel dieser Bank verifiziert; siehe
  `docs/OPEN_QUESTIONS.md` (M11-02-csv-header-verification).

Passt keine Signatur, greift das generische Mapping: der Nutzer ordnet die Spalten im CRM
selbst zu, nichts wird automatisch angenommen. Für Deutsche Bank, Commerzbank, Postbank und
Hypovereinsbank ist aktuell keine Signatur hinterlegt (Exportformat je nach Konto/Freischaltung
unterschiedlich und nicht verifiziert); diese Exporte laufen bis zur Bestätigung durch den
Betreiber ausschließlich über das generische Mapping.

## Unterstützte Formate

| Format-ID | Bank | Vertrauen |
| --- | --- | --- |
| `sparkasse_camt_csv` | Sparkasse, CSV-CAMT-Export | erkannt |
| `sparkasse_mt940_csv` | Sparkasse, CSV-MT940-Export | zu prüfen |
| `volksbank_atruvia_csv` | Volksbank/Raiffeisen (Atruvia-Umsatzexport) | zu prüfen |
| `dkb_csv` | DKB | zu prüfen |
| `ing_csv` | ING | zu prüfen |
| `n26_csv` | N26 | zu prüfen |
| `comdirect_csv` | comdirect | zu prüfen |
| `generic` | beliebig, Spaltenzuordnung durch den Nutzer | – |

## Robustheit

- **Zeichensatz**: Reihenfolge UTF-8 (mit/ohne BOM), danach Windows-1252; ist keiner lesbar,
  bricht der Import mit einer deutschen Fehlermeldung ab, statt Zeichen zu erraten.
- **Trennzeichen**: Semikolon, Komma oder Tabulator, per `csv.Sniffer` erkannt, mit
  Häufigkeits-Rückfall.
- **Kopfzeile**: einige Exporte (DKB, ING, comdirect) stellen der eigentlichen Tabelle
  Kontoinformationen voran; die erste Zeile, deren normalisierte Spalten zu einer bekannten
  Signatur passen, gilt als Kopfzeile, sonst die erste nichtleere Zeile.
- **Dezimalwerte**: deutsches Komma (`1.234,56`), englischer Punkt, Klammern als negatives
  Vorzeichen und Währungssymbole werden normalisiert; nicht lesbare Beträge werden als
  Zeilenfehler gemeldet, nie stillschweigend auf 0 gesetzt.
- **Datum**: `TT.MM.JJJJ`, `TT.MM.JJ`, `JJJJ-MM-TT`, `TT/MM/JJJJ`.
- **Soll/Haben getrennt**: das generische Mapping kann statt einer signierten Betragsspalte
  zwei Spalten (`amount_debit`/`amount_credit`) verwenden.

## Vorschau vor dem Import

`POST /banking/imports/csv/preview` liest ein bereits hochgeladenes Dokument
(`document_id`, wie beim CAMT/MT940-Import) und liefert erkanntes Format, Vertrauen,
Zeichensatz, Trennzeichen, Spaltenköpfe, Zeilenzahl, eine Stichprobe und je Zeile lesbare
Fehler, ohne etwas zu speichern. Erst danach löst `POST /banking/imports/csv` den
eigentlichen Import über `services.import_file` aus (gleicher Ablauf, gleiche Zähler
`new`/`duplicates`/`possible_duplicates`/`transfers` wie beim Datei-Import).

Eine eigene Kontonummer (IBAN) fehlt in mehreren Exporten (z. B. DKB, generisches Mapping
ohne passende Spalte). In diesem Fall verlangt der Import ausdrücklich
`property_bank_account_id`; ohne Angabe wird nichts importiert (A-054).

## Benutzerdefiniertes Mapping je Konto

Ein von Hand erstelltes Spaltenmapping wird über `POST /banking/csv-mappings`
(`property_bank_account_id`, `label`, Spaltenzuordnung) gespeichert und über
`GET /banking/csv-mappings?property_bank_account_id=...` sowie `mapping_id` beim Import
wiederverwendet, damit es nicht bei jedem Import neu eingegeben werden muss (Tabelle
`bank_csv_mapping`, Migration 0168).

## Nicht Gegenstand dieser Stufe

- Online-Kontoabruf (FinTS/HBCI: `mhvp.banking.fints`, finAPI: `mhvp.banking.finapi`) bleibt
  unverändert; dieses Modul betrifft ausschließlich hochgeladene CSV-Dateien.
- Keine Zahlungsauslösung (G2 bleibt geschlossen).
