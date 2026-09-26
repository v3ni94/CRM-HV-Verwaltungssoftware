# ADR 0010: Learning examples from ticket resolutions (ai_example per tenant, local matching)

- Status: Proposed, operator decision required (data protection, M7-04)
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
6. **Feature flag.** There is no per tenant switch for storing examples; the storage is
   coupled to the closing status. This deviates from section 0.3 (function behind a flag until
   the conflict is decided) and is listed as a gap requiring a code change.

## Consequences

- M7-04 is reopened with changed content: examples are stored, they contain personal data, a
  retention and deletion rule and, before any provider transfer, minimisation or
  pseudonymisation are needed. Owner: operator with data protection; gate: none, but M7-01 and
  M12-01 remain closed for provider use.
- Required code changes before productive use (not done here): per tenant switch for example
  storage, masking of the note before it enters a prompt, deletion of examples when a ticket or
  contact is deleted (DSGVO, S06), and a retention rule in `docs/rules/`.
- Rule M19-07 documents the behaviour; the plan note is in `docs/plans/M20.md` (Nachtrag
  26.09.2026, 1.25.0).
