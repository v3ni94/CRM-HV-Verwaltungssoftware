# PU02-SACHLICH Sachliche Rechnungsprüfung als Befunde (PÜ02, M14-02)

| Field | Content |
| --- | --- |
| ID | `PU02-SACHLICH` (Lückenliste M14-02) |
| Title | Abgleich der Eingangsrechnung gegen Auftrag, Dienstleistervertrag, WEG Beschluss, Budget (Wirtschaftsplanposition) und Rechnungsplan mit Preis- und Mengenabgleich; Zuständigkeitsvorschlag Objektverwalter |
| Scope | `mhvp.accounting.invoice_factual` (`factual_check`, `within`, `line_findings`), `invoice_checks.factual_findings` (Befunde an `invoice.findings`), `GET /accounting/invoices/{id}/factual-check`, `GET/PUT /accounting/invoice-check-settings`; Felder `invoice.work_order_id`, `invoice.resolution_id`, `invoice.plan_item_id`, `invoice_line.quantity`, `invoice_line.unit_price`, Tabelle `invoice_check_setting` (Migration 0291); alle Mandanten |
| Source status | Fachliche Umsetzung (0.2) von 7.9.1 PÜ02. Keine Rechtsregel: die Befunde sind Hinweise, die Bewertung trifft die prüfende Person. Toleranzen sind Produktschutz, Standard 0 (exakter Abgleich); ein anderer Wert ist Betreiberentscheidung |
| Acceptance case | `tests/integration/test_w5_t05_invoice_factual.py` (Angebot 1.000,00 gegen 1.190,00 bei 0 % Befund, bei 20 % kein Befund; Kostengrenze 1.100,00; Planansatz 2.000,00 mit zweiter Rechnung 2.380,00 überschritten; Beschluss angefochten und Leistung vor Beschlussdatum; Rechnungsplan monatlich mit Abstand zwei Monate; Betrag 130,00 gegen 119,00; Fremdmandant 404, Leserecht 403, negative Toleranz 422), `tests/unit/test_invoice_factual.py` (3 x 300,00 = 900,00 gegen 1.000,00) |
| Change reason | Lückenliste 30.09.2026 M14-02: sachliche Prüfung war nur Freitext ohne Verknüpfung |

## Regeln

- Der Auftrag wird als `work_order_id` verknüpft; ohne Verknüpfung gilt die Rückverknüpfung
  `work_order.invoice_id`. Der Freitext `order_reference` bleibt erhalten; ein reiner Freitext
  ohne Vertrag erscheint als Hinweis nur in der sachlichen Prüfung, nicht an der Rechnung.
- Auftrag: anderer Dienstleister, anderes Objekt, Auftrag nicht erteilt (Entwurf, angefragt,
  Angebot) oder abgelehnt/storniert, bereits anderer Rechnung zugeordnet, Abweichung vom
  Angebotsbetrag über der Preistoleranz (Brutto gegen `quote_amount`), Überschreitung der
  Kostengrenze `budget_limit`, erforderliche Zustimmung ohne Erfassung.
- Vertrag: bestehende Prüfung `contract_findings` (Aussteller, Vertragszeitraum).
- Beschluss: andere Gemeinschaft als der Rechtsträger des Buchungskreises, Status nicht
  positiv/bestandskräftig, Leistung vor dem Beschlussdatum. Über die Wirksamkeit eines
  Beschlusses wird nichts entschieden.
- Budget: Planposition in anderem Buchungskreis oder Wirtschaftsjahr, kein Rechnungskonto
  gleich dem Konto der Position, Summe der verknüpften Rechnungen (Gutschriften abgezogen,
  stornierte ausgenommen) über dem Planansatz zuzüglich Preistoleranz.
- Wiederkehr: Betrag gegen den Rechnungsplan (Preistoleranz), Aussteller, Plangeltung,
  Abstand zur Vorrechnung in Monaten gegen `interval_months`, zweite Rechnung im selben Monat.
  Ohne Verknüpfung: Hinweis bei gleichem Betrag eines laufenden Plans desselben Ausstellers.
- Menge: Menge mal Einzelpreis gegen den Positionsnetto (Mengentoleranz).
- Zuständigkeit: Objektverwalter (`property.manager_user_id`) des Objekts des Buchungskreises,
  sonst des Auftrags oder Vertrags, nur als Vorschlag.
- Keine Funktion setzt einen Prüfstatus, gibt frei, bucht oder zahlt (PÜ05,
  `automatic_release` immer false).

## Änderung Welle 16 (AE14, P03-03)

Geltungsbereich: sachliche Prüfung von Eingangsrechnungen mit Bezug zu Wirtschaftsplanposition oder Beschluss.
Budgetabgleich als Kennzahlen (Planansatz, bisher zugeordnet, diese Rechnung, Rest) und Beschlussdeckung
(Status, Gegenstand passt zum Wirtschaftsplan). Quellenstatus: Produktschutz, keine Rechtsgrundlage; eine
Wertgrenze für eine Beschlusspflicht wird nicht angenommen. Abnahmefall: tests/integration/test_ae14_invoice_budget.py
(Soll 2.000,00 EUR, bisher 952,00 EUR, Rechnung 1.190,00 EUR, Rest -142,00 EUR). Änderungsgrund: Prioritätenliste Punkt 14.
