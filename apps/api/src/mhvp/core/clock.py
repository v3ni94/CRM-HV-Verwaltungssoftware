"""Business calendar day (section 4.1, rule M1-09).

Dates of business facts (cut-off dates, validity, protocol dates, lock checks) use the
calendar day in the operator time zone, not the UTC day. Between 00:00 and 02:00 local
time the UTC day would be one day behind. Timestamps stay ``TIMESTAMPTZ`` in UTC.

Assumption (docs/ASSUMPTIONS.md): no per tenant time zone setting exists yet, so
``Europe/Berlin`` applies to all tenants.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BUSINESS_TZ_NAME = "Europe/Berlin"
BUSINESS_TZ = ZoneInfo(BUSINESS_TZ_NAME)


def local_today(now: datetime | None = None) -> date:
    """Calendar day in ``Europe/Berlin``; ``now`` (aware) allows deterministic tests."""
    moment = now if now is not None else datetime.now(UTC)
    return moment.astimezone(BUSINESS_TZ).date()


def local_date(moment: datetime) -> date:
    """Calendar day of an aware timestamp in the business time zone."""
    return moment.astimezone(BUSINESS_TZ).date()
