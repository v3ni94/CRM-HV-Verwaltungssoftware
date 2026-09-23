# mhvp.workspace

Workspace functions of M9 (MASTER-PROMPT 3.5, 18): dashboard, global search, notifications,
calendar, saved list filters, bulk actions, operations metrics.

* `/api/v1/workspace/...` for any tenant member; entries are scoped to the calling user.
* `/api/v1/platform/ops/metrics` for platform administrators (JSON or `?format=prometheus`).
* `notify()` is the helper for other modules; it is idempotent per unread entity.
* Job `mhvp.workspace.reminders` (hourly): maintenance reminders for the property manager.
* Money figures and money bulk actions are out of scope until the gates are released.
