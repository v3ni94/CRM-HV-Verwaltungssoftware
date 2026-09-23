"""Provider clients behind one protocol (9.1). Only the Anthropic adapter exists (M7-02)."""

import json
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from mhvp.ai.models import AiProvider


class ProviderError(Exception):
    """Call failed; ``retryable`` marks rate limits, overload and network problems."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Completion:
    data: Any  # parsed JSON (not yet schema validated)
    raw_text: str
    tokens_in: int
    tokens_out: int
    model: str


class ProviderClient(Protocol):
    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> Completion: ...


class AnthropicClient:
    """Messages API with structured output (``output_config.format`` json_schema)."""

    def __init__(self, api_key: str, *, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=1)

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> Completion:
        try:
            request: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                # Stable system prompt first so the prefix can be cached (9.3).
                "system": [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
                "messages": messages,
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }
            response = await self._client.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"HTTP {exc.status_code}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        if response.stop_reason == "refusal":
            raise ProviderError("refusal")
        if response.stop_reason == "max_tokens":
            raise ProviderError("output truncated (max_tokens)")
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        return Completion(
            data=data,
            raw_text=text,
            tokens_in=response.usage.input_tokens
            + (response.usage.cache_read_input_tokens or 0)
            + (response.usage.cache_creation_input_tokens or 0),
            tokens_out=response.usage.output_tokens,
            model=response.model,
        )


# Tests and the evaluation replace this factory with recorded responses.
def default_factory(provider: AiProvider, api_key: str) -> ProviderClient:
    if provider is AiProvider.ANTHROPIC:
        return AnthropicClient(api_key)
    raise ProviderError(f"provider {provider.value} is not implemented (M7-02)")


_factory = default_factory


def set_factory(factory: Any) -> None:
    global _factory
    _factory = factory


def client_for(provider: AiProvider, api_key: str) -> ProviderClient:
    client: ProviderClient = _factory(provider, api_key)
    return client
