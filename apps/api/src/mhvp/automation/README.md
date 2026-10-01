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
| `models.py` | `automation_rule` (tenant, name, active, trigger kind, trigger event type, schedule, schedule watermark, condition tree, action list), `automation_run` (rule, event or schedule window, time, status, error, executed actions; unique per rule and event), `automation_watermark` (position of the beat job per tenant), `automation_webhook_delivery` (outbox and delivery log of the `webhook` action: run, action position, URL, payload, status, attempts, next attempt, last result; A82). Migrations 0100, 0110 and 0133, tenant RLS on all tables. |
| `rules.py` | Pure logic: condition evaluation (`eq`, `ne`, `contains`, `gt`, `lt`, groups `and`/`or`, depth limit), field paths (`entity.category`, `payload.number`), `{placeholder}` rendering, loop guard marker. |
| `schedule.py` | Pure logic of the schedule trigger: validation, `previous_due` (latest due moment in Europe/Berlin, returned in UTC), deterministic window id per rule and due moment. |
| `schemas.py` | Pydantic validation of rules and actions; unknown action types, non-listed ticket fields, AI tasks outside the allow list, webhooks without secret and ticket actions on a schedule are rejected with 422. |
| `services.py` | Evaluation context per event (event fields plus the current ticket fields), action execution (stage 1 and 2), webhook secret sealing (`seal_actions`, `carry_secrets`, `public_actions`), dry run, `process_schedules` and `process_tenant` (beat loop), webhook outbox (`deliver_due_webhooks`, `attempt_webhook_delivery`, `schedule_after_attempt`, `redeliver_webhook`; A82). |
| `tasks.py` | Celery task `mhvp.automation.process_events` (beat every 60 seconds, queue `default`). |
| `routers.py` | `/api/v1/automation/meta`, `/rules` (CRUD, `/activate`, `/test`), `/runs` (with `webhook_deliveries` per run), `/webhook-deliveries/{id}/redeliver`. |
| `learning.py` | Lern-Workflow (rule M9-11, `docs/rules/M9-11-lern-workflow.md`): pattern detection over the decision log (`trailing_streak`, `qualifies`, `next_status`, `sender_keys`), `observe` hook after manual decisions, `accept` (re-verifies the evidence, then creates an active `automation_rule`) and `reject`, API `/api/v1/automation/rule-proposals` (list, `/{id}/accept`, `/{id}/reject`). Table `automation_rule_proposal` (migration 0218, tenant RLS). |

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
  `mhvp.core.webhooks.pin_target` when the run enqueues the payload and again on every
  attempt (https only, no private addresses unless `webhook_allow_private_targets`, call
  pinned to the checked address).
* Webhook retries (A82, M9-08, `docs/rules/M9-08.md`): the run does not call the target
  itself. It checks target and secret, builds the payload and writes one
  `automation_webhook_delivery` row per webhook action (due at the beat moment).
  `process_tenant` then sends the due deliveries of the tenant (`deliver_due_webhooks`, rows
  locked with `SKIP LOCKED`, one httpx client per pass); every attempt signs the stored body
  afresh (`X-MHVP-Signature`, `X-MHVP-Rule`, `X-MHVP-Delivery`) with the secret of the rule
  action as stored now, plus a stable `Idempotency-Key` (the delivery id, set once). Failures
  follow `WEBHOOK_RETRY_SCHEDULE_SECONDS` (1, 5, 15, 60 minutes), at most
  `WEBHOOK_MAX_ATTEMPTS` (5); the delivery then goes `dead` and the rule owner (its last
  editor) gets one internal notification (`automation_webhook_dead`). Unsafe target or
  missing secret fail the run without a delivery. Every attempt records the response code,
  its duration (`last_duration_ms`) and, on the next due slot, the retry time.
  `POST /automation/webhook-deliveries/{id}/redeliver` (`tenant_settings:update`) resets a
  delivery to pending; a `dead` row gets a fresh attempt budget, a still-pending row keeps its
  count. The run log returns the deliveries as `webhook_deliveries`; the CRM run log renders
  them with a resend button (`AutomationAdmin.tsx`).

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
* `tests/integration/test_m9_automation_webhook_retry.py` and
  `tests/unit/test_automation_webhook_retry.py` (A82, M9-08): staged retry schedule (1, 5, 15,
  60 minutes), signed attempts with delivery id and stable idempotency key, no double
  delivery per pass, `dead` after 5 attempts with an owner notification, manual redelivery
  with a fresh attempt budget (permission, tenant separation), delivery log on the run.
