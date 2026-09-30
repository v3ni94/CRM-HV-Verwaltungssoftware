"""Per tenant configuration of the standard jobs (S15-03, section 15.1, decision 12 a).

The beat schedule in ``mhvp.worker`` stays global. A job that runs per tenant asks
``job_allowed`` before it works on a tenant: a disabled job is skipped, and with a start time
the job only works in the window of ``WINDOW_MINUTES`` after that time (local time
Europe/Berlin), so a beat that fires more often than once a day still runs it once per day.
No row means: runs as scheduled. Switching jobs off or moving them opens no release gate.
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
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
    if run_at is None:
        return True
    local = now.astimezone(SCHEDULE_TZ)
    hour, minute = (int(x) for x in run_at.split(":"))
    elapsed = (local.hour * 60 + local.minute) - (hour * 60 + minute)
    return 0 <= elapsed < WINDOW_MINUTES


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
