# Eingehender Webhook für klassifizierte Mails (M20-04, AE38)

Stand 01.10.2026. Vertrag für das Bestandsprogramm "Mail optimierung" (Dossier
`docs/integrations/mail-optimierung.md`) und jedes andere Fremdsystem, das bereits klassifizierte
Mails in das Postfachmodul der Plattform liefern soll. Der Vertrag ist die Gegenrichtung zu den
ausgehenden Webhooks (`docs/integrations/webhooks.md`) und verwendet dieselbe Signatur.

Die Empfehlung des Dossiers lautet Übernahme als Modul (Reiter Mail, `mhvp.communication`).
Der Webhook ist die Brücke für die Zeit bis zur Entscheidung und für den Parallelbetrieb: er
bucht nichts, versendet nichts und löscht nichts. Ob das Bestandsprogramm überhaupt als
Webhook-Quelle weiterläuft oder abgelöst wird, bleibt Betreiberentscheidung (Frage AE38-01 in
`docs/OPEN_QUESTIONS.md`).

## Überblick

| Punkt | Festlegung |
| --- | --- |
| Endpunkt | `POST /api/v1/mail/inbound/sources/{source_id}/classified-mails` |
| Authentifizierung | API-Schlüssel (`X-API-Key`), mandantengebunden, Recht `mail_inbound:ingest` |
| Signatur | `X-MHVP-Signature: t=<unix>,v1=<hex>`, `v1 = HMAC-SHA256(secret, "<t>." + roher Body)` |
| Zeitfenster | 300 Sekunden in beide Richtungen, danach 401 |
| Idempotenz | `event_id` im signierten Body, eindeutig je Quelle |
| Größe | höchstens 1 MiB (1.048.576 Bytes), sonst 413 |
| Antwort | JSON mit Kennungen, ohne Mailinhalt |

Der Endpunkt gehört zur Gruppe der maschinellen Schnittstellen: Ein angemeldeter Benutzer mit
Bearer-Token wird mit 403 abgewiesen, auch wenn er das Recht hält.

## Einrichtung je Mandant

1. Quelle anlegen (Recht `tenant_settings:update`):
   `POST /api/v1/mail/inbound/sources` mit `name` (eindeutig je Mandant), optional `mailbox_id`
   (Postfach, an das die Mails gebunden werden) und `auto_ticket` (Standard `true`, entsprechend
   der Regel vom 25.09.2026: jede eingehende Mail erzeugt ein Ticket, außer sie gehört zu einem
   bestehenden Verlauf). Die Antwort enthält `secret` genau einmal und `delivery_path`.
2. API-Schlüssel ausstellen: `POST /api/v1/tenant/api-keys` mit dem einzigen Geltungsbereich
   `mail_inbound:ingest`. Der Schlüssel erlaubt nichts anderes. Das Recht halten nur die
   Administratorrollen; Standardrollen können es nicht vergeben.
3. Das Bestandsprogramm erhält Schlüssel, `source_id` und `secret`. Alle drei gehören in dessen
   geschützte Konfiguration, nicht in Quelltext oder Protokolle.

Verwalten: `GET /api/v1/mail/inbound/sources` (Liste ohne Geheimnis, mit `last_received_at`),
`PATCH .../sources/{id}` (`name`, `active`, `mailbox_id`, `auto_ticket`),
`POST .../sources/{id}/rotate-secret` (neues Geheimnis einmalig sichtbar, das alte ist sofort
ungültig), `GET .../sources/{id}/events?limit=` (Empfangsprotokoll: `event_id`, `message_id`,
`ticket_id`, `message_created`, `replay_count`). Rechte `tenant_settings:read` und
`tenant_settings:update`. Eine Quelle wird nicht gelöscht, sondern deaktiviert, damit das
Empfangsprotokoll erhalten bleibt.

## Aufruf

```
POST /api/v1/mail/inbound/sources/<source_id>/classified-mails
X-API-Key: mhvp_<mandant>_<präfix>_<geheimnis>
X-MHVP-Signature: t=1790000000,v1=<64 Hexzeichen>
Content-Type: application/json
```

Die Signatur wird über die exakten Bytes des gesendeten Bodys gebildet. Wer den Body nach der
Signatur neu serialisiert, bricht sie. Das Beispiel mit Python:

```python
import hashlib, hmac, json, time

body = json.dumps(document, ensure_ascii=False).encode()
t = int(time.time())
v1 = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
headers["X-MHVP-Signature"] = f"t={t},v1={v1}"
```

