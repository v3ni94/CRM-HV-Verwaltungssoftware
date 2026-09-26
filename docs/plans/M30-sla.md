# M30: SLA, Notfallkette und Bereitschaft

Übernahme des SLA-/Notfall-/Bereitschaftsmoduls aus dem Immoware Hub
(`app/Modules/Sla`, `docs/mail/04-status-und-sla.md`) in die CRM-Plattform. Der Auftrag
bezeichnete dies als M21; die Nummer M21 ist im Repository bereits für das Mieter-/
Dienstleisterportal vergeben (`docs/plans/M21.md`), daher hier M30.

Prioritäten folgen den fünf Ticket-Prioritäten (`low` bis `immediate`) statt P0-P3; die
Zuordnung und die Startvorschläge für Reaktions- und Lösungsfristen stehen in
`mhvp.sla.service.DEFAULT_RULES` und sind von der Geschäftsführung zu bestätigen.

## Umfang

- Modelle (`apps/api/src/mhvp/sla/models.py`): `SlaRule`, `EscalationStep`, `SlaClock`,
  `SlaClockLog` (append-only), `OnCallSchedule`, `EmergencyAlert`, `WorkCalendar`.
- Geschäftszeitenberechnung (`business_time.py`): Arbeitsminuten unter Berücksichtigung von
  Wochentagen, Öffnungszeiten und Feiertagen, zeitzonensicher (Europe/Berlin, Sommerzeit).
- Uhrensteuerung (`service.py`): Regelauflösung, Start bei Ticketanlage, Pause/Fortsetzung,
  Erstantwort, Lösung, Ampel (grün/gelb/rot, 50 % Warnschwelle).
- Eskalation (`escalation.py`, `tasks.py`): Celery-Task `mhvp.sla.check_clocks` alle 5 Minuten,
  Eskalationsstufen aus `EscalationStep`, ersatzweise Bereitschaft (`OnCallSchedule`) bei
  `urgent`/`immediate`.
- Router `/api/v1/sla`: Regeln und Eskalationsstufen (Berechtigung `sla:update`), Uhren lesen
  (`sla:read`) und pausieren/fortsetzen (`sla:update`), Bereitschaft (`sla:update`), Alarme lesen
  und bestätigen (`sla:read`), Kalender lesen/ändern.
- Hooks: Ticketanlage startet die Uhr (`tickets.routers.create_ticket`); die Freigabe einer
  ausgehenden Mail zu einem Ticket setzt `first_response_at` (`communication.routers.approve`).
- Migration `0042_sla_module.py` (RLS auf allen sieben Tabellen).
- BFF-Allowlist (`apps/web-crm/src/app/api/bff/[...path]/route.ts`) für die SLA-Endpunkte.

## Nicht umgesetzt (offene Punkte)

- Stand 26.09.2026: umgesetzt in `apps/web-crm/src/app/(app)/einstellungen/sla/page.tsx`
  (Einstellungsseite, Tabs Regeln, Bereitschaft, Kalender) und
  `apps/web-crm/src/components/tickets/SlaBadge.tsx` (SLA-Badge im Ticket-Detail).
- Stand 26.09.2026: umgesetzt, i18n-Namespace `Sla` liegt in
  `apps/web-crm/messages/de.json` und `apps/web-crm/messages/en.json` (seit 1.17.5).
- Stand 26.09.2026: E-Mail-Versand der Eskalation ist seit 1.16.0 an den bestehenden
  Mailversand (`mhvp.communication.transport`, Gmail `send_raw` oder SMTP) angebunden;
  Details siehe `docs/plans/M35-sla-eskalation-kanaele.md`.
- Permission-Namensgebung: der Auftrag nennt `sla:manage`; da das Rechtemodell (`ACTIONS`) keine
  Aktion `manage` kennt, wird stattdessen `sla:update` (Regeln, Eskalation, Bereitschaft,
  Kalender) verwendet, analog zu den übrigen Modulen.

## Erweiterung M35

E-Mail- und SMS-Versand der Eskalation, Kanäle je Stufe und SMS-Gateway: siehe
`docs/plans/M35-sla-eskalation-kanaele.md` (dort auch die Beispiel-Vorlage für seven.io).
