# Telefonie-Webhook (Rufnummernerkennung, Anrufnotiz)

Stand 26.09.2026, Lückenliste A70, Master-Prompt 13.5, Milestone M23. Code:
`apps/api/src/mhvp/communication/telephony.py`, Migration 0118 (`telephony_settings`,
`call_log`), CRM-Seiten `/einstellungen/telefonie` und Reiter Kommunikation am Kontakt.

## Betreiberentscheidung offen

Der Anbieter (TAPI-Anbindung, SIP-Anbieter, Cloud-Telefonanlage) ist beim Betreiber noch nicht
festgelegt (docs/OPEN_QUESTIONS.md, M23-06). Der Endpunkt ist bewusst anbieterneutral: Die
Telefonanlage oder ein kleiner Adapter (zum Beispiel ein Skript am TAPI-Server) sendet die
unten beschriebenen Ereignisse. Vor Produktivnutzung sind Auftragsverarbeitung und
Datenschutzhinweise für die Rufnummernverarbeitung zu prüfen.

## Endpunkt

`POST /api/v1/communication/webhooks/telephony` (Mandant im Header `X-MHVP-Tenant`, Slug oder
Id) oder `POST /api/v1/communication/webhooks/telephony/{mandant}` (Mandant im Pfad). Der
Endpunkt liegt außerhalb der Anmeldung; jede Zustellung wird geprüft wie beim
Paperless-Webhook (`docs/plans/M14-belegeingang.md`):

| Kopfzeile | Inhalt |
| --- | --- |
| `X-MHVP-Timestamp` | Unix-Sekunden; höchstens 300 Sekunden Abweichung zur Serverzeit |
| `X-MHVP-Signature` | `sha256=<hex>` von HMAC-SHA256(Geheimnis, `"<timestamp>." + Rohdaten`) |
| `X-MHVP-Tenant` | Mandanten-Slug oder Id (entfällt bei Pfadvariante) |
| `Content-Type` | `application/json` |

Antworten: 200 mit `status` (`recorded`, `updated`), `call_id`, `match_status`, `contact_id`,
`candidates`, `proposal`; 401 `MHVP-HOOK-0002` bei fehlender, veralteter oder falscher
Signatur, unbekanntem Mandanten oder deaktiviertem Webhook; 409 `MHVP-HOOK-0003` bei erneuter
Zustellung derselben Signatur (Replay, Fenster 600 Sekunden in Redis); 413 `MHVP-HOOK-0004`
bei mehr als 16 KiB; 422 bei ungültigem Inhalt oder unbekannten Feldern; 429 bei
Überschreiten des plattformweiten Anfragelimits je Absender-IP (A49).

Das Geheimnis wird je Mandant unter Einstellungen, Telefonie hinterlegt (mindestens 16
Zeichen), verschlüsselt gespeichert und nie wieder angezeigt.

## Nachrichtenformat

```json
{
  "event": "call.missed",
  "number": "+49 211 1234560",
  "direction": "inbound",
  "started_at": "2026-09-26T08:15:00Z",
  "duration_seconds": 0,
  "provider_ref": "pbx-call-8811"
}
```

| Feld | Pflicht | Bedeutung |
| --- | --- | --- |
| `event` | ja | `call.started`, `call.ended`, `call.missed` |
| `number` | ja | Rufnummer der Gegenseite, beliebiges Format; wird nach E.164 normalisiert (Standardregion DE). Nicht lesbare Werte (zum Beispiel `anonym`) bleiben als Text erhalten, ohne Zuordnung |
| `direction` | ja | `inbound` oder `outbound` |
| `started_at` | nein | Beginn (ISO 8601); fehlt er, gilt der Empfangszeitpunkt |
| `duration_seconds` | nein | Dauer in Sekunden, sinnvoll bei `call.ended` |
| `provider_ref` | nein | Referenz der Anlage; `call.started` und `call.ended` mit gleicher Referenz werden zu einem Eintrag zusammengeführt |

Weitere Felder werden abgelehnt. Gesprächsinhalte, Aufzeichnungen oder Transkripte werden
nie angenommen (Datenschutz).

Signatur in Python, zur Prüfung des Adapters:

```python
import hashlib, hmac, time
ts = int(time.time())
sig = "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
```

## Zuordnung und Anrufnotiz

* Vergleich der normalisierten Nummer mit `contact_phone.number` (E.164) des Mandanten,
  gelöschte Kontakte ausgenommen. Genau ein Treffer: Kontakt zugeordnet. Mehrere Treffer:
  Kandidatenliste (höchstens zehn), Zuordnung per `POST /communication/calls/{id}/assign`.
  Kein Treffer: Status `unknown`.
* Jeder Anruf ist eine Zeile in `call_log` (Anrufnotiz am Kontakt, Freitext `note` über
  `PATCH /communication/calls/{id}`).
* Ticket-Vorschlag "Rückruf": bei verpasstem Anruf oder wenn der zugeordnete Kontakt ein
  offenes Ticket hat (`related_ticket_id`). Ein Ticket entsteht erst durch
  `POST /communication/calls/{id}/proposal/accept` (Recht `tickets:create`, Quelle `phone`,
  Kontakt gesetzt, offenes Ticket als übergeordnetes Ticket), nie automatisch (Regel 0.1.6).
  `.../proposal/dismiss` verwirft den Vorschlag.

## Lesen

* `GET /api/v1/communication/calls` (Recht `communication:read`, Filter `contact_id`, `event`,
  `proposal_status`, `limit`). Ohne `contacts:read` ist die Rufnummer maskiert
  (`+4921****99`, `number_masked: true`).
* `GET /api/v1/contacts/{id}/calls` (Recht `contacts:read`), im CRM im Reiter Kommunikation
  des Kontakts mit Annahme oder Verwerfen des Rückruf-Vorschlags.
* `GET`/`PUT /api/v1/communication/telephony/settings` (Rechte `tenant_settings:read`,
  `tenant_settings:update`).

## Tests

`apps/api/tests/integration/test_a70_telephony.py` (Signatur gültig, ungültig, fehlend,
veraltet, Replay, Größenlimit, deaktivierter Mandant, Zuordnung eindeutig, mehrdeutig,
unbekannt, Rückruf-Vorschlag und Ticketanlage, Mandantentrennung, Maskierung ohne
`contacts:read`, Berechtigungen, Anfragelimit), `apps/api/tests/unit/test_a70_telephony.py`,
`apps/web-crm/src/components/settings/TelephonySettings.test.tsx`,
`apps/web-crm/src/components/contacts/CallsPanel.test.tsx`.
