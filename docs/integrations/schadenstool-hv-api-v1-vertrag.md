# HV API v1 Vertragsentwurf (bidirektional)

Status: Entwurf zur Umsetzung
Scope: Hausverwaltungs-Integrationen fuer Objekte + Tickets
Prioritaet: Additiv, ohne Breaking Changes an bestehenden Endpunkten

## 1. Ziele und Nicht-Ziele

Ziele:
- Vollstaendige Objektansicht (Objektdaten, Versicherungen, Schadenhistorien, Dokumente) exportieren und importieren.
- Ticket-Daten bidirektional synchronisieren.
- Kommentare und Dokumente/Anhaenge bidirektional synchronisieren.
- Stabiler Integrationsvertrag mit Idempotenz, Versionierung und Fehlercodes.

Nicht-Ziele in v1:
- Keine Entfernung oder Umbenennung bestehender interner Endpunkte.
- Kein erzwungener Echtzeit-Sync fuer alle Events (hybrid aus Pull + Webhook ist ausreichend).

## 2. Integrationsprinzipien

- Namespace fuer externe HV-Integration:
  - `/api/integrations/hv/v1/*`
- Additiver Betrieb:
  - Bestehende interne APIs bleiben unveraendert.
  - HV API wird separat eingefuehrt.
- Tenant-Isolation:
  - Jeder Request muss eindeutig einer Hausverwaltung/einem Tenant zugeordnet sein.
- Idempotenz fuer Schreiboperationen:
  - Header `Idempotency-Key` verpflichtend fuer POST/PATCH/DELETE in inbound Richtung.
- Cursor-basierte Pagination:
  - Keine page/offset fuer grosse Datenmengen.

## 3. Authentifizierung und Sicherheit

### 3.1 Inbound (HV -> Schadentool)
- `Authorization: Bearer <integration-token>`
- Optional zusaetzlich HMAC fuer hohen Schutz:
  - `X-Timestamp`, `X-Signature: sha256=<hex>`
  - Signatur ueber `${timestamp}.${rawBody}`

Beispiel-Request:
```bash
curl -X GET "https://api.midive.de/api/integrations/hv/v1/tickets?limit=50" \
  -H "Authorization: Bearer <integration-token>" \
  -H "Content-Type: application/json"
```

Bei einem ungültigen oder abgelaufenen Secret antwortet die API mit:
```http
HTTP/1.1 401 Unauthorized
{"message":"Ungueltiger API-Token"}
```

### 3.2 Outbound (Schadentool -> HV Webhook)
- HMAC Signatur identisch wie oben.
- Replay-Schutz:
  - Toleranzfenster z. B. 5 Minuten auf Empfaengerseite.

### 3.3 Rollen/Scopes
- Token ist immer tenantgebunden.
- Mindest-Scopes:
  - `objects:read`, `objects:write`
  - `tickets:read`, `tickets:write`
  - `comments:write`, `documents:write`

### 3.4 Token-Verwaltung im Adminbereich
- Das Secret wird im MDV-Adminbereich erzeugt.
- Jeder erzeugte Token ist einzeln widerrufbar.
- Beim Erstellen wird das Secret nur einmal angezeigt und danach nicht erneut im System ausgegeben.
- Ein Kunde erhält nur den Geheimtext; der Server speichert nur den Hash des Tokens.

## 4. Ressourcenmodell (extern)

- Objekt: `object`
- Versicherung: `policy`
- Schadenhistorie: `damage_history_entry`
- Dokument: `document`
- Ticket: `ticket`
- Kommentar: `comment`
- Attachment: `attachment`

Externe IDs:
- Jede Ressource bekommt:
  - `externalId` (ID aus HV-System)
  - `mdvId` (lokale UUID)
- Mapping wird persistiert (entityType, externalId, localId, tenantId).

## 5. Objekt-Schnittstellen

## 5.1 Vollsicht exportieren (outbound pull)
GET `/api/integrations/hv/v1/objects`

Query:
- `cursor` optional
- `limit` optional (default 100, max 500)
- `updatedSince` optional ISO-8601
- `include` optional CSV: `policies,damageHistory,documents,tickets`

Antwort 200:
- `items: ObjectFullView[]`
- `nextCursor: string | null`

Beispielstruktur pro Objekt:
- `id`
- `externalId` (falls gemappt)
- `name`, `address`, `customer`
- `units[]`
- `policies[]`
- `damageHistory[]`
- `documents[]`
- `updatedAt`

## 5.2 Einzelobjekt vollstaendig
GET `/api/integrations/hv/v1/objects/{objectId}`

Antwort 200:
- `ObjectFullView`

## 5.3 Objekt upsert (inbound)
PUT `/api/integrations/hv/v1/objects/{externalObjectId}`
Headers:
- `Idempotency-Key` (pflicht)

Body:
- Stammdaten des Objekts
- optional Einheiten
- optional Hausverwaltungszuordnung

Antwort:
- 200 (update) oder 201 (create)
- `id`, `externalId`, `updatedAt`

## 5.4 Versicherungen upsert
PUT `/api/integrations/hv/v1/objects/{externalObjectId}/policies/{externalPolicyId}`
Headers:
- `Idempotency-Key` (pflicht)

## 5.5 Schadenhistorie upsert
PUT `/api/integrations/hv/v1/objects/{externalObjectId}/damage-history/{externalDamageId}`
Headers:
- `Idempotency-Key` (pflicht)

