"""Optional optimistic locking with ETag/If-Match (MASTER-PROMPT 12, ADR 0012, S12-04).

Reads send ``ETag``; a write that carries ``If-Match`` is rejected with 412
(``VERSION_CONFLICT``) when the token no longer matches. Without the header the write runs
unchecked (backwards compatible). Resources with an optimistic ``version`` column use it;
others derive the token from ``updated_at`` (microsecond precision, set by the database on
every update), so no schema change is needed.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from mhvp.core.problems import ErrorCodes, ProblemError

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def etag_of(value: int | datetime) -> str:
    if isinstance(value, datetime):
        return f'"t{(value - _EPOCH) // timedelta(microseconds=1)}"'
    return f'"{value}"'


def check_if_match(if_match: str | None, value: int | datetime) -> None:
    """``*`` matches any existing resource (RFC 9110); weak prefixes ``W/`` are ignored."""
    if if_match is None:
        return
    current = etag_of(value)
    for candidate in (t.strip() for t in if_match.split(",")):
        if candidate == "*" or candidate.removeprefix("W/") == current:
            return
    raise ProblemError(ErrorCodes.VERSION_CONFLICT)


async def load_for_etag(
    session: Any,
    model: Any,
    entity_id: Any,
    tenant_id: Any | None = None,
    *,
    detail: str | None = None,
) -> Any:
    """Load the row ``FOR UPDATE`` before ``check_if_match`` (AC01-01, ADR 0012).

    The lock serialises concurrent writers carrying the same ETag: the second waits, then
    sees the new ``updated_at`` and gets 412. RLS hides rows of other tenants (404); the
    optional ``tenant_id`` adds an explicit check for callers outside a tenant session.
    """
    row = await session.get(model, entity_id, with_for_update=True)
    if row is None or (tenant_id is not None and getattr(row, "tenant_id", tenant_id) != tenant_id):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail=detail)
    return row
