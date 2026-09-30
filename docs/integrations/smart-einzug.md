# smart-einzug: Anbindung per Webhook

Stand 30.09.2026. Betriebsanleitung zu Abschnitt 13.3. Hintergrund und offene Fragen stehen
im Dossier `dossier-smart-einzug.md`. Ob smart-einzug angebunden oder abgelöst wird, ist
Entscheidung des Betreibers (siehe `docs/OPEN_QUESTIONS.md`); die Plattform liefert die
sendende Seite in beiden Fällen.

## Webhook-Ziel einrichten

Das Ziel ist je Mandant konfigurierbar, es gibt keine feste Adresse im Code:

1. Abonnement anlegen: `POST /api/v1/tenant/webhooks` mit der Empfangs-URL von smart-einzug
   (https, öffentliche Adresse) und den Ereignistypen `contact.updated`,
   `contact.mandate_iban_changed` und bei Bedarf `invoice.issued`. In der CRM-Oberfläche unter
   Einstellungen, Webhooks.
2. Das Geheimnis wird nur einmal angezeigt. Der Empfänger prüft `X-MHVP-Signature`
   (`t=<unix>,v1=<hex>`, HMAC-SHA256 über `<t>.<Rohkörper>`, Zeitstempel höchstens fünf Minuten alt).
3. Wiederholungen erkennt der Empfänger an `Idempotency-Key` (je Zustellung stabil, identisch
   bei jedem Versuch) und an `X-MHVP-Event-Id` (Ereignis-ID). `X-MHVP-Delivery` nennt die
   Zustell-ID.
4. Zustellprotokoll und manuelle Neuzustellung: `GET /api/v1/tenant/webhooks/{id}/deliveries`.

## Payload

Nur Kennungen und Feldnamen, keine Namen, Adressen oder IBAN (`docs/integrations/webhooks.md`).
Der Empfänger lädt bei Bedarf die Kontaktdaten mit einem API-Schlüssel nach.

## Offen

Empfangsschnittstelle, Authentifizierung und Antwortverhalten von smart-einzug liefert der
Betreiber (Dossier Abschnitt 3). Bis dahin ist keine Zustellung an ein produktives Ziel
eingerichtet.
