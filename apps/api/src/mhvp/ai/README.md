# mhvp.ai

AI gateway, onboarding chat, proposals and import runs (M7). Plan: `docs/plans/M7.md`.

* Specification: docs/MASTER-PROMPT.md 6.8, 9, 10; rules 0.1.6 and 0.1.13.
* Files: `models.py`, `tasks.py` (schemas, prompt registry), `prompts/<task>/v<n>.md`,
  `providers.py`, `gateway.py`, `imports.py`, `jobs.py`, `routers.py`, `schemas.py`,
  `evaluate.py` (`make ai-eval`).
* AI output is a proposal. Nothing is written without confirmation; nothing is sent to a provider
  without a released configuration with DPA evidence.
* Tests: `apps/api/tests/integration/test_m7_ai.py`, `apps/api/tests/unit/test_m7_ai.py`,
  evaluation cases in `apps/api/tests/ai_eval/`.


Providers (M7-02, 24.09.2026): Anthropic (Messages API, structured output) and OpenAI (Chat Completions, `response_format` json_schema), both behind `providers.ProviderClient`. A provider is used only after four-eyes release with a documented DPA (9.4).

Routing (M7-02): `TenantSettings.ai_routing` selects the strategy (`anthropic_first`, `openai_first`, `alternate`, `anthropic_only`, `openai_only`), set via `PUT /ai/routing`. Budgets apply per provider; with a `_first` or `alternate` strategy an exhausted budget or a provider error hands the run to the other released provider and `RunOut.fallback` lists the skipped ones. `_only` strategies block instead.

## Audit view of chats (24.09.2026)

`GET /ai/conversations?scope=all` lists the chats of every user of the tenant, newest first,
with user name, message count and last message; filters `user_id`, `date_from`, `date_to`,
`q` (title and message text). It requires `audit:read`; other users see only their own chats
(`scope=own`). Holders of `audit:read` may read any chat by id but cannot send messages into
another person's chat. The CRM page `/assistent` is this audit trail; new requests start in
the chat bubble on every page.

## Mail suggestions and playbooks (M20 take-over, 25.09.2026)

Two task types added for `mhvp.communication.suggest` (see `mhvp/communication/README.md`):
`classify_email` (`MailSuggestion`: category, urgency, summary, property number, contact name,
reply draft) for the suggestion on an inbound mail, and `draft_reply` (`PlaybookDraft`: title,
category, keywords, summary, steps, reply template) for a playbook draft learned from a closed
ticket. Both run through the same gateway as the assistant chat (release, budget, audit); a
missing release or an exhausted budget never raises an exception, the caller stores the
gateway's reason as the suggestion's skip reason (`Message.suggestion_status = "skipped"`).

## Large documents: chunking, tier escalation, progress (25.09.2026)

Root cause of "Die Unterlagen sind zu umfangreich" on a single, modest contact list: `retrieve()`
added up to 6 unrelated documents to `answer_question`/`summarize` even though the user attached
none needed, XLSX/CSV rows were never chunked, and `MAX_TABLE_ROWS` (2000) and
`MAX_INPUT_CHARS` (600000) were too tight for a spreadsheet with formatting far beyond the data.