* `tests/unit/test_automation_m9_08.py`: computed condition fields `entity.age_days` and
  `entity.due_in_days`, the `create_task` action schema.

## CRM

`apps/web-crm/src/app/(app)/einstellungen/automatisierung` with
`components/settings/AutomationAdmin.tsx`: list, structured form (trigger kind, event type or
schedule, condition rows with select fields, seven action editors, rule sentence preview,
JSON expert view), test run, log.

## Lern-Workflow (rule M9-11)

Repeated consistent manual decisions of the same sender (default 5, tenant setting
`rule_proposal_threshold`, 2 to 50) create a rule proposal; nothing becomes active without an
explicit accept by a member with `tenant_settings:update`.

* Evidence: the domain events `assignment_review.decided` (Ja, manual choice, Nein),
  `ticket.assigned` (reason `manuell`) and `ticket.topic_changed`, joined to the sender (mail
  `from_address`, ticket: first inbound mail). Events with the automation marker never count.
  The sender is compared as `message.from_address_norm` (stored generated column
  `lower(btrim(from_address))`, migration 0220) through the index
  `ix_message_tenant_from_address_norm` `(tenant_id, from_address_norm)`. A functional index on
  `lower(from_address)` is not usable for the runtime role: `message` forces RLS and `lower`
  is not leakproof, so the planner never takes it as an index condition ahead of the tenant
  policy. Domain patterns (`split_part`) remain a filter over the tenant's inbound mails.
* Patterns per entity type, field (`contact`, `property`, `unit`, `topic`,
  `assignee_user_id`; closed list) and sender address, plus sender domain for non shared
  domains with at least two addresses. A contradicting decision resets the streak and
  withdraws an open proposal; a rejected pattern returns only once the evidence doubled.
* Accept creates an ordinary rule: trigger `message.received`, condition
  `entity.from_address`/`entity.from_domain` (mail context, `build_context`), action
  `assign_record` (fills an empty assignment field through
  `assignment_review.apply_rule_assignment`, decision `rule`) or `set_ticket_field`
  (`topic`, `assignee_user_id`, on the ticket the mail opened, `entity.opens_ticket`).
* A member's decision always wins (fix 28.09.2026). A learned rule is a rule referenced by an
  accepted proposal (`automation_rule_proposal.rule_id`, no new column). Its
  `set_ticket_field` locks the ticket `FOR UPDATE` (like `PATCH /tickets/{id}`) and, like
  `assign_record`, fills only an empty field without a member's decision on it
  (`services.learned_field_kept`: `ticket.topic_changed`, or `ticket.assigned` with a user as
  actor, any reason). A classified topic and a template, mailbox, signature or history
  assignee stay, because a member who kept such a value leaves no event; no notification is
  sent and the run records the reason. Hand written admin rules keep the old overwrite
  semantics (backward compatibility, rule M9-02).
* One learned value per pattern group (fix 28.09.2026): accepting a proposal deactivates the
  active rules of earlier accepted proposals of the same entity type, field, scope and sender
  key (`learning.supersede_learned_rules`), logged as `automation_rule.updated` with reason
  `superseded`, the acceptor as actor and the superseding proposal and rule, listed in
  `rule_proposal.accepted` and returned as `superseded_rules` in the accept response (the list
  endpoint returns it empty). Hand written rules and other groups are not touched.
* A row set by `assign_record` lists the rule's value first and the check's proposals after it
  (`assignment_review._rule_candidates`, fix 28.09.2026, formerly empty), so a member confirms
  or corrects it directly with a Ja; a record outside the list needs Nein, then the manual
  choice (409 otherwise).
