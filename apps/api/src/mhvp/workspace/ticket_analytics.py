"""Ticket and mail throughput analytics (``GET /api/v1/workspace/ticket-analytics``,
operator request 26.09.2026).

Orientation figures only (no legal cut-off dates, no money). Everything is computed in a
fixed number of aggregated statements per request (no N+1) inside the tenant scope (RLS):

- ``tickets``: one row per ticket created in the window with its first staff response,
  reply count and source mailbox as correlated scalar subqueries;
- ``status events``: one row per status transition in the window (closing or reopening);
- ``messages``: inbound and sent outbound mails grouped by bucket, mailbox and author;
- ``backlog``: three counts before the window start (created, closed, reopened);
- ``open assigned``: open tickets per assignee;
- ``mailboxes``: all mailboxes of the tenant with their kind (personal, default, other);
  mails without mailbox or of a deleted mailbox count as ``other`` in ``by_kind``.

Definitions (documented in the handbook chapter ``auswertung-tickets``):

- Buckets are aligned to Europe/Berlin wall time (``bucket``: hour, day, week from Monday,
  month). Keys are the ISO 8601 bucket start with offset.
- ``tickets_created``: tickets by ``created_at``.
- ``tickets_closed``: status transitions from a non closing to a closing status
  (``CLOSING_STATUSES``), by the time of the transition; ``done`` to ``closed`` is no new
  closing. ``tickets_reopened``: transitions from a closing to a non closing status.
- ``backlog_end``: open tickets at the end of the bucket, derived as
  created minus closed plus reopened over the whole history up to the bucket end.
- ``inbound``: mails with ``direction == "in"`` by ``received_at`` (fallback ``created_at``);
  ``outbound``: mails with ``direction == "out"`` and ``status == "sent"`` by ``sent_at``.
- ``replies_per_ticket``: sent outbound mails linked to a ticket in the bucket divided by
  tickets created in the bucket.
- ``first_response``: minutes from ticket creation to the first sent outbound mail or the
  first comment by a staff user (whichever comes first), cohort by ticket creation;
  median and 90th percentile with linear interpolation (``percentile_cont``).
- ``time_to_close``: minutes from ticket creation to the closing transition, cohort by the
  closing time; median.
- ``throughput_per_minute``: tickets closed divided by the minutes of the bucket clipped to
  the window; ``throughput_per_hour`` is the same times 60. Two decimals.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, false, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox, MailboxUser, Message
from mhvp.tickets.models import Ticket, TicketComment, TicketEvent
from mhvp.tickets.status import CLOSING_STATUSES

LOCAL = ZoneInfo("Europe/Berlin")
LOCAL_NAME = "Europe/Berlin"

RANGES = ("day", "week", "month", "quarter", "year", "custom")
BUCKETS = ("auto", "hour", "day", "week", "month")
MAILBOX_KINDS = ("all", "personal", "default")
MAX_CUSTOM_DAYS = 400

Unit = Literal["hour", "day", "week", "month"]
Range = Literal["day", "week", "month", "quarter", "year", "custom"]

_CLOSING = [s.value for s in CLOSING_STATUSES]
_RANGE_DAYS = {"day": 0, "week": 6, "month": 29, "quarter": 89, "year": 364}
_AUTO_UNIT: dict[str, Unit] = {
    "day": "hour",
    "week": "day",
    "month": "day",
    "quarter": "week",
    "year": "month",
}


# Window and buckets ------------------------------------------------------------------------


def auto_unit(range_key: str, start: date, end: date) -> Unit:
    """Bucket size for ``auto``: hour for a day, day up to 31 days, week up to 120 days,
    month beyond."""
    if range_key != "custom":
        return _AUTO_UNIT[range_key]
    span = (end - start).days + 1
    if span <= 1:
        return "hour"
    if span <= 31:
        return "day"
    if span <= 120:
        return "week"
    return "month"


def trunc_local(moment: datetime, unit: Unit) -> datetime:
    """Start of the bucket (Europe/Berlin wall time, tz aware) containing ``moment``."""
    local = moment.astimezone(LOCAL)
    if unit == "hour":
        return local.replace(minute=0, second=0, microsecond=0)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == "day":
        return day
    if unit == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def next_bucket(start: datetime, unit: Unit) -> datetime:
    """Start of the following bucket; wall time arithmetic so that DST days keep whole days."""
    if unit == "hour":
        return (start.astimezone(UTC) + timedelta(hours=1)).astimezone(LOCAL)
    naive = start.replace(tzinfo=None)
    if unit == "day":
        naive += timedelta(days=1)
    elif unit == "week":
        naive += timedelta(days=7)
    else:
        days_in_month = calendar.monthrange(naive.year, naive.month)[1]
        naive += timedelta(days=days_in_month)
    return naive.replace(tzinfo=LOCAL)


def bucket_key(start: datetime) -> str:
    return start.astimezone(LOCAL).isoformat()


@dataclass
class Window:
    range: str
    unit: Unit
    start: datetime  # tz aware, local bucket boundary
    end: datetime  # exclusive
    starts: list[datetime] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return [bucket_key(s) for s in self.starts]


def build_window(
    range_key: str,
    today: date,
    *,
    unit: str = "auto",
    date_from: date | None = None,
    date_to: date | None = None,
) -> Window:
    """Window [start, end) in local time aligned to whole buckets. Named ranges roll back
    from ``today`` inclusive; ``custom`` uses ``date_from`` .. ``date_to`` inclusive."""
    if range_key == "custom":
        if date_from is None or date_to is None:
            raise ValueError("custom range requires from and to")
        if date_to < date_from:
            raise ValueError("to must not be before from")
        if (date_to - date_from).days + 1 > MAX_CUSTOM_DAYS:
            raise ValueError(f"custom range is limited to {MAX_CUSTOM_DAYS} days")
        first, last = date_from, date_to
    else:
        first, last = today - timedelta(days=_RANGE_DAYS[range_key]), today
    resolved: Unit = auto_unit(range_key, first, last) if unit == "auto" else unit  # type: ignore[assignment]
    start = trunc_local(datetime.combine(first, datetime.min.time(), tzinfo=LOCAL), resolved)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=LOCAL)
    starts: list[datetime] = []
    cursor = start
    while cursor < end:
        starts.append(cursor)
        cursor = next_bucket(cursor, resolved)
    return Window(range=range_key, unit=resolved, start=start, end=end, starts=starts)


def bucket_minutes(window: Window, index: int) -> float:
    """Minutes of the bucket clipped to the window (last bucket may be shorter)."""
    start = window.starts[index]
    end = window.starts[index + 1] if index + 1 < len(window.starts) else window.end
    end = min(end, window.end)
    return (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() / 60


# Statistics helpers ------------------------------------------------------------------------


def percentile(values: list[float], q: float) -> float | None:
    """Linear interpolation between closest ranks (PostgreSQL ``percentile_cont``)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 1)


