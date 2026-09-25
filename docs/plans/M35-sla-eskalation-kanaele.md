# M35: Eskalation an die Bereitschaft per E-Mail und SMS

Erweiterung des SLA-Moduls (`apps/api/src/mhvp/sla/`, Grundlage `docs/plans/M30-sla.md`).
Hinweis: Die Kennung M35 wird parallel für die objektakte-Übernahme
(`docs/plans/M35-objektakte-uebernahme.md`) verwendet; die offenen Punkte dieses Plans tragen
deshalb den Zusatz SLA.

## Umfang

- Kanäle je Stufe: `SlaRule.channels_by_level` (JSONB, optional). Standard ohne Eintrag:
  Stufe 1 intern, Stufe 2 intern und E-Mail, Stufe 3 und höher intern, E-Mail und SMS.
  Stufe 0 (Bereitschaftsalarm bei Notfall und Dringend ohne Eskalationsstufen) nutzt intern,
  E-Mail und SMS. Das bisherige Feld `EscalationStep.channel` bleibt erhalten, steuert den
  Versand aber nicht mehr.
- E-Mail: Systemmail ohne Vier-Augen-Freigabe über `mhvp.communication.transport` (derselbe
  Transport wie der Versand nach Freigabe: Gmail `send_raw` oder SMTP) aus dem Standardpostfach
  des Mandanten. Betreff `SLA-Eskalation Stufe {level}: Ticket #{nummer} {titel}`, Text mit
  Objekt, Priorität, Fälligkeit (Europe/Berlin) und Link `MHVP_WEB_CRM_URL/tickets/{id}`.
- SMS: anbieterneutrales HTTP-Gateway je Mandant (`sla_sms_gateway`, RLS), Versand per httpx
  mit 10 s Timeout, nur bei `enabled`. Empfänger sind die Benutzer der Stufe und die aktuelle
  Bereitschaft; Nummer aus `OnCallSchedule.phone`, sonst `Membership.mobile_phone`.
- Zustellung: `EmergencyAlert.delivered_at`, Fehler ohne Zugangsdaten in `delivery_error`;
  ein Fehler bricht die Eskalation nicht ab.
- Endpunkte: `GET/PUT /api/v1/sla/sms-gateway`, `POST /api/v1/sla/sms-gateway/test`,
  `PUT /api/v1/tenant/members/{id}/mobile-phone`.
- Migration `0055_sla_escalation_channels`.

## Beispiel-Vorlage seven.io (ohne Zugangsdaten)

Vor Einsatz gegen die aktuelle Anbieterdokumentation prüfen.

- URL: `https://gateway.seven.io/api/sms`, Methode `POST`
- Auth-Header-Name: `X-Api-Key`, Wert: API-Schlüssel des Betreibers (nur im CRM hinterlegen)
- Absender: bis 11 alphanumerische Zeichen, zum Beispiel `HVMueller`
- Vorlage:

```json
{"to": "{to}", "text": "{text}", "from": "{sender}"}
```

## Tests

- `apps/api/tests/unit/test_sla_escalation_channels.py`: Kanalauswahl je Stufe,
  Template-Rendering, Fehler ohne Gateway und Postfach, E-Mail-Text, httpx gemockt.
- `apps/api/tests/integration/test_m21_sla.py`: Gateway-Konfiguration ohne Secret in der
  Antwort, Test-SMS ohne aktives Gateway, Berechtigung.

## Offen

- M35-08: Wahl des SMS-Anbieters und Zugangsdaten durch den Betreiber offen.
