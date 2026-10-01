# Q15 Honorardokumente, Honorarlauf, USt je Objekt und Jahresübernahme

| Field | Content |
| --- | --- |
| ID | `Q15` (M13-05, M13-06, M18-06, M10-07, S13-03) |
| Title | Rechnungsdokument und Gutschrift-XRechnung ablegen, gesammelter Honorarlauf, USt-Übersicht je Objekt, Jahresübernahme als Entwurf mit Vier-Augen |
| Scope | `mhvp.accounting.fee_documents` (`POST /accounting/admin-fee-invoices/{id}/document`, `.../xrechnung-credit-note/document`, `POST /accounting/admin-fees-run`), `report_views.vat_overview_by_property` (`GET .../reports/vat-overview-by-property`), `mhvp.accounting.year_carryover` (`GET/POST /accounting/ledgers/{id}/year-carryover`); Migration 0282 (`admin_fee_invoice.pdf_document_id`); alle Mandanten |
| Source status | Fachliche Umsetzung nach 18 M13, 7.7 und 6.9.10. Keine Rechtsnorm zitiert. Die Auswahl der übernommenen Kontenarten und die Behandlung des Jahresergebnisses sind offen (OPEN_QUESTIONS Q15-02). ZUGFeRD ist nicht umgesetzt (Q15-03) |
| Acceptance case | `tests/integration/test_q15_fee_documents.py` (vorgerechnet: zwei Objekte je 2 x 40,00 = 80,00 netto, 15,20 USt, 95,20 brutto, Nummern 000001 und 000002, Wiederholung stellt nichts aus; USt 19,00 je Objekt und 9,50 ohne Objekt, Summe 28,50; Übernahme 5.000,00 und 20.000,00 gegen 009000, Bankstand bleibt 5.000,00; Rechte 403, anderer Mandant 404, Validierung 422) |
| Change reason | Lückenliste 30.09.2026, Welle 3, Paket Q15 |

## Regeln

- Das PDF entsteht aus denselben eingefrorenen Daten und denselben Sperren wie die XRechnung
  (`xrechnung.load`); es wird einmal abgelegt, verknüpft mit Objekt und Rechtsträger, und nie
  versendet. Eine Gutschrift trägt negative Beträge und nennt die korrigierte Rechnung.
- Honorarlauf: ohne `confirm` nur Vorschau. Je Honorar ein Savepoint mit eigener Nummer, ein
  Fehler wirft die Nummer zurück (lückenlos). Die Eindeutigkeit je Honorar und Zeitraum gilt weiter.
- USt je Objekt: Die Buchungszeile trägt keine Objekt-ID; das Objekt folgt der Einheit der Zeile.
  Die Summen entsprechen der USt-Übersicht des Zeitraums. Keine Abzugsregel, keine Voranmeldung.
- Jahresübernahme: zwei Entwürfe am ersten Tag des Folgejahres, Abschluss (Art custom) und
  Anfangsbestand (Art opening_balance) gegen das Anfangsbestandskonto, in Summe neutral für kumulierte
  Salden. Buchen des Anfangsbestands nur nach Prüfung durch eine zweite Person. Wiederholung liefert
  dieselben Entwürfe (Schlüssel je Geschäftsjahr). Das Geschäftsjahr muss beendet sein.
