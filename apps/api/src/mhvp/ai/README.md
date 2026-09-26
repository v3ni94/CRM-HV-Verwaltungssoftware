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
transaction (`DELETE /contacts/{id}` calls the latter); the rows are derived data, so this is a
hard delete. Open: retention rule and masking of the note (M7-04, docs/rules/M19-07).

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
  Playbook matching (`communication.suggest.best_playbook`) is still keyword based.
* No new dependency: `mhvp.ai.vector.Vector` is a small SQLAlchemy `UserDefinedType` for the
  text form `[..]` of pgvector, so the `pgvector` Python package is not needed (ADR 0001
  unchanged). No ANN index yet (exact scan; an HNSW index is a follow-up when a tenant exceeds
  some ten thousand chunks).
* Tests: `tests/unit/test_ai_embeddings.py` (chunking, text form, adapter with injected SDK
  client, cost), `tests/integration/test_m7_ai_embeddings.py` (fake embedding client without
  network, index job and counters, masking, budget accounting, permission, ranking with hand made
  vectors, tenant separation, keyword fallback, budget stop and provider error).
