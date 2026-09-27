# Objektakte (Objektübernahme) als angebundener Dienst

Stand 26.09.2026. Plan: `docs/plans/M29-dms.md` (Stufe 3 in objektakte, Stufe 4 im CRM).
Dieser Vertrag ist für beide Seiten verbindlich. Das Dossier nach Anhang B des Master-Prompts
steht noch aus.

## 1. Lesende Schnittstelle von objektakte

Basis-URL: `https://uebernahme.muellerhv.de/api/crm/v1/`. Anmeldung mit
`Authorization: Bearer <token>`. objektakte speichert Token nur als SHA-256-Hash mit Scopes;
Anlage per Management-Kommando `crm_token anlegen --name crm --scopes objects:read
documents:read persons:read`, der Klartext wird genau einmal ausgegeben. Fehlender oder falscher
Token: 401, fehlender Scope: 403. Nur GET, JSON in UTF-8, Zeitangaben ISO 8601 (UTC).
Paginierung `?page=1&page_size=100` (höchstens 500), Antwort
`{"count", "page", "page_size", "results": [...]}`. Objektschlüssel ist die Objektnummer
`number` (Text, zum Beispiel "523"), in beiden Systemen gleich; das CRM führt sie dreistellig
("82" entspricht "082").

| Nr. | Endpunkt | Scope | Inhalt |
| --- | --- | --- | --- |
| 1 | `GET /objects/` | objects:read | `number, name, archived, takeover_status, open_review_cases, completeness {required, present, missing, percent}, drive_folder_id, drive_folder_url, updated_at` |
| 2 | `GET /objects/{number}/` | objects:read | wie 1, zusätzlich `address {street, house_number, zip, city}`, `missing_documents [{category, subfolder, label}]`, `open_cases_by_type {"<typ>/<untertyp>": Anzahl}`; unbekannte Nummer 404 |
| 3 | `GET /objects/{number}/documents/` | documents:read | optional `?folder=<kategorie>&since=<iso>`; `id, title, doc_type, category, subfolder, status, drive_file_id, drive_url, sha256, filed_at, mime_type, size_bytes` |
| 4 | `GET /objects/{number}/owners/` | persons:read | `id, display_name, unit_labels, share, email_masked, iban_masked` (IBAN nie im Klartext) |
| 5 | `GET /objects/{number}/tenants/` | persons:read | `id, display_name, unit_labels, lease_start, lease_end, email_masked` |

## 2. Webhooks von objektakte an das CRM

Ziel `POST https://api.mueller-holding.ag/api/v1/integrations/objektakte/webhook`, in objektakte
über `CRM_WEBHOOK_URL` und `CRM_WEBHOOK_SECRET` einzurichten (leer bedeutet aus). Inhalt:

```json
{"event": "document.filed", "occurred_at": "2026-09-26T09:00:00Z", "object_number": "523",
 "document": {"id": 9100, "title": "...", "sha256": "...", "drive_file_id": "...", "...": "wie Endpunkt 3"}}
```

`event` ist `document.filed` oder `object.taken_over` (dann `document: null`). Kopfzeilen
`X-Objektakte-Signature: sha256=<hex HMAC-SHA256 über den rohen Inhalt mit dem Geheimnis>` und
`X-Objektakte-Event: <event>`. Versand asynchron mit drei Wiederholungen, nie blockierend für die
Ablage.

## 3. Umsetzung im CRM (Stufe 4)

Einstellungen (Umgebung der API, nie im Browser, nie im Repository):

| Variable | Bedeutung |
| --- | --- |
| `OBJEKTAKTE_API_URL` | Basis-URL der lesenden Schnittstelle |
| `OBJEKTAKTE_API_TOKEN` | Token mit den drei Scopes |
| `OBJEKTAKTE_WEBHOOK_SECRET` | Geheimnis der Webhook-Signatur (gleicher Wert wie `CRM_WEBHOOK_SECRET` in objektakte) |
| `OBJEKTAKTE_TENANT` | Mandant (Kürzel, zum Beispiel `hausverwaltung-mueller`), dem die Daten von objektakte gehören |

