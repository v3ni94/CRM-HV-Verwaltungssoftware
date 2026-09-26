# mhvp.automation

Rule engine stage 1 (docs/MASTER-PROMPT.md section 15.2, milestone M9, task A38 of
`docs/plans/LUECKENLISTE-2026-09-26.md`). Rule document: `docs/rules/M9-02-automation.md`.

Rules never post, pay, approve or send anything (rules 0.1.6 and 0.1.7). Stage 1 offers
exactly three actions: create a ticket from a template, internal notification to users or
roles, set a ticket field (priority, team, category, assignee). Stage 2 (webhook, mail or
letter drafts, AI tasks, schedules) is A39 and not part of this package yet.

## Layout

| File | Content |
| --- | --- |
| `models.py` | `automation_rule` (tenant, name, active, trigger event type, condition tree, action list), `automation_run` (rule, event, time, status, error, executed actions; unique per rule and event), `automation_watermark` (position of the beat job per tenant). Migration 0100, tenant RLS on all tables. |
| `rules.py` | Pure logic: condition evaluation (`eq`, `ne`, `contains`, `gt`, `lt`, groups `and`/`or`, depth limit), field paths (`entity.category`, `payload.number`), `{placeholder}` rendering, loop guard marker. |
| `schemas.py` | Pydantic validation of rules and actions; unknown action types and non-listed ticket fields are rejected with 422. |
| `services.py` | Evaluation context per event (event fields plus the current ticket fields), action execution, dry run, `process_tenant` (beat loop). |
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
* A test run (`POST /rules/{id}/test`) evaluates the rule against a sample event and returns
  the action previews; nothing is written and no run is recorded.

## Permissions

* `tenant_settings:update`: create, change, activate, test.
* `tenant_settings:delete`: delete (docs/rules/M2-07.md, tenant_admin only).
* `tenant_settings:read` or `tickets:read`: list rules, read the run log.

## Tests

* `tests/unit/test_automation_rules.py`: evaluation, validation, placeholders, loop marker, schema.
* `tests/integration/test_m9_automation.py`: rule creates a ticket, sets fields, notifies a
  role, idempotency and loop guard, inactive rule, failing rule, permissions, tenant separation.

## CRM

`apps/web-crm/src/app/(app)/einstellungen/automatisierung` with
`components/settings/AutomationAdmin.tsx`: list, form (trigger, condition rows, actions), test
run, log.
