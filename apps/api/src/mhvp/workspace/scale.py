"""Scale monitoring: the triggers of ADR 0021 as platform metrics with an alarm (AE36, AC09-01).

ADR 0021 (section Auslöser) names when the yearly partitioning of ``journal_entry`` and
``bank_transaction`` is planned. This module measures the figures behind those triggers and
reports them; it decides nothing and rebuilds nothing:

* size and row count of ``journal_entry``, ``journal_line`` and ``bank_transaction`` (estimate
  from ``pg_class`` for large tables, exact count per tenant below ``EXACT_COUNT_BELOW`` rows,
  so a young installation shows exact figures);
* P95 of the journal list and the bank transaction list from real requests (the pure ASGI
  middleware ``ListLatencyMiddleware`` stores path class and duration in Redis, nothing else:
  no tenant, no user, no query values), separate for deep access (offset from ``DEEP_OFFSET``);
* duration of the latest restore test (``ops.backup_verify``) against the restore target (RTO);
* number of productive tenants (demo tenants do not count) as the mark for repeating the
  measurement.

The thresholds are the proposals of ADR 0021 (``PlatformScaleSetting``, open decision AC09-01)
and can be changed by a platform administrator. ``evaluate`` is a pure function. The weekly job
(``mhvp.ops.scale_snapshot``) stores a snapshot per ISO week and, for a trigger that was not
active before, writes a platform audit event and a notification to every platform
administrator. The live view (``GET /platform/ops/scale``, Prometheus gauges) shows the same
evaluation at any time.
"""

import asyncio
import math
import time
import uuid
from collections.abc import Awaitable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, cast
from urllib.parse import parse_qs

from celery import shared_task
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.logging import get_logger
from mhvp.platform.models import (
    Membership,
    MembershipStatus,
    PlatformAuditEvent,
    Tenant,
    TenantStatus,
    User,
)
from mhvp.platform.scale_models import PlatformScaleSetting, PlatformScaleSnapshot
from mhvp.workspace import backup_verify

log = get_logger(__name__)

TABLES: tuple[str, ...] = ("journal_entry", "journal_line", "bank_transaction")
# From this estimated row count on, ``pg_class.reltuples`` is used instead of counting.
EXACT_COUNT_BELOW = 1_000_000
GIB = 1024**3

LATENCY_KEYS: tuple[str, ...] = (
    "journal_list",
    "journal_list_deep",
    "bank_list",
    "bank_list_deep",
)
DEEP_KEYS = frozenset({"journal_list_deep", "bank_list_deep"})
LATENCY_PREFIX = "mhvp:ops:latency:"
LATENCY_WINDOW_DAYS = 7
LATENCY_TTL_SECONDS = 14 * 86400
SAMPLE_CAP = 2000
# A P95 needs a basis: below this number of samples in the window no figure is reported.
MIN_SAMPLES = 20
# Access at or beyond this offset (rows) counts as deep access (ADR 0021: page 900 of 100).
DEEP_OFFSET = 10_000

KIND_PARTITION_REVIEW = "partition_review"
KIND_MEASURE_AGAIN = "measure_again"
NOTIFICATION_KIND = "platform_scale_trigger"
NOTIFICATION_TARGET = "platform_scale"

_JOURNAL_SUFFIX = "/entries"
_JOURNAL_MARK = "/accounting/ledgers/"
_BANK_PATH = "/api/v1/banking/transactions"


# Latency samples -------------------------------------------------------------------------


def classify(path: str, query_string: bytes) -> str | None:
    """Latency key of a GET request, ``None`` for every other path. Only the offset of the
    query is read to tell deep access from a normal page; no value is stored."""
    if path == _BANK_PATH:
        base, offset_name = "bank_list", "offset"
    elif (
        path.startswith("/api/v1" + _JOURNAL_MARK)
        and path.endswith(_JOURNAL_SUFFIX)
        and path.count("/") == 6
    ):
        base, offset_name = "journal_list", "offset"
    else:
        return None
    query = parse_qs(query_string.decode("latin-1"))
    try:
        if base == "journal_list" and "page_size" in query:
            page = int(query.get("page", ["1"])[0])
            offset = max(page - 1, 0) * int(query["page_size"][0])
        else:
            offset = int(query.get(offset_name, ["0"])[0])
    except ValueError:
        offset = 0
    return f"{base}_deep" if offset >= DEEP_OFFSET else base


