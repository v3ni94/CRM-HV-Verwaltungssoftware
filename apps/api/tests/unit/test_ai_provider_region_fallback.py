"""M7-07 endpoint region pass-through and M7-02 fallback on provider errors (no network:
fake transports only). Budget fallback needs the database and is covered in
``tests/integration/test_m7_ai.py::test_routing_strategy_and_fallback``."""

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import gateway, providers
from mhvp.ai.models import AiProvider, AiProviderConfig, AiTask
from mhvp.ai.providers import (
    AnthropicClient,
    Completion,
    OpenAIClient,
    ProviderError,
    base_url_for,
    validate_region,
)

SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _restore_factory():  # type: ignore[no-untyped-def]
    yield
    providers.set_factory(providers.default_factory)


# Region validation -------------------------------------------------------------------------


def test_openai_region_is_validated_against_the_supported_list() -> None:
    assert validate_region(AiProvider.OPENAI, None) is None
    assert validate_region(AiProvider.OPENAI, "  ") is None
    assert validate_region(AiProvider.OPENAI, " EU ") == "eu"
    assert validate_region(AiProvider.OPENAI, "us") == "us"
    with pytest.raises(ValueError, match="nicht unterstützt"):
        validate_region(AiProvider.OPENAI, "apac")


def test_anthropic_region_is_format_checked_only() -> None:
    # No base URL list for Anthropic: the value goes to the provider as inference_geo.
    assert validate_region(AiProvider.ANTHROPIC, "US") == "us"
    assert validate_region(AiProvider.ANTHROPIC, None) is None
    with pytest.raises(ValueError, match="Format"):
        validate_region(AiProvider.ANTHROPIC, "Region Nord!")


def test_base_url_per_provider_and_region() -> None:
    assert base_url_for(AiProvider.OPENAI, "eu") == "https://eu.api.openai.com/v1"
    assert base_url_for(AiProvider.OPENAI, "us") is None
    assert base_url_for(AiProvider.OPENAI, None) is None
    assert base_url_for(AiProvider.ANTHROPIC, "eu") is None


def test_default_factory_builds_openai_client_with_regional_base_url() -> None:
    eu = providers.default_factory(AiProvider.OPENAI, "k", "eu")
    assert isinstance(eu, OpenAIClient)
    assert str(eu._client.base_url).startswith("https://eu.api.openai.com/v1")
    default = providers.default_factory(AiProvider.OPENAI, "k", None)
    assert isinstance(default, OpenAIClient)
    assert str(default._client.base_url).startswith("https://api.openai.com/v1")


# Anthropic: inference_geo ------------------------------------------------------------------


class FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            model="claude-haiku-4-5",
            content=[SimpleNamespace(type="text", text='{"summary": "ok"}')],
            usage=SimpleNamespace(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )


async def test_anthropic_client_sends_inference_geo_only_when_configured() -> None:
    messages = FakeMessages()
    fake = SimpleNamespace(messages=messages)
    with_region = AnthropicClient("k", inference_geo="US", client=fake)  # type: ignore[arg-type]
    result = await with_region.complete(
        model="m",
        system="s",
        messages=[{"role": "user", "content": "x"}],
        schema=SCHEMA,
        max_tokens=5,
    )
    assert result.data == {"summary": "ok"}
    assert messages.calls[0]["inference_geo"] == "us"

    without = AnthropicClient("k", client=fake)  # type: ignore[arg-type]
    await without.complete(model="m", system="s", messages=[], schema=SCHEMA, max_tokens=5)
    assert "inference_geo" not in messages.calls[1]


# Factory signatures ------------------------------------------------------------------------


def test_client_for_passes_the_region_to_a_three_argument_factory() -> None:
    seen: list[tuple[AiProvider, str, str | None]] = []

    def factory(provider: AiProvider, key: str, region: str | None) -> Any:
        seen.append((provider, key, region))
        return SimpleNamespace()

    providers.set_factory(factory)
    providers.client_for(AiProvider.OPENAI, "k", " EU ")
    providers.client_for(AiProvider.ANTHROPIC, "k")
    assert seen == [(AiProvider.OPENAI, "k", "eu"), (AiProvider.ANTHROPIC, "k", None)]


def test_two_argument_test_factories_still_work() -> None:
    marker = SimpleNamespace()
    providers.set_factory(lambda _p, _k: marker)
    assert providers.client_for(AiProvider.OPENAI, "k", "eu") is marker


# Fallback in _call_plan --------------------------------------------------------------------


def _route(provider: AiProvider, model: str) -> gateway.Route:
    config = AiProviderConfig(
        provider=provider,
        api_key="secret-" + provider.value,
        models={},
        task_tiers={},
        monthly_budget_eur=Decimal("100"),
        endpoint_region="eu" if provider is AiProvider.OPENAI else None,
    )
    return gateway.Route(config, model, Decimal("1"), Decimal("5"))


class RecordingFactory:
    """Fake transport: records (provider, region) per call; listed providers fail with a 503."""

    def __init__(self, failing: set[str]) -> None:
        self.failing = failing
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, provider: AiProvider, _key: str, region: str | None) -> Any:
        factory = self

        class Client:
            async def complete(self, **kwargs: Any) -> Completion:
                factory.calls.append((provider.value, region))
                if provider.value in factory.failing:
                    raise ProviderError("HTTP 503: upstream overloaded", retryable=True)
                data = {"summary": f"von {provider.value}", "open_points": []}
                return Completion(
                    data=data,
                    raw_text=json.dumps(data),
                    tokens_in=100,
                    tokens_out=50,
                    model=kwargs["model"],
                )

        return Client()


async def test_call_plan_falls_back_to_the_secondary_on_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway, "RETRY_DELAYS_S", ())
    factory = RecordingFactory(failing={"anthropic"})
    providers.set_factory(factory)
    plan = [
        (_route(AiProvider.ANTHROPIC, "claude-haiku-4-5"), Decimal(0), Decimal(100)),
        (_route(AiProvider.OPENAI, "gpt-5-mini"), Decimal(0), Decimal(100)),
    ]
    keys = {r.config.provider: r.config.api_key or "" for r, _, _ in plan}
    result = await gateway._call_plan(
        plan, keys, "system", [{"role": "user", "content": "x"}], SCHEMA, AiTask.SUMMARIZE
    )
    assert result.output == {"summary": "von openai", "open_points": []}
    assert result.chosen.config.provider is AiProvider.OPENAI
    assert result.skips == ["anthropic: Anbieterfehler: HTTP 503: upstream overloaded"]
    # The primary is tried once (no retry delay), then the secondary with its own region.
    assert factory.calls == [("anthropic", None), ("openai", "eu")]
    assert "secret" not in json.dumps(result.skips)


async def test_call_plan_without_secondary_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gateway, "RETRY_DELAYS_S", ())
    factory = RecordingFactory(failing={"anthropic"})
    providers.set_factory(factory)
    plan = [(_route(AiProvider.ANTHROPIC, "claude-haiku-4-5"), Decimal(0), Decimal(100))]
    result = await gateway._call_plan(
        plan, {AiProvider.ANTHROPIC: "k"}, "system", [], SCHEMA, AiTask.SUMMARIZE
    )
    assert result.output is None
    assert result.error == "Anbieterfehler: HTTP 503: upstream overloaded"
    assert result.chosen.config.provider is AiProvider.ANTHROPIC
    assert factory.calls == [("anthropic", None)]