def _minutes(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 60


def _ratio(numerator: int, denominator: int, digits: int = 2) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, digits)


# Filters -----------------------------------------------------------------------------------


@dataclass
class Filters:
    user_id: uuid.UUID | None = None
    mailbox_ids: set[uuid.UUID] | None = None  # None = no mailbox restriction


def source_mailbox_expression() -> Any:
    """Correlated scalar subquery: mailbox of the earliest inbound mail of the ticket."""
    return (
        select(Message.mailbox_id)
        .where(Message.ticket_id == Ticket.id, Message.direction == "in")
        .order_by(func.coalesce(Message.received_at, Message.created_at), Message.created_at)
        .limit(1)
        .correlate(Ticket)
        .scalar_subquery()
    )


def _ticket_conditions(filters: Filters) -> list[Any]:
    conditions: list[Any] = []
    if filters.user_id is not None:
        conditions.append(Ticket.assignee_user_id == filters.user_id)
    if filters.mailbox_ids is not None:
        if not filters.mailbox_ids:
            conditions.append(false())
        else:
            conditions.append(source_mailbox_expression().in_(list(filters.mailbox_ids)))
    return conditions


_inbound_at = func.coalesce(Message.received_at, Message.created_at)
_outbound_at = func.coalesce(Message.sent_at, Message.created_at)
_message_at = case((Message.direction == "in", _inbound_at), else_=_outbound_at)


def _message_conditions(filters: Filters) -> list[Any]:
    conditions: list[Any] = [
        or_(
            Message.direction == "in",
            and_(Message.direction == "out", Message.status == "sent"),
        )
    ]
    if filters.mailbox_ids is not None:
        if not filters.mailbox_ids:
            conditions.append(false())
        else:
            conditions.append(Message.mailbox_id.in_(list(filters.mailbox_ids)))
    if filters.user_id is not None:
        # Outbound: mails drafted by the user. Inbound: mails of tickets assigned to the user.
        assigned = (
            select(Ticket.id)
            .where(Ticket.id == Message.ticket_id, Ticket.assignee_user_id == filters.user_id)
            .correlate(Message)
            .exists()
        )
        conditions.append(
            or_(
                and_(Message.direction == "out", Message.created_by == filters.user_id),
                and_(Message.direction == "in", assigned),
            )
        )
    return conditions


