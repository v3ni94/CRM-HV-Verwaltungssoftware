# M11-06 Zahlung nur Vorschlag bis G2

| Field | Content |
| --- | --- |
| ID | `M11-06` |
| Title | Ein aus dem Rechnungsabgleich erzeugter Zahlungsauftrag bleibt Entwurf, solange Gate G2 (Zahlungsauslösung) für den Mandanten geschlossen ist |
| Scope | Domäne `banking`, Endpunkt `POST /banking/invoice-matching/{invoice_id}/match`; alle Mandanten |
| Source status | Master-Prompt Abschnitt 18.0 (Freigabestufen G0-G5) und 0.1.6 (KI/Automatisierung schlägt nur vor); kein Rechnungsnorm-Bezug |
| Acceptance case | Master-Prompt Annex D Grundsatz "keine Zahlungsauslösung ohne G2"; Tests `apps/api/tests/integration/test_m11_invoice_matching.py::test_unmatched_invoice_creates_draft_proposal_never_initiates` |
| Implementation | `mhvp.banking.invoice_matching.propose_payment` (ruft ausschließlich `mhvp.banking.payments.order_from_invoice`), `mhvp.banking.models.PaymentOrder.status` startet als `DRAFT` |
| Change reason | M11-finapi Stage 3 (Rechnung-zu-Bankumsatz-Abgleich), Auftrag 25.09.2026 |

## Regeln

- Findet der automatische Abgleich (Betrag und Rechnungsnummer oder Empfänger-IBAN im
  Verwendungszweck) keinen passenden, bereits importierten Bankumsatz, darf die Plattform
  höchstens einen **Zahlungsvorschlag** anlegen: einen `PaymentOrder`-Datensatz im Status
  `draft` über den bestehenden, unveränderten `mhvp.banking.payments.order_from_invoice`-Pfad.
- Der Abgleich-Endpunkt selbst exportiert, übermittelt oder bestätigt nichts gegenüber einer
  Bank oder einem Zahlungsdienstleister; er ruft an keiner Stelle den finAPI-Client oder einen
  anderen Provider zur Zahlungsauslösung auf (dieser Codepfad existiert nicht, siehe
  `docs/integrations/finapi.md`, Stand "read only").
- Der weitere Weg eines Vorschlags (Freigabe durch zwei Personen, Exportdatei, Einreichung)
  bleibt der bestehende, unveränderte Zahllauf-Prozess (M15) samt Gate G2. Diese Regel fügt
  keinen neuen Freigabeweg hinzu und umgeht keinen bestehenden.
- Die API-Antwort kennzeichnet einen erzeugten Vorschlag wörtlich als
  `"vorbereitet, nicht ausgeführt"`, damit eine bearbeitende Person den Unterschied zu einer
  tatsächlichen Zahlung nicht übersehen kann; das CRM übernimmt denselben Text ungekürzt.
