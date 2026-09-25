# M32: Immoware24-Lesezugriff per DAV (Version 1.7.0)

## Ausgangslage

Referenz ist der alte Laravel-Hub unter `/home/user/IMMOWARE24` (nicht Teil dieses Repos):
`app/Modules/Contacts/Services/{DavClientFactory,CardDavConnector,CollectionStateStore,
DavPullRunner}.php`, `app/Modules/Calendar/Services/CalDavConnector.php`,
`app/Modules/Documents/Services/DocumentMirrorService.php`, `docs/immoware/07-sync-strategy.md`
und `docs/immoware/08-security.md` des Hubs. Wichtigster Befund: Es gibt keine
Immoware24-REST-API. Belegte Zugangswege sind ausschliesslich WebDAV, CardDAV und CalDAV, der
Zugriff ist dort strikt lesend, Zuordnung ausschliesslich ueber externe IDs (href, etag, uid),
nie ueber Namen oder E-Mail.

## Entscheidungen

- **Kein Schreibpfad.** `ReadOnlyDavClient` (`mhvp/immoware/client.py`) laesst nur `PROPFIND`,
  `REPORT` und `GET` zu; jede andere Methode wirft `WriteBlockedError`, bevor eine Anfrage
  gesendet wird (Test: `test_write_methods_are_blocked_before_any_request`).
- **Vollabgleich statt sync-token.** CardDAV: PROPFIND liefert die etags aller hrefs, ein
  Multiget-REPORT holt nur die geaenderten. CalDAV: ein calendar-query REPORT fuer den
  Zeitraum minus 90 bis plus 365 Tage liefert Daten direkt. WebDAV: PROPFIND Depth 1 rekursiv
  bis zu einer konfigurierbaren Tiefe (Default 4), da Immoware24 kein Depth: infinity
  zuverlaessig unterstuetzt (wie im Hub, vgl. `DavPullRunner`).
- **Kein Hard Delete.** Entfallene Zeilen erhalten `deleted_at`; Bulk-Upsert je href/uid mit den
  Pflichtfeldern `source_system`, `external_id`, `external_parent_id`, `external_updated_at`,
  `first_synced_at`, `last_synced_at`, `checksum`, `sync_version`.
- **Keine Secrets in Logs.** Passwoerter sind feldverschluesselt (`EncryptedText`).
  `sanitize_error()` entfernt Basic-Auth-Header und Zugangsdaten aus URLs, bevor ein Fehlertext
  gespeichert (`ImmowareConnection.last_error`, `ImmowareSyncRun.error`) oder als Problem-Detail
  zurueckgegeben wird.
- **Beat fest, Poll-Intervall je Tenant.** Celery-Beat feuert alle 15 Minuten; die Tasks prueft
  selbst, ob `poll_minutes` seit dem letzten `ImmowareSyncRun` vergangen ist. Eine Redis-Sperre
  je Tenant und Art verhindert einen Doppellauf; ohne Redis laeuft die Abholung ungesperrt
  weiter (kein harter Ausfall).
- **Keine neuen Pakete.** vCard- und iCalendar-Parser (`vcard.py`, `ical.py`) sind minimal selbst
  implementiert, HTTP laeuft ueber `httpx.AsyncClient` (Basic Auth, Timeout 30 s).
- **Kontakterstellung nimmt nur die vCard-Felder** (FN/ORG/EMAIL/TEL); es wird kein Datenabgleich
  mit bestehenden CRM-Kontakten vorgenommen, die Verknuepfung bleibt manuell (`/match`) oder
  entsteht bei der Anlage (`/create-contact`).

## Endpunkte (`/api/v1/immoware`, Permission-Ressource `immoware`, read/update)

```
GET    /connection                          Anbindung lesen
PUT    /connection                          Anbindung einrichten (Passwort nur schreibbar)
POST   /connection/check                    PROPFIND Depth 0 auf base_url
POST   /sync/{webdav|carddav|caldav}         Abholung manuell anstossen, liefert run_id
GET    /sync/runs                            Letzte 50 Laeufe
GET    /documents?path=&q=&page=&page_size=  Dokumentbaum (Pfadpraefix, Volltext auf Namen)
GET    /documents/{id}/file                  Download-Proxy (Content-Type durchgereicht)
GET    /contacts?q=&unmatched=&page=&page_size=
POST   /contacts/{id}/match {contact_id}     Nur Verknuepfung setzen
POST   /contacts/{id}/create-contact         CRM-Kontakt aus der vCard anlegen
GET    /events?from=&to=&page=&page_size=
```

Fehlercodes: `MHVP-IMW-0001` (502, nicht eingerichtet), `MHVP-IMW-0002` (503, nicht erreichbar),
`MHVP-IMW-0003` (500, Schreibversuch blockiert; wird intern durch `WriteBlockedError` ausgeloest,
im Regelbetrieb sollte dieser Code nie auftreten, da der Client keine Schreibmethode zulaesst).

## Datenmodell