Die Variablen werden auch mit dem Präfix `MHVP_` gelesen. Fehlt Adresse, Token oder Mandant,
ist die Anbindung aus; die DMS-Seite zeigt dann nur den Absprung je Objekt (Stufe 1) mit einem
Hinweis. Für jeden anderen Mandanten gilt die Anbindung als nicht eingerichtet
(Mandantentrennung). Zeitlimit je Aufruf 10 Sekunden (`MHVP_OBJEKTAKTE_API_TIMEOUT_SECONDS`).

Endpunkte des CRM (`/api/v1/integrations/objektakte`, Code `mhvp.objektakte.dms_routers`):

| Endpunkt | Recht | Zweck |
| --- | --- | --- |
| `GET /status` | objektakte:read | Anbindung eingerichtet, Webhook eingerichtet |
| `GET /objects`, `GET /objects/{number}` | objektakte:read | Kacheln und Detail, jeweils mit `property_id` des CRM-Objekts gleicher Nummer |
| `GET /objects/{number}/documents` | objektakte:read | Dokumentliste mit `crm_document_id` |
| `POST /objects/{number}/documents/link` | documents:create und objektakte:read | alle Dokumente des Objekts als CRM-Dokumente verknüpfen (Nachholen) |
| `GET /objects/{number}/owners`, `.../tenants` | objektakte:read und contacts:read | Listen ohne E-Mail und IBAN |
| `POST /objects/{number}/person-proposals` | objektakte:update und contacts:read | Importvorschlag: Abruf und Testlauf mit Abgleich |
| `GET /person-proposals`, `GET /person-proposals/{id}` | objektakte:read und contacts:read | Vorschläge und Abgleich |
| `POST /person-proposals/{id}/test-run` | objektakte:update und contacts:read | Testlauf wiederholen |
| `POST /person-proposals/{id}/approve` | objektakte:approve und contacts:read | Freigabe |
| `POST /person-proposals/{id}/reject` | objektakte:update und contacts:read | Verwerfen |
| `POST /webhook` | HMAC | Empfang der Webhooks |

Fehler von objektakte (Zeitüberschreitung, keine Verbindung, 401 oder 403 wegen Token oder Scope,
5xx, ungültige Antwort) beantwortet das CRM mit 502 `MHVP-OAK-0002`; eine nicht eingerichtete
Anbindung mit 502 `MHVP-OAK-0001`; eine in objektakte unbekannte Objektnummer mit 404
`MHVP-OAK-0003`. Token und Antwortinhalt erscheinen nie in Fehlermeldungen.

### Dokumente (M6)

Ein abgelegtes Dokument (Webhook `document.filed` oder Nachholen je Objekt) wird ein
CRM-Dokument mit Verknüpfung zum Objekt gleicher Nummer. Abgleich in dieser Reihenfolge:
objektakte-ID (`source_system = objektakte`, derselbe Schlüssel wie beim Dump-Import M35),
Drive-Datei-ID (`storage = google_drive`, `storage_ref`), Prüfsumme `sha256`. Ein Treffer wird
verknüpft, nie doppelt angelegt; die Herkunft eines im CRM hochgeladenen Dokuments bleibt
unverändert, der objektakte-Bezug steht zusätzlich in `source_meta.objektakte`. Das Original
bleibt in Google Drive, es wird nichts kopiert. Ein Dokument ohne gültige Prüfsumme wird nicht
angelegt und im Ergebnis als `invalid` gezählt.

### Webhook

Signatur über den rohen Inhalt mit `OBJEKTAKTE_WEBHOOK_SECRET`; ohne Geheimnis wird jede
Zustellung abgewiesen (401). `X-Objektakte-Event` muss zum Inhalt passen (sonst 422).
Idempotenz über (event, object_number, document.id) in `objektakte_webhook_receipt`
(Migration 0154): die erste Zustellung wird verarbeitet, jede Wiederholung erhält 200 mit
`"status": "duplicate"` und ändert nichts. `object.taken_over` wird als Ereignis
`objektakte.object_taken_over` protokolliert, weitere Folgen hat es in dieser Stufe nicht.
Unbekannte Ereignisse werden als `ignored` vermerkt.

### Eigentümer- und Mieterlisten als Importvorschlag (M8-Muster)