# Queries -----------------------------------------------------------------------------------


async def resolve_mailboxes(session: AsyncSession) -> list[dict[str, Any]]:
    """All mailboxes of the tenant with their kind: ``default`` (``is_default``),
    ``personal`` (bound to one or more users via ``MailboxUser``), else ``other``."""
    grants = (
        select(MailboxUser.mailbox_id, func.count().label("users"))
        .group_by(MailboxUser.mailbox_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Mailbox.id, Mailbox.address, Mailbox.is_default, grants.c.users)
            .outerjoin(grants, grants.c.mailbox_id == Mailbox.id)
            .where(Mailbox.deleted_at.is_(None))
            .order_by(Mailbox.address)
        )
    ).all()
    out = []
    for mailbox_id, address, is_default, users in rows:
        kind = "default" if is_default else ("personal" if (users or 0) > 0 else "other")
        out.append({"mailbox_id": mailbox_id, "address": address, "kind": kind})
    return out


async def _ticket_rows(
    session: AsyncSession, window: Window, filters: Filters
) -> list[dict[str, Any]]:
    first_out = (
        select(func.min(_outbound_at))
        .where(Message.ticket_id == Ticket.id, Message.direction == "out", Message.status == "sent")
        .correlate(Ticket)
        .scalar_subquery()
    )
    first_comment = (
        select(func.min(TicketComment.created_at))
        .where(TicketComment.ticket_id == Ticket.id, TicketComment.author_user_id.is_not(None))
        .correlate(Ticket)
        .scalar_subquery()
    )
    replies = (
        select(func.count())
        .where(Message.ticket_id == Ticket.id, Message.direction == "out", Message.status == "sent")
        .correlate(Ticket)
        .scalar_subquery()
    )
    query = (
        select(
            Ticket.id,
            Ticket.created_at,
            Ticket.created_by,
            Ticket.assignee_user_id,
            source_mailbox_expression().label("source_mailbox_id"),
            func.least(first_out, first_comment).label("first_response_at"),
            replies.label("replies"),
        )
        .where(Ticket.created_at >= window.start, Ticket.created_at < window.end)
        .where(*_ticket_conditions(filters))
    )
    return [dict(r._mapping) for r in (await session.execute(query)).all()]


async def _status_rows(
    session: AsyncSession, window: Window, filters: Filters
) -> list[dict[str, Any]]:
    """Closing and reopening transitions in the window (one row each)."""
    to_closing = TicketEvent.data["to"].astext.in_(_CLOSING)
    from_closing = TicketEvent.data["from"].astext.in_(_CLOSING)
    query = (
        select(
            TicketEvent.created_at.label("at"),
            TicketEvent.user_id,
            Ticket.created_at.label("ticket_created_at"),
            case(
                (and_(to_closing, ~from_closing), literal("closed")), else_=literal("reopened")
            ).label("transition"),
        )
        .join(Ticket, Ticket.id == TicketEvent.ticket_id)
        .where(
            TicketEvent.kind == "status",
            TicketEvent.created_at >= window.start,
            TicketEvent.created_at < window.end,
            or_(and_(to_closing, ~from_closing), and_(from_closing, ~to_closing)),
        )
        .where(*_ticket_conditions(filters))
    )
    return [dict(r._mapping) for r in (await session.execute(query)).all()]


def _bucket_expression(unit: Unit, column: Any) -> Any:
    return func.date_trunc(unit, func.timezone(LOCAL_NAME, column))


async def _message_rows(
    session: AsyncSession, window: Window, filters: Filters
) -> list[dict[str, Any]]:
    """Mails grouped by bucket, direction, mailbox, author and whether a ticket is linked."""
    bucket = _bucket_expression(window.unit, _message_at)
    linked = Message.ticket_id.is_not(None)
    query = (
        select(
            bucket.label("bucket"),
            Message.direction,
            Message.mailbox_id,
            Message.created_by,
            linked.label("linked"),
            func.count().label("n"),
        )
        .where(_message_at >= window.start, _message_at < window.end)
        .where(*_message_conditions(filters))
        .group_by(bucket, Message.direction, Message.mailbox_id, Message.created_by, linked)
    )
    return [dict(r._mapping) for r in (await session.execute(query)).all()]


