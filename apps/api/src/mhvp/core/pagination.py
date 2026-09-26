"""List pagination in the pattern of ``GET /tickets`` (review 26.09.2026, H7): the response
stays a plain list for existing callers; total and page are reported in the headers
``X-Total-Count``, ``X-Page`` and ``X-Page-Size``. ``limit`` alone returns the first page."""

from collections.abc import Sequence
from typing import Any

from fastapi import Response
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

PAGE_HEADERS: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "X-Total-Count": {
                "description": "Gesamtzahl der Einträge der Filterung",
                "schema": {"type": "integer"},
            },
            "X-Page": {"description": "Aktuelle Seite", "schema": {"type": "integer"}},
            "X-Page-Size": {"description": "Einträge je Seite", "schema": {"type": "integer"}},
        }
    }
}


async def paginate(
    session: AsyncSession,
    query: Select[Any],
    response: Response,
    *,
    page: int,
    page_size: int | None,
    limit: int,
    offset: int = 0,
) -> Sequence[Any]:
    """Counts ``query`` (without its ordering), fetches one page and sets the headers.
    ``page_size`` wins over ``limit``; ``offset`` adds to the page start (legacy callers)."""
    size = page_size or limit
    total = (
        await session.scalar(func.count().select().select_from(query.order_by(None).subquery()))
        or 0
    )
    rows = (await session.scalars(query.offset((page - 1) * size + offset).limit(size))).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(size)
    return rows
