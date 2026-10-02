# AE22 Verbindlichkeitsposten aus Guthaben von Abrechnungen (P04-04, Q01-01, M15-07)

| Field | Content |
| --- | --- |
| ID | `AE22` |
| Title | Guthaben aus Mietabrechnung, Eigentümerabrechnung und Kautionsabrechnung werden per Vorschlag und Freigabe zu Verbindlichkeitsposten; Zahlungsauftrag ohne Rechnung aus dem Posten; Storno-Pfad |
| Scope | `mhvp.accounting.credit_payables`, `mhvp.accounting.credit_payable_routers` (`/api/v1/accounting/credit-payables`), `mhvp.accounting.credit_payable_models` (`credit_payable`, `credit_payable_setting`), Buchungsart `credit_reclass` in `mhvp.accounting.services._apply_open_items`; Quellen `billing` (Ergebnisbuchung der Betriebskostenabrechnung, Eigentümerabrechnung ab Status `issued`), `contracts` (freigegebene Kautionsabrechnung); Auszahlung über `mhvp.banking.payment_run.order_for_payout`; alle Mandanten, Schalter je Mandant, Standard aus |
| Source status | Keine Rechtsgrundlage aus Anhang C. Die Buchungsregel (Konten, Buchungsart, Ausgleich des Debitorenguthabens) ist offen: OPEN_QUESTIONS Q01-01 und P04-04, Eigentümer Timo Müller mit Steuerberater, Gates G1, G2, G3. Beide Varianten sind technisch vorbereitet, keine ist freigegeben. Kontonummern sind Eingaben des Betreibers. Produktschutz: Vier-Augen-Freigabe (Standard an), G3 für die Freigabe, G2 und G3 für den Zahlungsauftrag, G1 für den Storno einer gebuchten Umbuchung |
| Acceptance case | kein Anhang-D-Fall; Sollwerte von Hand: Guthaben 80,00 EUR ergibt einen Verbindlichkeitsposten von 80,00 EUR und einen Zahlungsauftrag von 80,00 EUR; Tests `apps/api/tests/integration/test_ae22_credit_payables.py`, `apps/api/tests/unit/test_ae22_credit_payables.py`, `apps/web-crm/src/components/banking/CreditPayables.test.tsx` |
| Implementation | Migration `0378_ae22_credit_payable` (zwei Tabellen mit RLS, Enumwert `credit_reclass`) |
| Change reason | Prioritätenliste des Betreibers vom 01.10.2026, Punkt 22 (Welle 16, Paket AE22); Restpunkt M15-07 der Pakete P04 und Q01 |

## Regeln

- Schalter `credit_payable_setting.mode`:
  - `off` (Standard): Kandidaten werden angezeigt, Vorschläge sind gesperrt (409). Es entsteht
    kein Posten und keine Buchung.
  - `subledger`: Die Freigabe legt zur gebuchten Gutschrift der Ergebnisbuchung einen
    Verbindlichkeitsposten auf dem Debitorenkonto an (keine neue Buchung). Nur für die
    Mietabrechnung, da nur dort eine gebuchte Gutschrift besteht.
  - `reclass`: Die Freigabe schreibt einen Buchungsentwurf der Art `credit_reclass` (Soll
    Quellkonto, Haben hinterlegtes Kreditorenkonto). Quellkonto: Debitorenkonto des Vertrags
    (Mietabrechnung), hinterlegtes Sollkonto der Eigentümerauszahlung oder der
    Kautionsrückzahlung. Erst die Buchung auf dem normalen Weg erzeugt den Posten, und zwar
    nur auf der Habenzeile des Kreditorenkontos; die Sollzeile auf dem Debitorenkonto erzeugt
    keine Forderung.
- Kandidaten (nur Anzeige): gebuchte, nicht stornierte Ergebnisbuchung mit Schlüssel
  `rent-statement:<Abrechnung>:<Vertrag>`, die in `result_entry_ids` der Abrechnung steht
  (Status fällig, gebucht oder abgeschlossen) und das Debitorenkonto im Haben bewegt;
  Verrechnungsbuchungen offener Vorauszahlungen (`rent-statement-offset:`) zählen nicht.
  Eigentümerabrechnung ab `issued` mit positivem Auszahlungsbetrag (Berechnung der
  Abrechnung, `owner_statement_pdf.settlement`). Freigegebene Kautionsabrechnung mit
  positivem Auszahlungsbetrag; der Buchungskreis folgt dem Rechtsträger des Debitorenkontos
  des Vertrags.
- Ein aktiver Vorschlag je Quelle und Vertrag (eindeutiger Teilindex). Der Betrag ist das
  Abrechnungsergebnis; nur bei der Eigentümerauszahlung darf er gesenkt werden. Hinweise
  (keine Sperre): offene Forderungen des Vertrags (Verrechnung prüfen, keine automatische
  Verrechnung), Teilbetrag.
- Freigabe: Recht `accounting:approve`, G3, andere Person als der Vorschlag, solange
  `four_eyes_required` an ist; die Variante muss dem aktuellen Schalter entsprechen.
- Zahlungsauftrag: Recht `accounting:create`, G2 und G3; nur für einen offenen Posten ohne
  aktiven Auftrag; Empfängerkonto freigegeben und Mitglied der Vertragspartei
  (Eigentümerauszahlung: Mitglied der Eigentümerpartei des Rechtsträgers); Kautionsrückzahlung
  nur vom getrennten Kautionskonto. Der Auftrag braucht weiter zwei Freigaben, die Datei G2.
- Storno-Pfad (`POST /{id}/withdraw`, Grund Pflicht): Vorschlag zurücknehmen; Umbuchung im
  Entwurf verwerfen; gebuchte Umbuchung per Storno (B03, G1); ein Nebenbuchposten wird nur
  über den Storno der Ergebnisbuchung geschlossen (Korrektur der Abrechnung), der Storno
  gleicht den Posten aus. Gesperrt bei aktivem Zahlungsauftrag und bei (teilweiser) Zahlung:
  Korrektur dann nur über die Rückbuchung der Zahlung (0.1.7). Wird die Ergebnisbuchung nach
  einer gebuchten Umbuchung storniert, zeigt der Posten `source_reversed` und ist nicht
  auszahlbar.

Ergänzung Welle 17 (AF04, GAE-05, GAE-07):

- Storno einer Buchung mit offenen Posten oder Rechnungen: noch nicht an die Bank übergebene
  Zahlungsaufträge (Entwurf, freigegeben) werden mit dem Storno auf `cancelled` gesetzt, die
  Freigaben entfallen; an die Bank übergebene Aufträge (exportiert, eingereicht, angenommen)
  sperren den Storno (409) bis zur Ablehnung oder Rückgabe. Abnahmefall
  `test_gae05_reversal_cancels_open_payment_order`.
- Ein Umbuchungsentwurf eines freigegebenen Guthabenpostens wird nicht über `DELETE` der
  Buchung gelöscht (409), sondern über `/credit-payables/{id}/withdraw` zurückgenommen.
  Abnahmefall `test_gae07_delete_reclass_draft_refused`; Gesamtablauf Eigentümerabrechnung
  `test_gae06_owner_statement_reclass_end_to_end` (2.643,00 EUR).
