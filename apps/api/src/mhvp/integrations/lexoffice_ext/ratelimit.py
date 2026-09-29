"""Two requests per second per Lexware organisation, shared across workers (rule INT-LEXO-01,
vendor limit documented at developers.lexware.io, verified 28.09.2026).

Slot window 500 ms: ``INCR lexoffice:rl:{key}:{slot}`` with ``EXPIRE 2``; a result above one
means the slot is taken and the caller sleeps until the next slot. Without Redis (tests,
``redis is None``) an in process lock spaces calls 500 ms apart."""

from __future__ import annotations

import asyncio
import time
from typing import Any

SLOT_SECONDS = 0.5
_local_lock = asyncio.Lock()
_local_last: dict[str, float] = {}


def slot_of(now: float) -> int:
    return int(now / SLOT_SECONDS)


async def acquire(redis: Any | None, key: str) -> None:
    """Blocks until a slot for ``key`` is free. ``redis`` is a ``redis.asyncio.Redis`` or None."""
    if SLOT_SECONDS <= 0:  # tests disable the limiter
        return
    if redis is None:
        async with _local_lock:
            now = time.monotonic()
            last = _local_last.get(key)
            if last is not None and now - last < SLOT_SECONDS:
                await asyncio.sleep(SLOT_SECONDS - (now - last))
                now = time.monotonic()
            _local_last[key] = now
        return
    while True:
        now = time.time()
        slot = slot_of(now)
        name = f"lexoffice:rl:{key}:{slot}"
        count = int(await redis.incr(name))
        if count == 1:
            await redis.expire(name, 2)
        if count <= 1:
            return
        await asyncio.sleep((slot + 1) * SLOT_SECONDS - now + 0.001)


def reset_local() -> None:
    _local_last.clear()