## 5.6 Objektdokument hochladen
POST `/api/integrations/hv/v1/objects/{externalObjectId}/documents`
Headers:
- `Idempotency-Key` (pflicht)
Content-Type:
- `multipart/form-data`

Felder:
- `file`
- `externalDocumentId` optional (empfohlen)
- `category` optional
- `label` optional

Antwort 201:
- `documentId`, `downloadUrl`, `mimeType`, `size`

## 5.7 Objektdokument herunterladen
GET `/api/integrations/hv/v1/documents/{documentId}/download`

## 6. Ticket-Schnittstellen

## 6.1 Ticket-Liste (outbound pull)
GET `/api/integrations/hv/v1/tickets`

Query:
- `cursor`, `limit`
- `updatedSince`
- `status`
- `objectExternalId`

Antwort:
- `items`, `nextCursor`

## 6.2 Einzel-Ticket
GET `/api/integrations/hv/v1/tickets/{ticketId}`

## 6.3 Schadenmeldung empfangen (inbound create)
POST `/api/integrations/hv/v1/tickets`
Headers:
- `Idempotency-Key` (pflicht)

Body (minimal):
- `externalTicketId` optional (wenn HV bereits ID vergibt)
- `objectExternalId` oder `objectId`
- `title`
- `description`
- `reporter` (optional)
- `damage` (date, type, location)

Antwort 201:
- `id`, `externalId`, `status`, `createdAt`

## 6.4 Ticket-Update (inbound)
PATCH `/api/integrations/hv/v1/tickets/{externalOrMdvTicketId}`
Headers:
- `Idempotency-Key` (pflicht)

Updatefelder:
- `status`
- `title`
- `description`
- `priority`
- `assignees` (optional in v1)

## 6.5 Kommentar inbound
POST `/api/integrations/hv/v1/tickets/{ticketId}/comments`
Headers:
- `Idempotency-Key` (pflicht)

Body:
- `externalCommentId` optional
- `author`
- `message`
- `createdAt` optional

Antwort 201:
- `commentId`, `createdAt`

## 6.6 Kommentarliste outbound
GET `/api/integrations/hv/v1/tickets/{ticketId}/comments`

## 6.7 Attachment inbound
POST `/api/integrations/hv/v1/tickets/{ticketId}/attachments`
Headers:
- `Idempotency-Key` (pflicht)
Content-Type:
- `multipart/form-data`

Felder:
- `file`
- `externalAttachmentId` optional
- `category` optional
- `commentExternalId` optional

## 6.8 Attachmentliste outbound
GET `/api/integrations/hv/v1/tickets/{ticketId}/attachments`

## 7. Webhook-Events (outbound push)

Endpoint beim HV-System:
- Konfigurierbar pro Hausverwaltung

Eventschema:
- `eventId` (uuid)
- `eventType`
- `entityType`
- `entityId`
- `tenantId`
- `occurredAt`
- `payload` (leichtgewichtig)

Pflicht-Events v1:
- `ticket.created`
- `ticket.updated`
- `ticket.status_changed`
- `ticket.comment_added`
- `ticket.attachment_added`
- `object.updated`
- `policy.updated`
- `document.added`

Zustellung:
- At-least-once
- Retry mit exponential backoff
- Idempotenz beim Empfaenger via `eventId`

## 8. Fehler- und Statusmodell

Standardcodes:
- 200 OK
- 201 Created
- 202 Accepted (asynchron)
- 400 Bad Request
- 401 Unauthorized
- 403 Forbidden
- 404 Not Found
- 409 Conflict
- 422 Unprocessable Entity
- 429 Too Many Requests
- 500 Internal Server Error

Fehlerformat:
- `code` (stabiler Maschinen-Code)
- `message` (lesbar)
- `details` (feldbezogen)
- `correlationId`

## 9. Idempotenz-Regeln

- Schreibende Endpunkte muessen `Idempotency-Key` akzeptieren.
- Wiederholter identischer Request mit gleichem Key:
  - Liefert gleiches Ergebnis (oder Referenz auf Erstverarbeitung).
- Konfliktfall bei gleichem Key + abweichendem Body:
  - 409 `IDEMPOTENCY_KEY_PAYLOAD_MISMATCH`

## 10. Synchronisationsstrategie

v1 Hybrid:
- Initialer Vollabzug ueber Pull (`/objects`, `/tickets`).
- Laufender Delta-Abgleich ueber:
  - Pull mit `updatedSince` und Cursor
  - plus Webhook-Ereignisse fuer geringe Latenz

Reconciliation-Job:
- Taeglich oder stundenweise.
- Vergleicht Zaehler/Hashes und korrigiert Drift.

## 11. Kompatibilitaet und Versionierung

- URL-Versionierung: `/v1`
- Keine semantisch brechenden Feldaenderungen innerhalb v1.
- Neue optionale Felder erlaubt.
- v2 spaeter parallel unter `/v2`.

## 12. OpenAPI-Doku Mindestumfang

In Swagger/OpenAPI enthalten:
- Security schemes (Bearer + optionale HMAC Header)
- Alle Request/Response-Schemas
- Beispielpayloads je Endpoint
- Fehlercodes je Endpoint
- Webhook-Eventschema und Signaturverfahren

## 13. Akzeptanzkriterien fuer v1

- Objekt-Vollsynchronisation fuer mindestens einen Pilot-Tenant erfolgreich.
- Inbound Schadenmeldung erzeugt Ticket robust idempotent.
- Kommentare und Attachments laufen bidirektional.
- Outbound Webhooks sind signiert und retry-faehig.
- Keine Regressionen in bestehenden internen APIs.