async def record_latency(redis: Redis, key: str, milliseconds: float) -> None:
    """Pushes one sample (``<epoch seconds>:<milliseconds>``), newest first, list capped."""
    name = LATENCY_PREFIX + key
    pipe = redis.pipeline(transaction=False)
    pipe.lpush(name, f"{int(time.time())}:{milliseconds:.1f}")
    pipe.ltrim(name, 0, SAMPLE_CAP - 1)
    pipe.expire(name, LATENCY_TTL_SECONDS)
    await pipe.execute()


class ListLatencyMiddleware:
    """Measures the duration of the journal list and the bank transaction list (status 200)
    for the P95 of the scale monitoring. A Redis error never disturbs the request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return
        key = classify(str(scope.get("path", "")), scope.get("query_string", b""))
        if key is None:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if status == 200:
                elapsed = (time.perf_counter() - started) * 1000
                resources = getattr(getattr(scope.get("app"), "state", None), "resources", None)
                redis = getattr(resources, "redis", None)
                if redis is not None:
                    try:
                        await record_latency(redis, key, elapsed)
                    except Exception:  # monitoring must not fail a request
                        log.debug("latency_sample_failed", key=key)


def percentile95(values: Iterable[float]) -> float | None:
    """P95 by the nearest rank method; ``None`` below ``MIN_SAMPLES`` samples."""
    ordered = sorted(values)
    if len(ordered) < MIN_SAMPLES:
        return None
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def parse_samples(raw: Iterable[bytes | str], now: float) -> list[float]:
    """Milliseconds of the samples within the window; malformed entries are ignored."""
    cutoff = now - LATENCY_WINDOW_DAYS * 86400
    out: list[float] = []
    for item in raw:
        text_value = item.decode() if isinstance(item, bytes) else item
        stamp, _, millis = text_value.partition(":")
        try:
            if int(stamp) >= cutoff:
                out.append(float(millis))
        except ValueError:
            continue
    return out


async def latency_stats(redis: Redis | None, now: float | None = None) -> dict[str, dict[str, Any]]:
    """Samples and P95 per latency key over the last seven days. Without Redis or after an
    error the figures are empty (samples 0, p95 ``None``)."""
    moment = now if now is not None else time.time()
    out: dict[str, dict[str, Any]] = {}
    for key in LATENCY_KEYS:
        values: list[float] = []
        if redis is not None:
            try:
                raw: list[Any] = await cast(
                    "Awaitable[list[Any]]", redis.lrange(LATENCY_PREFIX + key, 0, -1)
                )
                values = parse_samples(raw, moment)
            except Exception:
                values = []
        p95 = percentile95(values)
        out[key] = {"samples": len(values), "p95_ms": round(p95, 1) if p95 is not None else None}
    return out


# Table figures ---------------------------------------------------------------------------

_STATS_SQL = text(
    """
    SELECT c.relname AS name,
           CASE WHEN c.relkind = 'p' THEN COALESCE((
                    SELECT sum(GREATEST(l.reltuples, 0)) FROM pg_partition_tree(c.oid) t
                    JOIN pg_class l ON l.oid = t.relid WHERE t.isleaf), -1)
                ELSE c.reltuples END AS tuples,
           CASE WHEN c.relkind = 'p' THEN COALESCE((
                    SELECT sum(pg_total_relation_size(t.relid)) FROM pg_partition_tree(c.oid) t
                    WHERE t.isleaf), 0)
                ELSE pg_total_relation_size(c.oid) END AS bytes
    FROM pg_class c
    WHERE c.oid IN (to_regclass('journal_entry'), to_regclass('journal_line'),
                    to_regclass('bank_transaction'))
    """
)


async def table_stats(
    factory: async_sessionmaker[AsyncSession], tenant_ids: list[uuid.UUID]
) -> dict[str, dict[str, Any]]:
    """Rows and bytes (including indexes) per table. ``exact`` is false for an estimate."""
    async with platform_transaction(factory) as session:
        found = {
            row.name: (int(row.tuples), int(row.bytes))
            for row in (await session.execute(_STATS_SQL)).all()
        }
    out: dict[str, dict[str, Any]] = {}
    needs_count: list[str] = []
    for name in TABLES:
        tuples, size = found.get(name, (-1, 0))
        out[name] = {"rows": max(tuples, 0), "bytes": size, "exact": False}
        if tuples < EXACT_COUNT_BELOW:
            needs_count.append(name)
    if needs_count:
        from mhvp.accounting.models import JournalEntry, JournalLine
        from mhvp.banking.models import BankTransaction

        models = {
            "journal_entry": JournalEntry,
            "journal_line": JournalLine,
            "bank_transaction": BankTransaction,
        }
        totals = dict.fromkeys(needs_count, 0)
        for tenant_id in tenant_ids:
            async with tenant_transaction(factory, tenant_id) as session:
                for name in needs_count:
                    totals[name] += int(
                        await session.scalar(select(func.count()).select_from(models[name])) or 0
                    )
        for name in needs_count:
            out[name].update(rows=totals[name], exact=True)
    return out


# Evaluation ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    rows: int
    size_gb: int
    p95_ms: int
    p95_deep_ms: int
    p95_weeks: int
    restore_seconds: int
    tenants_review: int

    @classmethod
    def from_row(cls, row: PlatformScaleSetting) -> "Thresholds":
        return cls(
            rows=row.rows_threshold,
            size_gb=row.size_gb_threshold,
            p95_ms=row.p95_ms_threshold,
            p95_deep_ms=row.p95_deep_ms_threshold,
            p95_weeks=row.p95_weeks,
            restore_seconds=row.restore_seconds_threshold,
            tenants_review=row.tenants_review_threshold,
        )


@dataclass
class Measurement:
    """Figures of one measurement (live or stored)."""

    tables: dict[str, dict[str, Any]]
    latency: dict[str, dict[str, Any]]
    restore_seconds: int | None
    tenants_productive: int
    tenants_demo: int


@dataclass(frozen=True)
class Trigger:
    key: str
    kind: str
    title: str
    detail: str
    value: float
    threshold: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "value": self.value,
            "threshold": self.threshold,
        }


@dataclass
class HistoryPoint:
    """The part of a stored snapshot the evaluation of the P95 trigger needs."""

    iso_week: str
    latency: dict[str, dict[str, Any]] = field(default_factory=dict)


def _german(number: float) -> str:
    return f"{number:,.0f}".replace(",", ".")


def evaluate(
    thresholds: Thresholds, current: Measurement, history: list[HistoryPoint]
) -> list[Trigger]:
    """Triggers of ADR 0021 that are reached. ``history`` holds the stored measurements before
    the current one, newest first. The P95 triggers need ``p95_weeks`` measurements in a row
    (the current one and the latest ones before it), all above the threshold."""
    out: list[Trigger] = []
    limit_bytes = thresholds.size_gb * GIB
    for name in TABLES:
        stat = current.tables.get(name)
        if stat is None:
            continue
        if stat["rows"] >= thresholds.rows:
            out.append(
                Trigger(
                    key=f"rows:{name}",
                    kind=KIND_PARTITION_REVIEW,
                    title=f"{name}: {_german(thresholds.rows)} Zeilen erreicht",
                    detail=(
                        f"Die Tabelle {name} hat {_german(stat['rows'])} Zeilen"
                        f"{'' if stat.get('exact') else ' (Schätzung)'}. Planung der "
                        "Jahrespartitionierung nach ADR 0021 beginnen."
                    ),
                    value=float(stat["rows"]),
                    threshold=float(thresholds.rows),
                )
            )
        if stat["bytes"] >= limit_bytes:
            out.append(
                Trigger(
                    key=f"size:{name}",
                    kind=KIND_PARTITION_REVIEW,
                    title=f"{name}: {thresholds.size_gb} GB erreicht",
                    detail=(
                        f"Die Tabelle {name} belegt {stat['bytes'] / GIB:.1f} GB mit Indizes. "
                        "Planung der Jahrespartitionierung nach ADR 0021 beginnen."
                    ),
                    value=round(stat["bytes"] / GIB, 2),
                    threshold=float(thresholds.size_gb),
                )
            )
    for key in LATENCY_KEYS:
        limit = thresholds.p95_deep_ms if key in DEEP_KEYS else thresholds.p95_ms
        points = [current.latency, *[h.latency for h in history]][: thresholds.p95_weeks]
        values = [(p.get(key) or {}).get("p95_ms") for p in points]
        if len(values) == thresholds.p95_weeks and all(v is not None and v > limit for v in values):
            latest = float(values[0] or 0)
            out.append(
                Trigger(
                    key=f"p95:{key}",
                    kind=KIND_PARTITION_REVIEW,
                    title=f"{key}: P95 über {limit} ms",
                    detail=(
                        f"Das P95 der Liste {key} liegt seit {thresholds.p95_weeks} "
                        f"Wochenmessungen über {limit} ms (zuletzt {latest:.0f} ms). Erst "
                        "Indizes und Statistik prüfen (Stufe 1 in ADR 0021), dann Partitionierung."
                    ),
                    value=latest,
                    threshold=float(limit),
                )
            )
    if current.restore_seconds is not None and current.restore_seconds > thresholds.restore_seconds:
        out.append(
            Trigger(
                key="restore:duration",
                kind=KIND_PARTITION_REVIEW,
                title="Wiederherstellung über dem Ziel",
                detail=(
                    f"Der Wiederherstellungstest dauerte {current.restore_seconds} s, das Ziel "
                    f"(RTO) liegt bei {thresholds.restore_seconds} s."
                ),
                value=float(current.restore_seconds),
                threshold=float(thresholds.restore_seconds),
            )
        )
    if current.tenants_productive >= thresholds.tenants_review:
        out.append(
            Trigger(
                key="tenants:productive",
                kind=KIND_MEASURE_AGAIN,
                title=f"{thresholds.tenants_review} produktive Mandanten",
                detail=(
                    f"{current.tenants_productive} produktive Mandanten (ohne Demo-Mandanten): "
                    "Skalierungsmessung nach dem Messplan von ADR 0021 wiederholen. Das löst "
                    "keinen Umbau aus."
                ),
                value=float(current.tenants_productive),
                threshold=float(thresholds.tenants_review),
            )
        )
    return out


# Measurement -----------------------------------------------------------------------------


async def get_settings_row(session: AsyncSession) -> PlatformScaleSetting:
    """The single settings row, created with the proposals of ADR 0021 on first use (an
    advisory lock keeps two first calls from creating two rows)."""
    row = await session.scalar(select(PlatformScaleSetting).limit(1))
    if row is None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('platform_scale_setting'))")
        )
        row = await session.scalar(select(PlatformScaleSetting).limit(1))
    if row is None:
        row = PlatformScaleSetting()
        session.add(row)
        await session.flush()
        await session.refresh(row)
    return row


def iso_week_of(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def measure(factory: async_sessionmaker[AsyncSession], redis: Redis | None) -> Measurement:
    """Takes the current figures. Row counts are physical: demo tenants are in the tables, so
    they are part of the size; only the tenant count leaves them out."""
    async with platform_transaction(factory) as session:
        rows = (await session.execute(select(Tenant.id, Tenant.status, Tenant.is_demo))).all()
    all_ids = [r.id for r in rows]
    productive = sum(1 for r in rows if r.status == TenantStatus.ACTIVE and not r.is_demo)
    demo = sum(1 for r in rows if r.is_demo)
    restore: int | None = None
    if redis is not None:
        try:
            summary = backup_verify.summarize(await backup_verify.load_result(redis))
            if summary["status"] == backup_verify.STATUS_OK and summary["duration_seconds"]:
                restore = int(summary["duration_seconds"])
        except Exception:
            restore = None
    return Measurement(
        tables=await table_stats(factory, all_ids),
        latency=await latency_stats(redis),
        restore_seconds=restore,
        tenants_productive=productive,
        tenants_demo=demo,
    )


async def load_history(
    session: AsyncSession, *, exclude_week: str | None, limit: int
) -> list[PlatformScaleSnapshot]:
    query = select(PlatformScaleSnapshot).order_by(PlatformScaleSnapshot.measured_at.desc())
    if exclude_week is not None:
        query = query.where(PlatformScaleSnapshot.iso_week != exclude_week)
    return list((await session.scalars(query.limit(limit))).all())


def history_points(rows: Iterable[PlatformScaleSnapshot]) -> list[HistoryPoint]:
    return [HistoryPoint(iso_week=r.iso_week, latency=dict(r.latency)) for r in rows]


async def live_view(
    factory: async_sessionmaker[AsyncSession], redis: Redis | None
) -> tuple[PlatformScaleSetting, Thresholds, Measurement, list[Trigger]]:
    """Settings, current figures and the triggers reached right now."""
    async with platform_transaction(factory) as session:
        setting = await get_settings_row(session)
        thresholds = Thresholds.from_row(setting)
        history = history_points(
            await load_history(session, exclude_week=None, limit=thresholds.p95_weeks)
        )
        session.expunge(setting)
    current = await measure(factory, redis)
    return setting, thresholds, current, evaluate(thresholds, current, history)


# Weekly snapshot and alarm ---------------------------------------------------------------


@dataclass
class SnapshotResult:
    iso_week: str
    triggers: list[Trigger]
    new_triggers: list[Trigger]
    notified: int


async def snapshot_once(
    factory: async_sessionmaker[AsyncSession],
    redis: Redis | None,
    *,
    today: date | None = None,
    source: str = "job",
    actor_user_id: uuid.UUID | None = None,
) -> SnapshotResult:
    """Stores the measurement of the current ISO week (replacing an earlier one of the same
    week) and alarms for every trigger that was not active at the previous measurement."""
    now = datetime.now(UTC)
    week = iso_week_of(today or now.date())
    current = await measure(factory, redis)
    async with platform_transaction(factory) as session:
        setting = await get_settings_row(session)
        thresholds = Thresholds.from_row(setting)
        alarm_enabled = setting.alarm_enabled
        history_rows = await load_history(session, exclude_week=week, limit=thresholds.p95_weeks)
        triggers = evaluate(thresholds, current, history_points(history_rows))
        same_week = await session.scalar(
            select(PlatformScaleSnapshot).where(PlatformScaleSnapshot.iso_week == week)
        )
        # A repeated run in the same week compares with the stored triggers of that week,
        # otherwise with the previous measurement; so a trigger is announced once.
        if same_week is not None:
            before_keys = set(same_week.triggers)
        else:
            before_keys = set(history_rows[0].triggers) if history_rows else set()
    # The alarm goes out before the measurement is stored: if it fails, the next run announces
    # the trigger again (at least once) instead of recording it silently.
    new_triggers = [t for t in triggers if t.key not in before_keys]
    notified = 0
    if new_triggers and alarm_enabled:
        notified = await alert_platform_admins(factory, new_triggers, week)
    async with platform_transaction(factory) as session:
        # One measurement per week even when the job and a manual run overlap.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('platform_scale_snapshot'))")
        )
        same_week = await session.scalar(
            select(PlatformScaleSnapshot).where(PlatformScaleSnapshot.iso_week == week)
        )
        snapshot = same_week or PlatformScaleSnapshot(iso_week=week, measured_at=now)
        snapshot.measured_at = now
        snapshot.tables = current.tables
        snapshot.latency = current.latency
        snapshot.restore_seconds = current.restore_seconds
        snapshot.tenants_productive = current.tenants_productive
        snapshot.tenants_demo = current.tenants_demo
        snapshot.triggers = [t.key for t in triggers]
        snapshot.source = source
        snapshot.created_by = snapshot.created_by or actor_user_id
        snapshot.updated_by = actor_user_id
        if same_week is None:
            session.add(snapshot)
        await session.flush()
    return SnapshotResult(
        iso_week=week, triggers=triggers, new_triggers=new_triggers, notified=notified
    )


def trigger_target_id(key: str) -> uuid.UUID:
    """Stable id of a trigger for the notification (an unread one of the same trigger is not
    repeated by ``workspace.services.notify``)."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"mhvp:scale-trigger:{key}")


