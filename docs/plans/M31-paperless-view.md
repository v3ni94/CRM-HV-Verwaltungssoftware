# M31: Paperless-Dokumente in Ticket- und Objektansicht

## Ziel

Zu einem Ticket und zu einem Objekt (Property) die zugehörigen Dokumente aus Paperless-ngx
anzeigen, read-only, ohne den Paperless-Token an den Browser zu geben.

## Entscheidungen

* Kein neues Feld auf `DmsConnection` per Migration. Die Custom-Field-IDs für Objektnummer und
  Gesellschaft liegen als Strings im bereits vorhandenen `DmsConnection.options` (JSONB,
  Schlüssel `object_field_id`, `company_field_id`). Die Spalte existiert genau für solche
  anbieterspezifischen Einstellungen (siehe `dms.py`, Kommentar zu `options`). Damit entfällt
  Alembic-Migration 0043 aus der ursprünglichen Aufgabenstellung; die UI/Doku nennt 7 und 5 nur
  als übliche Werte, hart codiert ist nichts.
* Objektnummer kommt aus `Property.number` (3-stelliger String, `UniqueConstraint(tenant_id,
  number)`, Format geprüft per `CheckConstraint`). Das ist dasselbe Feld, das
  `dms.property_folder_name` für die Drive-Ablage verwendet und das beim Immoware-Import als
  Objektnummer befüllt wird.
* Ticketsuche: kein eigenes Paperless-Feld für Ticketnummern vorhanden, daher Volltextsuche
  (`query=<Ticketnummer>`) zusätzlich zur Objektsuche über `ticket.property_id`, Ergebnisse nach
  Paperless-Dokument-ID dedupliziert.
* Datei-Proxy: `GET /api/v1/dms-documents/{id}/file?kind=download|preview|thumb` ruft Paperless
  serverseitig mit dem gespeicherten Token auf und streamt Bytes plus Content-Type zurück. Die
  Liste liefert nur Proxy-URLs, nie eine direkte Paperless-URL oder den Token.
* Der BFF-Proxy im Frontend (`apps/web-crm/src/app/api/bff/[...path]/route.ts`) reicht Binärdaten
  bereits unverändert über `arrayBuffer()` durch (siehe bestehenden Datei-Upload-Pfad), ein
  eigener `dms-file`-Route-Handler war daher nicht nötig, nur die Allowlist wurde erweitert.

## Endpunkte

* `GET /api/v1/properties/{property_id}/dms-documents?page=&page_size=`
* `GET /api/v1/tickets/{ticket_id}/dms-documents?page=&page_size=`
* `GET /api/v1/dms-documents/{paperless_id}/file?kind=download|preview|thumb`

Alle drei verlangen die Berechtigung `documents:read`. Fehlerformat RFC 7807
(`application/problem+json`), Codes `MHVP-DOC-0005` (Paperless nicht eingerichtet, 502) und
`MHVP-DOC-0006` (Paperless nicht erreichbar, 503).

## Konfiguration

`PUT /api/v1/dms-connections/PAPERLESS` mit `options: {"object_field_id": "7",
"company_field_id": "5"}` (bestehender Endpunkt, keine Schemaänderung). Ohne gepflegte
`object_field_id` liefert die Objektsuche eine leere Liste statt zu raten.

## Sicherheit

Der Paperless-Token verlässt die API nie. Der Browser sieht nur Proxy-URLs auf
`/api/v1/dms-documents/{id}/file`; die API hängt `Authorization: Token ...` serverseitig an.
Fehlermeldungen aus `paperless_search.py` enthalten nie den Token (getestet in
`tests/unit/test_documents_paperless_search.py`).

## Stand und offene Punkte

Aus Zeit-/Umgebungsgründen in dieser Sitzung umgesetzt: Backend-Service, Endpunkte, BFF-Allowlist,
Unit-Tests für `PaperlessSearch`, Doku. **Nicht umgesetzt** (siehe Bericht des Agenten): die
Frontend-Komponente `DmsDocumentsPanel.tsx`, die Einbindung in Ticket- und Objektseite, die
Pflege der Feld-IDs in der DMS-Einstellungsseite, sowie Übersetzungen de/en. Das sollte in einem
Folgeschritt nachgezogen werden.

Integrationstests für die Router-Endpunkte liegen inzwischen vor: `tests/integration/
test_m31_dms.py` (Paperless per `httpx.MockTransport` gefakt; Happy Path Objekt- und
Ticketsuche, Datei-Proxy, Berechtigung, Mandantentrennung, Validierung, Verhalten ohne
gepflegte `object_field_id` bzw. ohne eingerichtete Anbindung).
