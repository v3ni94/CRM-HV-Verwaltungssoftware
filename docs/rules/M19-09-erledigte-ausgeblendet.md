# M19-09 Erledigte Vorgänge standardmäßig ausgeblendet, Ampel nach Reaktionszeit, Dringlichkeitssortierung, Statuswechsel durch Administratoren ohne Zwischenschritte

| Field | Content |
| --- | --- |
| ID | `M19-09` |
| Title | Ticket- und Mailübersichten blenden Tickets in den Status done, closed und rejected ohne ausdrücklichen Statusfilter aus; jede Ticketzeile trägt eine serverseitig abgeleitete Ampel nach der Zeit seit der letzten Reaktion unsererseits (gelb neu, orange ab 24 Stunden, rot ab 96 Stunden, grün erledigt) und die Liste ist standardmäßig nach Dringlichkeit sortiert; Mandantenadministratoren dürfen jeden Status in jeden anderen setzen, protokolliert als admin_override |
| Scope | `GET /tickets` (`include_closed`, Standard false; `sort`, Standard `urgency`; Felder `last_staff_activity_at`, `last_inbound_at`, `last_activity_at`, `attention`), `GET /workspace/dashboard/stats` (Feld `tickets` mit `attention`), `GET /mail/messages` (`include_closed`), `mhvp.tickets.activity`, `mhvp.tickets.routers._may_skip_flow`, `mhvp.tickets.status.transition_status` (`skip_flow`); Kontakt-, Objekt- und Einheitenseiten laden die volle Historie und blenden Erledigte im Reiter standardmäßig aus; alle Mandanten, kein Geldfluss |
| Source status | Fachliche Umsetzung (Betreiberauftrag 26.09.2026, Versionen 1.23.0, 1.24.0 und 1.28.0). Produktschutz: Schwellen der Ampel 24 Stunden (orange) und 96 Stunden (rot) ohne Reaktion unsererseits, keine Rechtsgrundlage, interner Standard; Bypass des Flusses nur mit dem Recht `tickets:delete` (Regel M2-07, nur `tenant_admin` und Plattform-Admin), nie der Abschlussprüfungen |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m19_ticket_filters.py`, `test_m19_tickets.py`, `test_m19_ticket_attention.py` (Zeitreise: Ereignisse, Kommentare, ein- und ausgehende Mails, Sortierung, Erledigte nie überfällig, Mandantentrennung), Vitest `TicketFilters.test.tsx`, `TicketsList.test.tsx`, `TicketsSection.test.tsx`, `MailWorkspace.test.tsx` |
| Implementation | keine Migration; `mhvp.tickets.activity` (Ausdrücke in derselben Abfrage, kein N+1), `mhvp.tickets.routers`, `mhvp.workspace.routers`, `mhvp.communication.routers`, Web `TicketAttention` (Farben, Legende, Text), `TicketsList`, `TicketsSection`, `TicketAnalytics`, `TicketFilters` (Parameter `erledigt=1` und `sort=created_desc` in der URL), `MailWorkspace`, `TicketForms.allowedStatuses` |
| Change reason | Betreiberauftrag 26.09.2026: Übersichten sollen nur offene Arbeit zeigen; Präzisierung 26.09.2026: Ampel nach Zeit ohne Reaktion unsererseits und Sortierung nach Dringlichkeit, damit liegengebliebene Vorgänge oben stehen; Administratoren sollen Fehlstatus ohne Umweg korrigieren können |

## Regeln

- `GET /tickets` ohne `status` und ohne `merged_into` filtert `Ticket.status not in
  CLOSING_STATUSES`, wenn `include_closed=false` (Standard). Mit `status` gilt genau der
  Filter. Die Mailliste verhält sich gleich (`include_closed`, ohne `status` und ohne
  `ticket_id`): Mails, deren Ticket abgeschlossen ist, sind ausgeblendet.
- Listen je Kontakt, Objekt und Einheit (Reiter Tickets) rufen mit `include_closed=true`
  (vollständige Historie, Zähler offen), blenden Erledigte im Reiter aber standardmäßig aus;
  der Umschalter Erledigte anzeigen erscheint nur, wenn erledigte Tickets vorhanden sind.

## Ampel nach Reaktionszeit (M19-09-A, seit 1.28.0)

- Reaktion unsererseits (`last_staff_activity_at`): jüngste Handlung eines Mitarbeiters am
  Ticket, nämlich Ticketereignis mit Benutzer (Statuswechsel, Zuweisung, Antwort gesendet,
  Freigabe; nicht das Anlageereignis `created`), Kommentar eines Benutzers (intern oder
  öffentlich), ausgehende Mail (`direction = out`) oder Änderung eines Arbeitsauftrags
  (`work_order.updated_at`). Eingehende Mails, Portalkommentare von Mietern oder Eigentümern
  und Erinnerungen von außen setzen die Uhr nicht zurück; sie werden als `last_inbound_at`
  (letzte Nachricht des Kunden) getrennt ausgegeben.
- Bezugszeit `last_activity_at` = `last_staff_activity_at`, sonst `created_at` (neues Ticket
  ohne Reaktion).
- `attention` (serverseitig, Zeitpunkt der Abfrage, UTC): `closed` bei done, closed,
  rejected (nie überfällig); `stale_96h` ab 96 Stunden ohne Reaktion; `stale_24h` ab 24
  Stunden; `new` bei Status new mit jüngerer Bezugszeit; sonst `none`. Schwellen sind
  Produktschutz (interner Standard), nicht konfigurierbar.
- Farben im CRM (linker Rand und Textmarke mit Vorlesetext, Legende über der Liste): grün
  erledigt, gelb neu, orange 24 Stunden, rot 96 Stunden. Der Text nennt die Dauer
  (Seit 30 Stunden ohne Reaktion, Seit 4 Tagen ohne Reaktion).
- Berechnung in derselben Abfrage wie die Liste (korrelierte Aggregate über `ticket_event`,
  `ticket_comment`, `message`, `work_order`), kein N+1; gilt für `GET /tickets` und die
  offenen Tickets der Startseite (`GET /workspace/dashboard/stats`).

## Sortierung (M19-09-B, seit 1.28.0)

- `sort=urgency` (Standard, auch bei Paginierung): Erledigte zuletzt, davor aufsteigend nach
  Bezugszeit, also am längsten ohne Reaktion zuerst (rot vor orange vor gelb, da die Stufen
  monoton in der Wartezeit sind), bei gleicher Bezugszeit höchste Nummer zuerst.
- `sort=created_desc` (Filterhaken Nach Eingang): neuestes Ticket zuerst.
- Ein anderer Wert wird mit 422 abgewiesen.
- Flussregel `TICKET_FLOW` bleibt für alle Benutzer verbindlich. Wer `tickets:delete` hat,
  darf jeden Status in jeden anderen setzen; das Ereignis `status` trägt dann
  `data.admin_override=true`, wenn der Fluss den Wechsel verboten hätte. Die
  Abschlussprüfungen (Checkliste, Pflichtfelder, Erledigungsnotiz nach M19-07) gelten
  unverändert, auch für Administratoren. Das Frontend zeigt Administratoren alle Status, allen
  anderen nur die Folgestatus des Flusses.
- Ein Abschluss archiviert wie bisher die Ticketmails nach dem Commit (Postfacheinstellung
  `archive_on_ticket_done`, fachlich Erledigt archiviert); Voraussetzung ist die gespeicherte
  Gmail-Kennung, die der Abruf seit 1.23.0 speichert und für Eingangsmails der letzten 90 Tage
  nachträgt.
- Erledigt meint fachlich immer done, closed und rejected (`CLOSING_STATUSES`). Seit dem
  26.09.2026 archiviert dieselbe Einstellung auch eine einzelne eingegangene Mail, die auf
  `done` gesetzt wird, und die letzte erledigte Mail eines Tickets ohne offenen Arbeitsauftrag
  schließt das Ticket automatisch (Regel M20-07, `services.complete_message`).
