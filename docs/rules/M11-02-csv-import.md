# M11-02: Bank-CSV-Import

| Feld | Inhalt |
| --- | --- |
| ID | M11-02 |
| Geltungsbereich | Datei-Import von Kontoumsätzen aus Bank-CSV-Exporten (`mhvp.banking.csv_formats`), zusätzlich zum bestehenden CAMT.053/MT940-Import |
| Anforderungsart | Fachliche Umsetzung (Masterprompt Kapitel 8, Datei-Import) |
| Quellenstatus (Anhang C) | keine Rechtsnorm; Formaterkennung nur nach tatsächlich geprüften Kopfzeilen (Regel 0.1.3). Nur die Kopfzeile des Sparkasse-CSV-CAMT-Exports ist gegen eine reale Beispieldatei geprüft (Vertrauen `erkannt`); alle übrigen Formate (Sparkasse CSV-MT940, Volksbank/Raiffeisen Atruvia, DKB, ING, N26, comdirect) folgen öffentlich dokumentierten Exportkonventionen, sind aber nicht verifiziert (`zu_pruefen`, siehe `docs/OPEN_QUESTIONS.md` M11-02-csv-header-verification). Für Deutsche Bank, Commerzbank, Postbank und Hypovereinsbank ist keine Kopfzeile hinterlegt |
| Regel | Ein Format wird nur bei vollständig passender Kopfzeile automatisch erkannt; ohne Treffer verlangt der Import ein vom Nutzer gepflegtes Spaltenmapping (kein Raten von Spaltennamen). Zeichensatz (UTF-8/Windows-1252), Trennzeichen, deutsches Dezimalkomma und mehrere Datumsformate werden robust erkannt; nicht lesbare Zeilen werden als Fehler gemeldet, nie stillschweigend übersprungen oder falsch interpretiert. Die Normalisierung mündet in dieselbe Struktur wie CAMT/MT940, damit derselbe Dublettenschutz (Bankreferenz primär, Inhalts-Hash sekundär, D05) gilt. Vor jedem Import zeigt eine Vorschau erkanntes Format, Zeilen und Fehler; ohne eigene IBAN-Spalte im Export ist die Angabe des Kontos oder eines Mappings Pflicht (A-054) |
| Akzeptanzfall (Anhang D) | kein eigener Fall in Anhang D; Tests in `apps/api/tests/unit/test_csv_formats.py` (Formaterkennung je Bank, Zeichensatz-/Trennzeichen-/Betrags-/Datumsrobustheit, Fehlerzeilen, generisches Mapping, Soll-Haben-Spaltenpaar) |
| Änderungsgrund | M11-02 (Umsatzimport aus Bank-CSV-Exporten mit automatischer Formaterkennung) |

Verweise: `docs/integrations/bank-csv.md` (Endpunkte, Formatliste, Details),
`apps/api/src/mhvp/banking/README.md` (Abschnitt Bank specific CSV import), Migration 0168
(`bank_csv_mapping`).

## Nachtrag V11 (01.10.2026, Prüfung Welle 6)

| Feld | Inhalt |
| --- | --- |
| Geltungsbereich | `banking/csv_formats.py`, Vorschau und Import |
| Regel | Beträge mit mehr als zwei Nachkommastellen, Exponent, NaN oder Unendlich sind Zeilenfehler (z. B. "1.234" ist im deutschen Export 1.234,00 EUR und wird nicht geraten). Zeilen mit abweichendem Auftragskonto oder abweichender Währung sind Zeilenfehler. Weicht das Auftragskonto der Datei vom gewählten Konto ab, ist der Import gesperrt. |
| Quellenstatus (Anhang C) | Produktschutz, keine Rechtsnorm (Trennung der Bankmittel je Rechtsträger, 6.9.1, E01) |
| Abnahmefall | `tests/unit/test_csv_formats.py::test_v11_*` |
| Änderungsgrund | Prüfbericht `docs/reviews/REVIEW-W6-2026-10-01.md` |
