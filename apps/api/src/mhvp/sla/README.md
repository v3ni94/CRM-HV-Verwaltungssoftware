# SLA, Notfallkette und Bereitschaft

Übernahme aus dem Immoware Hub (`app/Modules/Sla`, `docs/mail/04-status-und-sla.md`), siehe
`docs/plans/M30-sla.md` für den vollständigen Umfang und offene Punkte.

- `models.py`: Regeln, Eskalationsstufen, Uhr je Ticket, Uhrenprotokoll (append-only),
  Bereitschaftsplan, Notfallalarme, Geschäftszeitenkalender.
- `business_time.py`: Arbeitszeitberechnung (Wochentage, Öffnungszeiten, Feiertage,
  zeitzonensicher).
- `service.py`: Regelauflösung, Uhr starten/pausieren/fortsetzen, Erstantwort, Lösung, Ampel.
- `escalation.py` / `tasks.py`: Eskalationskette und Celery-Task `mhvp.sla.check_clocks`
  (alle 5 Minuten).
- `channels.py` (M35): Kanäle je Stufe (`SlaRule.channels_by_level`, Standard Stufe 1 intern,
  Stufe 2 intern und E-Mail, Stufe 3 intern, E-Mail und SMS), E-Mail als Systemmail über
  `communication.transport` ohne Freigabeprozess, SMS über das HTTP-Gateway `sla_sms_gateway`.
  Zustellung in `EmergencyAlert.delivered_at`, Fehler ohne Zugangsdaten in `delivery_error`.
- `whatsapp.py` / `whatsapp_webhook.py` (M21-05, Betreiberauftrag 25.09.2026): zusätzlicher
  Kanal `AlertChannel.WHATSAPP` über die Meta Cloud API (`sla_whatsapp_config` je Mandant,
  Standard aus), ausschließlich freigegebene Vorlagen (kein Freitext), SMS als abschaltbarer
  Rückfall (`sms_fallback`). Zustellstatus in `sla_whatsapp_delivery`, aktualisiert durch den
  Statuswebhook `/api/v1/whatsapp/webhook` (Verifizierung per `hub.verify_token`, Statusupdate
  per `X-Hub-Signature-256`). Regeln und Setup: `docs/rules/M21-05.md`,
  `docs/integrations/whatsapp.md`.
- `routers.py`: `/api/v1/sla/...` (Regeln, Uhren, Bereitschaft, Alarme, Kalender, SMS-Gateway,
  WhatsApp-Konfiguration).

Hooks in anderen Modulen: `tickets.routers.create_ticket` startet die Uhr,
`communication.routers.approve` setzt `first_response_at`, sobald die erste ausgehende Mail zu
einem Ticket freigegeben wird.
