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


## Hallo-Heidi-Anrufe (`call_assistant.py`, 26.09.2026)

Protokoll-Mails der KI-Telefonassistenz werden in `propose_contact_change` erkannt (Absendermuster
wie `hallo-heidi`, Kennwort `hallo heidi` im Betreff, im Text nur mit beschrifteter Rufnummer;
je Mandant über `GET/PUT /mail/call-assistant`, Spalte `tenant_settings.call_assistant`,
Migration 0131). Regex liefert Anrufernummer (E.164, Label `mobile` bei +4915/16/17, sonst
`other`), Anrufername, Objekt (Nummer oder Anschrift), Einheit (Whg., WE, Etage) und Anliegen;
der KI-Task `call_summary` ergänzt nur Lücken, die Nummer sieht er maskiert. Zuordnung: Objekt,
dann Personen mit laufendem Miet- oder Eigentumsvertrag dort per Namensabgleich, sonst Name im
Mandanten (nur eindeutig, sonst Kandidaten), sonst eindeutige Rufnummer. Ticket erhält
`contact_id`, `property_id`, `unit_id` (nur wenn leer), das Ergebnis steht als Ereignis
`call_summary` am Ticket. Ist die Nummer neu, entsteht ein Vorschlag (`proposed.kind = "call"`,
Feld `phone` mit `label`) mit Antwortentwurf (Playbook, sonst generischer Text).
`POST /tickets/{id}/proposals/{pid}/accept-and-reply` übernimmt die Nummer und legt den Entwurf
an die E-Mail-Adresse des Kontakts am Ticket an; versendet wird nur über den Freigabepfad des
Mailmoduls. Ohne E-Mail-Adresse des Kontakts oder ohne zugeordneten Kontakt antwortet der
Aufruf mit 422 und ändert nichts (kein Entwurf ohne Empfänger); `accept` ohne Antwort bleibt
möglich.

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

## Follow-up instead of reopening (`follow_up.py`, rule M19-10, migration 0219)

Operator decision of 28.09.2026, taken by the lead within the mandate "alle Entscheidungen
selbst abwägen". A new inbound mail for a finished ticket (`done`, `closed`, `rejected`),
matched by thread or `TNR#` in `mhvp.communication.services.attach_to_ticket`:

* The mail goes to the current end of the case (`current_ticket`, rows locked): a merged
  ticket leads to its target, a finished ticket with a follow-up to that follow-up.
* Closed at most `tenant_settings.ticket_reopen_window_days` calendar days ago (operator time
  zone, default 30, boundary included, `within_reopen_window`): reopened as before.
* Closed longer ago: stays closed; `create_ticket(..., follow_up_of=...)` creates a new mail
  ticket with `follow_up_of_ticket_id`, property, unit and contact of the predecessor as preset
  (`preset`), an internal comment and a history entry in both tickets (`follow_up_of`,
  `follow_up_created`), the notification `ticket.follow_up_created` to the predecessor's
  assignees and the domain event `ticket.follow_up_created`. At most one follow-up per ticket
  (partial unique index `uq_ticket_follow_up_of`).
* Automatic replies (`classification.auto_submitted`, headers only,
  `mhvp.communication.mail.is_auto_submitted`) are attached without reopening and never create
  a follow-up.
* `GET /tickets/{id}` returns `follow_up_of_ticket_id`, `follow_up_of` (id, number, title,
  status) and `follow_ups`; the CRM shows both links (`TicketFollowUpLinks`), the window is
  edited under Einstellungen, Mandant (`TicketReopenWindow`).

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `competences.py`: competence catalogue of members and ticket topics (operator 25.09.2026)
* `tnr.py`: ticket number in the subject `TNR#<number>`, matching of inbound mails only for known senders (rule M19-06)

## Appointment proposals in the CRM (A74)

`work_order_proposal_routers.py`: `GET /api/v1/work-orders/{id}/appointment-proposals`
(tickets:read) returns the proposals a provider made in the portal (A58) with status, the
confirmed appointment (`scheduled_at`, `confirmed_proposal_id`) and the open count. Read only;
proposing and accepting stay in `mhvp.portal.routers`. CRM page `/auftraege/{id}`.

## Erledigungsnotiz und Lernen aus Erledigungen (Betreiberauftrag 26.09.2026)

