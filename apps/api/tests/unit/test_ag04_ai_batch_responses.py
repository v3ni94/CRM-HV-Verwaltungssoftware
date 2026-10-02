"""AG04 (GAB-10, GAB-09): OpenAI Responses API with strict Structured Outputs and fallback to
Chat Completions; Anthropic Message Batches (submit and poll) and the batch capture. Recorded
responses (SDK objects as ``SimpleNamespace``), no network.

Expected values by hand: an optional property becomes ``anyOf [schema, null]`` and required;
every object gets ``additionalProperties`` false; a ``null`` for an optional property is
removed from the parsed answer; a 404 of ``/responses`` falls back once to Chat Completions,
a 503 does not; a batch request with an identical key is answered from the results."""

from types import SimpleNamespace
from typing import Any

import openai
import pytest

from mhvp.ai import batch, providers
from mhvp.ai.models import AiProvider
from mhvp.ai.providers import (
    AnthropicClient,
    BatchRequest,
    Completion,
    OpenAIClient,
    ProviderError,
    drop_added_nulls,
    strict_schema,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "open_points": {"type": "array", "items": {"$ref": "#/$defs/Point"}, "default": []},
    },
    "required": ["summary"],
    "$defs": {
        "Point": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "due": {"type": "string"}},
            "required": ["text"],
        }
    },
}


def test_strict_schema_closes_objects_and_requires_every_property() -> None:
    out = strict_schema(SCHEMA)
    assert out["additionalProperties"] is False
    assert out["required"] == ["summary", "open_points"]
    assert out["properties"]["summary"] == {"type": "string"}
    open_points = out["properties"]["open_points"]
    assert open_points == {
        "anyOf": [{"type": "array", "items": {"$ref": "#/$defs/Point"}}, {"type": "null"}]
    }
    point = out["$defs"]["Point"]
    assert point["required"] == ["text", "due"]
    assert point["additionalProperties"] is False
    assert point["properties"]["due"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert "default" not in str(out)
    assert SCHEMA["required"] == ["summary"]  # the input stays unchanged


def test_drop_added_nulls_removes_only_optional_nulls() -> None:
    data = {"summary": None, "open_points": [{"text": "a", "due": None}]}
    assert drop_added_nulls(data, SCHEMA) == {"summary": None, "open_points": [{"text": "a"}]}
    assert drop_added_nulls({"summary": "x", "open_points": None}, SCHEMA) == {"summary": "x"}


# OpenAI ----------------------------------------------------------------------------------


class _Create:
    def __init__(self, result: Any) -> None:
        self.result, self.calls = result, []  # type: ignore[var-annotated]

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _status_error(status: int) -> openai.APIStatusError:
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status, request=request, json={"error": {"message": "nope"}})
    cls = openai.NotFoundError if status == 404 else openai.InternalServerError
    return cls("nope", response=response, body={"error": {"message": "nope"}})


def _resp(text: str, *, status: str = "completed", reason: str | None = None) -> Any:
    return SimpleNamespace(
        model="gpt-5-recorded",
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        output=[SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text")])],
        output_text=text,
        usage=SimpleNamespace(input_tokens=111, output_tokens=22),
    )


def _chat(text: str) -> Any:
    return SimpleNamespace(
        model="gpt-chat-recorded",
        choices=[
            SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content=text, refusal=None)
            )
        ],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
    )


def _openai(responses: Any, chat: Any) -> tuple[OpenAIClient, _Create, _Create]:
    r, c = _Create(responses), _Create(chat)
    fake = SimpleNamespace(responses=r, chat=SimpleNamespace(completions=c))
    return OpenAIClient("k", client=fake), r, c  # type: ignore[arg-type]


async def _complete(client: Any) -> Completion:
    result: Completion = await client.complete(
        model="gpt-5",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        schema=SCHEMA,
        max_tokens=300,
    )
    return result


async def test_openai_responses_request_is_strict_and_parsed() -> None:
    client, responses, chat = _openai(_resp('{"summary": "ok", "open_points": null}'), None)
    result = await _complete(client)
    assert result.data == {"summary": "ok"}
    assert (result.tokens_in, result.tokens_out, result.model) == (111, 22, "gpt-5-recorded")
    call = responses.calls[0]
    assert call["instructions"] == "sys"
    assert call["input"] == [{"role": "user", "content": "hi"}]
    assert call["max_output_tokens"] == 300
    assert call["store"] is False
    fmt = call["text"]["format"]
    assert (fmt["type"], fmt["name"], fmt["strict"]) == ("json_schema", "output", True)
    assert fmt["schema"] == strict_schema(SCHEMA)
    assert chat.calls == []


async def test_openai_refusal_and_truncation() -> None:
    refused = _resp("")
    refused.output = [SimpleNamespace(type="message", content=[SimpleNamespace(type="refusal")])]
    client, _, _ = _openai(refused, None)
    with pytest.raises(ProviderError, match="refusal"):
        await _complete(client)
    client, _, _ = _openai(_resp("{", status="incomplete", reason="max_output_tokens"), None)
    with pytest.raises(ProviderError, match="truncated"):
        await _complete(client)


async def test_openai_falls_back_to_chat_on_client_error_only() -> None:
    client, responses, chat = _openai(_status_error(404), _chat('{"summary": "chat"}'))
    result = await _complete(client)
    assert result.data == {"summary": "chat"}
    assert result.model == "gpt-chat-recorded"
    assert len(responses.calls) == 1
    assert len(chat.calls) == 1
    assert chat.calls[0]["response_format"]["json_schema"]["strict"] is False
    client, _, chat = _openai(_status_error(503), _chat("{}"))
    with pytest.raises(ProviderError) as info:
        await _complete(client)
    assert info.value.retryable
    assert chat.calls == []


