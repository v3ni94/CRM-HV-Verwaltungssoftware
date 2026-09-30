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


# OpenAI adapter over a mocked HTTP transport (no network) ----------------------------------


def _openai_with(handler: Any) -> OpenAIClient:
    import httpx
    import openai

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sdk = openai.AsyncOpenAI(
        api_key="sk-test-not-real",
        base_url="https://eu.api.openai.com/v1",
        http_client=http,
        max_retries=0,
    )
    return OpenAIClient("sk-test-not-real", client=sdk)


async def test_openai_complete_parses_structured_output_and_usage() -> None:
    import httpx

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m-configured",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"summary": "ok"}',
                            "refusal": None,
                        },
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        )

    client = _openai_with(handler)
    result = await client.complete(
        model="m-configured",
        system="s",
        messages=[{"role": "user", "content": "u"}],
        schema=SCHEMA,
        max_tokens=50,
    )
    assert result.data == {"summary": "ok"}
    assert (result.tokens_in, result.tokens_out) == (12, 3)
    assert seen["url"].startswith("https://eu.api.openai.com/v1/")
    assert seen["body"]["model"] == "m-configured"
    assert seen["body"]["response_format"]["type"] == "json_schema"


@pytest.mark.parametrize(("status", "retryable"), [(429, True), (503, True), (400, False)])
async def test_openai_status_errors_map_to_provider_error(status: int, retryable: bool) -> None:
    import httpx

    client = _openai_with(lambda _r: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(ProviderError) as info:
        await client.complete(model="m", system="s", messages=[], schema=SCHEMA, max_tokens=5)
    assert info.value.retryable is retryable
    assert "sk-test" not in str(info.value)


async def test_openai_timeout_is_a_retryable_provider_error() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _openai_with(handler)
    with pytest.raises(ProviderError) as info:
        await client.complete(model="m", system="s", messages=[], schema=SCHEMA, max_tokens=5)
    assert info.value.retryable is True


async def test_call_plan_falls_back_on_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway, "RETRY_DELAYS_S", ())
    factory = RecordingFactory(failing=set())

    def failing_429(provider: AiProvider, key: str, region: str | None) -> Any:
        client = factory(provider, key, region)
        if provider is AiProvider.ANTHROPIC:

            async def limited(**_kw: Any) -> Completion:
                factory.calls.append((provider.value, region))
                raise ProviderError("rate limited", retryable=True)

            client.complete = limited
        return client

    providers.set_factory(failing_429)
    plan = [
        (_route(AiProvider.ANTHROPIC, "a-model"), Decimal(0), Decimal(100)),
        (_route(AiProvider.OPENAI, "o-model"), Decimal(0), Decimal(100)),
    ]
    keys = {r.config.provider: "k" for r, _, _ in plan}
    result = await gateway._call_plan(plan, keys, "s", [], SCHEMA, AiTask.SUMMARIZE)
    assert result.chosen.config.provider is AiProvider.OPENAI
    assert result.skips == ["anthropic: Anbieterfehler: rate limited"]
    assert factory.calls == [("anthropic", None), ("openai", "eu")]