Beim Setzen auf `done`, `closed` oder `rejected` verlangt `transition_status` ein Feld
`resolution` (`ResolutionIn`): `kind` (Slug-Code) und `note` (Freitext, Pflicht bei
`sonstiges`). Eingebaute Arten (`ResolutionKind`, `resolution_kinds.BUILTIN_RESOLUTION_KINDS`):
`stammdaten_ergaenzt`, `handwerker_beauftragt`, `auskunft_erteilt`, `weitergeleitet`,
`kein_handlungsbedarf`, `abgelehnt`, `zahlung_geklaert`, `termin_vereinbart`,
`mangel_behoben`, `vertrag_geaendert`, `sonstiges`; `zusammengefuehrt` nur für Quelltickets
einer Zusammenführung. Je Mandant (Entscheidung M19-04, 26.09.2026) legt
`TenantSettings.resolution_kinds` (Migration 0136, Shape `{"disabled": [...], "custom":
[{"code", "label"}]}`, `ResolutionKindsConfig`) fest, welche eingebauten Arten abgeschaltet
sind (`sonstiges` und `zusammengefuehrt` nie) und welche eigenen Arten (höchstens 30) es gibt;
`GET /tickets/resolution-kinds` (`tickets:read`) liefert die Liste mit `active`, der
Abschlussdialog lädt sie. `assert_resolution_kind_allowed` weist eine nicht wirksame Art mit
422 ab (auch Bulk, dort je Zeile, und Merge). Ohne `resolution` antwortet die API mit 422,
auch beim Admin-Bypass (`skip_flow`); die Flussprüfung (409) kommt zuerst. Gespeichert werden
`ticket.resolution_kind`, `resolution_note`, `resolved_by` (Migration 0130) und die Notiz im
`TicketEvent` `status` (`data.resolution`); Wiedereröffnen leert die Felder. Abgeschlossene
Tickets behalten ihre Art nach dem Abschalten oder Entfernen; `resolution_text` zeigt eine
unbekannte Art mit ihrem Code.

* `PATCH /tickets/{id}` und `POST /tickets/bulk-status` nehmen `resolution` an, Bulk als
  gemeinsame Notiz aller Tickets. `POST /tickets/merge` nimmt eine optionale gemeinsame
  `resolution`; ohne sie erhalten die Quelltickets `zusammengefuehrt` mit Verweis auf das Ziel.
  In beiden Fällen entstehen je Quellticket das `TicketEvent` `status` mit `data.resolution`
  und `merge: true` sowie das Lernbeispiel, genau wie beim Einzelwechsel.
* Lernen: je Abschluss ein `AiExample` (Aufgabe `ticket_resolution`, kein KI-Lauf) mit Eingabe
  Betreff, Anliegen, Kategorie, Thema, erkannte Entitäten (Objekt, Einheit, Kontakt) und Ausgabe
  Art, Notiz, Status, zuletzt versendete Antwort. `learn_playbook_from_ticket` nimmt die
  Erledigung in den Prompt und als Schritt `Erledigung: ...` in das gelernte Playbook auf; ein
  bestehendes ähnliches Playbook erhält den Schritt ergänzt (höchstens 20 Schritte).
* Vorschläge (`communication/suggest.py`, `resolution_hint`): aus den letzten 200
  Erledigungsbeispielen werden die drei ähnlichsten (Schlagwortüberlappung mit Betreff und
  Anliegen) als "Bei ähnlichen Vorgängen wurde: ..." in Prompt und `suggestion.resolution_hint`
  übernommen.
* Wissensdatenbank: `GET /ai/examples` (`tenant_settings:read`, `task`, `page`, `per_page`,
  Antwort `data` plus `meta`), Playbooks über `GET /mail/playbooks` (jetzt mit
  `last_used_at`, gesetzt beim Anwenden). Seite `/einstellungen/wissen` mit den Reitern
  Playbooks (Deaktivieren mit `communication:update`, Bearbeiten unter `/mail/playbooks`) und
  Lernbeispiele (Filter nach Aufgabe).
* Frontend: Abschlussdialog `ResolutionDialog` im Ticket und in der Bulk-Aktion.
* Tests: `tests/integration/test_ticket_resolution.py`,
  `tests/unit/test_ticket_resolution_learning.py`, Vitest `ResolutionDialog.test.tsx` und
  `KnowledgeBase.test.tsx`.

