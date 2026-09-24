# mhvp.tickets

Tickets, work orders, templates, SLA.

* Milestone: M19 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.6.
* Status: M19 implemented (tickets, templates, teams, SLA, work orders). See docs/plans/M19.md.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/tickets/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Ticket merge

`POST /api/v1/tickets/merge` (permission `tickets:update`, docs/integrations/mail-optimierung.md,
decision "Vorgang und Ticket" 25.09.2026) takes at least two ticket ids of the same tenant, none
already closed or merged, and creates a new ticket with a new number: title and links (contact,
property, unit, ...) from the oldest source, missing fields filled from the others, the highest
priority and the earliest SLA due date of the sources. Comments, events, attachments and mail
messages of the sources are reassigned (foreign key update, no copies), keeping chronological
order by `created_at`. Each source gets a `merged_into` event and the new ticket a `merged_from`
event per source; sources are closed and get `merged_into_ticket_id` (migration 0037). The
response is the new ticket plus `merged_ticket_ids`; `GET /tickets/{id}` reports
`merged_into_ticket_id`. Emits `ticket.merged`. Test: `test_m6_ticket_merge.py`.
