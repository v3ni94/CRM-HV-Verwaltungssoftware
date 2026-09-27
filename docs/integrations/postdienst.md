# Postdienst (Brief- und Postversand mit Statusrückmeldung)

Stand 27.09.2026, Regel `docs/rules/M23-01.md`, Modul `mhvp.communication` (Dateien
`postal_providers.py`, `postal.py`, `postal_tasks.py`). Dieses Dokument ist das
Betreiberdokument: was das CRM kann, welcher Anbieter angebunden ist, was aus der
öffentlichen Dokumentation belegt ist und was vor dem Live-Betrieb zu prüfen bleibt.

## 1. Was umgesetzt ist

- Anbieterneutrale Schnittstelle `PostalProvider`: `submit(pdf, Empfängeranschrift,
  Optionen: Einschreiben r1/r2, Farbe, Duplex, Versandtag, Notiz)` liefert eine Auftrags-ID,
  `status(id)` liefert eingereicht, gedruckt, versendet, zugestellt, fehlgeschlagen oder
  storniert, `cancel(id)` storniert. Weitere Anbieter werden über
  `postal_providers.register_provider` angebunden, ohne die Domänenlogik zu ändern.
- `ManualPostalProvider` (Standard): Postausgangsliste im CRM unter Kommunikation,
  Postausgang. Das PDF wird gedruckt und von Hand versendet; Druck, Versanddatum und
  Zustellnachweis werden manuell erfasst.
- `LetterXpressProvider`: Adapter für die LXP API v3 (Abschnitt 2).
- Mandanteneinstellung `postal_settings`: Anbieter, Freigabe (`enabled`, Standard aus),
  Benutzername, API-Schlüssel (verschlüsselt, nie auslesbar), Modus `test` oder `live`
  (Standard `test`), Standardoptionen Farbe, Duplex, Einschreiben. Verbindung prüfen fragt
  bei LetterXpress das Guthaben ab.
- Postauftrag je Zustellung (`postal_job`) mit Statushistorie (`postal_job_event`), Anzeige
  an der Zustellung (`GET /postal/dispatches/{id}/history`) und in der Kontakthistorie.
- Beat-Job `communication-postal-status-poll` alle 30 Minuten (nur Mandanten mit
  freigegebenem externem Anbieter), Schaltfläche "Status abrufen" je Auftrag.
- Mahnwesen: `POST /postal/jobs {"dunning_case_id": ...}` reicht das abgelegte Mahnschreiben
  ein (Mahnlauf muss freigegeben sein; Fall gilt als versendet, M16-09); Zugang mit Nachweis
  wird am Mahnfall vermerkt. Über einen externen Anbieter nur bei offenem G1.
- Einzelbrief und Serienbrief: jede Zustellung mit Kanal `post` (`POST /dispatches`,
  `POST /dispatches/serial`, Anschreiben, Übergabeprotokoll) kann mit
  `POST /postal/jobs {"dispatch_id": ...}` in die Postausgangsliste aufgenommen oder beim
  Anbieter eingereicht werden.

## 2. LetterXpress (LXP API v3): Beleglage

Quelle: öffentliche Seite https://www.letterxpress.de/versandwege/api (Dokumentation
Version 3.0 vom 01.12.2024, dort auch als PDF `lxp-api_dokumentation.pdf` verlinkt),
gelesen am 27.09.2026. Die früher genannte Adresse `/dokumentation/` liefert 404. Nur die
dort gezeigten Felder und Antworten sind umgesetzt; alles andere ist als "zu prüfen"
gekennzeichnet und vor dem Live-Betrieb gegen die PDF-Dokumentation und das Testsystem zu
verifizieren.