## Fälligkeit `due_on` (Migration 0155)

Optionales Arbeitsdatum des Tickets (`due_on`, Datum), gesetzt im Formular oder per
`PATCH /tickets/{id}` (`null` löscht es). Der Kalenderleser `ticket_due`
(`mhvp.workspace.jobs`) erzeugt daraus den Termin mit Erinnerung und die Zeile der
Fristenliste; die SLA-Frist `sla_due_at` bleibt getrennt mit eigener Eskalation.

## Beiratsbeteiligung (M19-02, Migration 0203)

`board.py`: Vorlage eines Tickets oder Auftrags an den Verwaltungsbeirat einer GdWE
(`POST /tickets/{id}/board-submissions`, Mitglieder = Objektkontakte der Kategorie `board`,
Frist, Art `info`/`consent`), Rückmeldungen im Portal (`/portal/board/submissions`) und im CRM
(`/tickets/board/submissions/{id}/votes`), Abschluss und Empfehlungsregel je Mandant
(`/tickets/board/policy`). Alles steht als `ticket_event` im Verlauf. Das Votum ist
Information; Auftragsfreigabe und Zahlung bleiben bei der Verwaltung
(`docs/rules/M19-02-beiratsbeteiligung.md`).

## Prozessflows (`flows.py`, rule M19-11, migration 0235)

Operator request of 29.09.2026. Fixed catalogue of twelve process codes (`PROCESS_CODES`:
`kuendigung`, `vermietung`, `versicherungsschaden`, `reparaturanfrage`, `beschwerde`,
`buchhaltung`, `uebergabe`, `mieterhoehung`, `gericht`, `objektuebernahme`, `objektabgabe`,
`kaution`), each with German label, checklist (from the handbook pages where one exists),
responsible role code, required links (`LINK_KINDS`), linked deadline type codes (only codes
of `mhvp.workspace.jobs.DEADLINE_KINDS`, never a duration) and document kinds.

* `seed_process_templates(session, tenant_id)`: idempotent per tenant, creates one
  `TicketTemplate` per code (`process_code`, `responsible_role`, `required_links`,
  `deadline_type_codes`, `document_kinds`; partial unique index per tenant and code); a
  template edited by the tenant is kept. Called by `POST /tickets/process-catalogue/seed`
  (`tickets:approve` or `tenant_settings:update`) and by `python -m mhvp.platform.seed`.
  `GET /tickets/process-catalogue` lists the catalogue with the tenant's template ids.
* `apply_flow(session, ticket, tpl, actor_user_id, source)`: sets `process_code` and
  `category`, fills topic and team only when empty, appends the template checklist once
  (`instantiate_checklist`, existing keys and done marks stay), writes `ticket.flow`
  (`build_flow`: role, required links with status, deadline proposals `{type, status:
  proposed, due_on: null}`, document kinds, source) and one `TicketEvent` `flow_applied`.
  Idempotent: the same code again only refreshes the link status. Never a status change,
  never a posting, never a created deadline.
* Entry points: `POST /tickets/{id}/apply-process` (`tickets:update`),
  `POST /mail/messages/{id}/apply-process` (`communication:update` plus `tickets:update`;
  creates the ticket from the mail when missing, `tickets:create`, contact and property of
  the mail fill gaps), automation action `set_ticket_field` with field `process_code`.
  `GET /tickets?process_code=` filters, `_ticket_out` returns `process_code`, `process_label`
  and `flow`.
* Classification: `mhvp.communication.mail.process_category` (keywords, subject hits count
  twice, confidence 0.5, 0.75 or 0.9), stored as `classification.process` on ingest; the
  `classify_email` task (prompt v2) adds `process_code`, `process_confidence`,
  `process_reason`; `suggest.merge_suggestion` keeps only catalogue codes and falls back to
  the keywords otherwise.
* Tests: `tests/unit/test_m19_process_flows.py`, `tests/integration/test_m19_process_flows.py`;
  Vitest `TicketProcessBadge.test.tsx`, `TicketTemplatesAdmin.test.tsx`.

## Paket P11 (Lückenliste 30.09.2026)