async def alert_platform_admins(
    factory: async_sessionmaker[AsyncSession], triggers: list[Trigger], iso_week: str
) -> int:
    """Platform audit event per trigger and an in-app notification to every active platform
    administrator in each tenant of the administrator (the bell works per tenant). Sends no
    mail: mail alarms run through the monitoring (docs/runbooks/monitoring.md)."""
    from mhvp.workspace.services import notify

    async with platform_transaction(factory) as session:
        for trigger in triggers:
            session.add(
                PlatformAuditEvent(
                    action="scale.trigger_reached",
                    target_type="scale",
                    target_id=trigger.key,
                    payload={
                        "iso_week": iso_week,
                        "kind": trigger.kind,
                        "value": trigger.value,
                        "threshold": trigger.threshold,
                    },
                )
            )
        memberships = (
            await session.execute(
                select(Membership.tenant_id, Membership.user_id)
                .join(User, User.id == Membership.user_id)
                .where(
                    User.is_platform_admin.is_(True),
                    User.active.is_(True),
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
        ).all()
    created = 0
    for tenant_id, user_id in memberships:
        async with tenant_transaction(factory, tenant_id) as session:
            for trigger in triggers:
                row = await notify(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    kind=NOTIFICATION_KIND,
                    title=f"Skalierung: {trigger.title}",
                    body=trigger.detail,
                    target_type=NOTIFICATION_TARGET,
                    target_id=trigger_target_id(trigger.key),
                )
                created += 1 if row is not None else 0
    log.warning(
        "scale_trigger_reached",
        iso_week=iso_week,
        triggers=[t.key for t in triggers],
        notified=created,
    )
    return created


async def snapshot_job(settings: Settings, *, today: date | None = None) -> dict[str, Any]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url.get_secret_value())
    try:
        result = await snapshot_once(factory, redis, today=today)
    finally:
        await redis.aclose()
        await engine.dispose()
    return {
        "iso_week": result.iso_week,
        "triggers": [t.key for t in result.triggers],
        "new_triggers": [t.key for t in result.new_triggers],
        "notified": result.notified,
    }


@shared_task(name="mhvp.ops.scale_snapshot")
def scale_snapshot() -> dict[str, Any]:
    """Weekly measurement of the partitioning triggers (ADR 0021, AC09-01)."""
    return asyncio.run(snapshot_job(get_settings()))


# Metrics ---------------------------------------------------------------------------------


async def metric_gauges(
    factory: async_sessionmaker[AsyncSession], redis: Redis | None
) -> dict[str, int]:
    """Gauges for ``/platform/ops/metrics`` (JSON and Prometheus). Latency gauges are 0 while
    there are too few samples; the trigger gauges count the triggers reached right now."""
    _, _, current, triggers = await live_view(factory, redis)
    gauges: dict[str, int] = {}
    for name in TABLES:
        gauges[f"{name}_rows"] = int(current.tables[name]["rows"])
        gauges[f"{name}_bytes"] = int(current.tables[name]["bytes"])
    for key in LATENCY_KEYS:
        gauges[f"{key}_p95_ms"] = int(current.latency[key]["p95_ms"] or 0)
    gauges["tenants_productive"] = current.tenants_productive
    gauges["tenants_demo"] = current.tenants_demo
    gauges["scale_trigger_partition_review"] = sum(
        1 for t in triggers if t.kind == KIND_PARTITION_REVIEW
    )
    gauges["scale_trigger_measure_again"] = sum(1 for t in triggers if t.kind == KIND_MEASURE_AGAIN)
    return gauges


def snapshot_out(row: PlatformScaleSnapshot) -> dict[str, Any]:
    return {
        "iso_week": row.iso_week,
        "measured_at": row.measured_at,
        "source": row.source,
        "tables": row.tables,
        "latency": row.latency,
        "restore_seconds": row.restore_seconds,
        "tenants_productive": row.tenants_productive,
        "tenants_demo": row.tenants_demo,
        "triggers": row.triggers,
    }


def settings_out(row: PlatformScaleSetting) -> dict[str, Any]:
    return {
        "rows_threshold": row.rows_threshold,
        "size_gb_threshold": row.size_gb_threshold,
        "p95_ms_threshold": row.p95_ms_threshold,
        "p95_deep_ms_threshold": row.p95_deep_ms_threshold,
        "p95_weeks": row.p95_weeks,
        "restore_seconds_threshold": row.restore_seconds_threshold,
        "tenants_review_threshold": row.tenants_review_threshold,
        "alarm_enabled": row.alarm_enabled,
        "version": row.version,
        "updated_at": row.updated_at,
    }
