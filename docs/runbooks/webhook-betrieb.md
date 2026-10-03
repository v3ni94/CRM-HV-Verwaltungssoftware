# Runbook: Webhook-Betrieb (ausgehende Webhooks)

Beleg: `apps/api/src/mhvp/core/webhooks.py`, `core/hmac_signature.py`, `platform/routers.py`
(ab Zeile 2168), ADR 0028. Vertrag für Empfänger: `docs/integrations/webhooks.md`.

## 1. Zustellung im Überblick

- Job `mhvp.core.webhooks.dispatch` jede Minute, Queue `io`. Signatur
  `X-MHVP-Signature: t=<unix>,v1=<hex>` über `"<t>." + roher Body` (`webhooks.py:158`).
- Wiederholungen nach 1 min, 5 min, 30 min, 2 h, 6 h, 24 h (`RETRY_SCHEDULE_SECONDS`,
  `webhooks.py:42`), danach Status `failed`. Antwort 2xx gilt als zugestellt (`:352`).
- Zeitfenster der Prüfung: 300 Sekunden (`hmac_signature.py:14`, `webhooks.py:162`).

## 2. Signaturschlüssel erneuern

1. `POST /api/v1/tenant/webhooks/{id}/rotate-secret` (Recht `webhooks:update`,
   `platform/routers.py:2278`). Das neue Geheimnis erscheint genau einmal in der Antwort.
2. Der alte Schlüssel gilt sofort nicht mehr; es gibt keine Übergangsfrist (Docstring
   `routers.py:2285`). Ablauf deshalb: Empfänger vorbereiten (neuen Schlüssel bereithalten),
   erneuern, Schlüssel beim Empfänger eintragen, Testzustellung senden.
3. Zustellungen im Fenster dazwischen scheitern an der Signaturprüfung des Empfängers und
   laufen in die Wiederholungen; nach dem Eintrag des neuen Schlüssels über die manuelle
   Neuzustellung nachholen.
4. Ereignis `webhook_subscription.secret_rotated` steht im Ereignisprotokoll.

## 3. Testzustellung

`POST /api/v1/tenant/webhooks/{id}/test` (202, `routers.py:2308`) legt das Ereignis
`webhook_subscription.test` an und reiht eine Zustellung ein. Ergebnis im Zustellprotokoll
(`GET .../{id}/deliveries`).

## 4. Fehlerzähler und automatische Abschaltung

- Jede endgültig fehlgeschlagene Zustellung erhöht `consecutive_failures` und setzt
  `last_failure_at`; Erfolg setzt den Zähler zurück (`webhooks.py:116`ff., `record_final_failure`
  ab `:405`).
- Mitglieder mit `webhooks:update` erhalten je Abonnement eine ungelesene Benachrichtigung
  (`webhook.delivery_failed`).
- Automatische Deaktivierung nur mit Mandantenschalter `webhook_auto_disable_after` (1 bis 100,
  Standard leer, also aus; `platform/models.py:531`, setzen über `PUT
  /api/v1/tenant/webhook-settings`, `routers.py:2363`). Offene Entscheidung AI07-02. Ein
  abgeschaltetes Abonnement trägt `disabled_reason = consecutive_failures`.

## 5. Störungsbehebung

| Symptom | Prüfung | Maßnahme |
| --- | --- | --- |
| Zustellungen bleiben `pending` | Worker der Queue `io` und Beat laufen? | Dienste prüfen (`skalierung.md`) |
| Empfänger meldet falsche Signatur | Schlüssel nach Erneuerung nicht aktualisiert, Body verändert (Signatur über rohen Body) | Schlüssel eintragen, Neuzustellung |
| Empfänger lehnt Zeitstempel ab | Uhr des Empfängers, Fenster 5 Minuten | Zeitsynchronisation prüfen |
| Ziel nicht angelegt | private oder interne Adresse (SSRF-Schutz, `routers.py:2168`) | öffentliche https-Adresse; privat nur in Entwicklung mit `MHVP_WEBHOOK_ALLOW_PRIVATE_TARGETS=true` |
| Abonnement inaktiv | `disabled_reason`, Schalter Abschaltung | Ursache beheben, Abonnement per PATCH aktivieren, ausgefallene Zustellungen neu zustellen |

Manuelle Neuzustellung: `POST /api/v1/tenant/webhook-deliveries/{id}/redeliver`
(`webhooks.py:454`), die Versuchshistorie bleibt erhalten.

## 6. Datensparsamkeit

Nutzdaten enthalten nur Kennungen und Feldnamen, keine Inhalte (siehe
`docs/integrations/webhooks.md`). Empfänger nie mit Klartextdaten Dritter erweitern ohne Prüfung
nach DSGVO.
