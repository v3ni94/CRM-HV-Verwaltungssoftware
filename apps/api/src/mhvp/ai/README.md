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
