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
