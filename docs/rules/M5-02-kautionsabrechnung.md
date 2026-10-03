# M5-02 Kaution: getrennte Verwahrung, Verzinsung je Jahr, Kautionsabrechnung als Entwurf

| Field | Content |
| --- | --- |
| ID | `M5-02` |
| Title | Kaution: getrennte Verwahrung, Verzinsung je Jahr als Bewegung, Kautionsabrechnung bei Vertragsende als Entwurf mit wählbarer Zinsart |
| Scope | Mietverhältnisse (`contract.kind = tenancy`) mit Kaution (`deposit`), alle Mandanten; Tabellen `deposit_settlement` und `deposit_interest_reference_rate` (Domäne `contracts`, RLS je Mandant, Migration 0138); keine Buchung, keine Zahlung, keine Forderung (G1, G3 unberührt) |
| Source status | Offene Entscheidung, Typ Fachliche Umsetzung mit Produktschutz. Betreiberentscheidung vom 26.09.2026 (docs/OPEN_QUESTIONS.md, M5-02): Standardregel "Kaution getrennt verwahren, Zinsen je Jahr als Bewegung erfassen, Abrechnung bei Vertragsende als Entwurf". Quellenregister Anhang C: § 551 BGB ist als ergänzend geprüfter Baustein für Wohnraummietsicherheiten benannt (Vermögenstrennung, Zinszuordnung, D56); welcher Zinssatz für die Verzinsung rechtlich maßgeblich ist, ist nicht aus dem Register belegt und **durch Rechtsberatung zu bestätigen**. Eigentümer: Betreiber mit Rechtsberatung. Betroffenes Tor: G3 (Freigabe der Abrechnung), G1 (Bewegungen als Buchung ab M10) |
| Acceptance case | keine Nummer in Anhang D; D56 (Kaution bleibt ihrer Vermögenssphäre und Zinszuordnung zugeordnet) als Leitfall. Tests mit handgerechneten Erwartungswerten (Regel 0.1.8): `apps/api/tests/unit/test_m5_deposit_settlement.py` (drei Zinsarten, Schaltjahr, Rundung, Raten), `apps/api/tests/integration/test_m5_deposit_settlement.py` (API, Mandantentrennung, G3-Sperre, PDF-Dokument: `test_settlement_document`); CRM `apps/web-crm/src/components/contracts/DepositPanel.test.tsx`, `apps/web-crm/src/components/settings/DepositInterestRatesAdmin.test.tsx` |
| Implementation | `mhvp.contracts.deposit_settlement` (Modelle, Berechnung), `mhvp.contracts.deposit_settlement_routers` (`GET /deposit-interest-rates`, `PUT`/`DELETE /deposit-interest-rates/{year}`, `POST /deposits/{id}/settlements/preview`, `POST`/`GET /deposits/{id}/settlements`, `POST /deposit-settlements/{id}/release` hinter G3, `POST /contracts/{id}/deposit-settlements/{sid}/document` und `GET .../document-preview`), `mhvp.contracts.deposit_settlement_pdf` (Briefaufbau, Speicherung, Verknüpfung), CRM Vertragsdetail (Abschnitt Kautionen, Knopf "Abrechnung als PDF erzeugen und ablegen") und Einstellungen, Kautionszinsen; Regelversion 2 (27.09.2026, PDF-Ausgabe ergänzt) |
| Change reason | Betreiberentscheidung M5-02 vom 26.09.2026; zuvor waren Verzinsung und Abrechnung nicht umgesetzt (nur Soll, Raten, Bewegungen) |

## Regeln

- Die Kaution liegt auf einem getrennten Kautionskonto des Vermieters (bestehende Prüfung
  `check_deposit_account`, 6.9.1, D56). Sie ist kein freies Objektgeld.
- Verzinsung wird je Jahr als Bewegung `interest` erfasst (bestehendes Modell
  `deposit_movement`). Bewegungen bleiben bis M10 Datensätze, keine Buchungen
  (`review_required`).
- Die Kautionsabrechnung bei Vertragsende ist ein Entwurf (`deposit_settlement`, Status
  `draft`). Sie bucht nichts, zahlt nichts aus und erzeugt keine Forderung. Ein Entwurf
  übersteigt nie das Guthaben: übersteigen die Einbehalte das Guthaben, wird der Entwurf
  abgelehnt (422); eine Forderung gegen den Mieter ist ein eigener Vorgang (M13, G1).
- Zinsart je Entwurf, vom Sachbearbeiter gewählt:
  - `individual`: Zinsbeträge je Kalenderjahr werden eingegeben (z. B. aus dem Kontoauszug
    des Kautionskontos); bereits erfasste Zinsbewegungen werden im CRM vorbelegt. Jahre
    außerhalb der Laufzeit werden abgelehnt.
  - `reference_rate`: Zinsen werden je Kalenderjahr aus der Tabelle "Referenzzinssatz je
    Jahr" des Mandanten berechnet (`deposit_interest_reference_rate`, Prozent, bis fünf
    Nachkommastellen, vom Betreiber gepflegt). Fehlt der Satz für ein Jahr der Laufzeit,
    wird die Berechnung abgelehnt; es wird kein Satz bezogen, vorbelegt oder erfunden.
  - `none`: keine Verzinsung.
