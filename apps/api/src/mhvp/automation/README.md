# mhvp.automation

Rule engine (docs/MASTER-PROMPT.md section 15.2, milestone M9, tasks A38 and A39 of
`docs/plans/LUECKENLISTE-2026-09-26.md`). Rule document: `docs/rules/M9-02-automation.md`.

Rules never post, pay, approve or send mail (rules 0.1.6 and 0.1.7). Stage 1 offers three
actions: create a ticket from a template, internal notification to users or roles, set a
ticket field (priority, team, category, assignee). Stage 2 (A39) adds a signed outbound
`webhook` per rule, `mail_draft` (draft in the ticket mailbox, four eyes untouched),
`letter_draft` (letter on the letterhead stored as a document) and `ai_task` (queued gateway
run, proposal only), plus the trigger kind `schedule` (daily, weekly, monthly).

## Layout

| File | Content |
| --- | --- |
| `models.py` | `automation_rule` (tenant, name, active, trigger kind, trigger event type, schedule, schedule watermark, condition tree, action list), `automation_run` (rule, event or schedule window, time, status, error, executed actions; unique per rule and event), `automation_watermark` (position of the beat job per tenant). Migrations 0100 and 0110, tenant RLS on all tables. |
| `rules.py` | Pure logic: condition evaluation (`eq`, `ne`, `contains`, `gt`, `lt`, groups `and`/`or`, depth limit), field paths (`entity.category`, `payload.number`), `{placeholder}` rendering, loop guard marker. |
| `schedule.py` | Pure logic of the schedule trigger: validation, `previous_due` (latest due moment in Europe/Berlin, returned in UTC), deterministic window id per rule and due moment. |
| `schemas.py` | Pydantic validation of rules and actions; unknown action types, non-listed ticket fields, AI tasks outside the allow list, webhooks without secret and ticket actions on a schedule are rejected with 422. |
| `services.py` | Evaluation context per event (event fields plus the current ticket fields), action execution (stage 1 and 2), webhook secret sealing (`seal_actions`, `carry_secrets`, `public_actions`), dry run, `process_schedules` and `process_tenant` (beat loop). |
| `tasks.py` | Celery task `mhvp.automation.process_events` (beat every 60 seconds, queue `default`). |
| `routers.py` | `/api/v1/automation/meta`, `/rules` (CRUD, `/activate`, `/test`), `/runs`. |

## Processing

The event system (`mhvp.core.events.emit`) is untouched. The beat job reads new rows of
`domain_event` per active tenant since the tenant's watermark (`occurred_at, id`, with a lag
of `PROCESS_LAG` so late commits are not skipped) and runs every active rule whose trigger
equals the event type. The first run of a tenant only positions the watermark; older events
are history, not triggers.

* Idempotent: one run per rule and event (`uq_automation_run_event`); a second pass changes nothing.
* Isolated: every rule runs in a savepoint; a failing rule is recorded with status `failed`
  and error text, the other rules and the watermark continue.
* Depth 1: events written by rule actions carry `payload.automation = {rule_id, event_id,
  depth: 1}` and are skipped by the job, so a rule can never trigger itself or another rule
  through its own effects.
* A test run (`POST /rules/{id}/test`) evaluates the rule against a sample event (or, for a
  schedule rule, a due moment `due_at`) and returns the action previews; nothing is written,
  sent or queued and no run is recorded.
* Schedules: `process_schedules` runs before the event loop in the same beat task. A rule
  fires once per due moment (`last_scheduled_at` watermark plus the unique run id derived
  from rule and due moment); the first pass after activation only positions the watermark.
* Webhook secrets are encrypted with the tenant scope (`mhvp.core.crypto`) in the stored
  action JSON and are never returned by the API. Targets are checked with
  `mhvp.core.webhooks.check_target` at delivery (https only, no private addresses unless
  `webhook_allow_private_targets`). One attempt per run, no retry.

## Permissions

* `tenant_settings:update`: create, change, activate, test.
* `tenant_settings:delete`: delete (docs/rules/M2-07.md, tenant_admin only).
* `tenant_settings:read` or `tickets:read`: list rules, read the run log.

## Tests

* `tests/unit/test_automation_rules.py`: evaluation, validation, placeholders, loop marker, schema.
* `tests/unit/test_automation_schedule.py`: schedule validation, due moments (daily, weekly,
  monthly, DST), window ids, stage 2 action schemas and trigger rules.
* `tests/integration/test_m9_automation.py`: rule creates a ticket, sets fields, notifies a
  role, idempotency and loop guard, inactive rule, failing rule, permissions, tenant separation.
* `tests/integration/test_m9_automation_stage2.py`: signed webhook against a local receiver
  (signature verified, private target refused without the setting), mail draft, letter
  document with links, queued AI run, secret never exposed, patch keeps the secret, schedule
  rule fires once per window, changed schedule resets the watermark, tenant separation.

## CRM

`apps/web-crm/src/app/(app)/einstellungen/automatisierung` with
`components/settings/AutomationAdmin.tsx`: list, structured form (trigger kind, event type or
schedule, condition rows with select fields, seven action editors, rule sentence preview,
JSON expert view), test run, log.
