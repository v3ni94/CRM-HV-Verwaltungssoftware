"""Central Celery task policy (GAI-316 to GAI-319): time limits per task class, broker
visibility timeout, retry with backoff for network-bound tasks and a Redis lock against
overlapping runs of the frequent beat tasks.

The policy is applied through ``task_annotations`` so that the task modules stay unchanged
(no logic change in the tasks). Limits are settings (``MHVP_CELERY_LIMIT_<CLASS>_SOFT`` and
``..._HARD``) and can be raised per deployment without a code change.
"""

from __future__ import annotations

import logging
import random
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from celery.exceptions import SoftTimeLimitExceeded

from mhvp.core.config import Settings

logger = logging.getLogger(__name__)

TASK_CLASSES: tuple[str, ...] = ("short", "medium", "long", "import")

# Beat tasks that run at least every five minutes (GAI-318). They get the "short" limits,
# a beat ``expires`` equal to their interval and the overlap lock.
FAST_BEAT_TASKS: frozenset[str] = frozenset(
    {
        "mhvp.core.webhooks.dispatch",
        "mhvp.integrations.schadenstool.process",
        "mhvp.integrations.lexoffice.process",
        "mhvp.documents.mirror",
        "mhvp.objektakte.upload",
        "mhvp.communication.gmail_sync_all",
        "mhvp.communication.imap_sync_all",
        "mhvp.communication.gmail_settle_all",
        "mhvp.workspace.notification_mails",
        "mhvp.automation.process_events",
        "mhvp.banking.process_events",
        "mhvp.sla.check_clocks",
    }
)

_SHORT_EXTRA: frozenset[str] = frozenset({"mhvp.core.ping", "mhvp.platform.availability_probe"})

LONG_TASKS: frozenset[str] = frozenset(
    {
        "mhvp.accounting.dunning_run",
        "mhvp.accounting.receivable_run",
        "mhvp.accounting.audit_export_run",
        "mhvp.payments.payment_run",
        "mhvp.banking.sync_all",
        "mhvp.banking.finapi_fetch",
        "mhvp.banking.ebics_fetch",
        "mhvp.banking.finapi_scheduled_fetch",
        "mhvp.banking.ebics_scheduled_fetch",
        "mhvp.ai.batch_nightly",
        "mhvp.ai.embed_index",
        "mhvp.documents.process_inbox",
        "mhvp.documents.drive_changes",
        "mhvp.documents.deletion_proposals",
        "mhvp.communication.gmail_backfill",
        "mhvp.communication.archive_messages",
        "mhvp.communication.archive_ticket_messages",
        "mhvp.immoware.sync_webdav",
        "mhvp.immoware.sync_carddav",
        "mhvp.immoware.sync_caldav",
        "mhvp.immoware.learning_run",
        "mhvp.objektakte.sync_all",
        "mhvp.metering.run_sync_job",
    }
)

# Imports, exports and the restore test (its own script timeout goes up to six hours).
IMPORT_TASKS: frozenset[str] = frozenset(
    {
        "mhvp.imports.reconciliation_all",
        "mhvp.imports.reconciliation_tenant",
        "mhvp.objektakte.sync_tenant",
        "mhvp.objektakte.import_previews_tenant",
        "mhvp.objektakte.export_property",
        "mhvp.platform.tenant_export",
        "mhvp.platform.tenant_export_job",
        "mhvp.ops.backup_verify",
    }
)

# Event or API triggered tasks without beat catch-up whose work is idempotent (repeated
# reading or syncing from a provider). Only transient network errors are retried. Tasks that
# already call ``self.retry`` (finapi_fetch, ebics_fetch, postal_status_poll, mirror deletion)
# keep their own strategy. Money runs are never retried automatically.
NETWORK_RETRY_TASKS: frozenset[str] = frozenset(
    {
        "mhvp.communication.gmail_push_sync",
        "mhvp.communication.gmail_state_reconcile",
        "mhvp.communication.gmail_backfill",
        "mhvp.objektakte.sync_tenant",
        "mhvp.imports.reconciliation_tenant",
        "mhvp.metering.run_sync_job",
    }
)

TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    httpx.TransportError,
)
RETRY_MAX = 3
RETRY_BASE_SECONDS = 30
RETRY_CAP_SECONDS = 600
VISIBILITY_MARGIN_SECONDS = 600
LOCK_PREFIX = "mhvp:tasklock:"


@dataclass(frozen=True)
class TaskLimits:
    soft: int
    hard: int


