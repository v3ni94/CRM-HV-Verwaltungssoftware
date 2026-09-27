"""M7-03 embeddings without a database: chunking, the pgvector text form, the OpenAI embed
adapter with an injected SDK client (no network) and the cost per call."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import embeddings
from mhvp.ai.models import AiProviderConfig, EmbeddingSourceKind
from mhvp.ai.providers import OpenAIClient, ProviderError, supports_embeddings
from mhvp.ai.vector import from_db, to_db


def test_chunk_text_windows_with_overlap_and_line_cuts() -> None:
    assert embeddings.chunk_text("") == []
    assert embeddings.chunk_text("   \n ") == []
    short = "Kurzer Text"
    assert embeddings.chunk_text(short) == [short]
    lines = "\n".join(f"Zeile {i} mit etwas Inhalt" for i in range(200))
    chunks = embeddings.chunk_text(lines, size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    # Cut at a line end when one lies in the second half of the window; every line survives.
    assert all(not c.endswith("mit") for c in chunks)
    joined = "\n".join(chunks)
    assert all(f"Zeile {i} " in joined for i in range(200))
    # Overlap: the start of a chunk repeats the end of the previous one.
    assert chunks[1][:20] in chunks[0] + chunks[1]
    with pytest.raises(ValueError, match="positive"):
        embeddings.chunk_text("x", size=0)


def test_chunk_text_caps_very_long_sources() -> None:
    text = "wort " * (embeddings.CHUNK_CHARS * (embeddings.MAX_CHUNKS_PER_SOURCE + 5) // 5)
    assert len(embeddings.chunk_text(text)) == embeddings.MAX_CHUNKS_PER_SOURCE


def test_vector_text_form_round_trip() -> None:
    assert to_db(None) is None
    assert to_db([1, 0.5, -2]) == "[1.0,0.5,-2.0]"
    assert from_db("[1,0.5,-2]") == [1.0, 0.5, -2.0]
    assert from_db(b"[0.25]") == [0.25]
    assert from_db("[]") == []
    assert from_db(None) is None


def test_masked_source_text_hides_iban_and_mail() -> None:
    document: Any = SimpleNamespace(
        title="Brief", ocr_text="Bitte an max@example.org, IBAN DE89370400440532013000."
    )
    text = embeddings.masked_source_text(EmbeddingSourceKind.DOCUMENT, document)
    assert text.startswith("Brief\n")
    assert "max@example.org" not in text
    assert "DE89370400440532013000" not in text


class FakeEmbeddingsApi:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _client(response: Any) -> tuple[OpenAIClient, FakeEmbeddingsApi]:
    api = FakeEmbeddingsApi(response)
    fake = SimpleNamespace(embeddings=api)
    return OpenAIClient("k", client=fake), api  # type: ignore[arg-type]


def _response(*vectors: list[float], model: str = "text-embedding-3-small") -> Any:
    # Out of order on purpose: the adapter sorts by index.
    data = [SimpleNamespace(index=i, embedding=v) for i, v in reversed(list(enumerate(vectors)))]
    return SimpleNamespace(data=data, usage=SimpleNamespace(prompt_tokens=42), model=model)


async def test_openai_embed_request_and_order() -> None:
    client, api = _client(_response([0.1, 0.2], [0.3, 0.4]))
    assert supports_embeddings(client)
    result = await client.embed(model="text-embedding-3-small", inputs=["a", "b"])
    assert result.vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert (result.tokens_in, result.model) == (42, "text-embedding-3-small")
    call = api.calls[0]
    assert call["model"] == "text-embedding-3-small"
    assert call["input"] == ["a", "b"]
    assert call["encoding_format"] == "float"


async def test_openai_embed_count_mismatch_is_an_error() -> None:
    client, _ = _client(_response([0.1, 0.2]))
    with pytest.raises(ProviderError, match="mismatch"):
        await client.embed(model="m", inputs=["a", "b"])


def test_anthropic_style_client_has_no_embeddings() -> None:
    assert not supports_embeddings(SimpleNamespace(complete=lambda **_: None))


def test_cost_uses_input_price_only() -> None:
    route = embeddings.EmbeddingRoute(
        config=AiProviderConfig(monthly_budget_eur=Decimal("10")),
        model="text-embedding-3-small",
        price_in=Decimal("0.02"),
    )
    assert embeddings.cost(route, 1_000_000) == Decimal("0.02")
    assert embeddings.cost(route, 0) == Decimal(0)
