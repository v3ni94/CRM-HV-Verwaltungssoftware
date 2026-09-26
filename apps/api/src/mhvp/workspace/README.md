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
