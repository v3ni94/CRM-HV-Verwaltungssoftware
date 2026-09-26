# M14 Belegeingang: KI-Extraktion von Eingangsrechnungen als Vorschlag

Stand 26.09.2026. Backlog Welle 4, Punkt 15; Lückenliste A13 und A14. Regeln 0.1.6, 0.1.7, 0.1.13;
Spezifikation 6.4, 9, 13.5 (E-Rechnung lesen), PÜ01, PÜ03; Fälle D41, D42, D44.

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
| E-Rechnung (A13) | `apps/api/src/mhvp/receipts/einvoice.py`, Migration `0095_receipt_draft_einvoice.py` |
| Tests | `tests/unit/test_m14_receipt_drafts.py`, `tests/unit/test_m14_einvoice.py`, `tests/integration/test_m14_receipt_drafts.py`, `tests/ai_eval/extract_invoice/`, `components/receipts/*.test.tsx`, `components/tickets/TicketMailAttachments.test.tsx` |

Ablauf: Dokumenttext (bereits extrahiert) wird lokal nach IBAN-Kandidaten durchsucht, dann
maskiert (IBAN, BIC, E-Mail, Telefon, Namen mit Anrede) und als Anweisung an den vorhandenen
`extract_invoice`-Lauf des KI-Moduls übergeben (ohne `document_ids`, damit das Gateway das
Original nicht erneut liest). Das Ergebnis wird beim nächsten Lesen in den Entwurf übernommen:
je Feld Wert, Konfidenz, Quelle (KI, Plattform, kein Wert) und Hinweis. Der Objektbezug wird
lokal gegen die Objekte des Mandanten vorgeschlagen. Bestätigen erzeugt die Rechnung über den
bestehenden Pfad `mhvp.ai.imports.apply_invoice` (offen, ungebucht); Verwerfen schließt den
Entwurf.

## E-Rechnung lesen (A13, D41, D42)

Der strukturierte Teil einer E-Rechnung wird ohne KI gelesen (`receipts.einvoice`, defusedxml,
pypdf für den eingebetteten Anhang `factur-x.xml`, `zugferd-invoice.xml`, `ZUGFeRD-invoice.xml`
oder `xrechnung.xml`): XRechnung als XML (UBL 2.1 `Invoice` und CII `CrossIndustryInvoice`)
und ZUGFeRD/Factur-X als PDF mit XML. Die UBL-Namensräume kommen aus
`mhvp.accounting.xrechnung` (Ausgangsseite), nicht doppelt.

* Reine XML-Datei: Entwurf entsteht sofort (`status=proposed`, kein KI-Lauf, kein
  `masked_excerpt`); Felder Aussteller, Empfänger, Nummer, Datum, Fälligkeit, Netto, Steuer,
  Brutto, Währung, Skonto (Prozent aus `#SKONTO#TAGE=..#PROZENT=..#`, Frist nur als Hinweis),
  Auftrags- oder Käuferreferenz mit Quelle `xml`; Positionen (`xml_lines`) und Zahlungsangaben
  (`xml_payment`, IBAN maskiert, Prüfziffer) daneben. Die IBAN geht nur in die verschlüsselte
  Kandidatenliste und wird wie bisher nur mit `iban_confirmed` übernommen.
* Hybrid (PDF mit XML): das XML ist der Vorschlag, der PDF-Text wird weiterhin maskiert an das
  Modell gegeben. Rechnungsnummer und Bruttobetrag aus dem XML müssen im PDF-Text vorkommen,
  die KI-Lesung wird je Feld gegen das XML verglichen. Jede Abweichung steht in `conflicts`
  (Feld, XML-Wert, anderer Wert, Quelle `pdf_text` oder `ai`), erzeugt den Prüfhinweis
  "Hybridrechnung: XML und PDF widersprechen sich" und sperrt `confirm`, bis
  `conflicts_acknowledged=true` gesendet wird; die Widersprüche werden als Prüfhinweise an die
  Rechnung übernommen. Keine stille Auswahl (D42).
* Formale Prüfung (PÜ01): fehlende Pflichtangaben im XML, Netto plus Steuer gegen Brutto,
  Positionssumme gegen Netto und Fremdwährung als `findings`. Formale Lesbarkeit schließt keinen
  Prüfschritt: die Rechnung entsteht mit `review_status=open`, ein sachlicher Einwand sperrt
  Freigabe und Buchung (D41). `e_invoice_format` und der gedruckte Empfänger werden an die
  Rechnung übergeben, damit die Rechtsträgerprüfung greift.
* CRM: Quelle je Feld ("XML (E-Rechnung)"), Widersprüche als Warnung mit Zeilenmarkierung und
  Bestätigungspflicht, Prüfhinweise, Positionen und Zahlungsangaben laut XML, Upload akzeptiert
  XML.

## § 35a aus der KI-Extraktion (A14, D44)

