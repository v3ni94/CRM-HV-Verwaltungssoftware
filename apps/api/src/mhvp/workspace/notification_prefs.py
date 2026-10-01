"""Notification preferences per user (M23-04): channel per kind and mute.

Defaults without a row: in app on, mail off, not muted. The kinds of the catalogue can be
switched; ``MANDATORY_KINDS`` (legal or money relevant reminders and the SLA escalation) ignore
every switch and mute (Produktschutz, never claimed as a legal duty). Mail is only requested
here (``Notification.email_pending``); sending is done by the job ``send_pending_mails``.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.workspace.models import Notification, NotificationPreference

DEFAULT_KIND = "*"
MANDATORY_KINDS = frozenset({"sla_escalation", "compliance_deadline", "banking.consent_expiring"})
# Kinds offered on the settings page (label key in the UI: NotificationSettings.kind.<code>).
CATALOGUE: tuple[str, ...] = (
    "ticket_assigned",
    "ticket.mail_received",
    "ticket.follow_up_created",
    "portal_chat_message",
    "portal_chat_reply",
    "mail.approval_requested",
    "maintenance_due",
    "maintenance_overdue",
    "calendar_reminder",
    "daily_digest",
    "automation",
    "consumption_info",
    "automation_webhook_dead",
    "sla_escalation",
    "compliance_deadline",
    "banking.consent_expiring",
)
MAIL_BATCH = 100


@dataclass(frozen=True)
class Channels:
    in_app: bool
    email: bool


def resolve(rows: list[NotificationPreference], kind: str, now: datetime | None = None) -> Channels:
    """Effective channels for ``kind``: own row, else the user default, else the defaults."""
    if kind in MANDATORY_KINDS:
        return Channels(in_app=True, email=False)
    moment = now or datetime.now(UTC)
    by_kind = {r.kind: r for r in rows}
    own = by_kind.get(kind)
    default = by_kind.get(DEFAULT_KIND)
    for row in (own, default):
        if row is not None and row.muted_until is not None and row.muted_until > moment:
            return Channels(in_app=False, email=False)
    chosen = own or default
    if chosen is None:
        return Channels(in_app=True, email=False)
    return Channels(in_app=chosen.in_app, email=chosen.email)


async def channels_for(session: AsyncSession, user_id: uuid.UUID, kind: str) -> Channels:
    rows = (
        await session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.kind.in_((kind, DEFAULT_KIND)),
            )
        )
    ).all()
    return resolve(list(rows), kind)


async def send_pending_mails(
    session: AsyncSession, settings: object, tenant_id: uuid.UUID
) -> dict[str, int]:
    """Sends the requested mails of one tenant (system mail, no approval process like the
    digest). A failed send stays pending for the next run; an address-less user is skipped
    and marked as sent without a mail so that the job does not retry forever."""
    from mhvp.platform.models import User
    from mhvp.sla.channels import send_email

    rows = (
        await session.execute(
            select(Notification, User.email)
            .join(User, User.id == Notification.user_id)
            .where(Notification.email_pending.is_(True), Notification.email_sent_at.is_(None))
            .order_by(Notification.created_at)
            .limit(MAIL_BATCH)
        )
    ).all()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    for notification, address in rows:
        if not address:
            notification.email_sent_at = datetime.now(UTC)
            counts["skipped"] += 1
            continue
        error = await send_email(
            session,
            settings,  # type: ignore[arg-type]
            tenant_id,
            address,
            notification.title,
            (notification.body or notification.title)
            + "\n\nAutomatische Systemmail der Verwaltungsplattform. "
            "Die Einstellungen finden Sie unter Einstellungen, Benachrichtigungen.",
        )
        if error is None:
            notification.email_sent_at = datetime.now(UTC)
            counts["sent"] += 1
        else:
            counts["failed"] += 1
    await session.flush()
    return counts
