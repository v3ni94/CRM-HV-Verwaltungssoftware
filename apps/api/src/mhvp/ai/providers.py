"""Provider clients behind one protocol (9.1): Anthropic and OpenAI (M7-02).

Endpoint region (M7-07): ``AiProviderConfig.endpoint_region`` is resolved here, per provider,
into what the SDK documents:

* OpenAI: a region specific base URL (``REGION_BASE_URLS``). Only the listed regions are
  accepted; an unknown value is rejected at configuration time (``validate_region``).
* Anthropic: no region specific base URL exists for the first party API; data residency is
  the documented request parameter ``inference_geo`` of the Messages API, which is sent with
  every call. The SDK does not enumerate the accepted values, so only the format is checked
  here and the provider validates the value itself (a wrong value fails the connection test
  with the provider's own error text). Whether the DPA covers the chosen region stays an
  operator decision (docs/OPEN_QUESTIONS.md M7-07).
"""

import inspect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
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
class ToolCall:
    """A lookup the model asks for (tool use, ``mhvp.ai.tool_use``): tool name and arguments."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


def tool_calls_of(data: Any) -> list[ToolCall]:
    """Tool calls of a structured answer (``{"tool_calls": [{"name", "arguments"}]}``, the
    provider neutral form of tool use: both adapters return JSON by schema). Malformed entries
    are dropped."""
    if not isinstance(data, dict):
        return []
    raw = data.get("tool_calls")
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            args = item.get("arguments")
            out.append(ToolCall(item["name"], args if isinstance(args, dict) else {}))
    return out


@dataclass
class Completion:
    data: Any  # parsed JSON (not yet schema validated)
    raw_text: str
    tokens_in: int
    tokens_out: int
    model: str
    # Lookups the model asked for (empty without tool use). Filled from ``data`` by the
    # adapters; recorded test clients may set it directly.
    tool_calls: list[ToolCall] = field(default_factory=list)


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


@dataclass
class Embeddings:
    """Result of one embedding call (M7-03): one vector per input, in input order."""

    vectors: list[list[float]]
    tokens_in: int
    model: str


class EmbeddingClient(Protocol):
    async def embed(self, *, model: str, inputs: list[str]) -> Embeddings: ...


def supports_embeddings(client: object) -> bool:
    """Only the OpenAI adapter embeds (Anthropic offers no embeddings, M7-03)."""
    return callable(getattr(client, "embed", None))


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


# Region handling per provider (M7-07). Values are stored lower case without surrounding blanks.
REGION_BASE_URLS: dict[AiProvider, dict[str, str | None]] = {
    # OpenAI data residency: the EU endpoint is a separate base URL; "us" and "global" use the
    # SDK default (api.openai.com).
    AiProvider.OPENAI: {
        "eu": "https://eu.api.openai.com/v1",
        "us": None,
        "global": None,
    },
}
_REGION_FORMAT = re.compile(r"^[a-z]{2,16}(-[a-z0-9]{1,16})?$")


def normalize_region(value: str | None) -> str | None:
    """Empty stays empty; otherwise trimmed and lower case."""
    if value is None:
        return None
    text = value.strip().lower()
    return text or None


def validate_region(provider: AiProvider, value: str | None) -> str | None:
    """Normalized region, or ``ValueError`` (German text for the API problem) when the provider
    does not support it. ``None`` always means the provider's default endpoint."""
    region = normalize_region(value)
    if region is None:
        return None
    supported = REGION_BASE_URLS.get(provider)
    if supported is not None:
        if region not in supported:
            raise ValueError(
                f"Endpunktregion '{region}' wird für {provider.value} nicht unterstützt. "
                f"Zulässig: {', '.join(sorted(supported))} oder leer (Standardendpunkt)."
            )
        return region
    if not _REGION_FORMAT.match(region):
        raise ValueError(
            f"Endpunktregion '{region}' hat kein gültiges Format für {provider.value} "
            "(Kleinbuchstaben, z. B. 'us')."
        )
    return region


def base_url_for(provider: AiProvider, region: str | None) -> str | None:
    """Region specific base URL of the provider, ``None`` for the SDK default."""
    normalized = normalize_region(region)
    if normalized is None:
        return None
    return REGION_BASE_URLS.get(provider, {}).get(normalized)


class AnthropicClient:
    """Messages API with structured output (``output_config.format`` json_schema).
    ``inference_geo`` is the region of the tenant configuration (M7-07); ``None`` leaves the
    workspace default of the provider."""

    def __init__(
        self,
        api_key: str,
        *,
        inference_geo: str | None = None,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=1)
        self._inference_geo = normalize_region(inference_geo)

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
            if self._inference_geo is not None:
                request["inference_geo"] = self._inference_geo
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
            tool_calls=tool_calls_of(data),
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
            tool_calls=tool_calls_of(data),
        )

    async def embed(self, *, model: str, inputs: list[str]) -> Embeddings:
        """Embeddings API (M7-03): ``text-embedding-3-small`` by default (operator entered in
        ``models["embedding"]``). Same error mapping as ``complete``; the base URL (EU region)
        applies unchanged."""
        try:
            response = await self._client.embeddings.create(
                model=model, input=inputs, encoding_format="float"
            )
        except openai.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        rows = sorted(response.data, key=lambda item: item.index)
        if len(rows) != len(inputs):
            raise ProviderError(f"embedding count mismatch ({len(rows)} of {len(inputs)})")
        usage = response.usage
        return Embeddings(
            vectors=[[float(v) for v in row.embedding] for row in rows],
            tokens_in=usage.prompt_tokens if usage else 0,
            model=response.model,
        )


ClientFactory = Callable[[AiProvider, str, str | None], ProviderClient]


# Tests and the evaluation replace this factory with recorded responses.
def default_factory(
    provider: AiProvider, api_key: str, endpoint_region: str | None = None
) -> ProviderClient:
    if provider is AiProvider.ANTHROPIC:
        return AnthropicClient(api_key, inference_geo=endpoint_region)
    if provider is AiProvider.OPENAI:
        return OpenAIClient(api_key, base_url=base_url_for(provider, endpoint_region))
    raise ProviderError(f"provider {provider.value} is not implemented")


_factory: ClientFactory = default_factory


def _accepts_region(factory: Callable[..., ProviderClient]) -> bool:
    try:
        params = list(inspect.signature(factory).parameters.values())
    except (TypeError, ValueError):
        return True
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params):
        return True
    positional = [
        p
        for p in params
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 3


def set_factory(factory: Callable[..., ProviderClient]) -> None:
    """Installs a client factory ``(provider, api_key, endpoint_region)``. A two argument
    factory (recorded test clients) is still accepted; it never sees the region."""
    global _factory
    if _accepts_region(factory):
        _factory = factory
    else:
        two_arg = factory

        def _wrapped(provider: AiProvider, api_key: str, _region: str | None) -> ProviderClient:
            return two_arg(provider, api_key)

        _factory = _wrapped


def client_for(
    provider: AiProvider, api_key: str, endpoint_region: str | None = None
) -> ProviderClient:
    client: ProviderClient = _factory(provider, api_key, normalize_region(endpoint_region))
    return client