def limits_from_settings(settings: Settings) -> dict[str, TaskLimits]:
    """Limits per task class; a soft limit must lie below its hard limit."""
    result: dict[str, TaskLimits] = {}
    for cls in TASK_CLASSES:
        soft = int(getattr(settings, f"celery_limit_{cls}_soft"))
        hard = int(getattr(settings, f"celery_limit_{cls}_hard"))
        if soft >= hard:
            raise ValueError(f"celery_limit_{cls}_soft must be lower than the hard limit")
        result[cls] = TaskLimits(soft=soft, hard=hard)
    return result


def task_class(name: str) -> str:
    if name in FAST_BEAT_TASKS or name in _SHORT_EXTRA:
        return "short"
    if name in IMPORT_TASKS:
        return "import"
    if name in LONG_TASKS:
        return "long"
    return "medium"


def visibility_timeout(limits: Mapping[str, TaskLimits]) -> int:
    """Redis redelivers unacknowledged messages after this window (acks_late): it must exceed
    the largest hard limit, otherwise a long run is delivered a second time."""
    return max(item.hard for item in limits.values()) + VISIBILITY_MARGIN_SECONDS


def retry_countdown(retries: int) -> int:
    """Exponential backoff with full jitter, capped."""
    ceiling = min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * (2**retries))
    return max(1, random.randint(ceiling // 2, ceiling))  # noqa: S311 (jitter, not security)


def _redis_client(url: str) -> Any:
    import redis

    return redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def _lock_around(
    name: str, ttl: int, redis_url: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def around(call: Callable[..., Any]) -> Callable[..., Any]:
        def locked_call(task: Any, *args: Any, **kwargs: Any) -> Any:
            key = LOCK_PREFIX + name
            token = secrets.token_hex(8)
            client = None
            try:
                client = _redis_client(redis_url)
                acquired = bool(client.set(key, token, nx=True, ex=ttl))
            except Exception:
                logger.warning("task_lock.unavailable", extra={"task": name})
                return call(task, *args, **kwargs)
            if not acquired:
                logger.info("task_lock.skipped_overlap", extra={"task": name})
                return None
            try:
                return call(task, *args, **kwargs)
            finally:
                try:
                    if client.get(key) == token.encode():
                        client.delete(key)
                except Exception:
                    logger.warning("task_lock.release_failed", extra={"task": name})

        return locked_call

    return around


def _retry_around(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def around(call: Callable[..., Any]) -> Callable[..., Any]:
        def retrying_call(task: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return call(task, *args, **kwargs)
            except SoftTimeLimitExceeded:
                raise
            except TRANSIENT_ERRORS as exc:
                request = task.request
                if request.called_directly:
                    raise
                retries = int(request.retries or 0)
                if retries >= RETRY_MAX:
                    # Dead letter note: the run is given up and must be triggered again.
                    logger.error(
                        "task.retries_exhausted",
                        extra={"task": name, "retries": retries, "error": type(exc).__name__},
                    )
                    raise
                raise task.retry(
                    exc=exc, countdown=retry_countdown(retries), max_retries=RETRY_MAX
                ) from exc

        return retrying_call

    return around


class TaskPolicyAnnotation:
    """Celery annotation object: resolves limits, lock and retry per task name."""

    def __init__(self, settings: Settings) -> None:
        self.limits = limits_from_settings(settings)
        self.lock_enabled = settings.celery_overlap_lock_enabled
        self.redis_url = settings.redis_url.get_secret_value()

    def annotate(self, task: Any) -> dict[str, Any] | None:
        name = str(task.name)
        if not name.startswith("mhvp."):
            return None
        limits = self.limits[task_class(name)]
        result: dict[str, Any] = {"soft_time_limit": limits.soft, "time_limit": limits.hard}
        if name in NETWORK_RETRY_TASKS:
            result["@__call__"] = _retry_around(name)
        elif self.lock_enabled and name in FAST_BEAT_TASKS:
            result["@__call__"] = _lock_around(name, limits.hard + 30, self.redis_url)
        return result


def apply_beat_policy(schedule: dict[str, dict[str, Any]]) -> None:
    """Every beat entry names its queue; fast numeric entries expire after one interval so
    that a backlog on a busy worker does not run stale copies one after another."""
    for entry in schedule.values():
        options = entry.setdefault("options", {})
        options.setdefault("queue", "default")
        interval = entry.get("schedule")
        if (
            entry.get("task") in FAST_BEAT_TASKS
            and isinstance(interval, int | float)
            and "expires" not in options
        ):
            options["expires"] = float(interval)


def celery_policy_conf(settings: Settings) -> dict[str, Any]:
    limits = limits_from_settings(settings)
    return {
        "task_soft_time_limit": limits["medium"].soft,
        "task_time_limit": limits["medium"].hard,
        "task_annotations": (TaskPolicyAnnotation(settings),),
        "broker_transport_options": {"visibility_timeout": visibility_timeout(limits)},
        "result_backend_transport_options": {"visibility_timeout": visibility_timeout(limits)},
    }
