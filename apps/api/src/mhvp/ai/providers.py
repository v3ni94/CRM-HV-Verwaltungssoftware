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
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
import openai

from mhvp.ai.models import AiProvider

# Set by ``ai.batch`` while a deferred run is captured for or replayed from a provider batch.
batch_capture: ContextVar[Any] = ContextVar("mhvp_ai_batch_capture", default=None)


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


@dataclass
class BatchRequest:
    """One request of a provider batch; same parameters as ``ProviderClient.complete``."""

    custom_id: str
    model: str
    system: str
    messages: list[dict[str, str]]
    schema: dict[str, Any]
    max_tokens: int


@dataclass
class BatchPoll:
    ended: bool
    results: dict[str, "Completion | ProviderError"] = field(default_factory=dict)


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


# Strict schema normalization (OpenAI Structured Outputs, GAB-10) ---------------------------
_NESTED_SCHEMA_KEYS = ("items", "additionalItems", "not")
_SCHEMA_LIST_KEYS = ("anyOf", "oneOf", "allOf", "prefixItems")


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Copy of ``schema`` in the form strict mode accepts: every object closed
    (``additionalProperties`` false) with all properties required; a property that was not
    required becomes ``anyOf [original, {"type": "null"}]``. ``default`` is dropped (strict
    mode has no defaults; the task model applies its own after ``drop_added_nulls``)."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        out = {k: v for k, v in node.items() if k != "default"}
        for key in _NESTED_SCHEMA_KEYS:
            if isinstance(out.get(key), dict):
                out[key] = walk(out[key])
        for key in _SCHEMA_LIST_KEYS:
            if isinstance(out.get(key), list):
                out[key] = walk(out[key])
        for key in ("$defs", "definitions"):
            if isinstance(out.get(key), dict):
                out[key] = {name: walk(sub) for name, sub in out[key].items()}
        props = out.get("properties")
        if out.get("type") == "object" or isinstance(props, dict):
            props = props if isinstance(props, dict) else {}
            required = set(out.get("required") or [])
            new_props: dict[str, Any] = {}
            for name, sub in props.items():
                walked = walk(sub)
                if name not in required and not _is_nullable(walked):
                    walked = {"anyOf": [walked, {"type": "null"}]}
                new_props[name] = walked
            out["properties"] = new_props
            out["required"] = list(new_props)
            out["additionalProperties"] = False
        return out

    result: dict[str, Any] = walk(schema)
    return result


