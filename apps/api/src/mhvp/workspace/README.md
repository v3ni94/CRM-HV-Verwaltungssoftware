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

* `models.py`: notifications, calendar entries, saved filters, calendar event links (M9, M23-02)
* `routers.py`: `/api/v1/workspace` endpoints (dashboard, search, notifications, calendar, filters, digest, deadlines, job settings)
* `services.py`: idempotent `notify`, derived calendar dates, maintenance reminders
* `links.py`: routes of notification targets (CRM and portal), hint lookups for the calendar month and the property of a maintenance item
* `tasks.py`: Celery jobs: reminders (hourly), digest (07:00), compliance deadlines (20:00)

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