async def _backlog_before(session: AsyncSession, window: Window, filters: Filters) -> int:
    conditions = _ticket_conditions(filters)
    to_closing = TicketEvent.data["to"].astext.in_(_CLOSING)
    from_closing = TicketEvent.data["from"].astext.in_(_CLOSING)
    created = (
        select(func.count())
        .select_from(Ticket)
        .where(Ticket.created_at < window.start, *conditions)
        .scalar_subquery()
    )

    def transitions(condition: Any) -> Any:
        return (
            select(func.count())
            .select_from(TicketEvent)
            .join(Ticket, Ticket.id == TicketEvent.ticket_id)
            .where(
                TicketEvent.kind == "status",
                TicketEvent.created_at < window.start,
                condition,
                *conditions,
            )
            .scalar_subquery()
        )

    closed = transitions(and_(to_closing, ~from_closing))
    reopened = transitions(and_(from_closing, ~to_closing))
    row = (await session.execute(select(created, closed, reopened))).one()
    return int(row[0] or 0) - int(row[1] or 0) + int(row[2] or 0)


async def _open_assigned(session: AsyncSession, filters: Filters) -> dict[uuid.UUID, int]:
    query = (
        select(Ticket.assignee_user_id, func.count())
        .where(Ticket.status.not_in(list(CLOSING_STATUSES)), Ticket.assignee_user_id.is_not(None))
        .where(*_ticket_conditions(filters))
        .group_by(Ticket.assignee_user_id)
    )
    return {uid: int(n) for uid, n in (await session.execute(query)).all()}


# Aggregation -------------------------------------------------------------------------------


def _new_bucket() -> dict[str, Any]:
    return {
        "tickets_created": 0,
        "tickets_closed": 0,
        "tickets_reopened": 0,
        "inbound": 0,
        "outbound": 0,
        "replies": 0,
        "_first": [],
        "_close": [],
    }


def _finish(row: dict[str, Any], minutes: float | None) -> dict[str, Any]:
    first = row.pop("_first")
    close = row.pop("_close")
    replies = row.pop("replies")
    row["replies_per_ticket"] = _ratio(replies, row["tickets_created"])
    row["first_response_median_minutes"] = percentile(first, 0.5)
    row["first_response_p90_minutes"] = percentile(first, 0.9)
    row["time_to_close_median_minutes"] = percentile(close, 0.5)
    if minutes and minutes > 0:
        row["throughput_per_minute"] = round(row["tickets_closed"] / minutes, 2)
        row["throughput_per_hour"] = round(row["tickets_closed"] / minutes * 60, 2)
    else:
        row["throughput_per_minute"] = None
        row["throughput_per_hour"] = None
    return row


