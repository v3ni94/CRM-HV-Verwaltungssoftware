"""Notification preferences per user (M23-04): channel per kind and mute.

Defaults without a row: in app on, mail off, not muted. The kinds of the catalogue can be
switched; ``MANDATORY_KINDS`` (legal or money relevant reminders and the SLA escalation) ignore
every switch and mute (Produktschutz, never claimed as a legal duty). Mail is only requested
here (``Notification.email_pending``); sending is done by the job ``send_pending_mails`` as one
collective mail per user, immediately (every run) or daily per ``email_mode``.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

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
MAIL_PAGES = 20
EMAIL_MODE_IMMEDIATE = "immediate"
EMAIL_MODE_DAILY = "daily"
EMAIL_MODES = (EMAIL_MODE_IMMEDIATE, EMAIL_MODE_DAILY)
# U15-04: content of the notification mails per tenant (``tenant_settings.sources``). ``voll``
# is the previous behaviour; ``hinweis`` sends only the count and a link, no title or text.
MAIL_CONTENT_FULL = "voll"
MAIL_CONTENT_HINT = "hinweis"
MAIL_CONTENT_KEY = "notification_mail_content"


async def mail_content_mode(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings).where(TenantSettings.tenant_id == tenant_id))
    value = (row.sources or {}).get(MAIL_CONTENT_KEY) if row is not None else None
    return MAIL_CONTENT_HINT if value == MAIL_CONTENT_HINT else MAIL_CONTENT_FULL


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


def mail_mode(rows: list[NotificationPreference], kind: str) -> str:
    """Delivery of the mail for ``kind``: own row, else the user default, else immediate."""
    by_kind = {r.kind: r for r in rows}
    chosen = by_kind.get(kind) or by_kind.get(DEFAULT_KIND)
    return chosen.email_mode if chosen is not None else EMAIL_MODE_IMMEDIATE


async def send_pending_mails(
    session: AsyncSession, settings: object, tenant_id: uuid.UUID, *, daily: bool = False
) -> dict[str, int]:
    """Sends the requested mails of one tenant as one collective mail per user and run
    (system mail through the default mailbox of the tenant, no approval process like the
    digest). Preference ``immediate`` is sent by every run, ``daily`` only by the daily run
    (``daily=True``). The mute is respected when the notification is created
    (``notify``), so a mail requested before a later mute is still sent. A failed send stays
    pending for the next run; an
    address-less user is closed without a mail so that the job does not retry forever.
    ``sent``, ``failed`` and ``skipped`` count notifications, ``mails`` the mails sent."""
    from sqlalchemy import and_, tuple_

    from mhvp.platform.models import Membership, MembershipStatus, User
    from mhvp.sla.channels import send_email

    # U15: keyset pages so that daily mails held back by an immediate run never starve the
    # immediate ones behind them (MAIL_PAGES bounds one run). Only an active user with an
    # active membership of this tenant receives tenant content by mail; otherwise the
    # notification is closed without a mail (no data leaves after an offboarding).
    rows: list[Any] = []
    last: tuple[datetime, uuid.UUID] | None = None
    for _ in range(MAIL_PAGES):
        query = (
            select(Notification, User.email, User.active, Membership.status)
            .join(User, User.id == Notification.user_id)
            .outerjoin(
                Membership,
                and_(
                    Membership.user_id == Notification.user_id,
                    Membership.tenant_id == tenant_id,
                ),
            )
            .where(Notification.email_pending.is_(True), Notification.email_sent_at.is_(None))
            .order_by(Notification.created_at, Notification.id)
            .limit(MAIL_BATCH)
        )
        if last is not None:
            query = query.where(tuple_(Notification.created_at, Notification.id) > last)
        page = (await session.execute(query)).all()
        rows.extend(page)
        if len(page) < MAIL_BATCH:
            break
        last = (page[-1][0].created_at, page[-1][0].id)
    counts = {"sent": 0, "failed": 0, "skipped": 0, "mails": 0}
    hint_only = await mail_content_mode(session, tenant_id) == MAIL_CONTENT_HINT
    by_user: dict[uuid.UUID, list[tuple[Notification, str | None]]] = {}
    for notification, email, user_active, membership_status in rows:
        allowed = bool(user_active) and membership_status == MembershipStatus.ACTIVE
        address = email if allowed else None
        by_user.setdefault(notification.user_id, []).append((notification, address))
    now = datetime.now(UTC)
    for user_id, entries in by_user.items():
        prefs = list(
            (
                await session.scalars(
                    select(NotificationPreference).where(
                        NotificationPreference.user_id == user_id,
                    )
                )
            ).all()
        )
        due: list[Notification] = []
        for notification, address in entries:
            if not address:
                notification.email_sent_at = now
                counts["skipped"] += 1
            elif mail_mode(prefs, notification.kind) == EMAIL_MODE_DAILY and not daily:
                continue
            else:
                due.append(notification)
        if not due:
            continue
        address = entries[0][1] or ""
        if hint_only:
            # U15-04: no title and no text leave the platform, only count and link.
            base = str(getattr(settings, "web_crm_url", "") or "").rstrip("/")
            link = base if base else "dem CRM"
            noun = "Benachrichtigung" if len(due) == 1 else "Benachrichtigungen"
            subject = f"{len(due)} neue {noun}"
            text = f"Es liegen {len(due)} neue Benachrichtigung(en) im CRM vor: {link}"
        elif len(due) == 1:
            subject = due[0].title
            text = due[0].body or due[0].title
        else:
            subject = f"{len(due)} neue Benachrichtigungen"
            text = "\n\n".join(f"{n.title}" + (f"\n{n.body}" if n.body else "") for n in due)
        error = await send_email(
            session,
            settings,  # type: ignore[arg-type]
            tenant_id,
            address,
            subject,
            text + "\n\nAutomatische Systemmail der Verwaltungsplattform. "
            "Die Einstellungen finden Sie unter Einstellungen, Benachrichtigungen.",
        )
        if error is None:
            for n in due:
                n.email_sent_at = now
            counts["sent"] += len(due)
            counts["mails"] += 1
        else:
            counts["failed"] += len(due)
    await session.flush()
    return counts
