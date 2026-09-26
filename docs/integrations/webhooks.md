# Ausgehende Webhooks (Abschnitt 12, A69)

Stand 26.09.2026. Vertrag für Fremdsysteme (smart-einzug, lexoffice, Ablösung Immoware Hub),
unabhängig vom jeweiligen Dossier nach Anhang B. Die Ereignisse sind allgemeiner API-Vertrag
nach Abschnitt 12 und unterliegen der Versionsregel aus ADR 0009 (additiv ohne Versionswechsel,
Entfernung nur mit v2 nach mindestens sechs Monaten Vorlauf).

## Abonnement je Mandant

* Anlegen: `POST /api/v1/tenant/webhooks` mit `url` (https, öffentlich erreichbar; private
  Ziele nur in Entwicklung mit `MHVP_WEBHOOK_ALLOW_PRIVATE_TARGETS=true`), `event_types`
  (Liste aus dem Katalog unten oder `*`) und optionaler `description`. Die Antwort enthält
  das Geheimnis (`secret`) genau einmal; es wird verschlüsselt gespeichert.
* Verwalten: `GET /api/v1/tenant/webhooks`, `PATCH .../{id}` (aktiv, Ereignistypen),
  `GET .../{id}/deliveries` (Protokoll), `POST .../deliveries/{id}/redeliver` (manuelle
  Neuzustellung). Recht `tenant_settings:update`.
* Jeder Mandant sieht und erhält nur eigene Ereignisse (RLS, `domain_event.tenant_id`).

## Zustellung und Signatur

* Zustellung durch den Job `mhvp.core.webhooks.dispatch` (jede Minute, Queue `io`):
  `POST` mit `Content-Type: application/json`, Kopfzeilen `X-MHVP-Event` (Typ),
  `X-MHVP-Delivery` (Zustell-ID) und `X-MHVP-Signature: t=<unix>,v1=<hex>` mit
  `v1 = HMAC-SHA256(secret, "<t>." + Body)`. Empfänger prüfen die Signatur über den rohen
  Body und lehnen Zeitstempel ab, die älter als fünf Minuten sind.
* Antwort 2xx gilt als zugestellt. Wiederholung nach 1 min, 5 min, 30 min, 2 h, 6 h, 24 h,
  danach Status `failed` (sichtbar im Protokoll und in `GET /api/v1/platform/ops/metrics`).
* Body (Schlüssel sortiert, kompakt):

```json
{
  "id": "<Ereignis-ID, UUID v7>",
  "type": "contact.updated",
  "tenant_id": "<Mandanten-ID>",
  "entity_type": "contact",
  "entity_id": "<Kontakt-ID>",
  "occurred_at": "2026-09-26T08:15:00+00:00",
  "correlation_id": "<Korrelations-ID der auslösenden Anfrage>",
  "payload": { "fields": ["bank_accounts", "last_name"] }
}
```

## Datensparsamkeit

Payloads enthalten nur Kennungen, Feldnamen, Nummern, Daten und Beträge. Niemals enthalten:
IBAN, Kontoinhaber, Namen, Anschriften, E-Mail-Adressen, Telefonnummern, Dokumentinhalte oder
Geheimnisse. Der Empfänger holt Details über die API mit eigenem Schlüssel und Recht
(`GET /api/v1/contacts/{id}` usw.); so bleibt die Berechtigungsprüfung der Plattform
maßgeblich. Die Tests `apps/api/tests/integration/test_a69_webhooks.py` prüfen für die beiden
Ereignisse unten, dass weder IBAN noch Namen im signierten Body stehen.

## Ereigniskatalog (Auswahl, `mhvp.core.webhooks.EVENT_TYPES`)

| Typ | Auslöser | Payload |
| --- | --- | --- |
| `contact.created` | `POST /contacts` | leer (Kontakt-ID in `entity_id`) |
| `contact.updated` | `PUT /contacts/{id}` mit tatsächlicher Änderung | `fields`: sortierte Liste der geänderten Feldnamen (`last_name`, `addresses`, `bank_accounts`, ...), keine Werte |
| `contact.deleted` | `DELETE /contacts/{id}` | leer |
| `contact.mandate_iban_changed` | IBAN einer Bankverbindung mit SEPA-Mandat geändert | `mandate_reference` |
| `invoice.issued` | `POST /accounting/admin-fees/{id}/invoice-issue` (Verwalterhonorar als XRechnung ausgestellt) | `invoice_id`, `number`, `invoice_date`, `kind` (`admin_fee`), `fee_setting_id`, `property_id`, `debtor_legal_entity_id`, `net`, `vat`, `gross` (Strings mit zwei Nachkommastellen), `currency`, `xrechnung_url` |
| `admin_fee_invoice.xrechnung_stored` | XRechnung-XML im DMS abgelegt | `number`, `document_id` |
| `tenant_settings.updated` | Mandanteneinstellungen geändert | geänderte Schlüssel |

Weitere `domain_event.type` können abonniert werden; verbindlich dokumentiert ist der Katalog.
Neue Typen werden nur ergänzt, nie umbenannt (ADR 0009).

## Offene Punkte

* Ereignisse `invoice.received|approved|paid`, `journal_entry.posted|reversed`,
  `bank_transaction.*` aus Abschnitt 12 sind noch nicht im Katalog; sie folgen mit den
  Freigabestufen G1 und G2 (Zahlungsereignisse bleiben bis dahin intern).
* Kontaktänderungen über Importe (Immoware24, objektakte, Kontakte-Import) erzeugen derzeit
  kein `contact.updated`; nur die API-Änderung löst das Ereignis aus.
* Das smart-einzug-Dossier (V1) bleibt offen; die Felder des Ereignisses sind allgemein und
  nicht auf smart-einzug zugeschnitten.
