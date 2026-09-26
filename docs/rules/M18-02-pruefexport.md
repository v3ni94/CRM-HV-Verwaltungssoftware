# M18-02 Prüfexport: maschinell auswertbar im Umfang von Abschnitt 7.7, kein Datenträgerüberlassungsformat

| Field | Content |
| --- | --- |
| ID | `M18-02` |
| Title | Maschinell auswertbarer Prüfexport je Rechtsträger und Zeitraum als ZIP mit CSV je Tabelle, Inhaltsverzeichnis mit SHA-256 und verknüpften Originalbelegen; Export als `ExportRun` mit Prüfsumme, Zeitstempel, Ersteller und Parametern |
| Scope | Alle Buchungskreise (`Ledger`, einer je Rechtsträger, 6.9.1) aller Mandanten; nur gebuchte Sätze (`status = posted`), Entwürfe werden nicht exportiert; Zeitraum über `booking_date`, Eröffnungsbestände bis Periodenende, OP-Ausgleiche nach Ausgleichsdatum; Stammdatenhistorie nur soweit das Audit-Log (6.8) Feldänderungen enthält |
| Source status | Fachliche Umsetzung nach 7.7 (Umfang: Konten, Buchungen, OP-Ausgleich, Eröffnungsbestände, relevante Stammdatenhistorie, Freigaben, Änderungs-/Stornobeziehungen, Schlüssel-/Regelstände, lesbares Inhalts-/Verknüpfungsverzeichnis). Quellen laut Anhang C: R17 (§§ 146, 147 AO), R19 (GoBD-Änderung 14.07.2025) im jeweiligen Anwendungsbereich. Der Begriff GoBD ist hier nur Bezug auf den in 7.7 benannten Umfang, keine Zusicherung: Datenträgerüberlassungsformat, Beschreibungsstandard (index.xml) und vollständige GoBD-Fassung bleiben offen (docs/OPEN_QUESTIONS.md M18-01, P03, P05) |
| Acceptance case | D55 (Steuerberater-/Prüfexport und anschließende Auswertung): `apps/api/tests/integration/test_m18_audit_export.py::test_d55_audit_export_zip_contents_hashes_and_reversal`, `::test_d55_audit_export_on_worker`; Unit `apps/api/tests/unit/test_audit_export_csv.py` |
| Implementation | `mhvp.accounting.audit_export` (Sammlung, CSV, ZIP, Ablage), `mhvp.accounting.audit_export_routers` (`/api/v1/accounting/audit-exports`), `mhvp.accounting.tasks.audit_export_run` (Celery, Warteschlange `default`), Migration `0096_export_run_audit` (`export_run.status`, `params`, `error`, `finished_at`), CRM `apps/web-crm/src/components/accounting/AuditExportPanel.tsx` unter Buchhaltung, Auswertungen |
| Change reason | Lückenliste 26.09.2026 Aufgabe A26 (M18: GoBD-Export offen, D55 ohne Test), umgesetzt 26.09.2026 |

## Regeln

- Der Prüfexport wird je Buchungskreis (= Rechtsträger) und Zeitraum erstellt
  (`POST /accounting/audit-exports` mit `ledger_id`, `period_from`, `period_to`). Bis
  2.000 gebuchte Sätze im Zeitraum entsteht er in der Anfrage, darüber oder mit
  `run_in_background = true` auf dem Worker; der `ExportRun` durchläuft `queued`, `running`,
  `done` oder `failed` mit Fehlertext.
- Inhalt des ZIP (eine CSV je Tabelle, Semikolon, UTF-8 mit BOM, CRLF, Dezimalkomma,
  ISO-Datum, `ja`/`nein`, Formelneutralisierung über `mhvp.core.escaping.csv_safe_cell`):
  `konten`, `buchungen`, `buchungszeilen`, `storno_beziehungen`, `eroeffnungsbestaende`,
  `offene_posten`, `op_ausgleich`, `freigaben`, `ereignisse`, `stammdaten`,
  `stammdatenhistorie`, `verteilungsschluessel`, `verteilungsschluessel_werte`, `belege`;
  dazu `export.json` (Rechtsträger, Buchungskreis, Objekt, Zeitraum, Datenstand, Ersteller,
  Parameter, Zählwerte, Formatbeschreibung) sowie `index.csv` und `index.json` (Datei,
  Zeilenzahl, Spalten, Bytes, SHA-256 jeder Datei).
- Stornobeziehungen werden als Paar Original/Storno mit Nummern, Buchungstagen, Grund und
  Person geführt; liegt eine Seite außerhalb des Zeitraums, wird sie trotzdem benannt
  (B03, keine Überschreibung, nur Storno).
- Freigaben: zweite Person bei Eröffnungsbeständen (`approved_by`) und Prüfschritte der
  Rechnungen (`InvoiceReview`, PÜ05) der exportierten Buchungen. Freigaben des Mahnwesens
  und des Zahlungsverkehrs gehören nicht zum Buchhaltungsumfang von 7.7 und bleiben in ihren
  Modulen.
- Originalbelege: Dokumente, die an den Buchungen hängen (`JournalEntry.document_id`,
  `DocumentLink` mit `journal_entry`, `Invoice.document_id` der verbuchten Rechnung). Sie
  werden als Dateien unter `belege/` mitgeführt, solange ihre Gesamtgröße die Grenze
  `receipts_max_bytes` (Standard 100 MB, je Anfrage einstellbar) nicht überschreitet; sonst
  oder bei Ablage außerhalb des Objektspeichers enthält `belege.csv` nur den Verweis mit
  SHA-256, Größe und Buchungs-IDs. Ein Original, dessen Prüfsumme vom Index abweicht, wird
  nicht gepackt, sondern mit Hinweis gelistet.
- Der `ExportRun` (Format `audit_zip`) trägt SHA-256 des ZIP, Zeitstempel, Ersteller,
  Parameter und die Dokument-ID; das ZIP liegt als erzeugtes Dokument am Rechtsträger.
  Download nur über `GET /accounting/audit-exports/{id}/download` mit `accounting:export`;
  Liste und Status mit `accounting:read`. Mandantentrennung über RLS, Prüfsumme und Ereignis
  `export_run.downloaded` beim Abruf.
- Nicht enthalten und nicht behauptet: DATEV-Kontenrahmen oder Kontenzuordnung (M18-03),
  steuerliche Einordnung, Datenträgerüberlassungsformat und Beschreibungsstandard der GoBD
  (M18-01, P05). Diese Aussagen stehen auch in `export.json` unter `scope`.
