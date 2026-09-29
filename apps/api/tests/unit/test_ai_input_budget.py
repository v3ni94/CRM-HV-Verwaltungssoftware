"""Input budget of the chat (answer_question): the data block is fitted into the provider's
context window before the call (retrieved documents first, then excerpts, then lookup hits,
then history; never the question), a provider 400 naming the token limit is retried once with
the budget halved, a second refusal ends with the German notice (the job then answers with the
hit list). Production error 29.09.2026: "HTTP 400: Input tokens exceed the configured limit of
272000 tokens. Your messages resulted in 275573 tokens."
"""

import asyncio
import uuid

from mhvp.ai import gateway
from mhvp.ai.gateway import AnswerParts, DocPart, TaskInput, _PlanResult
from mhvp.ai.providers import ProviderError

BUDGET = 1_000  # tokens -> int(1000 * 3.5 * 0.85) = 2975 chars


def _lookup(links: int, tools: int) -> dict[str, object]:
    return {
        "terms": ["x"],
        "tools": [
            {"tool": f"t{i}", "label": f"T{i}", "permitted": True, "count": 1} for i in range(tools)
        ],
        "links": [
            {
                "type": "contact",
                "id": str(i),
                "label": f"Kontakt {i}",
                "href": f"/kontakte/{i}",
                "detail": "x" * 40,
            }
            for i in range(links)
        ],
    }


def _doc(name: str, chars: int, attached: bool = False) -> DocPart:
    return DocPart(name, uuid.uuid4(), "d" * chars, attached)


def test_budget_chars_is_tokens_times_3_5_times_reserve() -> None:
    """Expected by hand: 1000 tokens * 3.5 chars * 0.85 reserve = 2975 chars."""
    assert gateway.budget_chars(BUDGET) == 2975
    assert gateway.budget_chars(gateway.DEFAULT_INPUT_BUDGET_TOKENS) == 446_250


def test_everything_fits_is_left_untouched() -> None:
    parts = AnswerParts(
        history=["Nutzer: hallo", "Assistent: hi"],
        lookup=_lookup(3, 1),
        documents=[_doc("a.txt", 200)],
    )
    text, kept, stats = gateway.fit_answer_input(parts, BUDGET)
    assert len(text) <= 2975
    assert stats["trim_steps"] == 0
    assert stats["documents_dropped"] == 0
    assert stats["history_messages"] == 2
    assert stats["lookup_links"] == 3
    assert kept == [parts.documents[0].document_id]
    assert stats["a.txt"] == 200


def test_oversized_retrieval_is_trimmed_in_order() -> None:
    """Three retrieved documents of 3000 chars plus an attached one of 1500 chars (each far
    beyond the 2975 char budget together): the retrieved ones are dropped least relevant
    first, the attached one stays and is cut to an excerpt, the history stays complete."""
    attached = _doc("anhang.pdf", 1500, attached=True)
    parts = AnswerParts(
        history=[f"Nutzer: Frage {i}" for i in range(4)],
        lookup=_lookup(4, 1),
        documents=[attached, _doc("r1.pdf", 3000), _doc("r2.pdf", 3000), _doc("r3.pdf", 3000)],
    )
    text, kept, stats = gateway.fit_answer_input(parts, BUDGET)
    assert len(text) <= 2975
    assert kept == [attached.document_id]
    assert stats["documents_dropped"] == 3
    assert stats["documents_retrieved"] == 0
    assert stats["documents_attached"] == 1
    assert stats["history_messages"] == 4  # trimmed last, not needed here
    assert stats["trim_steps"] == 3
    assert "r3.pdf" not in text
    assert "r1.pdf" not in text
    assert 'name="anhang.pdf"' in text
    assert stats["budget_tokens"] == BUDGET
    assert stats["estimated_tokens"] == gateway.estimate_tokens(len(text))


