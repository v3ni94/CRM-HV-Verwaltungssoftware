# mhvp.workspace

Workspace functions of M9 (MASTER-PROMPT 3.5, 18): dashboard, global search, notifications,
calendar, saved list filters, bulk actions, operations metrics.

* `/api/v1/workspace/...` for any tenant member; entries are scoped to the calling user.
* `/api/v1/platform/ops/metrics` for platform administrators (JSON or `?format=prometheus`).
* `notify()` is the helper for other modules; it is idempotent per unread entity.
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
* `tasks.py`: Celery jobs: reminders (hourly), digest (07:00), compliance deadlines (20:00)

## Performance (Review 26.09.2026)

`GET /workspace/dashboard` computes all tiles in one statement (scalar subqueries). The
query budget of the start page, digest and search is asserted in
`tests/integration/test_perf_queries.py` (under 15 statements per request including the 8 of
authentication and tenant context). Measurements in `docs/reviews/2026-09-26-performance.md`.
