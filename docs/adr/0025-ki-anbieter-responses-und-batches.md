# ADR 0025: OpenAI Responses API with strict Structured Outputs, Anthropic Message Batches for deferred runs

- Status: Accepted
- Date: 2026-10-02

## Context

Section 9.1 asks for OpenAI via the Responses API with Structured Outputs (strict); the adapter
used Chat Completions with `strict: false` (finding GAB-10). Section 9.3 asks for the provider
batch interfaces for runs that are not time critical; `ai/batch.py` only ran a nightly collective
run through the normal call path (finding GAB-09). SDK versions in the repository: `openai`
2.54.0, `anthropic` 1.8.0. Endpoint names below are taken from these SDKs.

## Decision

1. `OpenAIClient.complete` calls `client.responses.create` with `instructions`, `input`,
   `max_output_tokens`, `store: false` and `text.format = {type: json_schema, name, schema,
   strict: true}`. The task schema is normalized for strict mode (`strict_schema`: every object
   `additionalProperties: false`, all properties required, formerly optional ones nullable via
   `anyOf [..., {type: null}]`, `default` removed); the `null` values strict mode forces are
   removed from the answer again (`drop_added_nulls`) before the gateway validates.
   Deviation: on an HTTP 4xx other than 429 from `/responses` (for example a compatible gateway
   behind `base_url` without the Responses API) the call falls back once to Chat Completions
   with `response_format` json_schema, not strict. 429, 5xx and connection errors do not fall
   back; they keep the existing retry and provider fallback of the gateway.
2. `AnthropicClient.submit_batch` (`messages.batches.create`, same params as `messages.create`,
   `custom_id` = SHA-256 of the request) and `poll_batch` (`messages.batches.retrieve`,
   `messages.batches.results` once `processing_status` is `ended`).
3. `batch.submit_deferred` uses the provider batch when the tenant switched `batch_enabled` on
   for a released provider configuration (column on `ai_provider_config`, migration 0422,
   default off). Deferred runs pass the unchanged gateway path with a capture active
   (`providers.batch_capture`); the provider request is recorded instead of sent, the run
   returns to `queued` (state `submitted`). The hourly beat task `mhvp.ai.batch_poll` polls;
   after the end the run passes the gateway again and the identical requests are answered from
   the batch results (replay). Further rounds (tool use, chunks) start another cycle, at most
   three, then the run is executed synchronously. Without the switch the collective run stays.
4. `batch_price_factor` (NUMERIC(20,8), 0 < f <= 1, default 1) is entered per provider
   configuration from the provider's price list; no discount is assumed in code. It is applied
   to the run's cost only when every provider answer of the run came from the batch; the list
   price is kept in `input_ref.batch.list_cost_eur`.

## Consequences

- All checks (release, DPA evidence, opt-out, budget, masking, deduplication) stay in the gateway
  and run again on replay; the budget check uses the list price (upper bound).
- Batch results are held by the provider until retrieved; whether the DPA covers this is an
  operator question (docs/OPEN_QUESTIONS.md AG04-01). Hence the switch defaults to off.
- OpenAI Batch is not wired (calls to OpenAI inside a captured run go synchronously).
- Tests: `tests/unit/test_ag04_ai_batch_responses.py`, `tests/integration/test_ag04_ai_provider_batch.py`
  (recorded responses, no network).

## Alternatives considered

- Duplicating prompt building outside the gateway for batches: rejected, two code paths for the
  same checks.
- Keeping Chat Completions with an ADR only: rejected, 9.1 names the Responses API.

## References

- `docs/MASTER-PROMPT.md` sections 9.1, 9.3; findings GAB-09, GAB-10.
