# Plan: assistant chat answers from platform data (rule AI-LOOKUP-01, 28.09.2026)

Operator request 28.09.2026, extended the same day (page context, conversation, chat actions).
Gates G1 to G5 stay closed; nothing here books, pays or issues a statement.

## Scope

1. Deterministic lookup tools (`mhvp.ai.lookup`): contacts, properties, units, contracts,
   tickets, page and handbook index; caller session under RLS, permission of the regular
   endpoint per tool, 10 hits per tool.
2. Orchestration in `answer_question`: hits, focus record facts and conversation history as
   masked data (prompt v2); deterministic fallback without provider or budget.
3. Structured links on run and message (migration 0223 `ai_message.links`), rendered in the chat
   bubble and the assistant log.
4. "Wo finde ich": `help_index.json` from settings index, navigation and `docs/handbuch`.
5. Page context: route derived record (`chat-suggestions.ts`), suggestion buttons per page.
6. Chat actions as `AiProposal` `chat_action` (contact change, note, ticket), applied only via
   `POST /ai/proposals/{id}/apply`; bank details refused.

## Files

API: `ai/lookup.py`, `ai/chat_actions.py`, `ai/gateway.py`, `ai/jobs.py`, `ai/routers.py`,
`ai/schemas.py`, `ai/tasks.py`, `ai/models.py`, `ai/prompts/answer_question/v2.md`,
`alembic/versions/0223_ai_message_links.py`, `scripts/build_help_index.py`.
CRM: `lib/chat-suggestions.ts`, `components/ai/ChatLinks.tsx`, `ChatActionProposal.tsx`,
`AiChatWidget.tsx`, `AssistantMessage.tsx`, messages de/en.

## Tests

`tests/integration/test_ai_lookup.py` (fallback, links per type, not found, help page, tenant
separation, permission, provider path with masking, focus and history, phone change proposal,
bank refusal, ticket proposal), `tests/unit/test_ai_lookup.py`; vitest `ChatLinks.test.tsx`,
`chat-suggestions.test.ts`, `AiChatWidget.test.tsx`.

## Open points

`docs/OPEN_QUESTIONS.md` AI-LOOKUP-Q1 to Q3.

Status 01.10.2026 (AC08, GA10-06): model planned lookups (tool use) implemented behind `models.<tier>.tool_use` (default off), rule AI-TOOL-01, decision AC08-01 / AI-LOOKUP-Q1 open.
