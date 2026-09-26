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

## Proposals from the ticket mail (`proposals.py`, 26.09.2026)

A mail that announces a change of the sender's own master data creates an `AiProposal` on the
ticket (deterministic keywords and patterns, refined by the AI task
`contact_master_data_change`). Endpoints under `/tickets/{id}/proposals`: list, compute now,
`accept`, `correct` (corrected final JSON), `reject`, `reply-draft` (creates the prepared reply
as an outbound draft on the ticket; sending stays with the mail module's submit/approve path).
Accept and correct write the contact through the same path as `PUT /contacts/{id}` (history via
`contact.updated`); every decision stores an `AiExample` for the tenant. Bank fields are refused
and IBANs never proposed (docs/rules/M19-05.md).


## Antwortvorlagen (`reply_templates.py`, model `TicketReplyTemplate`, 26.09.2026)

Vorgefertigte Antworten je Mandant (Betreiberrückmeldung 26.09.2026): Name, Betreff und Text
mit Platzhaltern (`PLACEHOLDERS`: `{anrede}`, `{name}`, `{vorname}`, `{nachname}`, `{objekt}`,
`{einheit}`, `{ticketnummer}`, `{tickettitel}`, `{datum}`), Thema aus dem Kompetenzkatalog und
Standardanhänge als Dokumentverweise (`attachment_document_ids`, Dokumentenmodul). Migration
0082, RLS wie jede Mandantentabelle.

* `GET/POST /tickets/reply-templates`, `GET/PATCH/DELETE /tickets/reply-templates/{id}`,
  `GET /tickets/reply-templates/placeholders`: Lesen mit `tickets:read`, Schreiben mit
  `tickets:update`, `tenant_settings:update` oder Admin-Rolle. Unbekannte Platzhalter, unbekannte
  Themen und fehlende Anhänge werden abgewiesen (422 bzw. 404), Namen sind je Mandant eindeutig.
* `GET /tickets/{ticket_id}/reply-templates/{id}/preview`: Betreff und Text mit ausgefüllten
  Platzhaltern (Ticket, Kontakt, Objekt, Einheit), Empfänger (Absender der letzten eingehenden
  Mail des Tickets, sonst Haupt-E-Mail des Kontakts), Postfach des Tickets und Anhänge.
* `POST /tickets/{ticket_id}/reply` (`tickets:update` und `communication:update`): legt die
  ausgehende `Message` am Ticket an und reicht sie sofort zur Freigabe ein (`pending`,
  Ereignis `reply_submitted`). Ohne `confirm: true` wird nichts angelegt (409). Der Versand
  selbst bleibt dem bestehenden Antwortweg vorbehalten (`POST /mail/messages/{id}/approve`,
  Vier-Augen-Prinzip, Postfach des Tickets); die Anhänge werden dort beigefügt
  (`mhvp.communication.attachments`). Kein automatischer Versand, keine KI.
* Tests: `tests/unit/test_ticket_reply_templates.py`,
  `tests/integration/test_m19_ticket_reply_templates.py`.

## Status transitions (review 26.09.2026)

`status.py` is the single service for status changes (`transition_status`): allowed flow,
completion checks, `TicketEvent` `status`, `resolved_at`, SLA clock (stop on done/closed/rejected,
restart on reopening), domain event `ticket.status_changed` (payload `from`, `to`, `number`),
playbook learning and mail archiving. `PATCH /tickets/{id}` and `POST /tickets/bulk-status`
call it; new entry points (mail, portal) must too. `GET /tickets` paginates with `page` and
`page_size` (the body stays a list); the total is in the `X-Total-Count` header.

Mail archiving on a closing status is an event consumer: `transition_status` registers it with
`mhvp.core.db.tenancy.after_commit`, so `enqueue_archive_for_ticket` runs only once the status
change is committed (review M14). A rolled back request never archives.

`assign_ticket` (same module) is the single service for the primary assignee: it keeps
`TicketAssignee.primary` in sync (the previous primary row loses its mark, review N3), writes the
`TicketEvent` `assigned` with `from`, `to` and `reason`, notifies the assignee and emits the
domain event `ticket.assigned` (payload `from`, `to`, `reason`, `number`). Used by
`POST /tickets` (template default assignee, reason `Vorlage`), `PATCH /tickets/{id}` and
`POST /tickets/{id}/assignees` with `primary: true`.

## Ticket detail (review 26.09.2026, M5, M6, N4, N8)

* `GET /tickets/{id}` returns `internal_description` (6.6, patchable via `PATCH`), comments with
  `id`, `author_user_id`, `author_name`, `author_contact_id` and `document_ids`, events with
  `data`, `user_name` and `assignee_name`, and `mail_attachments` (attachments of the inbound
  mails with filename, mime type and size from one bundled `document` query; mailbox rights as
  in the mail view). The CRM detail page renders these without further requests.
* `contact_id`, `property_id`, `unit_id` (create and patch) and comment `document_ids` must exist
  in the tenant, otherwise 404.
* `GET /tickets?mine=true` matches primary and additional assignees, like `assignee_user_id`.
* `TicketReplyIn.subject` is folded to a single line (header safety, N1).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `competences.py`: competence catalogue of members and ticket topics (operator 25.09.2026)
* `tnr.py`: ticket number in the subject `TNR#<number>`, matching of inbound mails only for known senders (rule M19-06)

## Appointment proposals in the CRM (A74)

`work_order_proposal_routers.py`: `GET /api/v1/work-orders/{id}/appointment-proposals`
(tickets:read) returns the proposals a provider made in the portal (A58) with status, the
confirmed appointment (`scheduled_at`, `confirmed_proposal_id`) and the open count. Read only;
proposing and accepting stay in `mhvp.portal.routers`. CRM page `/auftraege/{id}`.