Dasselbe in PHP (nur zur Veranschaulichung des Verfahrens, keine Aussage über den Aufbau des
Bestandsprogramms): `$v1 = hash_hmac('sha256', $t . '.' . $body, $secret);`

### Body

```json
{
  "event_id": "legacy-2026-09-30-000123",
  "source_ref": "4711",
  "classified_at": "2026-09-30T08:16:00+02:00",
  "mail": {
    "message_id": "<abc123@mail.example.org>",
    "in_reply_to": null,
    "references": null,
    "from_address": "mieter@example.org",
    "reply_to": null,
    "to": ["info@example.com"],
    "cc": [],
    "subject": "Heizung ausgefallen",
    "body_text": "Guten Tag, ...",
    "body_html": null,
    "received_at": "2026-09-30T08:15:00+02:00",
    "auto_submitted": false,
    "attachment_count": 0
  },
  "classification": {
    "category": "Heizung",
    "process": "Störung",
    "urgency": "urgent",
    "summary": "Heizungsausfall gemeldet",
    "confidence": 0.9,
    "labels": ["technik"],
    "ticket_number": null
  }
}
```

* Unbekannte Felder werden mit 422 abgewiesen (`extra = forbid`); der Vertrag wächst nur
  additiv und wird versioniert wie in ADR 0009.
* `event_id`: 1 bis 200 sichtbare ASCII-Zeichen ohne Leerzeichen, eindeutig je Quelle und Mail.
  Es ist der Idempotenzschlüssel.
* Zeitangaben tragen immer einen Zeitzonenversatz; ohne Versatz antwortet der Endpunkt mit 422.
* Pflicht sind `event_id`, `mail` und `mail.from_address`. Längen: Betreff 998, Text 100.000,
  HTML 400.000 Zeichen, `references` 20.000, je Liste höchstens 100 Empfänger.
* Anhänge sind nicht Teil des Webhooks. `attachment_count` ist nur eine Angabe für die
  Anzeige. Mails mit Anhängen, deren Dateien gebraucht werden, gehören in den Weg über
  `POST /api/v1/mail/ingest` mit der .eml-Datei (offener Punkt, siehe unten).

## Verarbeitung

Die Mail durchläuft denselben Aufnahmeweg wie jede andere eingehende Mail
(`mhvp.communication.services.ingest_parsed`):

* Zuordnung Kontakt und Objekt nach den Regeln der Zuordnungsprüfung, unsichere Treffer bleiben
  Rückfrage.
* Thread nach `In-Reply-To`, `References` und Gmail-Thread; Kennung `TNR#<nummer>` im Betreff
  nur bei bekanntem Absender. Eine Antwort wird an das Ticket des bisherigen Verlaufs gehängt
  (ein abgeschlossenes Ticket wird im Wiedereröffnungsfenster wieder geöffnet, sonst entsteht
  ein Folgeticket).
* Eine Mail, die nicht zu einem Verlauf gehört, erzeugt ein Ticket, wenn die Quelle
  `auto_ticket = true` hat.
* Eine Mail mit bereits bekannter Message-ID (zum Beispiel über die Gmail-Anbindung schon
  abgerufen) wird nicht doppelt gespeichert; das Ereignis verweist auf die vorhandene Nachricht
  (`message_created = false`).
* Das Ereignis `message.received` steht den Automationsregeln (`mhvp.automation`) wie bei jeder
  Mail zur Verfügung; zusätzlich entsteht `inbound_mail.received` mit Kennungen.
* Die Klassifikation des Bestandsprogramms wird unter `classification.external` und
  `classification.source` an der Nachricht abgelegt. Sie ist ein Vorschlag: sie überschreibt
  weder Kategorie, Dringlichkeit noch Zuordnung, die die Plattform selbst ermittelt, und
  genehmigt nichts. Ob die Fremdklassifikation künftig verbindlich übernommen wird, ist Teil der
  Frage AE38-01 und derzeit ausdrücklich nicht der Fall.

## Antworten

