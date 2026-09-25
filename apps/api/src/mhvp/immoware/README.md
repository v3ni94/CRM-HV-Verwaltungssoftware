# mhvp.immoware (M32)

Lesezugriff auf Immoware24 im CRM, als Spiegel ohne Schreibzugriff. Referenz ist der alte
Laravel-Hub unter `/home/user/IMMOWARE24` (nicht Teil dieses Repos): dort belegte Zugangswege
sind ausschliesslich WebDAV, CardDAV und CalDAV; es gibt keine Immoware24-REST-API.

## Sicherheitsregeln

- Nur `PROPFIND`, `REPORT`, `GET`. `ReadOnlyDavClient` (`client.py`) lehnt jede andere Methode
  mit `WriteBlockedError` ab, bevor eine Anfrage gesendet wird.
- Passwoerter werden feldverschluesselt gespeichert (`EncryptedText`) und nie geloggt.
  `sanitize_error()` entfernt Basic-Auth-Header und Zugangsdaten aus URLs, bevor ein Fehlertext
  gespeichert oder als Problem-Detail zurueckgegeben wird.
- Kein Hard Delete: entfallene Zeilen erhalten `deleted_at`, Zuordnung ausschliesslich ueber
  externe IDs (href, uid), nie ueber Namen oder E-Mail.

## Aufbau

- `models.py`: `ImmowareConnection` (eine Zeile je Tenant) sowie die Spiegeltabellen
  `immoware_dav_document`, `immoware_dav_contact`, `immoware_dav_event`, `immoware_sync_run`.
- `client.py`: HTTP-Basis (Basic Auth, Timeout 30 s, Methodensperre).
- `webdav.py`, `carddav.py`, `caldav.py`: die drei Adapter (PROPFIND/REPORT, Upsert je href).
- `vcard.py`, `ical.py`: minimale, selbst implementierte Parser (kein neues Paket, Regel 8).
- `service.py`: Verbindungsaufbau, Verbindungstest, Lauf-Buchhaltung (`ImmowareSyncRun`).
- `tasks.py`: Celery-Tasks je Art, Beat alle 15 Minuten, Task prueft `poll_minutes` selbst,
  Redis-Sperre je Tenant und Art gegen Doppellauf.
- `routers.py` / `schemas.py`: `/api/v1/immoware` (Permission-Ressource `immoware`, read/update).

## Endpunkte

```
GET    /api/v1/immoware/connection
PUT    /api/v1/immoware/connection
POST   /api/v1/immoware/connection/check
POST   /api/v1/immoware/sync/{kind}
GET    /api/v1/immoware/sync/runs
GET    /api/v1/immoware/documents
GET    /api/v1/immoware/documents/{id}/file
GET    /api/v1/immoware/contacts
POST   /api/v1/immoware/contacts/{id}/match
POST   /api/v1/immoware/contacts/{id}/create-contact
GET    /api/v1/immoware/events
```
