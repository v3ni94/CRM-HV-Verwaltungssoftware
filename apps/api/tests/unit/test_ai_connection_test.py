"""Connection test per tier (settings page) and the output limit per tier, with fake providers
and predefined expected results (rule 0.1.8); no live model calls."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from mhvp.ai import connection_test, gateway, providers
from mhvp.ai.models import AiProvider
from mhvp.ai.providers import Completion, ProviderError


class _Recorder:
    """Answers per model name: a queued exception is raised, anything else is returned."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[dict[str, Any]] = []
        self.closed = 0

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        answer = self.answers[kwargs["model"]]
        if isinstance(answer, Exception):
            raise answer
        return Completion(
            data=answer,
            raw_text=json.dumps(answer),
            tokens_in=40,
            tokens_out=8,
            model=f"{kwargs['model']}-20260901",
        )

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture
def recorder() -> Any:
    holder: dict[str, _Recorder] = {}

    def install(answers: dict[str, Any]) -> _Recorder:
        holder["r"] = _Recorder(answers)
        providers.set_factory(lambda _p, _k: holder["r"])
        return holder["r"]

    yield install
    providers.set_factory(providers.default_factory)


MODELS = {
    "small": {
        "model": "small-model",
        "input_eur_per_mtok": "1",
        "output_eur_per_mtok": "5",
        "max_output_tokens": 4096,
    },
    "large": {"model": "large-model", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
    "embedding": {"model": "embed-model", "input_eur_per_mtok": "0.1", "output_eur_per_mtok": "0"},
}


def test_configured_tiers_skips_embedding_and_empty_models() -> None:
    assert [t for t, _ in connection_test.configured_tiers(MODELS)] == ["small", "large"]
    assert connection_test.configured_tiers({"small": {"model": "  "}, "large": {}}) == []


@pytest.mark.asyncio
async def test_each_tier_gets_one_minimal_call_with_its_output_limit(recorder: Any) -> None:
    rec = recorder(
        {
            "small-model": {"summary": "Verbindungstest erfolgreich", "open_points": []},
            "large-model": {"summary": "Verbindungstest erfolgreich", "open_points": []},
        }
    )
    results = await connection_test.check_provider(AiProvider.ANTHROPIC, "sk-x", MODELS)
    assert [(r.tier, r.ok, r.model) for r in results] == [
        ("small", True, "small-model-20260901"),
        ("large", True, "large-model-20260901"),
    ]
    assert [c["max_tokens"] for c in rec.calls] == [4096, gateway.DEFAULT_MAX_OUTPUT_TOKENS]
    assert all("Verbindungstest" in c["messages"][0]["content"] for c in rec.calls)
    # Cost by hand: 40 * 1 / 1e6 + 8 * 5 / 1e6 = 0.00008 EUR for the small tier.
    assert results[0].cost_eur == Decimal("0.00008")
    assert results[0].tokens_in == 40
    assert results[0].tokens_out == 8
    assert results[0].duration_ms >= 0
    assert rec.closed == 2  # the client is closed after every call


@pytest.mark.asyncio
async def test_provider_error_is_reported_per_tier_and_does_not_stop_the_others(
    recorder: Any,
) -> None:
    recorder(
        {
            "small-model": ProviderError("HTTP 404: model not found", retryable=False),
            "large-model": {"summary": "ok", "open_points": []},
        }
    )
    results = await connection_test.check_provider(AiProvider.OPENAI, "sk-x", MODELS)
    assert results[0].ok is False
    assert results[0].error == "HTTP 404: model not found"
    assert results[0].model == "small-model"  # no answer, the configured name is reported
    assert results[0].cost_eur == 0
    assert results[1].ok is True
    assert results[1].error is None


@pytest.mark.asyncio
async def test_non_json_answer_counts_as_failure(recorder: Any) -> None:
    recorder({"small-model": None, "large-model": {"summary": "ok", "open_points": []}})
    results = await connection_test.check_provider(AiProvider.ANTHROPIC, "sk-x", MODELS)
    assert results[0].ok is False
    assert results[0].error == "Antwort ist kein gültiges JSON."


def test_max_output_tokens_of_defaults_and_rejects_unusable_values() -> None:
    assert gateway.max_output_tokens_of({}) == 16000
    assert gateway.max_output_tokens_of({"max_output_tokens": None}) == 16000
    assert gateway.max_output_tokens_of({"max_output_tokens": 8192}) == 8192
    assert gateway.max_output_tokens_of({"max_output_tokens": "32000"}) == 32000
    assert gateway.max_output_tokens_of({"max_output_tokens": 0}) == 16000
    assert gateway.max_output_tokens_of({"max_output_tokens": "abc"}) == 16000


@pytest.mark.asyncio
async def test_complete_with_retry_passes_the_tier_limit(recorder: Any) -> None:
    rec = recorder({"m": {"summary": "ok", "open_points": []}})
    await gateway._complete_with_retry(rec, "m", "sys", [], {}, max_tokens=2048)
    await gateway._complete_with_retry(rec, "m", "sys", [], {})
    assert [c["max_tokens"] for c in rec.calls] == [2048, gateway.DEFAULT_MAX_OUTPUT_TOKENS]
