"""Celery application (section 3.2: queues default, io, ocr, ai, bank, mail, beat).

``celery -A mhvp.worker worker`` resolves ``app`` lazily. Reliability defaults for later
money flows: late acknowledgement, requeue on worker loss, prefetch 1. Tasks with economic
effect must additionally be idempotent (B08); the queue settings alone do not guarantee it.
"""

from functools import lru_cache
from typing import Any

from celery import Celery, signals
from celery.schedules import crontab
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
        include=[
            "mhvp.core.tasks",
            "mhvp.core.webhook_tasks",
            "mhvp.documents.tasks",
            "mhvp.ai.jobs",
            "mhvp.workspace.tasks",
            "mhvp.communication.tasks",
            "mhvp.banking.tasks",
            "mhvp.accounting.tasks",
            "mhvp.letting.tasks",
            "mhvp.platform.licensing",
            "mhvp.sla.tasks",
            "mhvp.immoware.tasks",
            "mhvp.objektakte.tasks",
        ],
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
            # Maintenance reminders as in-app notifications (M9); idempotent per unread item.
            # Bank retrieval 06:00 (8.2); connectors without contract report "not configured".
            # Prospect records are deleted after their deletion date (M26).
            # Usage counters per tenant on the 1st (M27, operating metrics only).
            "platform-usage-all": {
                "task": "mhvp.platform.usage_all",
                "schedule": crontab(day_of_month=1, hour=2, minute=0),
            },
            "letting-purge-prospects": {
                "task": "mhvp.letting.purge_prospects",
                "schedule": crontab(hour=3, minute=30),
            },
            "banking-sync-all": {
                "task": "mhvp.banking.sync_all",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "io"},
            },
            # finAPI Stage 2: opt-in per tenant only (`FinApiTenantConfig.auto_fetch_enabled`,
            # default off); the task itself queues nothing for a tenant that has not opted in.
            "banking-finapi-scheduled-fetch": {
                "task": "mhvp.banking.finapi_scheduled_fetch",
                "schedule": crontab(hour=6, minute=30),
                "options": {"queue": "io"},
            },
            # Dunning previews on the 5th (15.1); approval and sending stay manual.
            "accounting-dunning-run": {
                "task": "mhvp.accounting.dunning_run",
                "schedule": crontab(day_of_month=5, hour=6, minute=0),
            },
            # Gmail inbox sync for enabled mailboxes (M20-01); read only, Message-ID dedup.
            "communication-gmail-sync": {
                "task": "mhvp.communication.gmail_sync_all",
                "schedule": 120.0,
                "options": {"queue": "mail"},
            },
            "workspace-reminders": {
                "task": "mhvp.workspace.reminders",
                "schedule": 3600.0,
            },
            # SLA-Ampel und Eskalation (M21 Übernahme aus dem Immoware Hub), alle 5 Minuten.
            "sla-check-clocks": {
                "task": "mhvp.sla.check_clocks",
                "schedule": 300.0,
            },
            # Immoware24-DAV-Abholung (M32): Beat fest alle 15 Minuten, Task prueft selbst
            # anhand von ``poll_minutes``, ob ein Lauf faellig ist (read only, kein Schreibpfad).
            "immoware-sync-webdav": {
                "task": "mhvp.immoware.sync_webdav",
                "schedule": 900.0,
            },
            "immoware-sync-carddav": {
                "task": "mhvp.immoware.sync_carddav",
                "schedule": 900.0,
            },
            "immoware-sync-caldav": {
                "task": "mhvp.immoware.sync_caldav",
                "schedule": 900.0,
            },
            # objektakte differential import (M35 Stufe 5): daily 05:15, opt-in per tenant only
            # (`ObjektakteSyncState.enabled`, default off); the task skips every other tenant.
            "objektakte-sync-all": {
                "task": "mhvp.objektakte.sync_all",
                "schedule": crontab(hour=5, minute=15),
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
