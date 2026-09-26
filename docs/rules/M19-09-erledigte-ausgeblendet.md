# M19-09 Erledigte Vorgänge standardmäßig ausgeblendet, Statuswechsel durch Administratoren ohne Zwischenschritte

| Field | Content |
| --- | --- |
| ID | `M19-09` |
| Title | Ticket- und Mailübersichten blenden Tickets in den Status done, closed und rejected ohne ausdrücklichen Statusfilter aus; Mandantenadministratoren dürfen jeden Status in jeden anderen setzen, protokolliert als admin_override |
| Scope | `GET /tickets` (`include_closed`, Standard false), `GET /mail/messages` (`include_closed`), `mhvp.tickets.routers._may_skip_flow`, `mhvp.tickets.status.transition_status` (`skip_flow`); Kontakt-, Objekt- und Einheitenseiten zeigen die volle Historie; alle Mandanten, kein Geldfluss |
| Source status | Fachliche Umsetzung (Betreiberauftrag 26.09.2026, Versionen 1.23.0 und 1.24.0). Produktschutz: Bypass des Flusses nur mit dem Recht `tickets:delete` (Regel M2-07, nur `tenant_admin` und Plattform-Admin), nie der Abschlussprüfungen |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m19_ticket_filters.py`, `test_m19_tickets.py`, Vitest `TicketFilters.test.tsx`, `MailWorkspace.test.tsx` (Umschalter Erledigte anzeigen) |
| Implementation | keine Migration; `mhvp.tickets.routers`, `mhvp.communication.routers`, Web `TicketFilters`, `MailWorkspace` (Parameter `erledigt=1` in der URL), `TicketForms.allowedStatuses` |
| Change reason | Betreiberauftrag 26.09.2026: Übersichten sollen nur offene Arbeit zeigen; Administratoren sollen Fehlstatus ohne Umweg korrigieren können |

## Regeln

- `GET /tickets` ohne `status` und ohne `merged_into` filtert `Ticket.status not in
  CLOSING_STATUSES`, wenn `include_closed=false` (Standard). Mit `status` gilt genau der
  Filter. Die Mailliste verhält sich gleich (`include_closed`, ohne `status` und ohne
  `ticket_id`): Mails, deren Ticket abgeschlossen ist, sind ausgeblendet.
- Listen je Kontakt, Objekt und Einheit (Reiter Tickets) rufen mit `include_closed=true` und
  zeigen die vollständige Historie.
- Flussregel `TICKET_FLOW` bleibt für alle Benutzer verbindlich. Wer `tickets:delete` hat,
  darf jeden Status in jeden anderen setzen; das Ereignis `status` trägt dann
  `data.admin_override=true`, wenn der Fluss den Wechsel verboten hätte. Die
  Abschlussprüfungen (Checkliste, Pflichtfelder, Erledigungsnotiz nach M19-07) gelten
  unverändert, auch für Administratoren. Das Frontend zeigt Administratoren alle Status, allen
  anderen nur die Folgestatus des Flusses.
- Ein Abschluss archiviert wie bisher die Ticketmails nach dem Commit (Postfacheinstellung
  `archive_on_ticket_done`); Voraussetzung ist die gespeicherte Gmail-Kennung, die der Abruf
  seit 1.23.0 speichert und für Eingangsmails der letzten 90 Tage nachträgt.