def _is_nullable(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    kind = node.get("type")
    if kind == "null" or (isinstance(kind, list) and "null" in kind):
        return True
    return any(_is_nullable(n) for n in node.get("anyOf") or [])


def drop_added_nulls(data: Any, schema: dict[str, Any]) -> Any:
    """Removes the ``null`` values strict mode forces for properties that the original schema
    did not require, so the task model treats them as absent (its defaults apply)."""
    defs = {**(schema.get("definitions") or {}), **(schema.get("$defs") or {})}

    def resolve(node: Any) -> Any:
        ref = node.get("$ref") if isinstance(node, dict) else None
        if isinstance(ref, str) and ref.rsplit("/", 1)[-1] in defs:
            return defs[ref.rsplit("/", 1)[-1]]
        return node

    def walk(value: Any, node: Any, depth: int = 0) -> Any:
        node = resolve(node)
        if depth > 32 or not isinstance(node, dict):
            return value
        if isinstance(value, dict) and isinstance(node.get("properties"), dict):
            required = set(node.get("required") or [])
            props = node["properties"]
            return {
                k: walk(v, props.get(k), depth + 1)
                for k, v in value.items()
                if not (v is None and k in props and k not in required)
            }
        if isinstance(value, list) and isinstance(node.get("items"), dict):
            return [walk(v, node["items"], depth + 1) for v in value]
        for option in node.get("anyOf") or []:
            option = resolve(option)
            if isinstance(option, dict) and option.get("type") != "null":
                if isinstance(value, dict) and "properties" in option:
                    return walk(value, option, depth + 1)
                if isinstance(value, list) and "items" in option:
                    return walk(value, option, depth + 1)
        return value

    return walk(data, schema)


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

    def _request(
        self,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            # Stable system prompt first so the prefix can be cached (9.3).
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if self._inference_geo is not None:
            request["inference_geo"] = self._inference_geo
        return request

    @staticmethod
    def _completion(response: Any) -> Completion:
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
            request = self._request(model, system, messages, schema, max_tokens)
            response = await self._client.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        return self._completion(response)

    # Message Batches API (9.3, GAB-09) ----------------------------------------------------
    async def submit_batch(self, requests: list[BatchRequest]) -> str:
        """Creates one message batch (``messages.batches.create``); returns its id. Each
        request carries the same parameters as ``complete`` and a ``custom_id``."""
        try:
            batch = await self._client.messages.batches.create(
                requests=[
                    {
                        "custom_id": r.custom_id,
                        "params": self._request(  # type: ignore[typeddict-item]
                            r.model, r.system, r.messages, r.schema, r.max_tokens
                        ),
                    }
                    for r in requests
                ]
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        return str(batch.id)

    async def poll_batch(self, batch_id: str) -> BatchPoll:
        """Status of a batch (``messages.batches.retrieve``); once ``processing_status`` is
        ``ended`` the results (``messages.batches.results``) are mapped per ``custom_id`` to a
        ``Completion`` or a ``ProviderError`` (errored, canceled, expired)."""
        try:
            batch = await self._client.messages.batches.retrieve(batch_id)
            if batch.processing_status != "ended":
                return BatchPoll(ended=False)
            results: dict[str, Completion | ProviderError] = {}
            async for entry in await self._client.messages.batches.results(batch_id):
                result = entry.result
                if result.type == "succeeded":
                    try:
                        results[entry.custom_id] = self._completion(result.message)
                    except ProviderError as exc:
                        results[entry.custom_id] = exc
                else:
                    results[entry.custom_id] = ProviderError(f"batch result {result.type}")
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        return BatchPoll(ended=True, results=results)

    async def cancel_batch(self, batch_id: str) -> None:
        """Cancels a submitted batch at the provider (``messages.batches.cancel``, GAI-610).
        The request carries only the batch id, no content; requests already processed stay
        processed, the remaining ones end as ``canceled``."""
        try:
            await self._client.messages.batches.cancel(batch_id)
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                status_detail(exc, exc.status_code), retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc


def supports_cancel(client: object) -> bool:
    """Whether the provider client can cancel a batch (GAI-610). Only clients with a batch
    path have one; today the Anthropic client."""
    return callable(getattr(client, "cancel_batch", None))


def supports_batch(client: object) -> bool:
    return callable(getattr(client, "submit_batch", None)) and callable(
        getattr(client, "poll_batch", None)
    )


class OpenAIClient:
    """Responses API with Structured Outputs (``text.format`` json_schema, ``strict`` true, 9.1).

    Strict mode needs a normalized schema (``strict_schema``: ``additionalProperties`` false,
    every property required, optional ones nullable via ``anyOf``); the ``null`` the model
    then sends for an optional field is removed again (``drop_added_nulls``) so the task's
    Pydantic model sees the field as absent. When the Responses call is rejected with a client
    error (HTTP 4xx other than 429, for example a compatible gateway without ``/responses``)
    the call falls back once to Chat Completions (``response_format`` json_schema, not strict;
    ADR 0025). ``base_url`` allows an EU endpoint or a compatible gateway (9.4)."""

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
        responses = getattr(self._client, "responses", None)
        if responses is None:
            return await self._complete_chat(model, system, messages, schema, max_tokens)
        request: dict[str, Any] = {
            "model": model,
            "instructions": system,
            "input": messages,
            "max_output_tokens": max_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "output",
                    "schema": strict_schema(schema),
                    "strict": True,
                }
            },
        }
        try:
            response = await responses.create(**request)
        except openai.RateLimitError as exc:
            raise ProviderError("rate limited", retryable=True) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderError(status_detail(exc, exc.status_code), retryable=True) from exc
            return await self._complete_chat(model, system, messages, schema, max_tokens)
        except openai.APIConnectionError as exc:
            raise ProviderError("connection failed", retryable=True) from exc
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            if any(getattr(c, "type", None) == "refusal" for c in item.content or []):
                raise ProviderError("refusal")
        details = getattr(response, "incomplete_details", None)
        if getattr(response, "status", None) == "incomplete":
            reason = getattr(details, "reason", None)
            if reason == "max_output_tokens":
                raise ProviderError("output truncated (max_tokens)")
            raise ProviderError(f"incomplete ({reason or 'unknown'})")
        text = response.output_text or ""
        try:
            data = drop_added_nulls(json.loads(text), schema)
        except ValueError:
            data = None
        usage = response.usage
        return Completion(
            data=data,
            raw_text=text,
            tokens_in=usage.input_tokens if usage else 0,
            tokens_out=usage.output_tokens if usage else 0,
            model=response.model,
            tool_calls=tool_calls_of(data),
        )

    async def _complete_chat(
        self,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> Completion:
        """Fallback: Chat Completions with ``response_format`` json_schema (not strict)."""
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
    capture = batch_capture.get()
    if capture is not None:
        # Provider batch (``ai.batch``, GAB-09): the active recorder may route the call.
        wrapped: ProviderClient = capture.wrap(provider, client)
        return wrapped
    return client