| Status | Bedeutung |
| --- | --- |
| 201 | Ereignis angenommen, Mail verarbeitet. Antwort: `event_id`, `replayed=false`, `message_created`, `message_id`, `ticket_id` |
| 200 | Dasselbe Ereignis mit identischem Inhalt war schon angenommen. Antwort mit den gespeicherten Kennungen und `replayed=true`; es entsteht nichts Neues |
| 401 | Schlüssel fehlt oder ungültig (`MHVP-AUTH-0001`), Signatur fehlt, falsch oder außerhalb des Zeitfensters (`MHVP-HOOK-0002`) |
| 403 | Schlüssel ohne Recht `mail_inbound:ingest`, oder Benutzer-Token statt Schlüssel |
| 404 | Quelle unbekannt oder Quelle eines anderen Mandanten |
| 409 | `event_id` wurde schon mit anderem Inhalt angenommen (`MHVP-HOOK-0005`); oder Quelle deaktiviert (`MHVP-HOOK-0006`) |
| 413 | Body größer als 1 MiB (`MHVP-HOOK-0004`) |
| 422 | Kein JSON, kein Objekt, unbekannte oder ungültige Felder, Zeitangabe ohne Zeitzone |

Die Reihenfolge der Prüfungen ist festgelegt: Schlüssel, Größe, Quelle, Signatur, Schalter der
Quelle, Schema, Idempotenz. Wer die Signatur nicht erzeugen kann, erfährt weder, ob die Quelle
aktiv ist, noch etwas über den Inhalt.

## Sicherheitsmerkmale

* HMAC-SHA256 über den rohen Body, Vergleich mit `hmac.compare_digest` (zeitkonstant); Header
  mit Nicht-ASCII-Zeichen, überlange Header und absurde Zeitstempel führen zu 401, nie zu einem
  Fehler.
* Das Zeitfenster von 300 Sekunden begrenzt den Wiederverwendungswert eines abgefangenen
  Aufrufs; innerhalb des Fensters wirkt die Idempotenz: ein erneuter Aufruf ändert nichts.
* Idempotenz in der Datenbank: eindeutiger Schlüssel (`Quelle`, `event_id`), Beanspruchung per
  `INSERT .. ON CONFLICT DO NOTHING` in derselben Transaktion wie die Mail. Parallele und
  wiederholte Zustellungen speichern genau eine Mail; ein Fehler rollt Ereignis und Mail
  gemeinsam zurück, sodass der Wiederholungsversuch wirkt. Der Inhalt wird als Hash des
  kanonischen JSON verglichen (Reihenfolge der Schlüssel und Leerraum spielen keine Rolle).
* Mandantenbindung doppelt: der Schlüssel trägt die Mandanten-ID, Quellen und Ereignisse liegen
  unter Row Level Security. Die Quelle eines anderen Mandanten ist 404.
* Das Geheimnis liegt verschlüsselt (`EncryptedText`) und wird nur bei Anlage und Erneuerung
  gezeigt. Das Empfangsprotokoll enthält Kennungen, Zähler und den Hash, keinen Mailinhalt.
  Wird die Nachricht gelöscht (Datenschutz), bleibt keine Kopie des Inhalts zurück.
* Die allgemeine Ratenbegrenzung je API-Schlüssel gilt. Der allgemeine Header `Idempotency-Key`
  wird nicht benötigt; sendet ein Client ihn trotzdem, antwortet zusätzlich die
  plattformweite Zwischenspeicherung bei exakt gleicher Wiederholung.

## Abnahme und Tests

`apps/api/tests/integration/test_ae38_inbound_mail_webhook.py` (Quelle verwalten, Zustellung,
Replay 200, anderer Inhalt 409, falsche, fehlende, veraltete und nicht ASCII Signatur 401,
Recht 403, Benutzer-Token 403, widerrufener Schlüssel 401, fremder Mandant 404, Größe 413,
Validierung 422, Antwort im Verlauf, bekannte Message-ID, Schalter `auto_ticket`, vier parallele
gleiche Zustellungen) und `apps/api/tests/unit/test_ae38_inbound_mail.py` (Zeitfenster
299/301 Sekunden, Signaturvarianten, Hash, Abbildung, Schema).

## Offene Punkte

* Das Bestandsprogramm hat laut Dossier keine eigene REST-API und keinen dokumentierten
  ausgehenden Webhook; für den Versand an diesen Endpunkt wäre eine Erweiterung dort nötig
  [zu ergänzen durch Betreiber: Aufwand und Entscheidung, siehe AE38-01].
* Anhänge als Dateien sind nicht Teil dieser Version.
* Es gibt keine Oberfläche; Pflege per API. Eine Karte unter Einstellungen, Postfächer folgt,
  sobald die Quelle produktiv genutzt wird.
* Fremdklassifikation verbindlich übernehmen (Kategorie, Dringlichkeit, Vorlage) ist nicht
  entschieden und deshalb nicht umgesetzt.