def test_documents_then_links_then_history_give_way_the_question_never() -> None:
    """Without documents the budget (2975 chars) is exceeded by 30 hits of one tool (about
    80 chars each) and 12 history turns of about 240 chars: hits beyond 10 per tool go first, then
    the history is cut to the last 6 turns (6 * 240 + 10 * 80 + headers < 2975)."""
    parts = AnswerParts(
        history=[f"Nutzer: Nachricht {i} " + "h" * 220 for i in range(12)],
        lookup=_lookup(30, 1),
        documents=[],
        instruction="Anweisung des Nutzers: Was ist offen?",
    )
    text, kept, stats = gateway.fit_answer_input(parts, BUDGET)
    assert kept == []
    assert stats["lookup_links"] == 10
    assert stats["history_messages"] == 6
    assert text.startswith("Anweisung des Nutzers: Was ist offen?")
    assert "Nachricht 11" in text
    assert "Nachricht 5" not in text
    assert "Kontakt 9" in text
    assert "Kontakt 10" not in text
    assert stats["trim_steps"] == 2


def test_document_excerpt_never_goes_below_the_minimum() -> None:
    parts = AnswerParts(
        history=[], lookup=None, documents=[_doc("gross.pdf", 100_000, attached=True)]
    )
    text, _kept, stats = gateway.fit_answer_input(parts, 100)
    assert stats["document_excerpt_chars"] == gateway.MIN_EXCERPT_CHARS
    assert "[gekürzt" in text
    assert len(text) > gateway.budget_chars(100)  # cannot fit, but nothing else to trim


def test_token_limit_error_is_recognised() -> None:
    limit = ProviderError(
        "HTTP 400: Input tokens exceed the configured limit of 272000 tokens. Your messages "
        "resulted in 275573 tokens."
    )
    assert gateway.is_token_limit_error(limit)
    assert gateway.is_token_limit_error(
        ProviderError("HTTP 400: prompt is too long: context window")
    )
    assert not gateway.is_token_limit_error(ProviderError("HTTP 400: invalid request schema"))
    assert not gateway.is_token_limit_error(ProviderError("HTTP 529: overloaded", retryable=True))


def _item(budget: int) -> TaskInput:
    return TaskInput(
        text="x" * budget,
        document_ids=[],
        context={},
        input_stats={"budget_tokens": budget},
        chunks=[],
    )


def _result(token_limit: bool) -> _PlanResult:
    route = object()
    return _PlanResult(
        None if token_limit else {"answer": "ok"},
        10,
        5,
        "Anbieterfehler: HTTP 400: Input tokens exceed the configured limit"
        if token_limit
        else None,
        [],
        route,  # type: ignore[arg-type]
        token_limit,
    )


def test_a_400_triggers_one_retry_with_the_budget_halved() -> None:
    calls: list[int] = []
    rebuilt: list[int] = []

    async def call(item: TaskInput) -> _PlanResult:
        calls.append(len(item.text))
        return _result(token_limit=len(calls) == 1)

    async def rebuild(budget: int) -> TaskInput:
        rebuilt.append(budget)
        return _item(budget)

    result, item = asyncio.run(gateway._call_within_budget(call, rebuild, _item(272_000), 272_000))
    assert rebuilt == [136_000]
    assert calls == [272_000, 136_000]
    assert result.output == {"answer": "ok"}
    assert result.error is None
    assert item.input_stats["budget_tokens"] == 136_000


def test_second_failure_falls_back_with_the_german_notice() -> None:
    rebuilt: list[int] = []

    async def call(item: TaskInput) -> _PlanResult:
        return _result(token_limit=True)

    async def rebuild(budget: int) -> TaskInput:
        rebuilt.append(budget)
        return _item(budget)

    result, _item_out = asyncio.run(gateway._call_within_budget(call, rebuild, _item(1000), 1000))
    assert rebuilt == [500]  # exactly one retry
    assert result.output is None
    assert result.error == gateway.CONTEXT_WINDOW_NOTICE
    assert "Kontextfenster" in gateway.CONTEXT_WINDOW_NOTICE
    assert "\u2013" not in gateway.CONTEXT_WINDOW_NOTICE


def test_without_a_token_limit_nothing_is_rebuilt() -> None:
    rebuilt: list[int] = []

    async def call(item: TaskInput) -> _PlanResult:
        return _result(token_limit=False)

    async def rebuild(budget: int) -> TaskInput:
        rebuilt.append(budget)
        return _item(budget)

    result, _ = asyncio.run(gateway._call_within_budget(call, rebuild, _item(10), 10))
    assert rebuilt == []
    assert result.output == {"answer": "ok"}
