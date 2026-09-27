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
- `service.py`: Verbindungsaufbau, Verbindungstest, Lauf-Buchhaltung (`ImmowareSyncRun`),
  Ablauf eines Laufs (`run_sync`) mit kurzen Transaktionen je Schritt.
- `tasks.py`: Celery-Tasks je Art, Beat alle 15 Minuten, Task prueft `poll_minutes` selbst;
  die Redis-Sperre ist nur ein Vorfilter, Doppellaeufe verhindert `service.start_run`.
- `routers.py` / `schemas.py`: `/api/v1/immoware` (Permission-Ressource `immoware`, read/update).

## Transaktionen und Doppellaeufe (Produktionsbefund 27.09.2026)

`pg_stat_activity` zeigte zwei Sessions von `mhvp_app` mit `idle in transaction` ueber 17 bzw.
22 Minuten, letzte Anweisung `INSERT INTO immoware_sync_run`: der DAV-Abruf lief innerhalb der
Transaktion, die die Laufzeile angelegt hatte. Folgen: Zeilensperren und Snapshot ueber Minuten,
`CREATE INDEX CONCURRENTLY` (Migration 0156) blockierte, zwei Laeufe liefen parallel, weil die
Redis-Sperre (TTL 900 s) vor Ende des Laufs ablief. Seitdem gilt:

- Waehrend der HTTP-Aufrufe (PROPFIND, REPORT, GET) ist nie eine Transaktion offen. Die Adapter
  sind in Abrufphase (`fetch_*`, ohne Session) und Anwendungsphase (`apply_*`, `mark_*`)
  getrennt; `pull_tree`, `pull_contacts`, `pull_events` bleiben als Einzelaufruf in einer
  Session fuer Tests erhalten.
- `service.run_sync(factory, tenant_id, kind)` oeffnet je Schritt eine eigene
  `tenant_transaction` (RLS: `app.tenant_id` wird in jeder Transaktion neu gesetzt):
  Laufzeile `running` anlegen und committen (sofort sichtbar), Abruf, Anwendung in Batches zu
  `SYNC_BATCH_SIZE` (50) mit Commit je Batch, Abschluss der Laufzeile mit Zaehlern. Ein Fehler
  setzt die Laufzeile in eigener Transaktion auf `failed`.
- `service.start_run` serialisiert Pruefung und Anlage je Tenant und Art ueber
  `pg_advisory_xact_lock`. Laeuft bereits ein Lauf gleicher Art (Status `running`, juenger als
  `STALE_RUNNING_AFTER`, 2 h), antwortet der Router mit 409 `MHVP-IMW-0005` und der Task
  ueberspringt den Tenant. Eine aeltere `running`-Zeile gilt als verwaist und wird beim naechsten
  Start als `failed` abgeschlossen.
- Der Router `POST /sync/{kind}` haelt keine Request-Transaktion um den Abruf.

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

## Weitere Dateien (Nachtrag 26.09.2026)

Im Abgleich mit dem Ordnerinhalt am 26.09.2026 fehlten oben:

* `discovery.py`: standardbasierte Discovery der DAV-Endpunkte (RFC 6764) und Diagnose-Endpunkt (Folgeauftrag 25.09.2026)
* `learning.py`: Lernphase (M33): rein lesende Auswertung der gespiegelten Zeilen je Art, Vergleich mit dem letzten Lauf