`ExtractedInvoice` kennt `section_35a_amount` und `section_35a_basis` (`invoice_statement`,
`line_items`, `estimate`). Nur ein vom Beleg ausgewiesener oder aus Positionen belegter Anteil
ist ein Vorschlag (Quelle `ai`, Prüfung am Original). Alles andere erhält die Quelle
`ai_estimate`, Sicherheit 0, den Prüfhinweis "§-35a-Anteil ... ist nur eine KI-Schätzung" und
die Rückfrage "Nachforderung: belegbare Aufteilung nach § 35a EStG". `confirm` übernimmt den
Wert nie (kein Feld in `InvoiceApplyIn`); der Prüfhinweis wandert an die Rechnung. Im CRM ist
das Feld nur zur Prüfung sichtbar, nicht editierbar.

## Abnahme

* Entwurf statt Buchung: nach der Extraktion existiert keine Rechnung; nach Bestätigung eine
  Rechnung mit `posting_status = unposted`, `review_status = open`.
* Maskierung: der Anbieteraufruf enthält keine IBAN, E-Mail, Telefonnummer und keinen Namen
  mit Anrede; der Ausstellername bleibt erhalten.
* IBAN: Bestätigung mit `payee_iban` ohne `iban_confirmed` wird mit 422 abgelehnt.
* Mandantentrennung: Entwürfe anderer Mandanten sind nicht lesbar, nicht entscheidbar und nicht
  in der Liste.
* D41 (`test_d41_xrechnung_xml_is_read_without_provider_call_and_objection_blocks_release`):
  XRechnung-XML ergibt einen Entwurf mit Quelle `xml` ohne Anbieteraufruf; nach Anlage bleibt
  die Prüfung offen; Einwand im Schritt `factual` sperrt Freigabe (409) und Buchung (409).
* D42 (`test_d42_hybrid_zugferd_conflict_is_visible_and_never_chosen_silently`): ZUGFeRD-PDF
  mit abweichender Textebene zeigt Widersprüche gegen PDF-Text und KI-Lesung, `confirm` ohne
  `conflicts_acknowledged` wird mit 422 abgelehnt, mit Bestätigung stehen die Widersprüche als
  Prüfhinweise an der Rechnung.
* D44 (`test_d44_ai_estimated_section_35a_share_is_never_shown_as_evidence`): geschätzter
  Anteil hat Quelle `ai_estimate`, Sicherheit 0, Prüfhinweis und Nachforderung; die Rechnung
  enthält den Wert nicht. Unit: `tests/unit/test_m14_einvoice.py` (UBL, CII, ZUGFeRD mit
  synthetischem PDF, Widerspruchserkennung, `test_d44_section_35a_estimate_is_never_evidence`).

## Paperless Post-Consume-Webhook (A30, 11.2/11.4)

* `mhvp/documents/paperless_webhook.py`: `POST /documents/webhooks/paperless` und
  `.../paperless/{tenant}` ohne Login; HMAC-SHA256 mit dem je Mandant hinterlegten
  `DmsConnection.webhook_secret` (Migration 0098, verschlüsselt, nur schreibbar) über
  `"<Zeitstempel>." + Rohbody`, Zeitfenster 300 s, Replay-Sperre über Redis (gleiche Signatur
  einmal, MHVP-HOOK-0003), ungültig oder fehlend MHVP-HOOK-0002 (401). Das Dokument wird über
  den bestehenden Paperless-Client (M31, `fetch_file`) einmal abgelegt
  (`Document.source_system = "paperless"`, `source_id` = Paperless-Nummer, eindeutig), der
  Spiegel-Eintrag wird als erledigt markiert, Ereignis `paperless.document_received`.
* Schalter `DmsConnection.auto_receipt_intake` (Standard aus, M14-05): dann Belegentwurf über
  `mhvp.receipts.extraction.prepare` und den KI-Lauf, Celery-Task
  `mhvp.documents.paperless_receipt_intake` (Queue `io`; in Tests inline über `ai_inline`).
  Quelle `paperless`, Ersteller leer, Ereignis `receipt_draft.started` mit `automatic=true`.
* CRM: Einstellungen, DMS-Anbindung, Abschnitt Post-Consume-Webhook (Geheimnis, Schalter).
* Tests: `tests/integration/test_m14_paperless_webhook.py` (gültig indexiert einmal, 401,
  Replay 409, Schalter aus/an, Tenant-Trennung).

## Offene Punkte

* Konfidenz je Feld ist abgeleitet (Gesamtkonfidenz des Modells plus deterministische
  Prüfungen), nicht vom Modell je Feld gemeldet; ein eigenes Schema mit Feldkonfidenzen wäre
  eine Prompt- und Schemaänderung von `extract_invoice` (siehe `docs/OPEN_QUESTIONS.md`).
