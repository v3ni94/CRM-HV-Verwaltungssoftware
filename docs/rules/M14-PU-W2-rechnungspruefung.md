# M14-PU-W2 Rechnungsprüfung: Pflichtangaben, Beträge, Bezüge, Delegation, Kreditoren, Rechnungspläne, E-Rechnungsnachweis

| Field | Content |
| --- | --- |
| ID | `M14-PU-W2` |
| Title | Weitere Prüfhinweise PÜ01 bis PÜ05 an der Eingangsrechnung, Gutschrift mit Pflichtbezug, dokumentierte Delegation, Kreditorenübersicht, Lebenszyklus der Rechnungspläne, gespeichertes Validierungsergebnis und Hashnachweis der E-Rechnung, Gutschrift als XRechnung mit Ursprungsbezug |
| Scope | `mhvp.accounting.invoice_checks`, `mhvp.accounting.invoices` (`evaluate`, `payment_hash`, `post`), `mhvp.accounting.creditor_routers` (`/accounting/ledgers/{id}/creditors…`, `/accounting/recurring-invoices…`), `mhvp.accounting.xrechnung_credit`, `mhvp.receipts.einvoice` (`archive_evidence`, `formal_validation`, `hybrid_deviations`), `POST /receipts/drafts/{id}/validation`; Migration 0252; alle Mandanten |
| Source status | Fachliche Umsetzung nach 7.9.1 PÜ01 bis PÜ05 und 7.11 S02, S03 (R19, R21, R22, R23 in Anhang C nur als Prüfhinweis). Die Pflichtangaben-Checkliste folgt der Aufzählung in PÜ01, sie ist keine Aussage über den gesetzlichen Mindestinhalt einer Rechnung. Reverse Charge und Bauabzugsteuer sind Kennzeichen zur Fachprüfung durch den Steuerberater, keine automatische Steuerbehandlung |
| Acceptance case | `tests/unit/test_w2_p03_checks.py`, `tests/integration/test_w2_p03_invoice_checks.py`, Ergänzung in `tests/integration/test_m14_receipt_drafts.py::test_d41_…`; D12 und D45 bleiben unverändert (`tests/integration/test_m14_invoices.py`) |
| Change reason | Lückenliste 30.09.2026, Befunde M14-01 bis M14-09, S711-01, S711-02, S711-04 |

## Regeln

- Alle neuen Prüfungen erzeugen nur Hinweise (`findings`); kein Prüfschritt wird dadurch
  abgeschlossen (PÜ05). Gesperrt wird nur, was schon gesperrt war, und zusätzlich die Buchung
  einer Gutschrift, deren Ursprungsrechnung nicht gebucht ist, einem anderen Aussteller oder
  Buchungskreis gehört oder durch alle Gutschriften überschritten würde (409).
- PÜ01: Leistungsort, USt-IdNr. oder Steuernummer des Ausstellers, weitere Anlagen
  (`attachment_document_ids`) und ein Vertragsbezug (`service_contract_id`) sind Felder. Ende
  vor Beginn des Leistungszeitraums wird abgewiesen (422); ein Zeitraum über das
  Wirtschaftsjahr des Buchungskreises hinaus und ein Beginn mehr als 366 Tage nach dem
  Rechnungsdatum sind Hinweise. Die Checkliste `mandatory_checklist` zeigt je Angabe vorhanden
  oder fehlend.
- PÜ02: Ein verknüpfter Dienstleistervertrag muss zum Aussteller gehören und den
  Leistungszeitraum abdecken (Beginn, Ende oder Kündigung). Hinweise auf verbundene
  Unternehmen oder Interessenkonflikte: Name gleich einem Rechtsträger des Mandanten, Rolle
  Eigentümer oder Verwalter, Kontakttyp Beirat, Mitglied des Rechtsträgers des Buchungskreises
  oder Beziehung zu einem solchen Kontakt. Eine Wertung trifft die Plattform nicht.
- PÜ03: Skonto wird aus Satz und Bruttobetrag nachgerechnet (kaufmännisch auf Cent) und mit
  dem angegebenen Skontobetrag verglichen. Zahlbetrag = Brutto minus Abzüge der
  Schlussrechnung minus Anzahlung minus Sicherheitseinbehalt; die Aufwandsbuchung bleibt
  unverändert, der Einbehalt bleibt Verbindlichkeit. Anzahlung und Einbehalt gehen, wenn
  gesetzt, in den Freigabehash ein (6.9.9).
- PÜ04: Inhaltsgleiche Dateien (SHA-256 des Dokuments) an einer anderen Rechnung sind ein
  Hinweis auf Doppelrechnung oder korrigierte Version; die Entscheidung trifft der Prüfer. Eine
  gegenüber der Vorversion (`supersedes_id`) geänderte IBAN verlangt die gesonderte
  Bestätigung.
- PÜ05: Ein Prüfschritt kann eine Delegation dokumentieren (`delegated_by` und
  `delegation_reason` nur gemeinsam, nicht an sich selbst) und die geprüften Seiten,
  Positionen oder Anlagen strukturiert nennen (`reviewed_items`).
- Rechnungspläne: Monatsende wird über den Ankertag behandelt (31.01. ergibt 28.02. und
  31.03.); der Leistungszeitraum endet am Tag vor der nächsten Fälligkeit; ein Bruttobetrag
  mit Steuersatz wird in Netto und Steuer geteilt, Netto ist der Rest (B06). Ein Plan wird
  beendet statt gelöscht, sobald er eine Rechnung erzeugt hat. Erzeugt wird immer nur ein
  ungeprüfter Entwurf.
- Kreditoren: Liste je Buchungskreis mit Saldo (Haben minus Soll), offenen Posten und
  Kontoauszug; Kreditorenkonten entstehen weiter erst mit der ersten Buchung.
- E-Rechnung (S02, S03): Profil (BT-24), eigenes Formalprüfergebnis mit Name und Version
  (`official=false`), SHA-256 der empfangenen Datei und des eingebetteten XML werden am
  Belegentwurf gespeichert; ein extern ermitteltes Validatorergebnis (z. B. KoSIT) wird mit
  Name, Version und Konfiguration erfasst und belegt nur formale Gültigkeit. Weitere
  Abweichungen zwischen XML und PDF-Text (Netto, Steuer, Datum, Fälligkeit, IBAN) werden
  unabhängig vom KI-Abgleich festgehalten und an die Rechnung übernommen.
- Gutschrift als XRechnung: UBL CreditNote mit Typcode 381 und BillingReference (BT-25, BT-26)
  auf die stornierte Honorarrechnung, Beträge positiv. Nur eigene Strukturprüfung; die
  offizielle Validierung ist offen (S711-02 in `docs/OPEN_QUESTIONS.md`).
