"""Provider clients are closed at the end of a plan step (worker log "Event loop is closed")."""

from __future__ import annotations

import pytest

from mhvp.ai import providers


class _Closable:
    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class _Failing:
    async def aclose(self) -> None:
        raise RuntimeError("already closed")


@pytest.mark.asyncio
async def test_close_client_calls_aclose() -> None:
    client = _Closable()
    await providers.close_client(client)
    assert client.closed == 1


@pytest.mark.asyncio
async def test_close_client_tolerates_missing_or_failing_aclose() -> None:
    await providers.close_client(object())
    await providers.close_client(_Failing())


@pytest.mark.asyncio
async def test_sdk_wrappers_expose_aclose() -> None:
    assert hasattr(providers.AnthropicClient, "aclose")
    assert hasattr(providers.OpenAIClient, "aclose")