`immoware_connection` (eine Zeile je Tenant), `immoware_dav_document`, `immoware_dav_contact`
(mit `matched_contact_id` als FK auf `contact`), `immoware_dav_event`, `immoware_sync_run`.
Migration `alembic/versions/0044_immoware_dav.py` (RLS ueber `tenant_rls_statements`).

## Sicherheitsregeln (Zusammenfassung)

1. Nur lesende DAV-Methoden, hart im Client durchgesetzt.
2. Passwoerter feldverschluesselt, nie geloggt; Fehlertexte werden vor dem Speichern bereinigt.
3. Zuordnung ausschliesslich ueber href/uid, nie ueber Namen oder E-Mail.
4. Kein Hard Delete auf Spiegeldaten.

## Offene Punkte

- Frontend (Einstellungsseite `einstellungen/immoware`, Uebersichtsseite `immoware` mit den
  drei Reitern Dokumente/Kontakte/Termine, Navigationseintrag, Uebersetzungen) ist mit diesem
  Meilenstein noch nicht umgesetzt; das Backend ist vollstaendig und ueber die BFF-Allowlist
  erreichbar, siehe Bericht des Auftrags fuer den Stand.
- Integrationstest (`tests/integration/test_m32_immoware.py`) liegt inzwischen vor: WebDAV/
  CardDAV/CalDAV per `httpx.MockTransport` gefakt, Happy Path (Sync, Dokument-/Kontakt-/
  Termin-Listen, Datei-Proxy), Berechtigung, Mandantentrennung, Validierung sowie die
  Read-only-Garantie (kein Schreib-Endpunkt, `ReadOnlyDavClient` blockiert Schreibmethoden vor
  jeder Anfrage). Die Unit-Tests in `tests/unit/test_immoware_dav.py` decken weiterhin Parser,
  Methodensperre und Fehlerbereinigung ab.

## Ergebnis Folgeauftrag (Betreiberbericht 25.09.2026)

Anlass: die DAV-Anbindung funktioniert in Produktion nicht, Kontakte wurden nicht ins CRM
übernommen, und es ist unklar, ob das DAV-Modul bei Immoware24 gebucht ist. Umgesetzt:

1. **Discovery** (`mhvp.immoware.discovery`, RFC 6764/4918/6352/4791): `.well-known`,
   `current-user-principal`, `addressbook-home-set`/`calendar-home-set`, Depth-1-Listing der
   Home-Sets sowie eine WebDAV-Wurzelsuche über die gebräuchlichen Pfade. Gefundene URLs werden
   nur übernommen, solange keine manuelle URL gesetzt ist (`*_discovered`-Flags auf
   `immoware_connection`).
2. **Diagnose-Endpunkt** `POST /connection/diagnose`: Schrittliste mit maskierter URL, Status und
   deutscher Einordnung (401/403, 404 auf allen Wurzeln → DAV-Modul vermutlich nicht gebucht,
   207 → gefunden), persistiert auf der Connection und im CRM unter „Verbindung
   diagnostizieren“ sichtbar (Migration `0063_immoware_discovery_diagnosis.py`).
3. **Kontakte-Massenübernahme** `POST /contacts/take-over` (alle oder ausgewählte), mit
   Duplikatprüfung über `mhvp.contacts.services.find_duplicates`, idempotent; optionales
   Connection-Flag `auto_take_over_contacts` (Default aus) löst dieselbe Übernahme automatisch
   nach jedem CardDAV-Sync aus. CRM-Seite „Kontakte“ hat einen „Alle übernehmen“-Knopf mit
   Ergebniszusammenfassung.
4. **Dokumente**: `pull_tree` bricht bei einem gesperrten Unterordner (401/403) nicht mehr ab,
   sondern protokolliert ihn in `immoware_sync_run.folder_errors` und geht weiter
   (Migration `0066_immoware_document_takeover.py`). Neue Endpunkte
   `POST /documents/{id}/take-over` (einzelne Datei, idempotent je href+etag, Objektverknüpfung
   über die geratene Objektnummer) und `POST /documents/take-over-folder` (Ordner-Bulk, einzelne
   Fehler zählen statt abzubrechen). CRM-Seite „Dokumente“ hat einen „Ordner übernehmen“-Knopf.
5. Tests: `tests/unit/test_immoware_dav.py` (SabreDAV-ähnlicher Discovery-Mock, reiner
   404-Server, gesperrter Unterordner ohne Abbruch) und `tests/integration/test_m32_immoware.py`
   (Diagnose-Endpunkt inkl. Credential-Maskierung, Kontakte-Bulk-Übernahme idempotent,
   Dokument- und Ordner-Übernahme idempotent, WebDAV-Lauf mit gesperrtem Unterordner).
6. Offener Punkt: ob das DAV-Modul bei Immoware24 tatsächlich gebucht ist, bleibt unbekannt und
   ist in `docs/OPEN_QUESTIONS.md` beim Betreiber eingetragen; die Diagnose macht den Verdacht nur
   sichtbar, ersetzt aber nicht die Rückfrage beim Immoware24-Support.
