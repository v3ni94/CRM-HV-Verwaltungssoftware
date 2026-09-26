"""Provider clients behind one protocol (9.1): Anthropic and OpenAI (M7-02)."""

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic
import openai

from mhvp.ai.models import AiProvider


class ProviderError(Exception):
    """Call failed; ``retryable`` marks rate limits, overload and network problems."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


_DETAIL_MAX = 300
# Provider secrets never reach the error text (rule 0.1.13), even if a provider echoed one.
_SECRET = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+)")


def status_detail(exc: object, status_code: int) -> str:
    """Error text for an HTTP status error: ``HTTP <status>`` plus the provider's message (or an
    excerpt of the response body), truncated to ``_DETAIL_MAX`` characters and stripped of
    anything that looks like a key. The API key itself is never part of an SDK error."""
    message = str(getattr(exc, "message", "") or "").strip()
    body = getattr(exc, "body", None)
    # The SDK message is "Error code: <status> - <body>"; prefer the provider's own message.
    if (not message or message.startswith("Error code:")) and body is not None:
        nested = body.get("error") if isinstance(body, dict) else None
        provider_message = (
            nested.get("message")
            if isinstance(nested, dict)
            else body.get("message")
            if isinstance(body, dict)
            else None
        )
        if isinstance(provider_message, str) and provider_message.strip():
            message = provider_message
        else:
            try:
                message = json.dumps(body, ensure_ascii=False)
            except (TypeError, ValueError):
                message = str(body)
    message = _SECRET.sub("[entfernt]", " ".join(message.split()))
    if len(message) > _DETAIL_MAX:
        message = message[: _DETAIL_MAX - 1] + "…"
    return f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}"


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


async def close_client(client: object) -> None:
    """Closes a provider client at the end of a job. The SDK clients would otherwise schedule
    their HTTP shutdown from ``__del__`` after ``asyncio.run`` has already closed the loop
    ("Event loop is closed" in the worker log). Recorded test clients have no ``aclose``."""
    closer = getattr(client, "aclose", None)
    if closer is None:
        return
    try:
        await closer()
    except Exception:  # closing must never mask the job result
        return


class AnthropicClient:
    """Messages API with structured output (``output_config.format`` json_schema)."""

    def __init__(self, api_key: str, *, client: anthropic.AsyncAnthropic | None = None) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=1)

    async def aclose(self) -> None:
        await self._client.close()

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
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
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


class OpenAIClient:
    """Chat Completions with structured output (``response_format`` json_schema, strict).
    ``base_url`` allows an EU endpoint or a compatible gateway (9.4, endpoint_region)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self._client = client or openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, max_retries=1
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> Completion:
        request: dict[str, Any] = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": schema, "strict": False},
            },
        }
        try:
            response = await self._client.chat.completions.create(**request)
        except openai.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        if not response.choices:
            raise ProviderError("empty response")
        choice = response.choices[0]
        if choice.message.refusal:
            raise ProviderError("refusal")
        if choice.finish_reason == "length":
            raise ProviderError("output truncated (max_tokens)")
        text = choice.message.content or ""
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        usage = response.usage
        return Completion(
            data=data,
            raw_text=text,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            model=response.model,
        )


# Tests and the evaluation replace this factory with recorded responses.
def default_factory(provider: AiProvider, api_key: str) -> ProviderClient:
    if provider is AiProvider.ANTHROPIC:
        return AnthropicClient(api_key)
    if provider is AiProvider.OPENAI:
        return OpenAIClient(api_key)
    raise ProviderError(f"provider {provider.value} is not implemented")


_factory = default_factory


def set_factory(factory: Any) -> None:
    global _factory
    _factory = factory


def client_for(provider: AiProvider, api_key: str) -> ProviderClient:
    client: ProviderClient = _factory(provider, api_key)
    return client
