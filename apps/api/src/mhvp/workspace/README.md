# mhvp.workspace

Workspace functions of M9 (MASTER-PROMPT 3.5, 18): dashboard, global search, notifications,
calendar, saved list filters, bulk actions, operations metrics.

* `/api/v1/workspace/...` for any tenant member; entries are scoped to the calling user.
* `/api/v1/platform/ops/metrics` for platform administrators or a monitoring API key with only
  `platform:metrics:read` (JSON or `?format=prometheus`); keys via `/platform/ops/metrics-keys`
  (M9-04a, see `mhvp/platform/README.md`).
* `notify()` is the helper for other modules; it is idempotent per unread entity.
* Every notification names its subject as a structured target (`target_type`, `target_id`;
  database columns `entity_type`, `entity_id`). The API derives `href` on read from
  `links.py`: CRM routes for `/workspace/notifications` (ticket, work_order, document,
  contract, property, message, approval, maintenance_item, appointment with
  `/kalender?termin=<id>&datum=...`, list pages for deadlines, digest, bank, proposals) and
  portal routes for `/portal/notifications` (ticket as Meldung, work_order, handover). An
  unknown target yields `href: null`, the entry is shown without a link. Routes are never
  stored (operator 26.09.2026).
* Job `mhvp.workspace.reminders` (hourly): maintenance reminders for the property manager.
* Money figures and money bulk actions are out of scope until the gates are released.
* Job `mhvp.workspace.digest` (07:00): daily overview per user as notification, optional
  system mail (tenant switch, default off); idempotent per user and day (`digest_run`).
* Job `mhvp.workspace.compliance_deadlines` (20:00): deadline list `compliance_deadline` from
  contracts, meters, bank consents and document retention with the tenant's lead time;
  one notification per row. Orientation only, no legal deadline calculation (rule M9-06).
* `GET /workspace/digest`, `GET /workspace/deadlines`, `GET/PUT /workspace/job-settings`.

## Calendar entries from date fields (P1 AP7, Ergänzung 4.10, migration 0151)

Every dated field of the master data becomes one calendar entry with a source: meter
calibration, energy certificate (building), contract end and termination, move in and
move out, maintenance, follow up of a contact note, owners' meeting and its resolution
deadline, ticket deadline, bank consent, document retention, notice date of service
contracts. The same job `mhvp.workspace.compliance_deadlines` (20:00) reads all of them
through the registry `jobs.calendar_sources()` (one reader per source) and writes

* the deadline list `compliance_deadline` (future dates only, `DEADLINE_KINDS`, one
  notification per row at its lead time) and
