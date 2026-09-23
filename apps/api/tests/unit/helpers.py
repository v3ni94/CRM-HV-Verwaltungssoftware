from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from mhvp.core.config import Settings
from mhvp.core.health import ReadinessCheck
from mhvp.main import Resources, create_app


def ok_check() -> Callable[[], Awaitable[None]]:
    async def check() -> None:
        return None

    return check


def app_with_checks(settings: Settings, checks: dict[str, ReadinessCheck] | None = None) -> FastAPI:
    fixed = checks if checks is not None else {"database": ok_check()}

    def factory(_: Settings, __: Resources) -> dict[str, ReadinessCheck]:
        return fixed

    return create_app(settings, readiness_checks_factory=factory)
