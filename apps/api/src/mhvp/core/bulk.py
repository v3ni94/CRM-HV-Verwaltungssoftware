"""Common partial success report of bulk endpoints (section 12 Massenendpunkte, S12-05).

Each item is processed on its own; a failure never aborts the others and is reported with the
problem code. ``BulkReport`` is the shared response shape (``BulkResultOut``).
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel

from mhvp.core.problems import ProblemError


class BulkItemOut(BaseModel):
    id: uuid.UUID
    ok: bool
    code: str | None = None
    detail: str | None = None


class BulkResultOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BulkItemOut]


async def run_bulk(
    ids: Sequence[uuid.UUID],
    action: Callable[[uuid.UUID], Awaitable[Any]],
    *,
    savepoint: Callable[[], Any] | None = None,
) -> BulkResultOut:
    """Run ``action`` per id. ``savepoint`` (e.g. ``session.begin_nested``) isolates the writes
    of one item so that a failed item rolls back alone."""
    items: list[BulkItemOut] = []
    for item_id in dict.fromkeys(ids):
        try:
            if savepoint is None:
                await action(item_id)
            else:
                async with savepoint():
                    await action(item_id)
            items.append(BulkItemOut(id=item_id, ok=True))
        except ProblemError as exc:
            items.append(BulkItemOut(id=item_id, ok=False, code=exc.error.code, detail=exc.detail))
    failed = sum(1 for i in items if not i.ok)
    return BulkResultOut(
        total=len(items), succeeded=len(items) - failed, failed=failed, items=items
    )
