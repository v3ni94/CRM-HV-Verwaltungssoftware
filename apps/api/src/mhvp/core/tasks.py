"""Core Celery tasks."""

from celery import shared_task


@shared_task(name="mhvp.core.ping")
def ping() -> str:
    """Worker liveness probe used by operations and tests."""
    return "pong"
