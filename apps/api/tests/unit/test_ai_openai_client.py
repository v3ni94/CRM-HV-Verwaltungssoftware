"""OpenAI adapter (M7-02): structured output request, usage mapping, refusal and truncation."""

from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai.providers import OpenAIClient, ProviderError

SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}}


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def _client(response: Any) -> tuple[OpenAIClient, FakeCompletions]:
    completions = FakeCompletions(response)
    fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIClient("k", client=fake), completions  # type: ignore[arg-type]


def _response(content: str | None, *, finish: str = "stop", refusal: str | None = None) -> Any:
    return SimpleNamespace(
        model="gpt-4.1-2025-04-14",
        choices=[
            SimpleNamespace(
                finish_reason=finish, message=SimpleNamespace(content=content, refusal=refusal)
            )
        ],
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30),
    )


async def test_structured_request_and_usage() -> None:
    client, completions = _client(_response('{"summary": "ok"}'))
    result = await client.complete(
        model="gpt-4.1",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        schema=SCHEMA,
        max_tokens=500,
    )
    assert result.data == {"summary": "ok"}
    assert (result.tokens_in, result.tokens_out, result.model) == (120, 30, "gpt-4.1-2025-04-14")
    call = completions.calls[0]
    assert call["messages"][0] == {"role": "system", "content": "sys"}
    assert call["response_format"]["json_schema"]["schema"] == SCHEMA
    assert call["max_completion_tokens"] == 500


async def test_refusal_and_truncation() -> None:
    client, _ = _client(_response(None, refusal="no"))
    with pytest.raises(ProviderError, match="refusal"):
        await client.complete(model="m", system="s", messages=[], schema=SCHEMA, max_tokens=1)
    client, _ = _client(_response("{", finish="length"))
    with pytest.raises(ProviderError, match="truncated"):
        await client.complete(model="m", system="s", messages=[], schema=SCHEMA, max_tokens=1)