* A contact set by `assign_record` feeds the sure chain of the assignment review in the same
  action (rule A80-01 no. 6, 28.09.2026): exactly one active tenancy contract or ownership
  unit of the contact fills property and unit, only into empty fields without a member's
  decision (unit only below the chain's property), row `auto` with the chain's reason, event
  `assignment_review.auto` with `rule_id` and the automation marker. The rule depth stays 1;
  ambiguous contracts change nothing and an open question stays open.
* Errors: `MHVP-AUTO-0001` (proposal already decided), `MHVP-AUTO-0002` (evidence no longer
  holds on accept).
* Tests: `tests/unit/test_rule_proposal_learning.py`, `tests/integration/test_m9_rule_proposals.py`,
  `tests/integration/test_a80_rule_assignment_chain.py`, CRM `RuleProposals.test.tsx`.


## Process flows (rule M19-11, 29.09.2026)

`set_ticket_field` accepts the field `process_code` (a code of `mhvp.tickets.flows.PROCESS_CODES`
or a `$field` reference). The action loads the tenant's active template of that process and
calls `mhvp.tickets.flows.apply_flow` (category, checklist once, role, link status, deadline
proposals as type only). Without an active template the action fails with a rule error; a
rule never removes a process code and never changes the status.

## Welle 2 (P21)

- Testmodus: `automation_rule.test_mode`; im Beat-Lauf nur Run mit Status `dry_run`, keine Aktion.
- Jobzeitpläne je Mandant: `tenant_job_schedule`, `GET/PUT /automation/job-schedules`, Prüfung über `job_schedule.job_allowed`; seit AA15 rufen alle Mandantenjobs sie auf (siehe Abschnitt Welle 12, AA15).

### Aktionen Feld setzen und Dienstleister informieren (S15-06, Paket Q11)

- `set_field`: Notizfelder von Objekt, Kontakt, Vertrag aus der geschlossenen Liste `models.SETTABLE_FIELDS`; Ziel ist das Ereignisobjekt oder, bei Ticketereignissen, Objekt oder Kontakt des Tickets; Modus `append` (Standard) oder `replace`. Das Änderungsereignis trägt die Automatisierungsmarke.
- `notify_provider`: E-Mail-Entwurf (Status draft) an den Dienstleister, nie versendet; nur für Ticketereignisse (`TICKET_ONLY_ACTIONS`).

### Aktion set_record_field (T12, S15-06)

Geschlossene Liste `models.RECORD_FIELDS`: Auftrag (`status` nur `requested` oder `in_progress` entlang `ORDER_FLOW` mit `WorkOrderEvent`, `scheduled_at` mit Zeitzone, `assignee_user_id` als Zuständiger des Auftragstickets) und Dokument (`category_id` mit Aufbewahrungsprofil, verweigert bei Sperre oder Dauerunterlage, `property_id` als Verknüpfung). Ziel ist das Ereignisobjekt; Änderungsereignisse tragen die Automatisierungsmarke. Regel: `docs/rules/T12.md`.

## Welle 12 (AA15, GA12)

- GA12-01: `job_allowed` wird jetzt auch in `documents.process_inbox` (Schlüssel `documents-process-inbox`), im geplanten Abstimmungsbericht (`imports-reconciliation-report`, nur Auslöser `beat`, ein manueller Lauf bleibt möglich) und im Zahllauf (`payments-payment-run-preview`, neu im `JOB_CATALOG`, nur Vorschau) geprüft. `ops-backup-verify` ist plattformweit und nicht mehr im Katalog.
- GA12-06: `in_window` löst die Startzeit auf einen echten Zeitpunkt (erste Entsprechung, UTC) auf; am 25.10.2026 öffnet das Fenster einmal, nicht in beiden Stunden 02:00, am 29.03.2026 verschiebt sich eine Startzeit in der fehlenden Stunde auf den ersten gültigen Zeitpunkt. `lock_job` (Advisory Lock je Mandant und Job) serialisiert planmäßigen und manuellen Lauf; Mahnlauf und Zahllauf Vorschau legen je Mandant und Tag nur einen geplanten Lauf an. Tests: `tests/integration/test_ga12_jobs.py`.
- GA12-02, GA12-03: CRM `/einstellungen/automatisierung` zeigt unter den Regeln die Tabelle der Standardjobs (Schalter, Uhrzeit HH:MM, `JobSchedulesAdmin`), im Regelformular den Schalter Testmodus (nur Protokoll), in der Regelliste die Kennzeichnung und im Protokoll den Ergebnisfilter (Testlauf).

## Data sharing for webhooks (AD03, GA02-06)

A rule webhook for `contact.updated` is queued without `event.payload` and `entity` (flag
`personal_data_withheld`) when the contact has no valid `data_sharing` consent; the reason is
logged as event `automation.webhook_data_withheld`. Rule: docs/rules/AC06-einwilligungen.md.