| Punkt | Belegt auf der Seite | Umsetzung im Adapter |
| --- | --- | --- |
| Basis-URL | `https://api.letterxpress.de/v3` | `LXP_BASE_URL` |
| Authentifizierung | JSON-Objekt `auth` mit `username`, `apikey`, `mode` (`test`, `live`) in jedem Request; Content-Type `application/json`; API-Key im Kundenbereich unter Funktionen, Zugangsdaten, LXP API | `auth` in jedem Request; `mode` aus der Mandanteneinstellung |
| Testmodus | `mode = test`: Aufträge gehen in den Warenkorb, keine Verarbeitung, nach 7 Tagen gelöscht | Standard `test`; der Adapter meldet `external = false` im Testmodus |
| Limits | 50 MB je PDF und Request, 120 Requests pro Minute | nicht geprüft (Betreiberhinweis); Statusabruf höchstens alle 10 Minuten je Auftrag |
| Brief anlegen | `POST`-Verhalten nicht ausdrücklich benannt; Endpunkt `/v3/printjobs` mit `letter` (`base64_file`, `base64_file_checksum` als md5 des Base64-Strings, `specification.color` 1 oder 4, `specification.mode` simplex oder duplex, `specification.shipping` national, international, auto, optional `registered` r1 (Einschreiben Einwurf) oder r2 (Einschreiben, nur national), `dispatch_date` (yyyy-mm-dd, Zukunft), `filename_original`, `notice` bis 255 Zeichen) | umgesetzt; HTTP-Methode `POST` ist REST-Konvention und **zu prüfen** |
| Empfängeradresse | Kein Adressfeld im Letter-Objekt; die Anschrift wird aus dem PDF gelesen und in `items[].address` zurückgegeben | Adressblock wird nur im CRM gespeichert (`recipient_address`); das PDF muss die Anschrift im Adressfenster tragen (Briefbogen nach DIN 5008, wie in `mhvp.documents.letters`) |
| Auftrag lesen | `GET /v3/printjobs/{id}`, Antwort `data.status` (queue, hold, done, canceled, draft), `items[].status` (queue, sent im Beispiel), optional `tracking_code`, `tracking_status` (Beispieltext "Zugestellt: ...") | Mapping: queue, hold, draft nach `submitted`; done nach `sent`; `tracking_status` beginnend mit "Zugestellt" nach `delivered`; canceled nach `cancelled`; unbekannte Werte bleiben `submitted` mit Hinweis "zu prüfen" und Rohantwort |
| Auftragsliste | `GET /v3/printjobs?filter=queue|hold|done|canceled|draft`, paginiert | nicht genutzt (Abruf je Auftrag) |
| Auftrag ändern | `/v3/printjobs/{id}` innerhalb von 15 Minuten, nur Spezifikation, nicht das PDF | nicht umgesetzt |
| Auftrag löschen | `/v3/printjobs/{id}` innerhalb von 15 Minuten, nicht bei `done`; Antwort `"Print job deleted successfully"` | `cancel` mit `DELETE` (Methode **zu prüfen**) |
| Guthaben | `GET /v3/balance` mit `auth` im Body, Antwort `data.balance`, `data.currency` | "Verbindung prüfen" |
| Preis | `/v3/price` mit `specification.pages` | nicht umgesetzt |
| Weitere Funktionen | Serienbrief-Trennung (`serial_letter`), Anhänge, Hintergründe, AGB, Überweisungsträger (`bank_form`), E-Mail-Briefe (`email_letter`, `/v3/emailjobs`), Transaktionen (`/v3/transactions`) | nicht umgesetzt (kein Bedarf, `bank_form` würde Bankdaten übertragen und bleibt ausgeschlossen) |

Zu prüfen vor Live-Betrieb: HTTP-Methoden für Anlegen und Löschen, vollständige Liste der
`items[].status`-Werte (nur `queue` und `sent` sind gezeigt; "gedruckt" wird von der API nicht
als eigener Status belegt und bleibt der manuellen Erfassung vorbehalten), Text der
`tracking_status`-Meldungen, Fehlerformat bei fachlichen Ablehnungen (nur `Unauthorized.`
ist gezeigt), Verhalten bei `shipping = auto` mit ausländischer Anschrift.

## 3. Datenschutz und Freigabe

- Ein externer Postdienst ist Auftragsverarbeiter: Briefe enthalten personenbezogene Daten
  (Anschrift, Forderungen). Vor der Freigabe je Mandant sind Auftragsverarbeitungsvertrag,
  Verarbeitungsort und Löschfristen des Anbieters zu prüfen (Betreiber, DSGVO).
- Kein Versand ohne Freigabe: `enabled` Standard aus, `mode` Standard `test`, Einreichen
  extern nur mit `communication:approve`. Der Adapter enthält keine Rechtslogik; Zugang gilt
  nur mit Nachweis (Regel M23-01).
- Der API-Schlüssel steht ausschließlich verschlüsselt in `postal_settings.api_key` und
  erscheint in keiner Antwort, keinem Log und keiner Fehlermeldung.

## 4. Bedienung im CRM

Kommunikation, Mail, Postausgang: Filter nach Status (offen, alle, je Status), Anbieter und
"nur Mahnschreiben"; je Auftrag Anbieterstatus, Sendungsnummer, Details mit Statushistorie,
manuelle Erfassung (gedruckt, versendet, zugestellt mit Nachweisart und Referenz,
fehlgeschlagen), "Status abrufen" und "Stornieren". Administratoren
(`tenant_settings:update`) richten den Postdienst auf derselben Seite ein und prüfen die
Verbindung.

## 5. Offene Punkte

Siehe `docs/OPEN_QUESTIONS.md` M23-08: Anbieterwahl, Auftragsverarbeitung, Testzugang und
die Verifizierung der oben markierten Punkte bleiben Betreiberentscheidung.