* `extract_contacts`/`extract_property` never retrieve documents (only what was attached), and
  their table documents (`XLSX`/`text/csv`) are split into row chunks (`CHUNK_ROWS` = 80 rows,
  `CHUNK_CHARS` = 150000 chars, whichever is hit first), repeating the header (the first data
  row) at the top of every chunk (`gateway._chunk_table_body`). One provider call per chunk; a
  `max_tokens` truncation halves the chunk and retries (`gateway._split_chunk_in_half`) instead of
  failing the run. Results are merged (`gateway.merge_extraction`): contacts/rows are
  concatenated and deduped by exact identical entries, questions are merged, one `property`
  record (the first chunk's) is kept. A run warning is added when the row count does not match
  contacts extracted plus explicitly skipped chunks.
* `answer_question`/`summarize` keep a single call: on overflow, retrieval is cut to the best 3
  documents and each document to `MAX_DOCUMENT_CHARS`; only a single attached document beyond
  `HARD_LIMIT_CHARS` (2000000, never chunked, since these tasks need the whole text) still blocks,
  naming the file and its size. `MAX_INPUT_CHARS` (the pre chunking guard) is 1500000.
* Model tier escalation: input size is estimated at chars / 3.5 tokens; when a tier's optional,
  operator entered `context_tokens` (`AiProviderConfig.models[tier]["context_tokens"]`, never
  invented here, `None` means unknown and no escalation) is exceeded, the provider's `large` tier
  is used instead and `RunOut.model_tier_reason` explains it ("Großes Modell wegen Umfang
  gewählt").
* `RunOut.input_stats` lists the character count read per attached document (debug: why a run
  was, or would have been, too large); `RunOut.progress` (`{"stage", "current", "total"}`) is
  updated after every chunk ("Verarbeitung Teil i von n", then "Fertig"); `RunOut.warnings` carries
  the non fatal notices above. All three live in `AiTaskRun.input_ref` (no migration).
* Encoding: `gateway.decode_text` tries UTF-8 (with an optional BOM), then Windows-1252, then
  Latin-1 (never fails, so nothing is silently replaced) and is used by `csv_text`. Uploads of
  type `text/plain`/`text/csv` are still decoded in `mhvp.documents.text.extract` with
  `errors="replace"`; that path is outside this module's scope and needs the same fix
  (`docs/OPEN_QUESTIONS.md` candidate) so umlauts in a plain text upload are not lost before the
  gateway ever sees the text.
* `MAX_TABLE_ROWS` raised to 20000 (still visibly truncated beyond that, `[gekürzt: ...]`).

## Contact master data change from a ticket mail (26.09.2026)

Task `contact_master_data_change` (`ContactChangeResult`, tier `small`, prompt
`prompts/contact_master_data_change/v1.md`) refines the deterministic detection in
`mhvp.tickets.proposals` (docs/rules/M19-05.md). Input is the mail with IBAN, e-mail and phone
values masked (`mhvp.objektakte.masking.mask_identifiers`); the result is an `AiProposal`
(`entity_type="contact_change"`, `context_id` = ticket) decided in `/tickets/{id}/proposals`.
Every decision writes an `AiExample` of the tenant, which `gateway.examples` hands to later runs
as few-shot context. IBANs are never part of the schema nor of an applied change.


## Connection test, output limit per tier, pasted contacts (26.09.2026)

- `POST /ai/providers/{provider}/test` (`tenant_settings:update`, `connection_test.py`): one
  minimal `summarize` prompt per configured tier (small, large; never embedding) with the stored
  key, no retries and no fallback. Needs no four eyes release and never grants or withdraws one;
  each call is recorded as an `AiTaskRun` (`input_ref.connection_test = true`) so the monthly
  budget is charged. Returns status, model, duration and the provider's error text per tier.
- `TierModel.max_output_tokens` (JSONB in `ai_provider_config.models`, no schema change): the
  provider's published output limit per tier, sent as `max_tokens`; unset means
  `gateway.DEFAULT_MAX_OUTPUT_TOKENS` (16000). `Route.max_output_tokens` carries it per run.
- `extract_contacts` without documents: the chat message itself is the only chunk
  (`gateway.NO_DOCUMENT_HINT`); the widget offers this when contact data is pasted or the user
  asks to create contacts without a file. The result stays a proposal (rule 0.1.6).

## KI-Plausibilität eines Abrechnungsentwurfs (A35, 26.09.2026)

Task `check_statement` (`CheckStatementResult`, tier `large`, prompt
`prompts/check_statement/v1.md`) checks a calculated operating cost statement (M17) or HOA
statement (M24) and answers with findings only: field, description, severity (`low`, `medium`,
`high`), reference to a position (`P1`, ...) or a unit, overall assessment, summary. No amounts,
no corrections, no decision (rule 0.1.6). Input assembly, masking (no ids, no IBAN, no titled
names, parties as unit numbers) and result normalisation live in `mhvp.billing.ai_check`;
`jobs.run_and_propose` stores a succeeded run as an `AiProposal` of entity type
`statement_check`. Endpoints: `POST`/`GET` `/statements/{id}/ai-check` and
`/hoa/statements/{id}/ai-check`. Evaluation: `tests/ai_eval/check_statement/cases.jsonl`
(24 cases), scorer `_check_statement` in `evaluate.py`. Plan: `docs/plans/M17.md`.

## Offline-Evaluation der Vorschlagsaufgaben (A46, 26.09.2026)

`tests/ai_eval/<task>/cases.jsonl` holds recorded answers with hand written expectations for
`classify_email` (22 cases), `draft_reply` (21), `map_columns` (24) and
`contact_master_data_change` (26, M7-08). Each set has border cases (null or empty fields,
limits, ambiguous rows, low confidence) and at least one prompt injection case. The scorers in
`evaluate.py` measure the platform's post-processing on the recorded answer, never the model:
`_classify_email` runs `communication.suggest.merge_suggestion` over the keyword fallback,
`_draft_reply` runs `communication.suggest.playbook_fields`, `_map_columns` runs
`table_mapper.mapping_usable` and `apply_mapping` on the case's small table, and
`_contact_change` runs the deterministic stage and `tickets.proposals.merge`, title and greeting.
These scorers take the case input as well (`INPUT_SCORERS`). `propose_posting` (M7-09) has
`PostingProposalResult`, prompt v1 and a first set of 10 cases scored by `_propose_posting`
(`banking.ai_posting.normalize_result`); the minimum for this task is 10 until release
(`evaluate.MIN_CASES_BY_TASK`). The task is disabled until M12-01 (tenant switch
`ai_posting_enabled` plus released provider). Test: `tests/unit/test_a46_ai_eval.py`.


## Learning examples: tenant switch and deletion (26.09.2026, ADR 0010)

`examples.py`: `learning_examples_enabled` reads `tenant_settings.ai_learning_examples_enabled`
(migration 0134, default false); `mhvp.tickets.status.record_resolution_example` stores no
`ticket_resolution` example while it is off. `delete_examples_for_ticket` and
`delete_examples_for_contact` remove the examples of a deleted ticket or contact in the caller's
transaction (`DELETE /contacts/{id}` and the soft delete of an import undo,
`imports._remove("contact", ...)`, call the latter); the rows are derived data, so this is a
hard delete. Open: masking of the note before it enters a prompt (M7-04, docs/rules/M19-07).

Retention (operator decision 27.09.2026, "Vollständig speichern mit Mandantenschalter",
migration 0154): examples are stored in full while the switch is on and deleted by the daily
Celery task `mhvp.ai.examples_retention` (`jobs.examples_retention_once`, beat
`ai-examples-retention` 03:45) once older than
`tenant_settings.ai_learning_examples_retention_months` (default 24, `PATCH /tenant/settings`,
1 to 120; CRM page Einstellungen, Mandant). Calendar months, day clamped
(`examples.retention_cutoff`). Every tenant run is journaled as the event
`ai_examples.retention` (payload: retention_months, cutoff, before, deleted, remaining); a
failing tenant is reported in the task result and the others still run. Tests:
`tests/unit/test_ai_examples_retention.py`, `tests/integration/test_m7_ai_examples_retention.py`.
The data protection review of the stored content stays with the operator (OPEN_QUESTIONS M7-04).

## Endpunktregion und Anbieterwechsel (M7-07, M7-02, 26.09.2026)

- `AiProviderConfig.endpoint_region` reaches the client now (`providers.client_for(provider,
  api_key, endpoint_region)`, also in the connection test). Resolution per provider in
  `providers.py`: OpenAI gets a region specific `base_url` (`REGION_BASE_URLS`: `eu` is
  `https://eu.api.openai.com/v1`, `us` and `global` are the SDK default); any other value is
  rejected with 422 on `PUT /ai/providers/openai` (`validate_region`). Anthropic has no
  regional base URL for the first party API; the value is sent as the Messages API parameter
  `inference_geo` on every call. The Anthropic SDK does not enumerate the accepted values, so
  only the format is checked and a wrong value surfaces in the connection test with the
  provider's own error text. Whether the DPA covers the chosen region remains an operator
  decision (OPEN_QUESTIONS M7-07). Test factories with two arguments keep working
  (`set_factory` wraps them); the region is passed to three argument factories.
- Fallback (M7-02): the routing plan already skips providers with an exhausted budget and hands
  a provider error (network, 5xx, timeout, rate limit after the retries) to the next provider
  of the plan. New: the answering provider is stored as `AiTaskRun.input_ref.provider_used`
  (`RunOut.provider_used`), every proposal created in `jobs.run_and_propose` carries
  `proposed.provider_used`, and a real switch (answering provider differs from the preferred
  one) emits the event `ai.provider_fallback` (payload: task, preferred, provider_used,
  reasons) plus a structured log line without key material. Without a second released
  provider, or with an `_only` strategy, there is no fallback: the run fails or is blocked
  with the reason. AI output stays a proposal (rule 0.1.6).
- SDK choice: the `openai` package (Chat Completions, `response_format` json_schema) is used,
  see ADR 0001 (Nachtrag 26.09.2026). Tests: `tests/unit/test_ai_provider_region_fallback.py`,
  `tests/unit/test_ai_openai_client.py`, integration `test_m7_ai.py::test_routing_strategy_and_fallback`.

## Einbettungen und Ähnlichkeitssuche (M7-03, Betreiberentscheidung 26.09.2026)

`embeddings.py`, table `ai_embedding` (migration 0142, pgvector `vector(1536)`, RLS per tenant),
task value `embed`. Decision: OpenAI `text-embedding-3-small` through the existing adapter
(`OpenAIClient.embed`, Embeddings API; the EU base URL of `endpoint_region = eu` applies), model
and price entered by the operator in `AiProviderConfig.models["embedding"]` (`input_eur_per_mtok`,
output price 0). Anthropic offers no embeddings; the route needs the same release conditions as
every other call (four eyes release, DPA evidence, opt-out, key), otherwise nothing is embedded.

* Sources: extracted document texts (`Document.text_status = extracted`) and knowledge entries
  (`ai_knowledge_entry`, not deleted). The text (title plus body) is masked with
  `mhvp.objektakte.masking.mask_identifiers` (IBAN, e-mail, phone) before it leaves the platform,
  split into chunks (`CHUNK_CHARS` 1500, overlap 200, at most `MAX_CHUNKS_PER_SOURCE` 200), and
  only the vectors are stored; the chunk text is not. A source is pending when it has no chunk 0
  row or its `updated_at` is newer than the row; an unchanged text (same `content_hash`, e.g. a
  title edit) is marked current without a provider call. Orphans (deleted documents or knowledge
  entries) are removed at the start of every job.
* Job: Celery task `mhvp.ai.embed_index` (`jobs.embed_index`, queue `io`; inline with
  `ai_inline`), `index_tenant` runs batches of up to `SOURCES_PER_BATCH` sources and
  `BATCH_CHUNKS` (64) chunks per provider call, each batch in its own transaction. Every call is an
  `AiTaskRun` of task `embed` with tokens and cost, so the monthly budget per provider applies
  unchanged (hard stop before the call, `budget_block`). A stop (budget, route missing, provider
  error) ends the job and is recorded in a summary run (`input_ref.job_summary`, status `failed`
  with the reason, or `succeeded`); the failed call keeps its own run row with the error.
* Endpoints: `GET /ai/embeddings/status` (`tenant_settings:read`): route state and reason,
  model, documents and knowledge entries total, embedded, pending, chunk rows, last job (time,
  status, error, report). `POST /ai/embeddings/reindex` (`tenant_settings:update`, 202): embeds
  missing and changed sources; `full: true` drops all vectors of the tenant first (model change);
  422 without a usable route; event `ai_embeddings.reindex`.
* Search: `gateway.retrieve` (answer_question) uses `embeddings.retrieve_documents` (cosine
  distance `<=>`, best chunk per source, cut-off `MAX_COSINE_DISTANCE` 0.8, docs/ASSUMPTIONS.md
  A-051) and falls back to `retrieve_keyword` (the previous full text search) when the tenant has
  no embeddings, no route, the budget is reached, the provider fails or nothing is under the
  cut-off. The portal scope (`document_scope_for_user`) is applied as `only_ids` before the
  ranking (9.1). The knowledge context of the mail preparation
  (`communication.preparation._knowledge_context`) ranks the permission scoped entries by
  similarity to subject and excerpt (`rank_knowledge`), recency order stays the fallback.
  Playbook matching (`communication.suggest.best_playbook`) is keyword based with a bonus for
  the mail's deterministic category (`rank_playbooks`, 29.09.2026).

## Knowledge base context, usage and feedback (audit 29.09.2026)

`knowledge.py` is the one place that selects knowledge entries for a run, used by the mail
preparation (`communication.preparation._knowledge_context`) and the assistant chat
(`gateway.knowledge_context`, part of `build_input` for `answer_question`): approved and
currently valid entries only (M34-01, release workflow unchanged), one row per `group_id`,
ranked by similarity when embeddings exist, capped at `MAX_CONTEXT_ENTRIES` (30),
`MAX_CONTEXT_CHARS` (20.000) and `MAX_ENTRY_CHARS` (2.000, cut visibly). In the chat the block
stands in front of the documents ("Vorrang vor Dokumenttext"); the property in focus
(`context.entity_type = property`) adds its entries. Used ids go to
`input_ref["knowledge_ids"]` and `RunOut.knowledge_ids`; `usage_count` and `last_used_at` are
bumped per entry (counters keep `updated_at`).

Feedback: `POST /ai/runs/{id}/feedback` (author of the run only; a second vote replaces the
first and moves the counters of the used entries), `POST /ai/knowledge/{id}/feedback`,
`POST /mail/playbooks/{id}/feedback`, each `{helpful: bool}`. Counters only
(`helpful_count`, `unhelpful_count`), shown in the CRM; no status change, no automatic
withdrawal. `KnowledgeEntryOut.stale` flags an approved entry unchanged for
`STALE_AFTER_DAYS` (180): a review hint without legal meaning. Migration 0237.
* No new dependency: `mhvp.ai.vector.Vector` is a small SQLAlchemy `UserDefinedType` for the
  text form `[..]` of pgvector, so the `pgvector` Python package is not needed (ADR 0001
  unchanged).
* ANN index (27.09.2026, migration 0154): `ix_ai_embedding_embedding_hnsw` on
  `ai_embedding.embedding` with `vector_cosine_ops`, so the `<=>` ordering of
  `similar_sources` uses the HNSW index (pgvector defaults `m` 16, `ef_construction` 64). The
  migration creates and drops it `CONCURRENTLY` inside an Alembic `autocommit_block` (no lock
  on a running system); the column change of the same migration runs in the transaction
  before it. The index is declared on the model (`postgresql_using="hnsw"`,
  `postgresql_ops`) so `alembic check` sees no drift. Test:
  `test_m7_ai_embeddings.py::test_hnsw_index_on_embedding`. CRM: the AI settings page shows
  the status counters and offers "Neu aufbauen" (incremental) and "Vollständig neu aufbauen"
  (`components/ai/EmbeddingsStatus.tsx`, permission `tenant_settings:update`).
* Tests: `tests/unit/test_ai_embeddings.py` (chunking, text form, adapter with injected SDK
  client, cost), `tests/integration/test_m7_ai_embeddings.py` (fake embedding client without
  network, index job and counters, masking, budget accounting, permission, ranking with hand made
  vectors, tenant separation, keyword fallback, budget stop and provider error).

## M34 Nachtrag 27.09.2026: Erklärbarkeit (Ablehnungsgrund) und Maskierung des Prompt-Kontexts

Soll-Ist-Abgleich Masterprompt 9 und 10 gegen `mhvp.ai` und `apps/web-crm/.../assistent`
(Betreiberauftrag, nur Lücken ohne Anbieterfreigabe). Erklärbarkeit (Quelle, Konfidenz,
„Warum?“) war bereits vollständig (`ProposalBadge`, `Reasoning` aus `AiTaskRun.output`); zwei
Lücken geschlossen:

* `POST /ai/proposals/{id}/reject` nimmt jetzt `{"reason": "..."}` (`RejectProposalIn`,
  `ai_proposal.rejection_reason`, migration 0212) und legt bei gesetztem Grund und
  eingeschaltetem Mandantenschalter (`tenant_settings.ai_learning_examples_enabled`, wie
  `ticket_resolution`) ein `ai_example` mit `result.rejected = true` und dem Grund an
  (`examples.record_rejection`), damit ein abgelehnter Vorschlag als Few-Shot-Gegenbeispiel in
  die nächste Ausführung derselben Aufgabe einfließen kann; Retention wie jedes andere Beispiel
  (`purge_expired_examples`, ADR 0010). Ohne Grund oder ohne Schalter wird nur die Ablehnung
  selbst protokolliert (`ai_proposal.rejected` Ereignis), wie zuvor.
* `gateway.build_input` maskierte bislang nur den Embedding-Text (`embeddings.py`); der
  eigentliche Prompt-Kontext von `answer_question`, `summarize`, `check_statement`,
  `classify_email`, `classify_document`, `draft_reply` und `call_summary` ging unmaskiert an den
  Anbieter (9.1 „Pseudonymisierung von Namen und IBANs, wo die Aufgabe es zulässt“ war für
  diesen Pfad nicht umgesetzt). Neu: `MASKED_TASKS` maskiert IBAN, E-Mail und Telefon
  (`mask_identifiers`, Namen bleiben für die Anrede) für genau diese Aufgaben; `extract_contacts`/
  `extract_property` (Kontext braucht die Rohdaten), `extract_invoice`/`propose_posting`
  (brauchen die Bankverbindung) und `map_columns` (braucht die Rohwerte zur Spaltenerkennung)
  bleiben bewusst ausgenommen. Test: `tests/unit/test_m34_ai_masking.py`.

Offen (nicht in dieser Sitzung, siehe `docs/OPEN_QUESTIONS.md` M34-05/M34-06): Straßen- und
Hausnummernmaskierung fehlt in `mhvp.objektakte.masking` weiterhin (nur die Namensheuristik
erfasst zufällig manche Adressen); der Onboarding-Chat für neue Mitarbeiter (Kapitel 10, Rolle,
Aufgaben, erste Schritte je Modul, `ui_preferences`) existiert nicht — `OnboardingWizard.tsx`
(M27-03) ist die Mandantenanlage für Betreiber, kein Nutzer-Onboarding.

## Platform lookup, page context and chat actions (rule AI-LOOKUP-01, 28.09.2026)

- `lookup.py`: deterministic tools for `answer_question` (contacts, properties, units,
  contracts, tickets, plus the page and handbook index `help_index.json`). They run in the
  request's tenant session (RLS) with the permission of the regular endpoint; a tool without
  permission returns nothing and is named in the answer. At most 10 hits per tool. The record
  open on the page (`MessageIn.context_entity_type` / `context_entity_id`) is looked up first
  (`focus_record`: contracts, tickets, mails of a contact; units, owners, open tickets of a
  property; thread of a ticket). The result is stored as `input_ref["lookup"]`.
- The gateway adds the hits, facts and the stored conversation history (last 10 messages) to
  the masked data block; prompt `answer_question/v2` is conversational. The input hash includes
  the hit ids and the turn, so dedup never reuses another conversation's answer. The user's
  instruction is its own part `<frage>` in front of `<daten>` (`TaskInput.instruction`, chat
  only); every record field, fact and history message is written on one line
  (`lookup.flat`), and contact hits carry `model_detail` with placeholders instead of phone and
  e-mail for the model (`links_of` strips it for messages and runs). Mail facts of the open
  record apply the mailbox rule of the mail endpoints through the session principal.
- `answer_question` started outside the chat (`create_extraction_run`: automation `ai_task`,
  intake) keeps prompt v1 (`NON_CHAT_PROMPT`) and never produces a chat action (`jobs.py`
  builds one only when `input_ref["lookup"]` exists).
- Area tools (`lookup_tools.py`, 29.09.2026): the chat bubble sends `area` / `sub_area` of the
  open menu item (`chat-suggestions.ts` route table, `useChatContext` override); `AREA_MAP`
  adds the tools of that area, which run without a search term (calendar, deadlines,
  documents, resolutions, meetings, reserve, rent increases, work orders, bank transactions,
  open items). `lookup.parse` turns time words into `Query.range` and filter words into
  `Query.flags`; tools may add facts (`Query.facts`). Each tool follows the permission and the
  legal entity scope of its endpoint; the reserve is reported only inside the scope. Prompt
  `answer_question/v3` names the area and the two new proposal kinds `calendar_create` and
  `deadline_create` (internal `CalendarEntry` of the confirmer, never an invitation).
- Input budget (`fit_answer_input`, 29.09.2026): the data block of a chat call is fitted into
  the tier's `context_tokens` (default 150000 tokens, chars / 3.5, reserve 0.85): retrieved
  documents first, then excerpts, then lookup hits beyond 10 per tool, then history beyond 6
  turns; never the question. A provider 400 naming the token limit is retried once with the
  budget halved (`_call_within_budget`); a second refusal fails the run with
  `CONTEXT_WINDOW_NOTICE` and the job answers with the hit list. Sizes go to `input_stats`.
- `jobs.py` appends the platform hit list to the answer, stores the links on the message
  (`ai_message.links`, migration 0223) and, without a released provider or budget, answers with
  the hit list only. `RunOut.links` and `RunOut.lookup_answer` carry the same.
- `chat_actions.py`: an `AnswerResult.action` becomes an `AiProposal` with
  `entity_type="chat_action"` (contact_change, contact_note, ticket_create) only for records of
  the run's own hits and only when the user's own message (page hint stripped) asks for that
  kind (`CHANGE_INTENT`, `NOTE_INTENT`, `TICKET_INTENT`; otherwise dropped and logged); phone
  and e-mail come from the user's message, name and address values must appear in it; bank
  words or an IBAN in the message, the note or the ticket text refuse the action. The
  proposal carries the model's `reason`, shown in the chat card. `POST /ai/proposals/{id}/apply`
  with `{"chat_action": {}}` writes decision, import run, event and the record (contact change
  path of `mhvp.tickets.proposals`, a `ContactNote`, or `tickets.routers.create_ticket_in_session`)
  in one transaction. The import run has no items; `POST /imports/{id}/undo` refuses runs with
  source `ai:answer_question:*` (409). A rejected chat action is stored as a masked learning
  example (`examples.masked_copy`), and `gateway._messages` masks the examples of masked tasks.
- `scripts/build_help_index.py` regenerates `help_index.json` from
  `apps/web-crm/src/lib/settings-index.ts`, the main navigation and `docs/handbuch`;
  `make lint` checks it is current.

## P18 (30.09.2026)

- `masking.py`: `mask_personal_data` adds street and postal code masking to the identifier masking (rule AI-MASK-02); names stay (M34-05 open).
- `journal_history.py`: migrated journal entries as read only few shot examples for `propose_posting` (rule AI-HIST-01).
- `GET /ai/usage` additionally returns `runs_by_task`, `tokens_in_by_task`, `tokens_out_by_task`.

## Personenabgleich im Objekt-Onboarding (M7-02)

`person_match.py` gleicht Personen aus dem Objekt-Import gegen das Adressbuch ab (IBAN,
E-Mail, Name, Postleitzahl, Straße). Schwellwerte je Mandant über
`GET/PUT /onboarding/match-settings` (Standard 0,90 verknüpfen, 0,60 vorschlagen).
`apply_property` verknüpft Treffer ab dem Verknüpfungsschwellwert mit dem bestehenden
Kontakt, sonst wird ein unvollständiger Kontakt angelegt (Hinweis bei Vorschlagsbereich).
`POST /onboarding/person-match` liefert die Vorschau, schreibt nichts.

## Q06 (30.09.2026, rule Q06)

* Chat actions `property_create`, `document_file`, `portal_invite_prepare`, `letter_create` (M7-03, 10.3) in `chat_actions.py`; database checks (template, e-mail, existing portal account) in `chat_actions.enrich` inside the job; writes in `routers._apply_chat_action` through the paths of `POST /properties`, `POST /documents/{id}/links`, `POST /letters` and `POST /portal-admin/accounts`. Prompt `answer_question/v4`.
* Follow up steps (M7-04): `followups.py`, stored as `summary.next_steps` of the import run and posted as a chat message; offers only.
* Cascade small to large (M7-08): `gateway.cascade_reason`, `large_route_of`, `stage_record`; operator threshold `models.small.cascade_confidence_below`; stages in `input_ref.cascade` and `RunOut.cascade`, `cost_eur` is the sum of the stages.
* Budget stop notification (M7-09): `gateway.notify_budget_block` (kind `ai.budget_blocked`, recipients with `tenant_settings:update`). Monthly AI cost per tenant stays in `usage_counter.ai_cost_eur` (platform licensing).
* Batch (M7-07): `batch.py` (`defer`, nightly job `mhvp.ai.batch_nightly`); the provider batch APIs are not wired, see module docstring.
* Rent increase AI check (M26-01): task `rent_increase_check` (migration 0275), `rent_increase_check.py`, endpoints `POST`/`GET /letting/rent-increases/{id}/ai-check`; hint proposals are refused by `apply` (409).
* Portal chat pre-qualification (M21-01): `portal_prequalify.py`, called from `mhvp.portal.chat.prequalify` when switch and gateway gate are open.
* Historical bank assignments (M8-05): `journal_history.bank_examples` (`migrated_bank_link`) next to the journal examples of `propose_posting`.
* R09 (package of 01.10.2026): `automation.py` (tenant switches `rent_increase_check` and `batch_mail_classification`, default off, `GET`/`PUT /ai/automation`, stored under `objektakte_classification["ai_automation"]` without migration); `rent_increase_check.auto_queue` for the automatic proposal; `batch.run_callers` connects callers to the nightly collective run (M7-07). See `docs/rules/R09.md`.

## R03 (01.10.2026): Anlage beim Objekt-Onboarding und Abgleichvorschau

`PropertyChoice` (Body von `POST /ai/proposals/{id}/apply`, Feld `property`) nimmt zusätzlich
`bank_accounts`, `allocation_keys` (alle vier Arten, Werte je Einheitennummer),
`create_debtor_accounts`, `link_source_documents` (Standard an) und `document_ids` entgegen.
`imports._apply_onboarding_extras` legt alles in der Transaktion von `apply_property` an und
protokolliert `property_bank_account`, `ledger`, `ledger_account` und `document_link` als
`ImportRunItem`; die Rücknahme entfernt sie vor dem Objekt, solange nichts gebucht oder
zugeordnet wurde. Zusatzrechte: `properties:update` (Konten, Schlüssel), `accounting:create`
(Debitorenkonten), `documents:update` (Verknüpfungen). `POST /onboarding/person-match-batch`
liefert den Abgleich für bis zu 500 Personen als Vorschau (Tabelle im Import-Dialog).
Regel: `docs/rules/R03-onboarding-uebernahme.md`.

R03-02 (Rechtsträger je Konto): `OnboardingBankAccountChoice.legal_entity_id` und
`PropertyChoice.debtor_legal_entity_ids`. Passen mehrere Rechtsträger (mehrere Eigentümer einer
Mietverwaltung) und fehlt die Wahl, legt `apply_property` das Konto nicht an und gibt
`summary.entity_decisions` zurück (Kandidaten, keine IBAN). `POST
/ai/import-runs/{id}/resolve-entities` (`imports.resolve_entities`) legt die Konten nach der
Auswahl an, protokolliert sie im selben Importlauf und leert die erledigten Entscheidungspunkte.
CRM: `EntityDecisions` in `OnboardingExtras.tsx`, eingebunden in `PropertyProposal`.

### Aufgabe reply_draft (T12, M20-02)

`AiTask.REPLY_DRAFT` (Migration 0296) mit Schema `tasks.ReplyDraftResult` und Prompt `prompts/reply_draft/v1.md`; `draft_reply` bleibt der Playbook-Entwurf. Aufruf und Freigabe in `mhvp.communication` (`suggest.reply_task_for_message`, `POST /mail/messages/{id}/reply-ai`); maskiert (`MASKED_TASKS`), nur Vorschlag. Regel: `docs/rules/T12.md`.

### V06-01 (W05): Standardteam und Zuständiger der Übernahme-Tickets

`mhvp.ai.takeover_defaults` liest und schreibt `team_id` und `assignee_user_id` unter dem Schlüssel `takeover_tickets` im JSON-Dokument `TenantSettings.objektakte_classification` (keine Migration). `GET/PUT /onboarding/takeover-ticket-defaults` (Rechte `tenant_settings:read` und `tenant_settings:update`); Team und Zuständiger müssen zum Mandanten gehören (422), leer bedeutet ohne Zuweisung. `POST /properties/{id}/takeover-checklist/tickets` setzt Team und Zuständigen (über `assign_ticket`) bei neu angelegten Tickets. Ein Sammelkonto je Eigentümer wird nicht angelegt (Entscheidungspunkt V06-02).

* AA05 (GA04-12): learning examples are embedded by the index job (`EmbeddingSourceKind.AI_EXAMPLE`, masked text of task, features and result; `embeddings.status` counts `examples_*`). `gateway.similar_examples` orders the few shot examples by cosine distance to the input via `embeddings.rank_examples`; without embeddings, route, budget or hit it keeps the recency order. Distance limit AA05-03.

## Tool use (GA10-06, AC08, rule AI-TOOL-01)

`tool_use.py`: read only tools for model planned lookups (`kontakte`, `vertraege`,
`offene_posten`, `dokumente`, `termine` reuse the functions of `lookup` / `lookup_tools`;
`kontenplan` is new). The model asks for them in the structured answer (`tool_calls`, parsed by
`providers.tool_calls_of` into `Completion.tool_calls`); `gateway._tool_loop` runs at most
`MAX_CALLS` calls in `MAX_ROUNDS` rounds within `TIME_LIMIT_S`, each round in a tenant
transaction with the caller's principal (`input_ref.tool_grant`, written by `send_message`),
masks the results (`results_text`) and logs every call in `input_ref.tool_calls`
(`RunOut.tools_used`). Switch: `models.<tier>.tool_use` of the provider config, default off.
AD04: `GET /ai/conversations/{id}` returns `MessageOut.tools_used` (optional) and merges the tool hit links (`tool_calls[].links`) into `links` (`tool_use.merge_links`); `ProviderSettings` carries the `tool_use` switch.

AE28 (M7-06, SA-04): `portal_answer.py` answers questions of portal users (`input_ref.audience =
"portal"`, prompt variant `portal_v1`). The gateway then derives the readable documents from the
access grants of `input_ref.portal_account_id` (`portal.assistant_scope.audience_scope`, never
`None`), skips the knowledge base and few shot examples, and `retrieve_keyword` filters by
`only_ids` before the limit. `tasks.prompt` loads named variants (`<name>_v<n>`) that never
become the latest numbered prompt. Rule: `docs/rules/AE28-01.md`.

## AF21 (02.10.2026): Rücknahmevorschau und Goldstandard

- `GET /imports/{id}/undo-preview` (`imports.undo_preview`): Trockenlauf der Rücknahme in einem immer zurückgerollten Savepoint, je Datensatz `removable` oder `kept_reason`. Schreibt nichts. Das CRM zeigt die Liste im Dialog `ImportUndoDialog` vor der Bestätigung.
- `make ai-eval` deckt zusätzlich `classify_document` (Maskierung, Kategorie 01 bis 06, Klassencode, Schwelle der automatischen Stufe), `call_summary` (`call_assistant.merge_ai`) und `rent_increase_check` (`normalize_result`) mit je mindestens 20 synthetischen Fällen ab. Regel docs/rules/AF21-01.md.

## AG04 (02.10.2026): Responses API und Anbieter-Stapel (GAB-10, GAB-09, ADR 0025)

- `OpenAIClient` nutzt die Responses API (`responses.create`, `text.format` json_schema mit
  `strict: true`); das Schema wird mit `providers.strict_schema` normalisiert, erzwungene
  `null` für optionale Felder entfernt `drop_added_nulls`. Bei HTTP 4xx (außer 429) fällt der
  Aufruf einmal auf Chat Completions zurück.
- `AnthropicClient.submit_batch` und `poll_batch` (Message Batches API).
- `batch.submit_deferred`: mit `ai_provider_config.batch_enabled` (Standard aus) laufen
  zurückgestellte Läufe über den Anbieter-Stapel (Aufzeichnung im Gateway, Wiedergabe nach dem
  Abruf durch den stündlichen Beat-Task `mhvp.ai.batch_poll`), sonst wie bisher als Sammellauf.
- `batch_price_factor` (0 < f <= 1, Standard 1) wirkt nur auf Läufe, die vollständig aus dem
  Stapel beantwortet wurden; der Listenpreis bleibt in `input_ref.batch.list_cost_eur`.

### Welle 20 (AI06): Batch-Freigabeprüfung und Goldstandard reply_draft

- GAH-203: `batch.batch_configs` und `batch.batch_config_usable` prüfen dieselben Bedingungen wie die Gateway-Route (aktiv, Batch-Schalter, Vier-Augen-Freigabe, AVV unterzeichnet, AVV-Dokument, Opt-out, Schlüssel), bei jedem Einreichen und Abruf. Fehlt eine Bedingung nachträglich, wird ein offener Stapel nicht abgerufen; die Läufe gehen mit `reason: release_withdrawn` und `aborted_batch_id` in die Nachtwarteschlange zurück, wo das Gateway sie sperrt.
- GAH-204: Negativtests `tests/integration/test_ai06_withdrawn_release.py` (Gateway, Batch Einreichen und Abruf, Einbettungsroute; Fake-Anbieter zählt Aufrufe).
- GAH-205: Goldstandard `tests/ai_eval/reply_draft` (20 Fälle, zwei Injektionsfälle), Bewertung über `suggest.reply_task_payload` in `evaluate._reply_draft`.
* GAI-610 (AJ25): when the release, the DPA, the DPA document or the training opt-out is withdrawn while a provider batch is open, `batch.poll_submitted` no longer polls it but cancels it at the provider (`AnthropicClient.cancel_batch`, `messages.batches.cancel`, only the batch id is sent) and emits `ai.batch_cancelled` with the outcome `cancelled`, `failed` or `not_possible` (no stored key or no cancel capability). The runs go back to `deferred` with `provider_cancel` set. Tests use a fake provider (`test_ai06_withdrawn_release.py`), no network.

## Schalter der KI-Pfade je Mail und Regel (AM04, GAJ-605 bis GAJ-607)

`ai_automation` in `TenantSettings.objektakte_classification` trägt drei weitere Schalter, die
über `GET/PUT /ai/automation` gelesen und gesetzt werden und auf der Seite Fachliche Regeln
erscheinen: `realtime_mail_classification` (Vorschlag je eingehender Ticket-Mail),
`master_data_change_proposals` (Stammdatenvorschlag je Ticket-Mail) und `automation_ai_task`
(Regelaktion `ai_task`). Standard an, damit das bisherige Verhalten erhalten bleibt; die
Standardfrage ist offen (OPEN_QUESTIONS AM04-01 bis AM04-03). Regeln mit `ai_task` dürfen nur
Personen mit `ai:approve` anlegen oder ändern (403 sonst).

## Budget warning notification (GAJ-609, wave 23)

When a run crosses 80 percent of the monthly budget, `ai.budget_warning` is emitted and
`gateway.notify_budget_warning` notifies every member with `tenant_settings:update`
(kind `ai.budget_warning`, idempotent on the unread notification).
