# M14 Belegeingang: KI-Extraktion von Eingangsrechnungen als Vorschlag

Stand 26.09.2026. Backlog Welle 4, Punkt 15. Regeln 0.1.6, 0.1.7, 0.1.13; Spezifikation 6.4, 9.

## Ziel

Eingangsrechnungen aus Mail-Anhängen, Paperless oder Upload werden von der KI als Entwurf mit
Konfidenz je Feld vorgeschlagen. Der Entwurf ist nie eine Buchung; erst die Bestätigung durch
eine Person legt einen offenen, ungebuchten Rechnungsentwurf an. Eine IBAN wird nie ohne
ausdrückliche Bestätigung übernommen.

## Umsetzung

| Bereich | Dateien |
| --- | --- |
| Modell und Migration | `apps/api/src/mhvp/receipts/models.py`, `apps/api/alembic/versions/0080_receipt_draft.py` |
| Maskierung und IBAN-Kandidaten | `apps/api/src/mhvp/receipts/masking.py` |
| Extraktion, Feldkonfidenz, Objektvorschlag | `apps/api/src/mhvp/receipts/extraction.py` |
| API | `apps/api/src/mhvp/receipts/routers.py`, `schemas.py` (`/api/v1/receipts`) |
| CRM | `apps/web-crm/src/app/(app)/rechnungen/belegeingang/page.tsx`, `components/receipts/ReceiptIntake.tsx` |
| Tests | `tests/unit/test_m14_receipt_drafts.py`, `tests/integration/test_m14_receipt_drafts.py`, `tests/ai_eval/extract_invoice/` |

Ablauf: Dokumenttext (bereits extrahiert) wird lokal nach IBAN-Kandidaten durchsucht, dann
maskiert (IBAN, BIC, E-Mail, Telefon, Namen mit Anrede) und als Anweisung an den vorhandenen
`extract_invoice`-Lauf des KI-Moduls übergeben (ohne `document_ids`, damit das Gateway das
Original nicht erneut liest). Das Ergebnis wird beim nächsten Lesen in den Entwurf übernommen:
je Feld Wert, Konfidenz, Quelle (KI, Plattform, kein Wert) und Hinweis. Der Objektbezug wird
lokal gegen die Objekte des Mandanten vorgeschlagen. Bestätigen erzeugt die Rechnung über den
bestehenden Pfad `mhvp.ai.imports.apply_invoice` (offen, ungebucht); Verwerfen schließt den
Entwurf.

## Abnahme

* Entwurf statt Buchung: nach der Extraktion existiert keine Rechnung; nach Bestätigung eine
  Rechnung mit `posting_status = unposted`, `review_status = open`.
* Maskierung: der Anbieteraufruf enthält keine IBAN, E-Mail, Telefonnummer und keinen Namen
  mit Anrede; der Ausstellername bleibt erhalten.
* IBAN: Bestätigung mit `payee_iban` ohne `iban_confirmed` wird mit 422 abgelehnt.
* Mandantentrennung: Entwürfe anderer Mandanten sind nicht lesbar, nicht entscheidbar und nicht
  in der Liste.

## Offene Punkte

* Konfidenz je Feld ist abgeleitet (Gesamtkonfidenz des Modells plus deterministische
  Prüfungen), nicht vom Modell je Feld gemeldet; ein eigenes Schema mit Feldkonfidenzen wäre
  eine Prompt- und Schemaänderung von `extract_invoice` (siehe `docs/OPEN_QUESTIONS.md`).
* Personennamen ohne Anrede (z. B. Einzelunternehmer als Aussteller) werden nicht maskiert.
* Die bestehende Aktion "Anhang als Rechnung erfassen" in der Mailansicht nutzt weiterhin den
  Chat-Vorschlag (`/ai/proposals`); Umstellung auf `POST /receipts/drafts` mit
  `source=mail_attachment` steht aus.
* Migration 0080: `down_revision` beim Zusammenführen auf den tatsächlichen Head setzen.