Abruf und Testlauf gleichen jede Zeile von objektakte mit den laufenden Verträgen gleicher Art
(Eigentum oder Miete) der genannten Einheiten ab (Einheit über Nummer oder Bezeichnung, Name
ohne Rücksicht auf Reihenfolge und Groß- und Kleinschreibung): übereinstimmend, abweichend,
neu (kein laufender Vertrag), Einheit unbekannt, ohne Einheit; Personen, die nur im CRM stehen,
erscheinen als "nur im CRM". Gespeichert werden nur Name, Einheiten und Anteil beziehungsweise
Mietbeginn und Mietende, keine E-Mail und keine IBAN, auch nicht maskiert. Die Freigabe
bestätigt den Abgleich als Arbeitsgrundlage; Kontakte, Verträge und Einheiten werden weder beim
Testlauf noch bei der Freigabe geändert (`writes_master_data: false`). Die Pflege der
Stammdaten erfolgt in den Stammdatenmasken oder über den Import M8.

## 4. Upload aus dem CRM in objektakte (Ergänzung 26.09.2026)

Ziel: Ein im CRM hochgeladenes Dokument wird von objektakte verarbeitet und dort abgelegt, in
der Drive-Struktur des Objekts mit Eigentümer- und Mieterakten und in Paperless. Das CRM
behält das Original in S3 und den Index; es spiegelt solche Dokumente nicht selbst nach
Paperless oder Drive, damit jedes System das Dokument genau einmal hält.

Endpunkte in objektakte (Umsetzung dort: `docs/betrieb/crm-schnittstelle.md`, Abschnitt 3a):

| Nr. | Endpunkt | Scope | Inhalt |
| --- | --- | --- | --- |
| 6 | `POST /objects/{number}/documents/` | documents:write | `multipart/form-data`: `file`, `crm_document_id` (UUID des CRM-Dokuments), `hints` (JSON); Antwort 202 oder bei Wiederholung 200 mit dem Stand wie Endpunkt 7 |
| 7 | `GET /documents/{id}/` | documents:read | Zeile wie Endpunkt 3, dazu `object_number`, `open_review_cases`, `deleted`, `duplicate_of` |

Jede Dokumentzeile (Endpunkte 3 und 7, Webhook) trägt zusätzlich `crm_document_id` und
`paperless_id` (sonst null). `hints` enthält nur Kennungen und Bezeichnungen: `title`,
`unit_labels`, `contact_refs` (Kontakt-IDs des CRM), `ticket_number` (`TNR#<nummer>`),
`category`; keine Namen, keine Kontaktdaten. Statuscodes des Uploads: 400 (Datei, Kennung,
Hinweise oder Dateityp ungültig), 404 (Objekt unbekannt), 409 (Kennung einem anderen Objekt
zugeordnet oder Objekt archiviert), 413 (zu groß), 503 mit `Retry-After`, solange der Schalter
`sync.crm_uploads_enabled` in objektakte aus ist.

Weiche im CRM (`mhvp.objektakte.upload`, Tabelle `objektakte_upload`, Migration 0155): Ein
Dokument geht an objektakte, wenn

1. `OBJEKTAKTE_UPLOAD_ENABLED=true` gesetzt und die Lese-API eingerichtet ist,
2. der Mandant der in `OBJEKTAKTE_TENANT` genannte ist,
3. die Quelle ein Upload oder Scan ist (erzeugte Schreiben, Exporte, SEPA-Dateien, E-Mails,
   Portal und Importe gehen weiter den bisherigen Weg),
4. der Dateityp von objektakte angenommen wird (PDF, Bilder, DOCX, XLSX, XLSM, CSV, TXT, EML,
   MSG, HTML) und
5. die Verknüpfungen genau ein Objekt ergeben: direkt, über eine Einheit oder über ein Ticket
   mit Objekt. Kontakte allein bestimmen kein Objekt.

Sonst gilt die bisherige Spiegelung (`mhvp.documents.tasks.mirror`). Verknüpfungen, die erst
nach dem Upload entstehen, ändern den Weg nicht.

