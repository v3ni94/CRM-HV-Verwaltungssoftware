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
* Verwalten: `GET /api/v1/tenant/webhooks` (Liste mit letzter Zustellung:
  `last_delivery_status`, `last_delivery_status_code`, `last_delivery_at`, sowie
  `created_at`), `GET .../webhooks/event-types` (Katalog mit Beschreibung), `PATCH .../{id}`
  (aktiv, Ereignistypen), `DELETE .../{id}` (löscht mit Zustellprotokoll, Recht
  `webhooks:delete`), `GET .../{id}/deliveries` (Protokoll, `page`, `page_size`),
  `POST /api/v1/tenant/webhook-deliveries/{id}/redeliver` (manuelle Neuzustellung). Rechte
  `webhooks:read|create|update|delete`.
* CRM: Pflegeseite unter Einstellungen, Webhooks (Karte mit `tenant_settings:update`),
  siehe `docs/handbuch/kommunikation.md`. Eine Testzustellung gibt es nicht; beim Anlegen
  entsteht `webhook_subscription.created` für bestehende Abonnements.
* Jeder Mandant sieht und erhält nur eigene Ereignisse (RLS, `domain_event.tenant_id`).

## Zustellung und Signatur

* Zustellung durch den Job `mhvp.core.webhooks.dispatch` (jede Minute, Queue `io`):
  `POST` mit `Content-Type: application/json`, Kopfzeilen `X-MHVP-Event` (Typ),
  `X-MHVP-Delivery` (Zustell-ID) und `X-MHVP-Signature: t=<unix>,v1=<hex>` mit
  `v1 = HMAC-SHA256(secret, "<t>." + Body)`. Empfänger prüfen die Signatur über den rohen
  Body und lehnen Zeitstempel ab, die älter als fünf Minuten sind.
* Antwort 2xx gilt als zugestellt. Wiederholung nach 1 min, 5 min, 30 min, 2 h, 6 h, 24 h,
  danach Status `failed` (sichtbar im Protokoll und in `GET /api/v1/platform/ops/metrics`).
* Ablauf je Zustellung (GAM-501, Welle 26): Der Job beansprucht jede fällige Zustellung in
  einer eigenen kurzen Transaktion (Versuchszähler plus eins, nächster Versuchszeitpunkt als
  Sperrfrist, Commit), ruft das Ziel ohne offene Datenbanktransaktion auf (höchstens
  15 Sekunden je Aufruf, Zeitüberschreitung zählt als Fehlversuch) und schreibt das Ergebnis
  in einer neuen Transaktion. Bricht der Worker zwischen Beanspruchung und Ergebnis ab, gilt
  der Versuch als fehlgeschlagen; nach dem letzten Versuch wird die Zustellung `failed`
  ("outcome unknown"). Ein Lauf endet nach seinem Zeitbudget (Soft-Limit der Klasse short
  minus 40 Sekunden, Standard 200 Sekunden), die Zeit wird gleichmäßig auf die Mandanten
  verteilt.
* Fehlerisolation (GAM-502): Ein Fehler bei einem Mandanten wird protokolliert und gezählt,
  die übrigen Mandanten werden weiter bedient.
* Neue Ereignisse (GAM-503): Je Abonnement wird ein Wasserzeichen (`watermark_occurred_at`)
  geführt; gelesen werden nur Ereignisse ab Wasserzeichen minus 15 Minuten (Überlappung für
  spät bestätigte Transaktionen), höchstens 1.000 je Lauf.
* Reihenfolge: Die Zustellreihenfolge ist nicht garantiert. Eine fehlgeschlagene ältere
  Zustellung kann nach jüngeren eintreffen (zum Beispiel `*.updated` vor `*.created`).
  Empfänger ordnen nach `occurred_at` im Body und entdoppeln über `Idempotency-Key`
  (gleich der Zustell-ID, bei jeder Wiederholung identisch).
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
| `contact.created` | `POST /contacts`, Immoware24-Kontaktlisten (`import.kontakte`) | `kind`; bei Importen zusätzlich `source` (Kontakt-ID in `entity_id`) |
| `contact.updated` | `PUT /contacts/{id}` mit tatsächlicher Änderung; Immoware24-Listenimporte bei Rollenänderung (`source` = `import.kontakte` oder `import.zuordnung`, nur bei Übernahme, nie im Testlauf) | `fields`: sortierte Liste der geänderten Feldnamen (`last_name`, `addresses`, `bank_accounts`, `roles`, ...), keine Werte |
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
* Die Importe erzeugen seit A87 `contact.created` und `contact.updated` wie der API-Pfad
  (Feldnamen ohne Werte, `source` im Payload: `import.kontakte`, `import.zuordnung`,
  `import.staging`, `import.objektakte`). Testläufe und Vorschauen erzeugen kein Ereignis, ein
  wiederholter Lauf über dieselben Daten ebenfalls nicht. Tests
  `tests/integration/test_a87_import_contact_events.py` und
  `tests/integration/test_a87_import_contact_events_apply.py`.
* Das smart-einzug-Dossier (V1) bleibt offen; die Felder des Ereignisses sind allgemein und
  nicht auf smart-einzug zugeschnitten.

Test für Eigentümerkontakte mit Zustellfehler und Neuzustellung (gleicher Idempotency-Key, signiert, ohne Namen, Adressen und IBAN): `apps/api/tests/integration/test_ga09_smart_einzug_contact_updated.py` (GA09-04).

## Verwaltung und Fehlschläge (AI07, GAH-206, GAH-207)

* `PATCH /tenant/webhooks/{id}` ändert zusätzlich `url` (gleiche Zielprüfung wie beim Anlegen) und `description`.
* `POST /tenant/webhooks/{id}/rotate-secret` erzeugt einen neuen Signaturschlüssel (einmalige Anzeige).
* `POST /tenant/webhooks/{id}/test` (202) plant das Ereignis `webhook_subscription.test` nur für dieses Abonnement ein; Abonnements mit `*` erhalten es ebenfalls.
* Je Abonnement: `consecutive_failures`, `last_failure_at`, `disabled_reason`. `GET/PUT /tenant/webhook-settings`: `auto_disable_after` (leer = nur melden), `objektakte_require_timestamp`.
