# Lexware Office (lexoffice) Anbindung

Verbindliches Schnittstellendokument für `apps/api/src/mhvp/integrations/lexoffice.py`
(synchroner Client der bestehenden Export und Importfunktionen) und
`apps/api/src/mhvp/integrations/lexoffice_async.py` mit dem Paket
`mhvp.integrations.lexoffice_ext` (Regel [INT-LEXO-01](../rules/INT-LEXO-01-lexware-office.md)).
Ein Endpunkt, der hier nicht als verifiziert aufgeführt ist, wird nicht aufgerufen.

## Quelle

Entwicklerdokumentation `https://developers.lexware.io/docs/` (Nachfolger von
developers.lexoffice.io), zuletzt geprüft am 28.09.2026 (Kontakte, Belegliste, Rechnungen,
Dateien) und am 29.09.2026 (Dauerrechnungen). Basisadresse `https://api.lexware.io`, Kopfzeile
`Authorization: Bearer {accessToken}`, Schlüssel je Organisation unter
`https://app.lexware.de/addons/public-api`. Anfragelimit laut Dokumentation zwei Anfragen je
Sekunde, darüber HTTP 429.

## Verifizierte Endpunkte (Stand 28.09.2026)

| Endpunkt | Verwendung | Hinweise |
| --- | --- | --- |
| `GET /v1/profile` | Verbindungstest, Organisationsbindung | `organizationId`, `companyName`, `taxType`, `smallBusiness`, `businessFeatures` werden an der Konfiguration gespeichert |
| `GET /v1/contacts` | Abgleichslauf, Suche, Existenzprüfung nach 504 | Filter `email`, `name` (mindestens drei Zeichen, `&`, `<`, `>` HTML kodiert), `number`, `customer`, `vendor`, `page`, `size` (höchstens 250) |
| `GET /v1/contacts/{id}` | Lesen vor jedem Schreiben, Verknüpfung auffrischen | liefert `version` |
| `POST /v1/contacts` | Anlage nach Personenentscheidung (Rolle Kunde oder Lieferant) | `version: 0`, Rollen als leere Objekte |
| `PUT /v1/contacts/{id}` | Übertragung geänderter Stammdaten | ersetzt den ganzen Datensatz, deshalb wird immer das gelesene Objekt mit ersetzten Feldern gesendet; `version` aus dem GET, 409 bei veralteter Version, je Liste nur ein Eintrag |
| `GET /v1/voucherlist` | Rechnungssuche, Belegimport, Existenzprüfung eines Entwurfs | `voucherType` und `voucherStatus` sind Pflicht, `voucherNumber` filtert als Teilzeichenkette (die Plattform filtert exakt nach), `contactId`, Datumsfilter `updatedDateFrom` und `createdDateFrom` im Format `yyyy-MM-dd`, `size` höchstens 250 |
| `GET /v1/invoices/{id}` | Rechnungsdetails (Adresse, Status, Betrag, E-Rechnungsprofil) | |
| `GET /v1/invoices/{id}/file` | Rechnungsdatei | `Accept: application/pdf` für die PDF, `*/*` für die XRechnung XML; 409 solange die Rechnung Entwurf ist |
| `POST /v1/invoices` | Rechnungsentwurf aus dem CRM | ohne `finalize`; `finalize=true` nur über den bestehenden, mit G1 gesperrten Export |
| `POST /v1/vouchers`, `GET /v1/vouchers/{id}`, `POST /v1/files` | bestehender Export und Import (Passthrough, G1) | unverändert |
| `GET /v1/recurring-templates`, `GET /v1/recurring-templates/{id}` | nur lesend (geprüft 29.09.2026) | Dauerrechnungen können über die API nicht angelegt werden, siehe Abschnitt Dauerrechnungen |

Nicht verwendet: `GET /v1/invoices/{id}/document`, `files.documentFileId`, `GET /v1/files/{id}`
für Verkaufsbelege, der Parameter `updatedAtFrom` (existiert nicht; die frühere Verwendung im
Belegimport war ein Fehler und ist korrigiert).

Lexware Office bietet keinen serverseitigen Idempotenzschlüssel. Dublettenschutz ist
clientseitig: Idempotenzschlüssel je Warteschlangeneintrag, überholte Einträge, Existenzprüfung
nach 504 bei Anlagen. Eine dennoch entstandene Dublette wird in Lexware Office manuell
bereinigt (Deeplink in der Prüfliste).

## Einrichtung in sechs Schritten

1. AVV erfassen: Datum und Vermerk je Organisation; das bestätigende Mitglied wird gespeichert.
2. Schlüssel je Gesellschaft hinterlegen: eine Lexware Organisation je Gesellschaft (Hausverwaltung
   Müller GmbH, Müller Holding AG, Einzelunternehmen Timo Müller) oder die Standardkonfiguration
   ohne Gesellschaft. Der Schlüssel wird verschlüsselt gespeichert und nie wieder angezeigt.
3. Verbindung testen: `GET /v1/profile` bindet die Organisation an die Konfiguration. Ein
   anderer Schlüssel einer anderen Organisation wird abgelehnt, sobald Verknüpfungen bestehen
   (`MHVP-LEXO-0013`).
4. Postfach zuordnen: Rechnungskopien gehen aus dem Postfach der rechnungsstellenden
   Gesellschaft; ohne Postfach wird die Freigabe verweigert.
5. Rechnungsarten zuordnen: Maklerrechnungen, Beratung und Hausverwaltung je einer Gesellschaft
   (Konfiguration des Mandanten, Vorbelegung nur für die verwaltende Gesellschaft).
6. Kontakte zuordnen und Schalter aktivieren: Abgleichslauf, Prüfung je Zeile, danach die
   Schalter `sync_contacts`, `sync_names`, `invoice_copies`, `invoice_drafts` nach Freigabe der
   Geschäftsführung (ADR 0015).