* Personennamen ohne Anrede (A65, 26.09.2026): vor dem Anbieteraufruf werden zusätzlich zu den
  Anreden alle Personenkontakte des Mandanten (`Vorname Nachname`, `Nachname, Vorname`,
  schreibweisenunabhängig, OCR-Leerräume toleriert) sowie ein Ausstellername aus der
  E-Rechnung, der wie eine natürliche Person aussieht (`issuer_person_name`, Handwerkswort
  wie "Malerbetrieb" wird abgestreift), deterministisch durch `[NAME]` ersetzt
  (`mhvp.receipts.masking`, `extraction.known_person_names`, Tests
  `tests/unit/test_receipts_masking.py`). Ein Nachname allein wird bewusst nie maskiert,
  damit Firmennamen wie "Elektro Müller GmbH" erhalten bleiben. Der Prüfer sieht den
  maskierten Auszug (`masked_excerpt`).
* Einzelunternehmer ohne Kontakt (A84, 26.09.2026, umgesetzt): `masking.header_person_names`
  erkennt deterministisch und ohne Anbieteraufruf Personennamen im Absenderblock (Namenszeile
  unter den ersten acht Zeilen, gefolgt von einer Anschriftszeile mit Straße oder PLZ;
  Berufsbezeichnungen wie "Malermeister", "Elektromeister", akademische Titel wie
  "Dipl.-Ing." werden abgestreift) sowie unter Grußformeln ("Mit freundlichen Grüßen",
  "Hochachtungsvoll"). Firmennamen mit Rechtsform oder Marker (GmbH, AG, e.K., KG, OHG, UG,
  Stadtwerke, Verband) und Zeilen mit Dokumentwörtern (Rechnung, Objekt, Kunde) sind nie
  Kandidaten; eine Namenszeile im Kopf ohne folgende Anschrift gilt als zweifelhaft und wird
  nur maskiert, wenn der Name im Dokument mindestens zweimal vorkommt. Jeder erkannte Name
  erhält einen stabilen Platzhalter (`[NAME 1]`, `[NAME 2]`, beide Schreibweisen
  `Vorname Nachname` und `Nachname, Vorname`); `extraction.field_confidences` verwirft
  Werte mit diesen Platzhaltern wie bisher. Grenzen: nur Namen aus lateinischem Alphabet
  mit Großschreibung, kein Name in Großbuchstaben (OCR) als Kandidat, ein Name tief im
  Text ohne Grußformel wird nicht geraten. Tests: 21 Fälle in
  `tests/unit/test_receipts_masking.py` (positiv, negativ, Firmenname, OCR-Leerräume,
  zweifelhafte Treffer).
* Die Aktion "Als Rechnung erfassen" in der Mail- und Ticketansicht nutzt
  `POST /receipts/drafts` mit `source=mail_attachment` (`components/receipts/AttachmentReceiptAction.tsx`,
  `components/tickets/TicketMailAttachments.tsx`). Der API-Endpunkt
  `/mail/messages/{id}/attachments/{id}/invoice-extraction` (Chat-Vorschlag) bleibt für die
  API und `tests/integration/test_m14_ai_intake.py` bestehen, wird im CRM aber nicht mehr
  aufgerufen; Rückbau nach Abnahme möglich.
* Die Entwurfsliste zeigt Aussteller, Betrag, Datum, Objektvorschlag, niedrigste
  Feldsicherheit und Quelle, sortiert nach Eingang; die Rechnungsseite zeigt die Anzahl
  offener Entwürfe an der Schaltfläche Belegeingang (die Seitennavigation kennt keine Badges).
* `messages/en.json` enthält keinen Namensraum `Receipts` und `Invoices` (Stand vor M14);
  die englischen Texte des Belegeingangs fehlen weiterhin.
* Migration 0080: `down_revision` beim Zusammenführen auf den tatsächlichen Head setzen.
* E-Rechnung: keine Validierung gegen XSD und Schematron der XRechnung, keine UBL-Gutschrift,
  Skontofrist nur als Tage, Leistungszeitraum nur im Entwurf; Details in
  `docs/OPEN_QUESTIONS.md` M14-06. Die Prompt-Version von `extract_invoice` bleibt v1, die
  §-35a-Felder sind optional im Ausgabeschema beschrieben.
* `apps/api/openapi.json` und `packages/api-client` wurden nicht neu erzeugt (parallele
  Änderungen anderer Aufgaben); `make openapi` nach dem Zusammenführen ausführen.

## Stand 26.09.2026

Zusammenfassung aus den Nachträgen dieses Plans, dem `CHANGELOG.md` (1.19.0 bis 1.22.1) und der Lückenliste `docs/plans/LUECKENLISTE-2026-09-26.md`; keine neuen Sachverhalte.

* Im Code: `mhvp.receipts` (Entwürfe, Extraktion, E-Rechnung, Maskierung, Router), Migration 0080, Aktion "Als Rechnung erfassen" über `POST /receipts/drafts`, Paperless-Webhook (A30), Maskierung von Personenkontakten und Ausstellernamen (A65).
* Tests: `test_m14_receipt_drafts.py` (D41, D42, D44), `test_m14_einvoice.py`, `test_m14_paperless_webhook.py`, `tests/unit/test_receipts_masking.py`.
* Offen wie in "Offene Punkte": Feldkonfidenzen, englische Texte, M14-06, `make openapi`. A84 (Einzelunternehmer ohne Kontakt) ist heuristisch umgesetzt, siehe oben.