- Berechnung (nur `Decimal`, kein Float, Regel 6.9.8):
  - Basis ist das Kautionsguthaben aus erfassten Einzahlungen abzüglich Verrechnungen und
    Auszahlungen nach Datum. Erfasste Zinsbewegungen werden zum Abgleich ausgewiesen, aber
    weder verzinst noch erneut addiert (kein Zinseszins innerhalb des Entwurfs; das Erfassen
    der berechneten Zinsen als Jahresbewegung bleibt ein eigener Schritt).
  - Tagesgenau: ein Guthaben zählt ab dem Tag der Bewegung bis zum Tag vor der nächsten
    Bewegung, der letzte Abschnitt bis zum Abrechnungsdatum einschließlich. Jahresbasis
    365 oder 366 Tage.
  - Je Kalenderjahr: Summe über die Abschnitte von Guthaben x Satz / 100 x Tage / Jahrestage,
    dann einmal je Jahr kaufmännisch auf den Cent gerundet (ROUND_HALF_UP).
  - Auszahlungsbetrag = Guthaben vor Zinsen + Zinsen gesamt (laut Zinsart) minus Einbehalte
    des Entwurfs.
- Bewegungen nach dem Abrechnungsdatum und ein Abrechnungsdatum vor dem Vertragsende werden
  abgelehnt. Ohne Einzahlung gibt es keine Abrechnung.
- `POST /deposit-settlements/{id}/release` (Freigabe zur Auszahlung) steht hinter
  Freigabetor G3 und ist je Mandant standardmäßig geschlossen (`MHVP-GATE-0001`). Bis zur
  Freigabe ändert sich am Entwurf nichts; die Auszahlung selbst bleibt ein manueller Vorgang
  (Bewegung `payout`, Zahlung erst hinter G2).
- Ausgabe: JSON-Datensatz (Kaution, Zinsen je Jahr mit Satz und Tagen, erfasste
  Verrechnungen und Auszahlungen, Einbehalte, Auszahlungsbetrag). Zusätzlich erzeugt
  `POST /contracts/{id}/deposit-settlements/{sid}/document` (Restpunkt vom 27.09.2026,
  `mhvp.contracts.deposit_settlement_pdf`) die Abrechnung als PDF-Entwurf auf dem
  Briefbogen des Mandanten (`mhvp.documents.letters`, DIN 5008): Positionen des
  Kautionsguthabens, Zinsverlauf je Jahr (Zinsart, Satz, Tage, Betrag, sofern verzinst),
  Einbehalte mit Begründung, Auszahlungsbetrag und die maskierte Bankverbindung des
  Mieters (`mhvp.ai.table_mapper.mask_iban`). Das Dokument wird im Dokumentenindex
  abgelegt und mit Vertrag und Mieterkontakt verknüpft (`deposit_settlement.document_id`,
  Migration 0184); es bucht nichts und weist nichts aus (kein `MHVP-GATE`-Bezug, G1/G3
  bleiben unberührt). Welcher Zinssatz rechtsverbindlich maßgeblich ist, bleibt weiterhin
  eine Einschätzung im Brieftext, keine Rechtsauskunft.

## Rechenbeispiel (Erwartungswert von Hand, Regel 0.1.8)

Einzahlung 1.200,00 EUR am 01.01.2025, Verrechnung 200,00 EUR am 01.04.2026, Abrechnung
zum 30.06.2026, Referenzzinssatz 2025 = 1,00 %, 2026 = 0,50 %.

| Jahr | Abschnitt | Guthaben | Tage | Rechnung | Zinsen |
| --- | --- | --- | --- | --- | --- |
| 2025 | 01.01. bis 31.12. | 1.200,00 | 365 | 1.200 x 0,01 x 365/365 | 12,00 |
| 2026 | 01.01. bis 31.03. | 1.200,00 | 90 | 1.200 x 0,005 x 90/365 = 1,4794... | |
| 2026 | 01.04. bis 30.06. | 1.000,00 | 91 | 1.000 x 0,005 x 91/365 = 1,2465... | 2,73 |

Zinsen gesamt 14,73 EUR, Guthaben vor Zinsen 1.000,00 EUR, Einbehalt 150,00 EUR,
Auszahlungsbetrag 864,73 EUR.

## Offene Punkte

- Rechtsgrundlage des maßgeblichen Zinssatzes und der Anlageform (Rechtsberatung).
- Zinseszins innerhalb eines Entwurfs über mehrere Jahre ohne erfasste Zinsbewegungen
  (derzeit bewusst nicht; Entscheidung Betreiber mit Rechtsberatung).
- Übergang der Bewegungen in Buchungen (M10, G1) und PDF-Vorlage der Kautionsabrechnung.

## Invariante: höchstens eine freigegebene Abrechnung je Kaution (AP25)

- Art: Produktschutz (Geld Dritter, keine zweite Auszahlung); Quellenstatus: keine Rechtsgrundlage, technische Absicherung.
- Freigabe sperrt die Abrechnung (Zeilensperre) und die Kaution; der Status wird innerhalb der Sperre geprüft, eine zweite parallele Freigabe erhält 409.
- Solange eine freigegebene Abrechnung besteht, lehnt die API das Anlegen und Freigeben eines weiteren Entwurfs derselben Kaution mit 409 ab. Ein Storno freigegebener Abrechnungen gibt es derzeit nicht; es bliebe hinter G3.
- Datenbank: partieller eindeutiger Index `uq_deposit_settlement_released` (Migration 0469); die Migration bricht bei vorhandenen Doppelungen mit Meldung ab.
- Abnahmefall: tests/integration/test_m5_deposit_settlement_parallel.py.
- Änderungsgrund: AP10-01 und AP10-02 (Welle 26, GAM-606).
