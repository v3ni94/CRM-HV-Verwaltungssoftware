"""Celery application (section 3.2: queues default, io, ocr, ai, bank, mail, beat).

``celery -A mhvp.worker worker`` resolves ``app`` lazily. Reliability defaults for later
money flows: late acknowledgement, requeue on worker loss, prefetch 1. Tasks with economic
effect must additionally be idempotent (B08); the queue settings alone do not guarantee it.
"""

from functools import lru_cache
from typing import Any

from celery import Celery, signals
from kombu import Queue

from mhvp.core.config import Settings, get_settings
from mhvp.core.logging import configure_logging

QUEUES: tuple[str, ...] = ("default", "io", "ocr", "ai", "bank", "mail", "beat")


def create_celery(settings: Settings | None = None) -> Celery:
    settings = settings or get_settings()
    backend = settings.celery_result_backend
    app = Celery(
        "mhvp",
        broker=settings.celery_broker_url.get_secret_value(),
        backend=backend.get_secret_value() if backend else None,
        include=["mhvp.core.tasks", "mhvp.core.webhook_tasks", "mhvp.documents.tasks"],
    )
    app.conf.update(
        task_queues=[Queue(name) for name in QUEUES],
        task_default_queue="default",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        enable_utc=True,
        timezone="Europe/Berlin",
        broker_connection_retry_on_startup=True,
        result_expires=86_400,
        worker_hijack_root_logger=False,
        # Jobs of section 15.1 are added with their milestones and remain subject to the
        # release gates and domain checks (Freigabevorbehalt aller Zeitpläne).
        beat_schedule={
            # Webhook delivery is not a money flow; its retries follow section 12.
            "webhooks-dispatch": {
                "task": "mhvp.core.webhooks.dispatch",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
            # Mirror copies to Paperless/Drive; only tenants with an enabled connection (11.1).
            "documents-mirror": {
                "task": "mhvp.documents.mirror",
                "schedule": 60.0,
                "options": {"queue": "io"},
            },
        },
    )
    return app


@lru_cache(maxsize=1)
def get_celery() -> Celery:
    return create_celery()


@signals.setup_logging.connect
def _configure_worker_logging(**_: Any) -> None:
    configure_logging(get_settings())


def __getattr__(name: str) -> Celery:
    if name in ("app", "celery"):
        return get_celery()
    raise AttributeError(name)
