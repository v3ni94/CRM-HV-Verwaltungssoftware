"""Per tenant configuration of the standard jobs (S15-03, section 15.1, decision 12 a).

The beat schedule in ``mhvp.worker`` stays global. A job that runs per tenant asks
``job_allowed`` before it works on a tenant: a disabled job is skipped, and with a start time
the job only works in the window of ``WINDOW_MINUTES`` after that time (local time
Europe/Berlin), so a beat that fires more often than once a day still runs it once per day.
No row means: runs as scheduled. Switching jobs off or moving them opens no release gate.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.automation.models import JOB_CATALOG, TenantJobSchedule
from mhvp.automation.schedule import SCHEDULE_TZ

WINDOW_MINUTES = 60
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def validate_job(job_key: str, run_at: str | None) -> None:
    if job_key not in JOB_CATALOG:
        raise ValueError("Unbekannter Job.")
    if run_at is not None and not _TIME.match(run_at):
        raise ValueError("Uhrzeit im Format HH:MM angeben.")


def in_window(run_at: str | None, now: datetime) -> bool:
    """True when ``now`` lies in the window of ``WINDOW_MINUTES`` after today's start time.

    The start is resolved to one real instant (first occurrence, ``fold=0``) and compared in
    UTC, so the repeated hour of the clock change on the last Sunday of October (02:00 to 03:00
    twice) opens one window, not two, and the missing hour of March shifts the start to the
    first valid instant instead of opening none (GA12-06)."""
    if run_at is None:
        return True
    local = now.astimezone(SCHEDULE_TZ)
    hour, minute = (int(x) for x in run_at.split(":"))
    start = datetime(local.year, local.month, local.day, hour, minute, tzinfo=SCHEDULE_TZ, fold=0)
    elapsed = now.astimezone(UTC) - start.astimezone(UTC)
    return timedelta(0) <= elapsed < timedelta(minutes=WINDOW_MINUTES)


async def lock_job(session: AsyncSession, tenant_id: uuid.UUID, job_key: str) -> None:
    """Serialises the scheduled and a manual run of one job for one tenant until the end of the
    transaction (advisory lock), so that a check for an existing run is safe (GA12-06)."""
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(f"job:{job_key}:{tenant_id}", 0)))
    )


async def job_allowed(
    session: AsyncSession, tenant_id: uuid.UUID, job_key: str, *, now: datetime | None = None
) -> bool:
    row = await session.scalar(
        select(TenantJobSchedule).where(
            TenantJobSchedule.tenant_id == tenant_id, TenantJobSchedule.job_key == job_key
        )
    )
    if row is None:
        return True
    return row.enabled and in_window(row.run_at, now or datetime.now(UTC))