# Anthropic Message Batches -----------------------------------------------------------------


def _message(text: str, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=None,
        ),
        model="claude-recorded",
    )


class _Results:
    def __init__(self, entries: list[Any]) -> None:
        self.entries = entries

    def __aiter__(self) -> Any:
        async def gen() -> Any:
            for e in self.entries:
                yield e

        return gen()


class _Batches:
    def __init__(self, status: str, entries: list[Any]) -> None:
        self.status, self.entries, self.created = status, entries, []  # type: ignore[var-annotated]

    async def create(self, *, requests: list[Any]) -> Any:
        self.created.append(requests)
        return SimpleNamespace(id="msgbatch_recorded")

    async def retrieve(self, batch_id: str) -> Any:
        return SimpleNamespace(id=batch_id, processing_status=self.status)

    async def results(self, batch_id: str) -> _Results:
        return _Results(self.entries)


def _anthropic(status: str = "ended", entries: list[Any] | None = None) -> Any:
    batches = _Batches(status, entries or [])
    fake = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    return AnthropicClient("k", inference_geo="eu", client=fake), batches  # type: ignore[arg-type]


REQ = BatchRequest(
    custom_id="a" * 64,
    model="claude-x",
    system="sys",
    messages=[{"role": "user", "content": "u"}],
    schema=SCHEMA,
    max_tokens=99,
)


async def test_anthropic_submit_batch_sends_message_params() -> None:
    client, batches = _anthropic()
    assert await client.submit_batch([REQ]) == "msgbatch_recorded"
    sent = batches.created[0][0]
    assert sent["custom_id"] == "a" * 64
    params = sent["params"]
    assert params["model"] == "claude-x"
    assert params["max_tokens"] == 99
    assert params["output_config"] == {"format": {"type": "json_schema", "schema": SCHEMA}}
    assert params["inference_geo"] == "eu"
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}


async def test_anthropic_poll_batch_maps_results() -> None:
    client, _ = _anthropic("in_progress")
    assert (await client.poll_batch("b")).ended is False
    entries = [
        SimpleNamespace(
            custom_id="ok",
            result=SimpleNamespace(type="succeeded", message=_message('{"summary": "b"}')),
        ),
        SimpleNamespace(
            custom_id="cut",
            result=SimpleNamespace(type="succeeded", message=_message("{", "max_tokens")),
        ),
        SimpleNamespace(custom_id="gone", result=SimpleNamespace(type="expired")),
    ]
    client, _ = _anthropic("ended", entries)
    poll = await client.poll_batch("b")
    assert poll.ended
    ok = poll.results["ok"]
    assert isinstance(ok, Completion)
    assert ok.data == {"summary": "b"}
    assert ok.tokens_in == 10
    assert isinstance(poll.results["cut"], ProviderError)
    assert str(poll.results["gone"]) == "batch result expired"


# Capture ------------------------------------------------------------------------------------


class _Inner:
    def __init__(self, batch_capable: bool) -> None:
        self.calls = 0
        if batch_capable:
            self.submit_batch = self.poll_batch = lambda *_a: None

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls += 1
        return Completion(data={}, raw_text="{}", tokens_in=1, tokens_out=1, model="sync")


async def test_capture_records_replays_and_passes_through() -> None:
    cap = batch.Capture(frozenset({AiProvider.ANTHROPIC}))
    args: dict[str, Any] = {
        "model": "m",
        "system": "s",
        "messages": [{"role": "user", "content": "u"}],
        "schema": SCHEMA,
        "max_tokens": 5,
    }
    inner = _Inner(batch_capable=True)
    token = providers.batch_capture.set(cap)
    try:
        providers.set_factory(lambda _p, _k: inner)
        client = providers.client_for(AiProvider.ANTHROPIC, "k")
        with pytest.raises(batch.BatchPending):
            await client.complete(**args)
        key = batch.request_key(AiProvider.ANTHROPIC, "m", "s", args["messages"], SCHEMA, 5)
        assert list(cap.pending) == [key]
        assert len(key) == 64
        assert inner.calls == 0
        answer = Completion(
            data={"summary": "r"}, raw_text="", tokens_in=1, tokens_out=1, model="b"
        )
        cap.results[key] = answer
        assert await client.complete(**args) is answer
        assert cap.replayed == 1
        cap.results[key] = ProviderError("batch result errored")
        with pytest.raises(ProviderError):
            await client.complete(**args)
        # A provider without batch support (OpenAI here) is called synchronously.
        sync_inner = _Inner(batch_capable=False)
        providers.set_factory(lambda _p, _k: sync_inner)
        other = providers.client_for(AiProvider.OPENAI, "k")
        assert (await other.complete(**args)).model == "sync"
        assert cap.sync_calls == 1
    finally:
        providers.batch_capture.reset(token)
        providers.set_factory(providers.default_factory)
    assert providers.batch_capture.get() is None


def test_pending_detection_inside_exception_groups() -> None:
    assert batch._is_pending(BaseExceptionGroup("g", [batch.BatchPending("k")]))
    assert not batch._is_pending(ValueError("x"))
    assert batch.MODE == batch.MODE_NIGHTLY
