"""Optional optimistic locking with ETag/If-Match (MASTER-PROMPT 12, ADR 0012, S12-04).

Reads send ``ETag``; a write that carries ``If-Match`` is rejected with 412
(``VERSION_CONFLICT``) when the token no longer matches. Without the header the write runs
unchecked (backwards compatible). Resources with an optimistic ``version`` column use it;
others derive the token from ``updated_at`` (microsecond precision, set by the database on
every update), so no schema change is needed.
"""

from datetime import UTC, datetime, timedelta

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
