"""Connection test for a provider configuration (settings page, "Verbindung testen").

One minimal prompt per configured tier (small, large) goes to the provider with the stored key.
The test needs no four eyes release (it exists so the operator can check key, model names and
output limits before the release), it never grants or withdraws one, and its cost is recorded
like any other run so the monthly budget is charged (rule 0.1.13: the key stays server side).
"""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from mhvp.ai import gateway, providers, tasks
from mhvp.ai.models import AiProvider, AiTask

TEST_TIERS: tuple[str, ...] = ("small", "large")
TEST_TASK = AiTask.SUMMARIZE  # smallest schema; the answer is one short sentence
TEST_INSTRUCTION = (
    "Anweisung des Nutzers: Verbindungstest. Antworte mit summary = "
    '"Verbindungstest erfolgreich" und einer leeren Liste open_points.'
)
# The provider's output limit is sent as configured so a wrong entry is reported by the test;
# the answer itself is a few tokens, so the cost stays minimal either way.
_ERROR_MAX = 300


@dataclass
class TierTestResult:
    tier: str
    model: str
    ok: bool
    duration_ms: int
    error: str | None
    tokens_in: int
    tokens_out: int
    cost_eur: Decimal


def configured_tiers(models: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Tiers of the configuration that carry a model name, in ``TEST_TIERS`` order."""
    out: list[tuple[str, dict[str, Any]]] = []
    for tier in TEST_TIERS:
        entry = models.get(tier) or {}
        if isinstance(entry, dict) and str(entry.get("model") or "").strip():
            out.append((tier, entry))
    return out


def _price(entry: dict[str, Any], key: str) -> Decimal:
    try:
        return Decimal(str(entry.get(key, 0) or 0))
    except ArithmeticError:
        return Decimal(0)


async def check_tier(
    provider: AiProvider, api_key: str, tier: str, entry: dict[str, Any]
) -> TierTestResult:
    """One call, no retries and no fallback: the operator wants to see this provider's answer."""
    model = str(entry["model"])
    prompt = tasks.prompt(TEST_TASK)
    schema = tasks.json_schema(TEST_TASK)
    messages = [{"role": "user", "content": f"<daten>\n{TEST_INSTRUCTION}\n</daten>"}]
    client = providers.client_for(provider, api_key)
    started = time.monotonic()
    error: str | None = None
    tokens_in = tokens_out = 0
    answered_model = model
    try:
        completion = await client.complete(
            model=model,
            system=prompt.system,
            messages=messages,
            schema=schema,
            max_tokens=gateway.max_output_tokens_of(entry),
        )
        tokens_in, tokens_out = completion.tokens_in, completion.tokens_out
        answered_model = completion.model or model
        if not isinstance(completion.data, dict):
            error = "Antwort ist kein gültiges JSON."
    except providers.ProviderError as exc:
        error = str(exc)[:_ERROR_MAX]
    except Exception as exc:  # unexpected SDK error: reported, never raised to the page
        error = f"{type(exc).__name__}: {str(exc)[:_ERROR_MAX]}"
    finally:
        await providers.close_client(client)
    duration_ms = int((time.monotonic() - started) * 1000)
    cost = (
        Decimal(tokens_in) * _price(entry, "input_eur_per_mtok")
        + Decimal(tokens_out) * _price(entry, "output_eur_per_mtok")
    ) / gateway.MTOK
    return TierTestResult(
        tier=tier,
        model=answered_model,
        ok=error is None,
        duration_ms=duration_ms,
        error=error,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_eur=cost,
    )


async def check_provider(
    provider: AiProvider, api_key: str, models: dict[str, Any]
) -> list[TierTestResult]:
    """Every configured tier in order; a failing tier does not stop the others."""
    return [
        await check_tier(provider, api_key, tier, entry) for tier, entry in configured_tiers(models)
    ]
