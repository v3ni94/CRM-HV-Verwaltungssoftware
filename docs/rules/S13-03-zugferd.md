# S13-03 ZUGFeRD / Factur-X erzeugen und lesen

| Field | Content |
| --- | --- |
| ID | `S13-03` (Welle 16, Paket AE25, Prioritätenliste Punkt 24) |
| Title | Honorarrechnung und Gutschrift als ZUGFeRD/Factur-X (PDF mit eingebettetem CII im Profil EN 16931), PDF/A-3 Kennzeichnung ohne Konformitätsnachweis, Profil- und Containerangaben beim Lesen |
| Scope | `mhvp.accounting.zugferd` (`GET /accounting/admin-fee-invoices/{id}/zugferd.pdf`, `GET .../zugferd/check`, `POST .../zugferd/document`), `mhvp.receipts.einvoice` (`profile_name`, `pdf_container`, `container_findings`, `formal_validation`); Migration 0381 (`admin_fee_invoice.zugferd_document_id`, `zugferd_check`); alle Mandanten, kein Schalter (es wird nichts versendet und nichts gebucht) |
| Source status | Fachliche Umsetzung nach 13.5 (E-Rechnung lesen und erzeugen). Formatangaben nach der Factur-X / ZUGFeRD Spezifikation (ADR 0020), keine Rechtsnorm zitiert. Die PDF/A-3 Konformität (ISO 19005-3) ist nicht nachgewiesen; die Prüfung mit veraPDF und das Einbetten der Schriften sind offen (OPEN_QUESTIONS AE25-01, P03-02, Q15-03). Ob ein ZUGFeRD-Beleg neben der XRechnung als Rechnung im Sinne der Ausstellungspflicht genutzt wird, entscheidet der Betreiber mit dem Steuerberater (V12) |
| Acceptance case | `tests/unit/test_ae25_zugferd.py` (vorgerechnet: 3 x 25,00 = 75,00 plus Anpassung 25,00 = 100,00 netto, 19 % = 19,00, brutto 119,00, Zeitraum 01.07. bis 30.09.2026; Gutschrift 381 mit positiven Beträgen und Bezug; Kleinunternehmer Kategorie E mit Befreiungsgrund; Abweichungen BT-1, BT-112), `tests/integration/test_ae25_zugferd.py` (2 x 40,00 = 80,00 netto, 15,20 USt, 95,20 brutto, Nummer ZF-2026-000001; Rechte 403, anderer Mandant 404, Validierung 422, Ablage idempotent), Anhang D D41 und D42 (formale Lesbarkeit, Widersprüche XML und PDF) |
| Change reason | Prioritätenliste des Betreibers vom 01.10.2026, Punkt 24; Lückenliste 30.09.2026 S13-03 |

## Regeln

- Der ZUGFeRD-Beleg entsteht aus denselben eingefrorenen Daten und denselben Sperren wie die
  XRechnung (`xrechnung.load`: Steuerdaten, Leitweg-ID, IBAN, Firmendaten). Sichtteil ist das
  Rechnungsdokument auf dem Briefbogen (`fee_documents.build_letter`), der strukturierte Teil
  das CII im Profil EN 16931. PDF und XML weichen nicht voneinander ab; die eigene Prüfung liest
  das XML mit dem Belegeingangsleser zurück und vergleicht es mit der Rechnung.
- Eine Gutschrift trägt im XML den Typ 381, positive Beträge und den Bezug auf die Ursprungsrechnung
  (BT-25, BT-26); das Dokument zeigt wie bisher negative Beträge.
- PDF/A-3: Die Datei trägt die Kennzeichnung (XMP `pdfaid` Teil 3 B, Factur-X Erweiterungsschema,
  Ausgabebedingung sRGB, Associated File mit `AFRelationship` Alternative). Die Konformität wird
  nie behauptet: die eigene Vorprüfung meldet immer `not_verified`, sichtbare Blocker (derzeit
  nicht eingebettete Standardschriften des Briefbogens) und die nicht prüfbaren Punkte.
- Ablage einmal je Rechnung mit Prüfergebnis (Zeitpunkt, SHA-256, Befunde). Kein Versand, keine
  Buchung; die XRechnung (UBL) bleibt unverändert verfügbar.
- Lesen: Profil aus der Spezifikationskennung, Containerangaben aus XMP und Anhang. Abweichungen
  (kein PDF/A-Kennzeichen, Profil MINIMUM oder BASIC WL, Profil laut XMP ungleich XML, fehlende
  AFRelationship) sind Hinweise, die formale Lesung und das Ergebnis bleiben unverändert.
