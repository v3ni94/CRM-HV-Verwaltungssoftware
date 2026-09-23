"""Request scoped context values (correlation id)."""

from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("mhvp_correlation_id", default=None)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> object:
    return _correlation_id.set(value)


def reset_correlation_id(token: object) -> None:
    _correlation_id.reset(token)  # type: ignore[arg-type]