* `order_routers.py`: `GET /work-orders`, `GET /work-orders/{id}`, Teams (`GET/PATCH/DELETE`), `GET /tickets/{id}/comments`, `DELETE /tickets/{id}/comments/{cid}` (archiviert, `removed_at`).
* Migration 0260: Ticketfelder `building_id`, `start_date`, `follow_up_date`, `external_comments`, `external_attachments`, Kommentararchiv. Durchsetzung der Sichtbarkeitsfelder im Portal offen (OPEN_QUESTIONS P11-02).
* Regel: `docs/rules/P11-tickets-w2.md`. Paperless im Ticket: `documents/paperless_search.py` `list_by_ticket` und `list_by_correspondent`.

* Paket Q05 (Welle 3): Formular für Gebäude, Beginn und Wiedervorlage (neu und bearbeiten), Team-Verwaltung (Einstellungen, Teams) und Sammelzuweisung in der Ticketliste (`POST /workspace/bulk`, `tickets.assign`). Regel: `docs/rules/Q05-crm-oberflaechen.md`.

- Paket R06 (Welle 4): `POST /tickets/bulk` (Status, gemeinsame Erledigungsnotiz) im Berichtsformat von `core/bulk.py` mit Savepoint je Ticket, neben `bulk-status`. Der Schritt Termin (`order_step`) schreibt den Kalendereintrag sofort über `workspace.jobs.sync_work_order_entry`. Regel: `docs/rules/R06-tickets-workspace-w4.md`.

* Paket U06 (Welle 6, S12-05): `POST /tickets/bulk` nimmt neben `status` (mit `resolution`) auch `assignee_user_id` (aktives Mitglied, sonst 422), `team_id` (unbekanntes Team 422) und `priority`, einzeln oder kombiniert, mindestens eine Änderung. Antwort im gemeinsamen Berichtsformat (`total`, `succeeded`, `failed`, `items` je Ticket mit Code und Detail), je Ticket ein Savepoint. Zuweisung läuft über `assign_ticket` (Historie, Benachrichtigung, Ereignis). Limit 10 Tickets ohne `tickets:approve` gilt unverändert. `POST /tickets/bulk-status` bleibt als Alias. Die CRM-Ticketliste nutzt nur noch `/tickets/bulk` und zeigt den Teilerfolgsbericht mit den fehlgeschlagenen Tickets.

* Paket W02 (Welle 8, V11-09): Änderungen von Priorität und Team schreiben Ticket-Ereignisse `priority_changed` und `team_changed` (Daten `from`, `to`, bei Team zusätzlich `from_name`, `to_name`; `bulk: true` bei der Sammelaktion), sowohl über `PATCH /tickets/{id}` als auch über `POST /tickets/bulk`. Unveränderte Werte erzeugen kein Ereignis. Status und Zuständiger hatten bereits Ereignisse (`status`, `assigned`, Grund `sammelaktion`). Die Ereignisse erscheinen im Ticketverlauf (`TicketHistory`) und zählen als Mitarbeiteraktivität (M19-09).

* Paket AA03 (Welle 12, GA04-01, GA04-08): `POST /tickets/{id}/comments` erzeugt das Ereignis `ticket.commented` (Ticket-ID, Kommentar-ID, internal, nie der Text). `ticket.category_id` verweist auf `ticket_template` (Migration 0305, Trigger setzt die ID aus dem Freitext `category`, Freitext bleibt Fallback).

* AA05 (GA04-07): `WorkOrder.approval_workflow_id` (optional UUID without FK, in `POST /work-orders` and the order output, migration 0307). The board vote stays the effective approval until AA05-01 is decided.
* AB05 (GA04-07): `PATCH /work-orders/{id}/approval-workflow` sets or clears the reference (`tickets:update`, 404 other tenant, 422 invalid UUID); list and detail output carry `approval_workflow_id`. No check against a workflow table (AA05-01). CRM: reference field on the order page.

## Contact data on work orders (AD03, GA02-06)

`order_sharing.order_contact_share` decides whether the resident's contact (ticket contact,
else initiator) goes to the provider: `consent_rules.data_sharing_decision` with contractual
necessity, tenant switch `consent_policy.data_sharing`. `POST /work-orders` returns
`contact_share` and logs `work_order.contact_data_shared` or `work_order.contact_data_withheld`;
the portal order list carries `resident_contact` (checked on every read, revocation applies
at once). Rule: docs/rules/AC06-einwilligungen.md.
