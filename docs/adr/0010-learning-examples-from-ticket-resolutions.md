# ADR 0010: Learning examples from ticket resolutions (ai_example per tenant, local matching)

- Status: Proposed, operator decision required (data protection, M7-04); technical part (switch, deletion) implemented 26.09.2026
- Date: 2026-09-26

## Context

Version 1.24.0 (operator order of 26.09.2026, merged in 1.25.0 as migration 0130) stores one
`AiExample` row per ticket closure (task `ticket_resolution`) and uses these rows to propose
resolutions for similar new mails ("Bei ähnlichen Vorgängen wurde ...", rule M19-07). Until
then `ai_example` existed only structurally: `docs/OPEN_QUESTIONS.md` M7-04 recorded that no
examples are stored until data minimisation or pseudonymisation is decided, because confirmed
results contain personal data and would go to the provider as few shot examples. The new code
was written without an ADR and changes that state, so the decision is recorded here and
presented to the operator (section 0.3).

## Decision

1. **Storage per tenant, no provider transfer of the rows.** Examples live in the tenant table
   `ai_example` (RLS, ADR 0002) with `created_by` set to the closing user. Input: ticket title
   (300 characters), public description (1000), category, topic, IDs of property, unit and
   contact, ticket id. Output: resolution kind, note, status and the last sent reply (2000
   characters). The rows are never sent to the AI provider as examples.
2. **Local matching only.** `mhvp.communication.suggest.resolution_hint` compares keyword
   overlap of title and description with the last 200 examples of the tenant in process and
   returns at most three distinct resolution texts. This runs without any provider call and
   without embeddings (M7-03 stays open).
3. **What reaches the provider.** Only the hint text built from resolution kind and note
   ("Bei ähnlichen Vorgängen wurde: Stammdaten ergänzt: ...") is added to the
   `classify_email` prompt, and only when a provider is released (M7-01, M12-01). The note is
   free text, so it can carry personal data; the identifier masking of
   `mhvp.objektakte.masking` is not applied to it.
4. **Playbook learning.** `learn_playbook_from_ticket` adds the resolution as step
   `Erledigung: ...` to the learned playbook; playbooks were already a learned artefact
   (M20, 25.09.2026) and keep their existing review path.
5. **Visibility.** Page `/einstellungen/wissen` lists playbooks (with hit count, last use,
   deactivate) and examples (filter by task) for `tenant_settings:read`; there is no delete or
   edit of examples in the UI and no retention job.
6. **Feature flag (addendum 26.09.2026).** `tenant_settings.ai_learning_examples_enabled`
   (migration 0134, default false, `PATCH /tenant/settings`, CRM page Einstellungen,
   Mandant) gates the storage per tenant; `record_resolution_example` stores nothing while it
   is off (rule 0.1.3, section 0.3). Switching it off stops new examples and leaves existing
   rows. Every change is logged as `tenant_settings.updated`. Until the addendum the storage
   was coupled to the closing status without a switch.
7. **Deletion with the source (addendum 26.09.2026).** `mhvp.ai.examples` removes the
   `ticket_resolution` examples of a deleted contact (`DELETE /contacts/{id}`, match on
   `features.entitaeten.contact_id`) in the same transaction; `delete_examples_for_ticket`
   is available for a ticket deletion path (none exists today, tickets are merged, not
   deleted). Hard delete: the rows are derived data, the ticket event log keeps the
   resolution. Addendum 27.09.2026: the soft delete of a contact through an import undo
   (`mhvp.ai.imports._remove`) calls the same deletion in its transaction.
8. **Retention (addendum 27.09.2026, operator decision "Vollständig speichern mit
   Mandantenschalter").** The examples are stored in full (no minimisation) while the tenant
   switch is on, and `tenant_settings.ai_learning_examples_retention_months` (migration 0154,
   default 24, 1 to 120, `PATCH /tenant/settings`, CRM page Einstellungen, Mandant) limits
   how long they stay: the daily job `mhvp.ai.examples_retention` (beat 03:45) deletes every
   example of the tenant created before now minus the retention months (calendar months) and
   journals each tenant run as the event `ai_examples.retention` with the counts
   (before, deleted, remaining, cut-off, months). Switching the storage off does not delete;
   the retention run does. Rule 0.1.7 does not apply (derived data). The data protection
   review of the stored content (personal data in subject, note and answer excerpt) remains
   the operator's decision and is not replaced by the retention period (M7-04).

## Consequences

- M7-04 is reopened with changed content: examples are stored, they contain personal data, a
  retention and deletion rule and, before any provider transfer, minimisation or
  pseudonymisation are needed. Owner: operator with data protection; gate: none, but M7-01 and
  M12-01 remain closed for provider use.
- Required code changes before productive use: per tenant switch for example storage (done
  26.09.2026, default off), deletion of examples when a contact is deleted (done
  26.09.2026) and the retention period with daily deletion run (done 27.09.2026, default
  24 months); still open: masking of the note before it enters a prompt and the operator's
  data protection review (M7-04, operator with data protection).
- Rule M19-07 documents the behaviour; the plan note is in `docs/plans/M20.md` (Nachtrag
  26.09.2026, 1.25.0).
