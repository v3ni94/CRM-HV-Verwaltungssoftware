# M19-10 Folgevorgang statt Wiedereröffnung

Stand 28.09.2026. Betreiberentscheidung vom 28.09.2026, getroffen durch den Lead im Rahmen
des Mandats "alle Entscheidungen selbst abwägen". Regel `docs/rules/M19-10-folgevorgang.md`,
Annahme A-070.

## Umfang

- Migration `0219_ticket_follow_up`: `tenant_settings.ticket_reopen_window_days` (Standard 30,
  0 bis 3650), `ticket.follow_up_of_ticket_id` mit partiellem eindeutigem Index.
- `mhvp.tickets.follow_up`: Fristprüfung in Kalendertagen, aktuelles Ende des Vorgangs
  (Zusammenführung, Folgeticket), Vorbelegung, Hinweise, Verlauf, Benachrichtigung, Ereignis.
- `mhvp.communication.services.attach_to_ticket` und `create_ticket(follow_up_of=...)`;
  `mail.is_auto_submitted` (nur Kopfzeilen), `classification.auto_submitted`.
- API: `GET /tickets/{id}` mit `follow_up_of_ticket_id`, `follow_up_of`, `follow_ups`;
  `GET`/`PATCH /tenant/settings` mit `ticket_reopen_window_days` (OpenAPI und Client neu).
- CRM: `TicketFollowUpLinks` im Ticketdetail, Verlaufsarten in `TicketHistory`,
  `TicketReopenWindow` unter Einstellungen, Mandant; de/en.

## Tests

- Integration `tests/integration/test_m19_ticket_follow_up.py`, Unit
  `tests/unit/test_m19_ticket_follow_up.py`, bestehend `test_m19_ticket_mail_thread.py`.
- Vitest `TicketFollowUpLinks.test.tsx`, `TicketHistory.test.tsx`,
  `TicketReopenWindow.test.tsx`, BFF-Allowlist-Abdeckung.

## Offene Punkte

- Abwesenheitsnotizen ohne Kopfzeilenkennzeichnung werden nicht erkannt (bewusst, A-070).
- Keine Playwright-Abdeckung des Folgevorgangs.