* generated rows in `calendar_entry` (`jobs.calendar_sync`): no owner, shared,
  `source_type`/`source_id`/`category` as idempotency key (partial unique index
  `uq_calendar_entry_generated`), `reminders` with the codes of B.30 (`CALENDAR_REMINDERS`,
  a maintenance item's `remind_before` wins), dates from `CALENDAR_PAST_DAYS` (365) back.
  A second run on the same data changes nothing; a moved date updates the entry, a removed
  date or deleted source row deletes it. Manual entries are never touched.

Reminders and recurrence (B.30, migration 0155): the same job runs `jobs.notify_reminders`
after the sync: one notification `calendar_reminder` per reminder code and entry (per
occurrence for recurring entries) when the code's offset in days is reached
(`REMINDER_OFFSET_DAYS`); sent codes are recorded in `calendar_entry.reminders_sent` as
`<code>@<date>`, so a rerun sends nothing twice. Generated entries notify the users with the
update permission of their kind with the target of the source row (`links.target_href`,
property hints from the entry), manual entries notify their owner with the calendar route.
The lead time notification of the deadline list stays separate. Manual entries accept
`reminders` and `recurrence` (`{frequency: weekly|monthly|yearly, interval, until}`);
occurrences are expanded on read by `jobs.expand_occurrences` for `GET /workspace/calendar`
(one item per occurrence, `recurrence` set) and `GET /workspace/deadlines` (kind
`appointment`, own and shared manual entries with a reminder), never persisted. Owners'
meetings resolve their legal entity to the property, so `href` is
`/weg/{property_id}/versammlung/{meeting_id}`. Tickets carry `due_on` (source `ticket_due`).

`GET /workspace/calendar` shows generated entries with the read permission of their kind
(`DEADLINE_PERMISSIONS`), `editable=false`, `category`, `reminders` and `href` (route to the
source, `links.target_href`); `GET /workspace/deadlines` carries the same `href`. The live
derived dates (`services.derived_dates`) remain for sources the job has not yet
materialised and are suppressed when a generated entry of the same source and date exists.
Readers of fields that other work packages add register only when the model carries the
field (`hasattr`), see `calendar_sources()`. The Google Calendar link (`calendar_event`,
M23-02) is unchanged; generated entries are not synced to Google.

## Deadline types, deadline entries, notice period and checklists (rule WS-01)

`deadlines.py` and `deadline_routers.py` (migration 0230, tables `deadline_type`,
`deadline_entry`, `property_checklist`, all with tenant RLS):

* `GET /workspace/deadline-types` (every member; seeds the system types Verwalterwechsel,
  Kautionsabrechnung and Mieterhöhung once per tenant, without duration), `POST` and
  `PATCH /workspace/deadline-types/{id}` (`tenant_settings:update`). A type has a trigger
  (`deadlines.TRIGGERS`), `duration_months` and `duration_days` entered by the operator (no
  default, no legal claim, UI label "zu verifizieren") and a responsible role code.
* `GET /workspace/deadline-entries` (`tickets:read`, filter `source_type`, `source_id`,
  `status`), `GET /workspace/deadline-entries/compute` (due date preview),
  `POST /workspace/deadline-entries` (`tickets:create`; from a ticket, contract, unit, property
  or rent increase case; due date computed from the type or entered, `MHVP-WS-0001` when
  neither exists; `warnings: ["ES-10"]` without a responsible person),
  `POST /workspace/deadline-entries/{id}/done` (`tickets:update`).
  `GET /workspace/assignable-users` lists names of active members for the responsible select.
* The entry is the source row: reader `_read_deadline_entries` mirrors open entries as kind
  `custom_deadline` into `compliance_deadline` and the generated calendar (reminders 14d, 1d);
  the create endpoint writes the mirror at once, done closes it. The lead time notification
  goes to the responsible person when set, otherwise to the holders of `tickets:update`.
* `GET /workspace/notice-period` (`contracts:read`): termination date plus entered months and
  days, optionally to the month end, as orientation with `verify=true`; with `contract_id` the
  stored end date and `contract_end_covers` for the hint in the termination form. The contract
  has no notice period field (A-076); nothing blocks the termination.
* `GET/POST /workspace/checklists` (`properties:read` / `properties:update`),
  `GET /workspace/checklists/templates`, `POST /workspace/checklists/{id}/items/{code}` with
  `{done}`: checklist `manager_change` from the handbook page Verwalterwechsel, one open list
  per property and kind (`MHVP-WS-0003`), every tick stores date, user id and display name;
  all steps done closes the list.
* Tests: `tests/unit/test_deadline_math.py`, `tests/integration/test_deadline_types.py`.

## Job `ops.backup_verify` (A67)

`mhvp.workspace.backup_verify`: täglich 02:00 (Beat `ops-backup-verify`, Queue `io`) läuft
`scripts/backup-verify.sh`, wenn `MHVP_BACKUP_VERIFY_ENABLED=true` und das Skript vorhanden ist;
sonst wird `not_configured` protokolliert. Das Ergebnis (Status, Beginn, Dauer, geprüfte Datei,
Exit-Code, Fehler) liegt in Redis (`mhvp:ops:backup_verify:last`, sieben Tage) und erscheint in
`GET /api/v1/platform/ops/metrics` unter `jobs.backup_verify` sowie als Gauges
`mhvp_backup_verify_*`; Alarme `backup_verify_failed` und `backup_verify_stale` (älter als 36 h
oder kein Lauf). Tests: `tests/integration/test_ops_jobs.py`.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `models.py`: notifications, calendar entries (manual and generated, P1 AP7), saved filters, calendar event links (M9, M23-02)
* `routers.py`: `/api/v1/workspace` endpoints (dashboard, search, notifications, calendar, filters, digest, deadlines, job settings)
* `services.py`: idempotent `notify`, derived calendar dates, maintenance reminders
* `links.py`: routes of notification targets (CRM and portal), hint lookups for the calendar month and the property of a maintenance item
* `tasks.py`: Celery jobs: reminders (hourly), digest (07:00), compliance deadlines and generated calendar entries (20:00)
* `jobs.py`: source reader registry, deadline list, generated calendar entries, digest

## Global search (P1 AP6, Ergänzung 5 and 7.4)

`GET /workspace/search?q=` returns hits of the types contact, property, building, unit,
contract, document, ticket and posting. Each type is guarded by its own read permission
(`contacts:read`, `properties:read` for property, building and unit, `contracts:read`,
`documents:read`, `tickets:read`, `accounting:read`); postings additionally respect the legal
entity scope of the principal. Property, unit and building hits come from one `UNION ALL`
statement so the query budget of `test_perf_queries.py` holds. `parent_id` carries the
property of a building and the ledger of a posting; the web app builds the route in
`apps/web-crm/src/lib/entity-links.ts`. Tests: `tests/integration/test_workspace_search_p1.py`.

## Performance (Review 26.09.2026)

`GET /workspace/dashboard` computes all tiles in one statement (scalar subqueries). The
query budget of the start page, digest and search is asserted in
`tests/integration/test_perf_queries.py` (under 15 statements per request including the 8 of
authentication and tenant context). Measurements in `docs/reviews/2026-09-26-performance.md`.

## Ticket analytics (`GET /workspace/ticket-analytics`, operator 26.09.2026)

Throughput and effectiveness of inbound and outbound tickets and mails; module
`mhvp.workspace.ticket_analytics`, CRM page `/auswertung/tickets`, permission `tickets:read`
(the user filter needs the same right as `/dashboard/stats`). Orientation figures only.

Parameters: `range` (`day`, `week`, `month`, `quarter`, `year`, `custom` with `from`/`to`,
at most 400 days), `bucket` (`auto`: hour for day, day for week and month, week for quarter,
month for year; or explicit `hour`, `day`, `week`, `month`), `user_id`, `mailbox_id`,
`mailbox_kind` (`all`, `personal` = mailboxes bound to users via `MailboxUser`, `default` =
`Mailbox.is_default`). Buckets are Europe/Berlin wall time, keys ISO 8601 with offset; the
window is aligned to whole buckets, the last bucket may be shorter (`minutes`).

Per bucket and in `totals`: `tickets_created` (by `created_at`), `tickets_closed` (status
transitions into `CLOSING_STATUSES` from a non closing status, by transition time),
`tickets_reopened` (the reverse), `backlog_end` (open at bucket end = backlog before the window
plus created minus closed plus reopened), `inbound` (mails `in` by `received_at`), `outbound`
(mails `out` with status `sent` by `sent_at`), `replies_per_ticket` (sent mails with a ticket
divided by tickets created), `first_response_median_minutes` and `_p90_` (first sent mail or
first staff comment after creation, cohort by creation, `percentile_cont` interpolation),
`time_to_close_median_minutes`, `throughput_per_minute` (tickets closed divided by the minutes
of the bucket, two decimals) and `throughput_per_hour`. Tables `staff` (closed by actor,
created by `created_by`, replies sent by `Message.created_by`, median first response by
assignee, currently open assigned), `mailboxes` (inbound, outbound, tickets whose first
inbound mail came from the mailbox, share of inbound) and `by_kind` (personal, default,
other). `all_mailboxes` lists the tenant's mailboxes for the filter without the admin only
mailbox endpoint. Six statements per request (tickets of the window with correlated
subqueries, status transitions, grouped mails, backlog before the window, open per assignee,
mailboxes); no N+1. Tests: `tests/integration/test_workspace_ticket_analytics.py`.

## Alarme, Filter, Sammelaktionen (P15, 30.09.2026)

* `ALERTING` enthält zusätzlich `bank_sync_runs_failed_24h`, `bank_connections_error`,
  `payment_orders_rejected_24h` und `dunning_cases_blocked` (Regel `M9-01`).
* Gespeicherte Filter: Ressource `tickets` zusätzlich zulässig; die Komponente `SavedFilters`
  steht in Kontakten, Objekten, Verträgen, Tickets und Dokumenten.
* `POST /workspace/bulk`: Aktion `tickets.assign` (Bearbeiter für mehrere Tickets über
  `tickets.status.assign_ticket`, Recht `tickets:update`, alles oder nichts, Bearbeiter muss
  aktives Mitglied sein).

### Gespeicherte Filter für Bank und Rechnungen (M9-03)

`FILTER_RESOURCES` enthält zusätzlich `bank_transactions` und `invoices`. Die Komponente `SavedFilters` hat einen optionalen Rückruf `onApply` für Listen, die Filter im Zustand halten (Bankliste). Die Rechnungsliste nimmt die Filter als Abfrageparameter `q`, `review`, `posting`.

### Welle 3, Paket Q11 (30.09.2026)

- M19-06: `jobs._read_work_order_appointments` (Kategorie `work_order_appointment`, intern, ohne Einladung).
- M23-04: `notification_prefs.py` (Katalog, `resolve`, `send_pending_mails`), Tabelle `notification_preference`, Spalten `notification.email_pending` und `email_sent_at` (Migration 0280). `services.notify` prüft die Einstellung vor dem Schreiben. `GET/PUT /workspace/notification-preferences`, Beat `workspace-notification-mails` alle 5 Minuten. Pflichtarten siehe `MANDATORY_KINDS`.
- M9-04: `POST /workspace/bulk` mit `documents.set_category`, `documents.link_property`, `deadline_entries.done`; UI `DocumentBulkBar` (Dokumentliste) und Sammelauswahl im `DeadlineEntriesPanel`.
- Q04 (M3-05): `GET /workspace/search` findet Verträge zusätzlich über den Namen eines Parteimitglieds, Einheiten über die Objektstraße und Dokumente über Titel und Dateiname; zusammengeführte Kontakte (M3-03) sind ausgeblendet, der alte Name führt zum Ziel.
- Paket R06 (Welle 4): `POST /workspace/notifications/mute` (alle nicht verpflichtenden Arten stummschalten oder aufheben, eigene Standardzeile `*`), `jobs.sync_work_order_entry` (Auftragstermin sofort im Kalender, Tagesjob bleibt Auffangnetz), `maintenance.done` in `POST /workspace/bulk` folgt dem Intervall wie die Einzelaktion (Feld `done_on`). UI: `NotificationBell`, `MaintenancePanel`.
- Paket T08 (Welle 5): M23-04 Zustellung der Mail je Art (`notification_preference.email_mode` immediate oder daily, Migration 0293), `send_pending_mails` fasst je Benutzer und Lauf zu einer Sammelmail zusammen, Beat `workspace-notification-mails-daily` 07:30 für Einstellung täglich. Die Stummschaltung wirkt beim Anlegen der Benachrichtigung (`notify`).

## Inhaltsmodus der Benachrichtigungsmails (U15-04)

Der Mandantenschalter `notification_mail_content` (`voll` Standard, `hinweis`) liegt im JSON `tenant_settings.sources`. `send_pending_mails` liest ihn je Lauf (`mail_content_mode`); im Modus `hinweis` enthält die Sammelmail nur Anzahl und CRM-Link, keinen Titel und keinen Text. Regel `docs/rules/U15-04.md`.

## Skalierungsmessung der Partitionierungsauslöser (AE36, Welle 16, AC09-01)

* `scale.py`: Kennzahlen zu den Auslösern aus ADR 0021. `ListLatencyMiddleware` (reine ASGI-Middleware in `main.py`) legt für die Journalliste und die Bankumsatzliste nur Zeitpunkt und Dauer in Redis ab (`mhvp:ops:latency:<Liste>`, höchstens 2.000 Stichproben, 14 Tage Lebensdauer); `table_stats` liest Zeilen und Größe (exakt bis 1.000.000 Zeilen, darüber `pg_class`); `evaluate` ist eine reine Funktion (Auslöser nach Schwellen und Verlauf); `snapshot_once` speichert die Wochenmessung und alarmiert neue Auslöser (Plattformaudit `scale.trigger_reached`, Glocke an Plattformadministratoren, Art `platform_scale_trigger`, Ziel `platform_scale` auf `/plattform/betrieb`); Celery-Aufgabe `mhvp.ops.scale_snapshot`, Beat `ops-scale-snapshot` (montags 03:10).
* `scale_routers.py`: `GET /platform/ops/scale`, `PATCH /platform/ops/scale/settings`, `POST /platform/ops/scale/snapshot` (nur Plattformadministratoren, Änderungen im Plattformaudit).
* `ops.py`: `/platform/ops/metrics` ergänzt um Gauges `<Tabelle>_rows`, `<Tabelle>_bytes`, `<Liste>_p95_ms`, `tenants_productive`, `tenants_demo` und die Alarme `scale_trigger_partition_review`, `scale_trigger_measure_again`; die Summen und `tenants_active` lassen Demo-Mandanten weg.
* Regel `docs/rules/AE36-SCALE.md`, Runbook `docs/runbooks/leistungsmessung.md` (Abschnitt AE36). Tests: `tests/unit/test_ae36_scale.py`, `tests/integration/test_ae36_demo_scale.py`.

GAI-110 (Welle 21): `FILTER_RESOURCES` enthält zusätzlich `journal`, `open_items`, `dunning_cases`, `hoa_properties` und `work_orders`. Angebunden sind das Journal (Parameter `property`) und die Auftragsliste (`status`); Offene Posten, Mahnfälle und WEG Listen haben noch keine Abfrageparameter in der Oberfläche, die Ressourcen stehen für die Anbindung bereit.

AL05 (Welle 23, GAI-110 Rest): `FILTER_RESOURCES` enthält zusätzlich `payment_runs` (gespeicherte Zahllauf-Vorschauen, Parameter `as_of`, `trigger`) und `mailbox` (Postfach, Parameter `tab`, `status`, `postfach`, `q`, `abgleich`). `GET /accounting/payment-runs/previews` nimmt zusätzlich `as_of` (Stichtag, exakt) und `trigger` (`manual`, `schedule`, `failed`) an; unbekannte Parameter bleiben 422. Tests: `tests/integration/test_al05_preview_filters.py`.