## Datenabfluss

| Verlässt die Plattform | Nie |
| --- | --- |
| Name, Rechnungsanschrift, primäre E-Mail, primäres Telefon nach einer im CRM angewandten Änderung (Namen nur mit eigenem Schalter) | IBAN, BIC, Mandate, Steuernummern, Umsatzsteuer-IDs, Notizen, interne Beschreibungen, Rollen und Nummern aus dem CRM |
| Positionen, Steuerart, Leistungszeitraum und Texte eines Rechnungsentwurfs | Dokumente außer der angeforderten Rechnungsdatei, die in die Plattform hinein kommt |
| Filterwerte der Kontaktsuche (E-Mail oder Name, mindestens drei Zeichen) | Antworttexte von Lexware Office in Fehlermeldungen (`args`, `additionalData`, `message` werden verworfen) |

## Betrieb

- Warteschlange: jede Übertragung ist ein Eintrag in `lexoffice_outbox`, Verarbeitung jede
  Minute (`mhvp.integrations.lexoffice.process`), Wiederholungen nach dem Webhook Plan
  (1 min, 5 min, 30 min, 2 h, 6 h, 24 h), `Retry-After` bei 429 wird eingehalten, 400 und 406
  sind endgültig, 401 und 403 setzen `token_invalid` und halten die Konfiguration an.
- Anfragelimit: zwei Anfragen je Sekunde je Organisation, geteilt über alle Worker (Redis
  Zähler je 500 ms Fenster, ohne Redis Abstand im Prozess).
- Aufbewahrung: Warteschlangeneinträge in Endzuständen werden nach 90 Tagen gelöscht
  (`mhvp.integrations.lexoffice.purge`, täglich 03:20); offene Frage LEXO-12.
- Fehlercodes `MHVP-LEXO-0001` bis `0017` in `mhvp.core.problems`.

## Kontaktabgleich

Zuordnung nach Name und E-Mail mit Prüfung je Zeile (Betreiberentscheidung 28.09.2026, keine
gemeinsame Kundennummer). Bewertung: Kundennummer im CRM Feld `external_ids.lexoffice_customer_number`
1,0; E-Mail identisch 0,9; Name und PLZ 0,7; nur Name 0,4. Vorschläge ab 0,7, gleiche
Spitzenwerte werden mehrdeutig, ein Lexware Kontakt wird höchstens einem CRM Kontakt vorgeschlagen.
Der Lauf schreibt nichts nach Lexware Office.

## Rechnungskopien

Erkennung im Postfach (deterministisch: Rechnungsbegriff plus Absicht wie "nochmals",
"Kopie", "nicht erhalten", Rechnungsnummer nur wörtlich aus dem Text) oder manuelle Anforderung
am Ticket. Suche in der Belegliste jeder Organisation mit Rechnungskopien, exakte Nummer.
Prüfung: der anfragende Kontakt (Kontakt der Mail oder des Tickets, korrigierbar) muss der
über die Verknüpfungstabelle bekannte Rechnungsempfänger sein; die Absenderadresse ist nur ein
Hinweis. Die PDF (und XRechnung XML) wird im DMS abgelegt und ein Antwortentwurf ausschließlich
an die bekannte primäre E-Mail des Empfängers erstellt, mit gesperrtem Empfänger
(`MHVP-LEXO-0015`) und Freigabe durch eine zweite Person.

## Rechnungsentwürfe

`POST /v1/invoices` ohne `finalize` mit den dokumentierten Feldern `voucherDate`, `address`,
`lineItems`, `totalPrice`, `taxConditions`, `shippingConditions`, `title`, `introduction`,
`remark`, `language`. Die Gesellschaft ergibt sich aus der Rechnungsart. Beträge werden lokal
nur zur Kontrolle summiert; Lexware Office berechnet verbindlich. Steuerarten und Sätze sind
mit dem Steuerberater abzustimmen (LEXO-08).

## Dauerrechnungen

Laufende Verwaltervergütungen werden bereits als Dauerrechnungen in Lexware Office geführt.
Die API stellt Dauerrechnungen nur lesend bereit (`GET /v1/recurring-templates`, geprüft am
29.09.2026). Beim Erfassen eines Verwalterhonorars am Objekt bereitet die Plattform deshalb
Kontakt, Betrag, Intervall und Text vor und zeigt eine Checkliste für die manuelle Anlage; die
ID der angelegten Vorlage wird anschließend erfasst (Deeplink
`{app_base_url}/permalink/recurring-templates/view/{id}`). Offene Frage LEXO-07.

## Export und Import (bestehend)

- `POST /api/v1/integrations/lexoffice/export/invoices` und `.../export/contacts`
  (Berechtigung `accounting:create`, Freigabestufe G1). Der Kontaktexport schreibt zusätzlich
  die Verknüpfungstabelle (eine Wahrheit für Kontakte, ADR 0015).
- `POST /api/v1/integrations/lexoffice/import/receipts`: `GET /v1/voucherlist` mit
  `voucherType=purchaseinvoice`, `voucherStatus` (Standard `any`) und `updatedDateFrom`
  (aus `updated_at_from`, auf das Datum in Europe/Berlin gekürzt). Weiterverwendung offen
  (LEXO-14).
- Die Endpunkte `GET/PUT /config`, `POST /test`, `GET /runs` bleiben als Alias der
  Standardkonfiguration ohne Gesellschaft bestehen; `GET /config` genügt `tenant_settings:read`.

## smart-einzug

Für smart-einzug gibt es keine öffentlich dokumentierte REST API (Stand 27.09.2026); keine
Anbindung, siehe docs/OPEN_QUESTIONS.md M13-lexoffice-04.