async def compute(
    session: AsyncSession,
    window: Window,
    filters: Filters,
    mailboxes: list[dict[str, Any]],
) -> dict[str, Any]:
    tickets = await _ticket_rows(session, window, filters)
    transitions = await _status_rows(session, window, filters)
    messages = await _message_rows(session, window, filters)
    backlog = await _backlog_before(session, window, filters)
    open_assigned = await _open_assigned(session, filters)

    keys = window.keys
    buckets: dict[str, dict[str, Any]] = {k: _new_bucket() for k in keys}
    totals = _new_bucket()

    def bucket_for(moment: datetime) -> dict[str, Any] | None:
        return buckets.get(bucket_key(trunc_local(moment, window.unit)))

    staff: dict[uuid.UUID, dict[str, Any]] = {}

    def staff_row(user_id: uuid.UUID) -> dict[str, Any]:
        return staff.setdefault(
            user_id, {"closed": 0, "created": 0, "replies_sent": 0, "_first": []}
        )

    by_mailbox: dict[uuid.UUID | None, dict[str, int]] = {}

    def mailbox_row(mailbox_id: uuid.UUID | None) -> dict[str, int]:
        return by_mailbox.setdefault(
            mailbox_id, {"inbound": 0, "outbound": 0, "tickets_created": 0}
        )

    for t in tickets:
        row = bucket_for(t["created_at"])
        targets = [totals] + ([row] if row is not None else [])
        first = t["first_response_at"]
        minutes_first = _minutes(first, t["created_at"]) if first is not None else None
        for target in targets:
            target["tickets_created"] += 1
            if minutes_first is not None:
                target["_first"].append(minutes_first)
        if t["created_by"] is not None:
            staff_row(t["created_by"])["created"] += 1
        if t["assignee_user_id"] is not None and minutes_first is not None:
            staff_row(t["assignee_user_id"])["_first"].append(minutes_first)
        mailbox_row(t["source_mailbox_id"])["tickets_created"] += 1

    for e in transitions:
        row = bucket_for(e["at"])
        targets = [totals] + ([row] if row is not None else [])
        if e["transition"] == "closed":
            minutes_close = _minutes(e["at"], e["ticket_created_at"])
            for target in targets:
                target["tickets_closed"] += 1
                target["_close"].append(minutes_close)
            if e["user_id"] is not None:
                staff_row(e["user_id"])["closed"] += 1
        else:
            for target in targets:
                target["tickets_reopened"] += 1

    for m in messages:
        local_start = m["bucket"].replace(tzinfo=LOCAL)
        row = buckets.get(bucket_key(local_start))
        targets = [totals] + ([row] if row is not None else [])
        n = int(m["n"])
        if m["direction"] == "in":
            for target in targets:
                target["inbound"] += n
            mailbox_row(m["mailbox_id"])["inbound"] += n
        else:
            for target in targets:
                target["outbound"] += n
                if m["linked"]:
                    target["replies"] += n
            mailbox_row(m["mailbox_id"])["outbound"] += n
            if m["created_by"] is not None:
                staff_row(m["created_by"])["replies_sent"] += n

    running = backlog
    out_buckets: list[dict[str, Any]] = []
    for index, key in enumerate(keys):
        row = buckets[key]
        running += row["tickets_created"] - row["tickets_closed"] + row["tickets_reopened"]
        row["backlog_end"] = running
        start = window.starts[index]
        end = window.starts[index + 1] if index + 1 < len(window.starts) else window.end
        minutes = bucket_minutes(window, index)
        out_buckets.append(
            {
                "key": key,
                "start": start.astimezone(LOCAL),
                "end": min(end, window.end).astimezone(LOCAL),
                "minutes": round(minutes, 2),
                **_finish(row, minutes),
            }
        )
    total_minutes = (window.end.astimezone(UTC) - window.start.astimezone(UTC)).total_seconds() / 60
    totals["backlog_end"] = running
    totals_out = {"backlog_start": backlog, **_finish(totals, total_minutes)}

    staff_out = []
    for uid in sorted(set(staff) | set(open_assigned), key=str):
        row = staff.get(uid, {"closed": 0, "created": 0, "replies_sent": 0, "_first": []})
        first = row.pop("_first")
        staff_out.append(
            {
                "user_id": uid,
                **row,
                "first_response_median_minutes": percentile(first, 0.5),
                "open_assigned": open_assigned.get(uid, 0),
            }
        )

    total_inbound = totals_out["inbound"]
    mailbox_out = []
    by_kind: dict[str, dict[str, Any]] = {
        k: {"inbound": 0, "outbound": 0, "tickets_created": 0}
        for k in ("personal", "default", "other")
    }
    for m in mailboxes:
        counts = by_mailbox.get(
            m["mailbox_id"], {"inbound": 0, "outbound": 0, "tickets_created": 0}
        )
        if filters.mailbox_ids is not None and m["mailbox_id"] not in filters.mailbox_ids:
            continue
        for k, v in counts.items():
            by_kind[m["kind"]][k] += v
        mailbox_out.append(
            {
                **m,
                **counts,
                "share_inbound_pct": _ratio(counts["inbound"] * 100, total_inbound, 1),
            }
        )
    # Mails without mailbox and mails of mailboxes no longer listed (deleted) count as
    # "other" when no mailbox filter is set, so that the kinds add up to the totals.
    listed = {m["mailbox_id"] for m in mailboxes}
    if filters.mailbox_ids is None:
        for mailbox_id, counts in by_mailbox.items():
            if mailbox_id in listed:
                continue
            for k, v in counts.items():
                by_kind["other"][k] += v
    for kind_row in by_kind.values():
        kind_row["share_inbound_pct"] = _ratio(kind_row["inbound"] * 100, total_inbound, 1)

    return {
        "range": window.range,
        "bucket": window.unit,
        "timezone": LOCAL_NAME,
        "start": window.start,
        "end": window.end,
        "totals": totals_out,
        "buckets": out_buckets,
        "staff": staff_out,
        "mailboxes": mailbox_out,
        "by_kind": by_kind,
        "all_mailboxes": mailboxes,
    }
