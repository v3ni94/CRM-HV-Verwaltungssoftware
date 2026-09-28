# Schadenbearbeiter (Schadenstool, MDV/midive)

Stand 28.09.2026. Regel `docs/rules/INT-SDT-01-schadenbearbeiter.md`, Vertragsentwurf der
Gegenseite `docs/integrations/schadenstool-hv-api-v1-vertrag.md`, Plan
`docs/plans/M-schadenstool.md`.

Die Plattform ist gegenüber dem Schadenbearbeiter Client seiner API
(`<Basisadresse>/api/integrations/hv/v1`) und Empfänger seiner Webhooks. Der Vertrag ist ein
Entwurf; ob alle Endpunkte produktiv sind, ist offen (SDT-02).

## Einrichtung durch den Betreiber

1. AVV mit dem Schadenbearbeiter abschließen (SDT-01). Ohne eingetragenes AVV-Datum lässt
   sich die Anbindung nicht aktivieren.
2. Im Adminbereich des Schadenbearbeiters einen Integrationstoken für den Mandanten erzeugen.
   Der Token wird dort nur einmal angezeigt.
3. In der Plattform unter Einstellungen, Schnittstellen, Schadenbearbeiter eintragen:
   Basisadresse (zum Beispiel `https://api.midive.de`), Integrationstoken, optional ein
   HMAC-Geheimnis für ausgehende Anfragen (falls die Gegenseite es verlangt), ein
   Webhook-Geheimnis (mindestens 16 Zeichen, frei gewählt), AVV-Datum und Vermerk.
4. Speichern, dann "Verbindung testen". Der Test ruft `GET /tickets?limit=1` auf und zeigt nur
   das Ergebnis. "Token ungültig" bedeutet: der Token wurde abgelehnt oder widerrufen.
5. Anbindung aktiv setzen und speichern.

## Was der Schadenbearbeiter auf seiner Seite einrichten muss

- Webhook-Adresse: die auf der Einstellungsseite angezeigte Adresse, vorne ergänzt um die
  öffentliche Adresse der Plattform, also
  `https://<plattform>/api/v1/integrations/schadenstool/webhook/<Mandanten-ID>/<Pfad-ID>`.
  Die Pfad-ID ist zufällig und gehört zu genau einem Mandanten.
- Webhook-Geheimnis: identisch mit dem in der Plattform hinterlegten Wert. Jede Zustellung
  trägt `X-Timestamp` (Unix-Sekunden) und `X-Signature: sha256=<hex>` über
  `${timestamp}.${rawBody}`. Zustellungen älter als 5 Minuten werden abgewiesen.
- Ereignisse mit `eventId`, `eventType`, `entityType`, `entityId`; ausgewertet werden
  `ticket.created`, `ticket.updated`, `ticket.status_changed`, `ticket.comment_added`,
  `ticket.attachment_added`. Andere Ereignisse werden angenommen und ignoriert. Eine doppelte
  `eventId` bleibt ohne Wirkung.
- Antwortfelder nach SDT-02 bestätigen; die Statusliste nach SDT-03 liefern.

## Was die Plattform verlässt

| Anlass | Inhalt |
| --- | --- |
| Übergabe eines Tickets | Ticket-ID, Objektnummer, Einheitennummer, Titel, öffentliche Beschreibung, im Formular erfasste meldende Person und Schadendaten (Datum, Art, Ort) |
| Kommentar senden | nur der ausdrücklich gesendete Text und der Anzeigename des Verfassers |
| Dokument senden | nur das ausdrücklich gewählte Dokument des Tickets |
| Statuswechsel eines verknüpften Tickets | der abgebildete Status (Tabelle in INT-SDT-01) |

Nicht übermittelt werden interne Beschreibung, interne Notizen, Kontaktdaten, Versicherungs-
oder Policendaten und Buchungsdaten.

## Was in die Plattform kommt

- Status des Schadenbearbeiters: gespeichert und am Ticket angezeigt, ohne den eigenen Status
  zu ändern.
- Kommentare: als interne Notiz am Ticket, Verfasser am Austauschdatensatz.
- Anhänge: nach Virenprüfung im DMS abgelegt und mit dem Ticket verknüpft.
- Neue Schadentickets ohne Zuordnung: in der Liste "Vorhandene Schadentickets übernehmen" mit
  Vorschlag für Objekt (Objektnummer) und Ticket (externe ID). Ein Mitglied legt ein neues
  Ticket an, verknüpft oder verwirft; automatisch geschieht nichts.

## Betrieb

- Warteschlange: Nutzeraktionen werden gespeichert und jede Minute gesendet
  (`mhvp.integrations.schadenstool.process`). Wiederholung nach 1 min, 5 min, 30 min, 2 h,
  6 h, 24 h; bei 429 frühestens nach `Retry-After`. Danach "fehlgeschlagen" am Ticket.
- Abgleich alle 15 Minuten (`mhvp.integrations.schadenstool.pull`) über `updatedSince` und
  Cursor, als Rückfallebene für verpasste Webhooks; "Jetzt abgleichen" stößt ihn sofort an.
- Anbindung aus: kein Aufruf zum Schadenbearbeiter, der Webhook antwortet 404.
- Jeder Austausch erzeugt ein Domänenereignis `schadenstool.*` (Audit). Protokolle enthalten
  keine Tokens und keine Inhalte.

## Nicht in v1

Objekt-, Policen- und Schadenhistorien-Abgleich (Vertrag Abschnitt 5, SDT-04), Priorität,
Zuständige, Löschungen.