Job `mhvp.objektakte.upload` (Beat jede Minute, Warteschlange `io`): `pending` wird hochgeladen
und wird `submitted`; `submitted` wird alle 5 Minuten mit Endpunkt 7 abgefragt, bis objektakte
das Dokument abgelegt hat (`done`, Verknüpfung mit dem Objekt und Vermerk in
`source_meta.objektakte` mit Drive-Datei, Paperless-ID, Kategorie und Unterordner). Eine
Dublette in objektakte wird mit der Ablage des Originals verknüpft. 503 verschiebt den Upload
um 15 Minuten ohne Fehlerzählung; eine endgültige Ablehnung (400, 404, 409, 413) setzt
`failed` mit der Begründung von objektakte; Netz- und Serverfehler wiederholen mit derselben
Staffel wie die Spiegelung und setzen nach sechs Versuchen `failed`. Die Aktion "Spiegelung
erneut anstoßen" (`POST /documents/{id}/mirror`) setzt einen fehlgeschlagenen Upload zurück.
Der Webhook `document.filed` mit `crm_document_id` schließt den Upload sofort ab und legt kein
zweites Dokument an.

Stand je Dokument: `GET /api/v1/integrations/objektakte/documents/{document_id}/filing`
(`objektakte:read`), `routed` false bedeutet bisheriger Spiegelweg. `GET .../status` meldet
zusätzlich `upload_enabled`.

Einrichtung:

1. objektakte: neues Token mit den Scopes `objects:read documents:read persons:read
   documents:write` anlegen, das bisherige sperren; Schalter `sync.crm_uploads_enabled`
   einschalten. Nach Paperless überträgt objektakte nur, wenn `paperless.mode` es erlaubt
   (`full`, im Pilotbetrieb nur Pilotobjekte).
2. CRM: `OBJEKTAKTE_API_TOKEN` auf das neue Token setzen, `OBJEKTAKTE_UPLOAD_ENABLED=true`,
   API und Worker neu starten.

Grenzen: Die Zuordnung zu Eigentümer- und Mieterakten in objektakte setzt voraus, dass dort
Einheiten und Personen des Objekts bekannt sind. Die Einheit aus dem Upload (`unit_labels`)
wirkt, wenn objektakte die Einheit unter demselben Bezeichner führt und der Text selbst keine
Einheit nennt. Kontakt-IDs werden gespeichert, wirken aber noch nicht, weil objektakte die
Personen nicht mit ihrer CRM-Kennung führt; die Eigentümer und Mieter kommen dort bisher über
den Listenimport (Immoware24-Export) hinein. Löschung: Wird ein über objektakte abgelegtes
Dokument im CRM gelöscht (Aufbewahrung abgelaufen oder von Hand), bleiben die Ablagen in
objektakte, Drive und Paperless bestehen; die Löschspiegelung des CRM (`mirror_deletion`) gilt
nur für die eigenen Spiegel. Die Löschung dort erfolgt nach den Aufbewahrungsregeln von
objektakte.

## 5. Einheiten, Eigentümer und Mieter an objektakte (Ergänzung 27.09.2026)

Damit objektakte Uploads in die Eigentümer- und Mieterakten mit Namen einordnen kann, überträgt
das CRM je Objekt eine Einheitenliste: `POST /api/v1/integrations/objektakte/objects/{number}/persons-export`
(`objektakte:update` und `contacts:read`), Knopf "Liste übergeben" auf der DMS-Seite des Objekts.
Inhalt (`mhvp.objektakte.person_export`): Format der Immoware24-Einheitenliste mit Objektnummer,
Objekt, Verwaltungsart, Gebäude, Einheitennummer und Bezeichnung sowie den Namen der am
Stichtag laufenden Eigentums- und Mietverträge (mehrere Personen mit "und"). Keine Anschriften,
E-Mail, Telefon, Bankdaten oder Beträge; die Geldspalten des Formats bleiben leer.

objektakte legt daraus einen Import des Objekts an (Endpunkt `objects/{number}/imports/`, Scope
`persons:write`, Schalter `sync.crm_persons_enabled`). Übernommen wird erst nach Prüfung und
Freigabe im Importassistenten von objektakte; die Antwort nennt den Link zur Prüfung. Dieselbe
Liste ein zweites Mal ergibt keinen neuen Import (Prüfsumme). Ereignis im CRM:
`objektakte.persons_exported`. Einrichtung: Token in objektakte um `persons:write` erweitern (neues
Token anlegen, altes sperren), Schalter `sync.crm_persons_enabled` einschalten.
