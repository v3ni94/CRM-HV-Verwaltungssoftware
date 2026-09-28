"""Consequences of back channel decisions in mode ``done`` (rule M20-08, sections 6 and 7):
automatic ticket close with its guards, reopen from Gmail, reopen from the CRM (P03, P05 with
optional restore of the INBOX label), the settle run and the revert of an automatic decision.

Comments are internal, without author (shown as "System"); notifications use
``workspace.services.notify``. Gmail events never write to Gmail; the CRM writes back only
with ``gmail_restore_inbox_on_reopen`` and always with the expected state set first.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import duplicates, gmail_state
from mhvp.communication.gmail import GmailError
from mhvp.communication.models import Mailbox, Message
from mhvp.core.config import Settings
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError

log = logging.getLogger(__name__)

Hook = Callable[[], Awaitable[None]]

AUTO_CLOSE_KIND = "auskunft_erteilt"
CLOSE_ACTIONS = frozenset({"archived", "trashed"})
OPEN_OUTBOUND = ("draft", "pending", "sending")
RESTORE_STATES = frozenset({"archived", "trashed"})

K1 = (
    "Automatisch erledigt. Die letzte offene Mail dieses Tickets wurde in Gmail im Postfach "
    "{mailbox_address} {action_text} am {date} um {time} Uhr. Wird die Mail dort wieder in den "
    "Posteingang gelegt, öffnet die Plattform das Ticket innerhalb von {window_days} Tagen "
    'automatisch wieder. Diese Entscheidung kann in der Mailansicht über "Automatik '
    'zurücknehmen" aufgehoben werden.{sent_hint}'
)
K1_SENT_HINT = (
    " Hinweis: In der Gmail Konversation liegen {n} gesendete Antworten, die nicht im CRM "
    "gespeichert sind. Bitte bei Bedarf im Ticket nachtragen."
)
K2 = (
    "Automatisch wieder geöffnet. Die Mail wurde in Gmail im Postfach {mailbox_address} am "
    "{date} um {time} Uhr wieder in den Posteingang gelegt."
)
K3 = (
    'Hinweis: Die Mail "{subject}" wurde in Gmail im Postfach {mailbox_address} endgültig '
    "gelöscht. Das Original bleibt in der Plattform gespeichert. Das Ticket wurde nicht "
    "automatisch abgeschlossen, bitte prüfen."
)
K4 = (
    'Hinweis: Die Mail "{subject}" wurde in Gmail wieder in den Posteingang gelegt. Das '
    "Wiedereröffnungsfenster von {window_days} Tagen ist abgelaufen, das Ticket bleibt "
    "geschlossen. Die Mail ist in der Mailübersicht wieder offen."
)
ACTION_TEXT = {"archived": "archiviert", "trashed": "in den Papierkorb verschoben"}


def _stamp(now: datetime) -> tuple[str, str]:
    from mhvp.workspace.services import _LOCAL

    local = now.astimezone(_LOCAL)
    return local.strftime("%d.%m.%Y"), local.strftime("%H:%M")


async def _comment(session: AsyncSession, ticket: Any, body: str) -> None:
    from mhvp.tickets.models import TicketComment

    session.add(
        TicketComment(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            internal=True,
            author_user_id=None,
            body=body,
        )
    )


async def _recipients(session: AsyncSession, ticket: Any) -> set[uuid.UUID]:
    from mhvp.tickets.models import Team, TicketAssignee

    users: set[uuid.UUID] = set()
    if ticket.assignee_user_id:
        users.add(ticket.assignee_user_id)
    users.update(
        await session.scalars(
            select(TicketAssignee.user_id).where(TicketAssignee.ticket_id == ticket.id)
        )
    )
    if ticket.team_id:
        team = await session.get(Team, ticket.team_id)
        if team is not None:
            users.update(team.member_user_ids or [])
    return users


async def _notify(
    session: AsyncSession, ticket: Any, users: set[uuid.UUID], kind: str, title: str, body: str
) -> None:
    from mhvp.workspace.services import notify

    for user_id in users:
        await notify(
            session,
            tenant_id=ticket.tenant_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            target_type="ticket",
            target_id=ticket.id,
        )


def _skip_event(ticket: Any, reason: str, trigger: Message, detail: str | None = None) -> Any:
    from mhvp.tickets.models import TicketEvent

    data: dict[str, Any] = {"reason": reason, "source": "gmail", "message_id": str(trigger.id)}
    if detail:
        data["detail"] = detail[:500]
    return TicketEvent(
        tenant_id=ticket.tenant_id, ticket_id=ticket.id, kind="auto_close_skipped", data=data
    )


# After apply: once per ticket ---------------------------------------------------------------


async def after_apply(
    session: AsyncSession,
    settings: Settings,
    mailbox: Mailbox,
    completed: Sequence[gmail_state.Applied],
    tenant_settings: Any,
) -> None:
    """Ticket consequences of the groups completed in one run, once per ticket (a thread
    archived at once yields one status event, never n minus 1 refusals)."""
    seen: set[uuid.UUID] = set()
    for applied in completed:
        ticket_id = applied.ticket_id
        trigger = applied.trigger
        if ticket_id is None or ticket_id in seen or trigger is None:
            continue
        seen.add(ticket_id)
        if applied.gmail_action == "deleted":
            await note_deleted(session, ticket_id, trigger, mailbox.address)
            continue
        await try_auto_close_ticket(
            session,
            settings,
            ticket_id,
            trigger=trigger,
            mailbox_address=mailbox.address,
            gmail_action=applied.gmail_action or "archived",
            history_id=applied.history_id,
            tenant_settings=tenant_settings,
        )


async def note_deleted(
    session: AsyncSession, ticket_id: uuid.UUID, trigger: Message, mailbox_address: str
) -> None:
    """E09: a permanent deletion from the inbox completes the mail but never the ticket."""
    from mhvp.tickets.models import Ticket

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        return
    await _comment(
        session,
        ticket,
        K3.format(subject=trigger.subject or "", mailbox_address=mailbox_address),
    )
    session.add(_skip_event(ticket, "deleted", trigger))


async def try_auto_close_ticket(
    session: AsyncSession,
    settings: Settings,
    ticket_id: uuid.UUID,
    *,
    trigger: Message,
    mailbox_address: str,
    gmail_action: str,
    history_id: int | None,
    tenant_settings: Any,
) -> dict[str, Any]:
    """Conditions of section 6.1, all must hold; every refusal writes one
    ``auto_close_skipped`` event with its reason and leaves the mail done."""
    from mhvp.tickets import follow_up
    from mhvp.tickets.models import Ticket, TicketEvent, TicketStatus, WorkOrder
    from mhvp.tickets.resolution_kinds import active_kind_codes, load_resolution_kinds_config
    from mhvp.tickets.status import CLOSING_STATUSES, ResolutionIn, transition_status

    result: dict[str, Any] = {"ticket_closed": False, "reason": None}
    mode = str(tenant_settings.gmail_done_sync_mode)
    if mode != gmail_state.MODE_DONE:
        return result
    ticket = await session.get(Ticket, ticket_id, with_for_update=True)
    if ticket is None:
        return result
    if not tenant_settings.gmail_done_closes_ticket:
        result["reason"] = "ticket_close_disabled"
        if not await _skipped_today(session, ticket.id, "ticket_close_disabled"):
            session.add(_skip_event(ticket, "ticket_close_disabled", trigger))
        return result

    def refuse(reason: str, detail: str | None = None) -> dict[str, Any]:
        result["reason"] = reason
        session.add(_skip_event(ticket, reason, trigger, detail))
        return result

    if gmail_action not in CLOSE_ACTIONS:
        return refuse("deleted")
    if ticket.status in CLOSING_STATUSES or ticket.merged_into_ticket_id is not None:
        return result
    resolution = await follow_up.resolve(session, ticket.id)
    if resolution.ticket is None or resolution.ticket.id != ticket.id:
        return refuse("not_current")
    if ticket.status is TicketStatus.WAITING:
        return refuse("status_waiting")
    assigned = ticket.assignee_user_id is not None or ticket.status is TicketStatus.IN_PROGRESS
    if assigned and not tenant_settings.gmail_close_assigned_tickets:
        refuse("assigned_in_progress")
        if ticket.assignee_user_id:
            await _notify(
                session,
                ticket,
                {ticket.assignee_user_id},
                "ticket.auto_close_blocked",
                f"Ticket {ticket.number}: Mail in Gmail archiviert, Ticket bleibt offen",
                "Mail in Gmail archiviert, Ticket bleibt offen, weil es Ihnen zugewiesen ist",
            )
        return result
    group_ids = [m.id for m in await duplicates.group_members(session, trigger)] or [trigger.id]
    tenant_id = ticket.tenant_id
    open_mails = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == tenant_id,
            Message.ticket_id == ticket.id,
            Message.direction == "in",
            Message.status != "done",
            Message.duplicate_of_id.is_(None),
            Message.id.not_in(group_ids),
        )
    )
    if open_mails:
        return refuse("open_mails")
    from mhvp.communication.services import OPEN_WORK_ORDER_STATUSES

    open_orders = await session.scalar(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.ticket_id == ticket.id, WorkOrder.status.in_(OPEN_WORK_ORDER_STATUSES))
    )
    if open_orders:
        return refuse("open_work_order")
    open_outbound = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.ticket_id == ticket.id,
            Message.direction == "out",
            Message.status.in_(OPEN_OUTBOUND),
        )
    )
    if open_outbound:
        return refuse("open_outbound")
    if await _open_proposals(session, ticket.id):
        return refuse("open_proposal")
    if await _open_assignment_reviews(session, ticket.id):
        return refuse("open_assignment_review")
    if await _open_invoice(session, ticket.id):
        return refuse("open_invoice")
    keep_open = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.ticket_id == ticket.id,
            Message.direction == "in",
            Message.gmail_keep_open_label.is_not(None),
        )
    )
    if keep_open:
        return refuse("keep_open_label")
    config = await load_resolution_kinds_config(session, tenant_id)
    if AUTO_CLOSE_KIND not in active_kind_codes(config):
        return refuse("resolution_kind_disabled")
    try:
        changed = await transition_status(
            session,
            settings,
            ticket,
            TicketStatus.DONE,
            None,
            resolution=ResolutionIn(
                kind=AUTO_CLOSE_KIND, note=f"In Gmail archiviert (Postfach {mailbox_address})"
            ),
            extra_payload={"source": "gmail", "auto_close": True},
        )
    except ProblemError as exc:
        return refuse("transition_refused", exc.detail or "")
    if not changed:
        return result
    ticket.resolved_by = None
    await session.flush()
    event = await session.scalar(
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket.id, TicketEvent.kind == "status")
        .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
        .limit(1)
    )
    if event is not None and event.data.get("to") == TicketStatus.DONE.value:
        event.data = {
            **event.data,
            "auto_close": True,
            "source": "gmail",
            "message_id": str(trigger.id),
            "mailbox_address": mailbox_address,
            "gmail_action": gmail_action,
            "history_id": history_id,
        }
    now = datetime.now(UTC)
    date, time = _stamp(now)
    window_days = await follow_up.reopen_window_days(session, tenant_id)
    sent_hint = await _sent_hint(session, settings, trigger)
    await _comment(
        session,
        ticket,
        K1.format(
            mailbox_address=mailbox_address,
            action_text=ACTION_TEXT.get(gmail_action, "archiviert"),
            date=date,
            time=time,
            window_days=window_days,
            sent_hint=sent_hint,
        ),
    )
    await _notify(
        session,
        ticket,
        await _recipients(session, ticket),
        "ticket.auto_closed",
        f"Ticket {ticket.number} automatisch erledigt (Gmail)",
        f"Die letzte offene Mail wurde in Gmail im Postfach {mailbox_address} "
        f"{ACTION_TEXT.get(gmail_action, 'archiviert')}.",
    )
    result["ticket_closed"] = True
    return result


async def _skipped_today(session: AsyncSession, ticket_id: uuid.UUID, reason: str) -> bool:
    from mhvp.tickets.models import TicketEvent

    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    found = await session.scalar(
        select(TicketEvent.id).where(
            TicketEvent.ticket_id == ticket_id,
            TicketEvent.kind == "auto_close_skipped",
            TicketEvent.created_at >= start,
            TicketEvent.data["reason"].astext == reason,
        )
    )
    return found is not None


async def _open_proposals(session: AsyncSession, ticket_id: uuid.UUID) -> bool:
    from mhvp.ai.models import AiProposal, Decision

    found = await session.scalar(
        select(AiProposal.id).where(
            AiProposal.entity_type == "ticket",
            AiProposal.context_id == ticket_id,
            AiProposal.decision == Decision.PENDING,
        )
    )
    return found is not None


async def _open_assignment_reviews(session: AsyncSession, ticket_id: uuid.UUID) -> bool:
    from mhvp.communication.assignment_review import AssignmentReview

    mail_ids = select(Message.id).where(Message.ticket_id == ticket_id)
    found = await session.scalar(
        select(AssignmentReview.id).where(
            AssignmentReview.status == "open",
            ((AssignmentReview.entity_type == "message") & AssignmentReview.entity_id.in_(mail_ids))
            | (
                (AssignmentReview.entity_type == "ticket")
                & (AssignmentReview.entity_id == ticket_id)
            ),
        )
    )
    return found is not None


async def _open_invoice(session: AsyncSession, ticket_id: uuid.UUID) -> bool:
    from mhvp.ai.models import AiTaskRun, RunStatus
    from mhvp.communication.models import InvoiceIntakeAutoRun

    forwarding = await session.scalar(
        select(Message.id).where(
            Message.ticket_id == ticket_id,
            Message.classification["invoice_attached"].astext == "true",
            Message.classification["invoice_forward"]["status"].astext.in_(("queued", "failed")),
        )
    )
    if forwarding is not None:
        return True
    intake = await session.scalar(
        select(InvoiceIntakeAutoRun.id)
        .join(Message, Message.id == InvoiceIntakeAutoRun.message_id)
        .join(AiTaskRun, AiTaskRun.id == InvoiceIntakeAutoRun.task_run_id)
        .where(
            Message.ticket_id == ticket_id,
            AiTaskRun.status.in_((RunStatus.QUEUED, RunStatus.RUNNING)),
        )
    )
    return intake is not None


async def _sent_hint(session: AsyncSession, settings: Settings, trigger: Message) -> str:
    """Section 6.3: sent messages of the Gmail thread without a stored row; empty without
    thread, without mailbox or on a Gmail error (logged)."""
    from mhvp.communication.gmail import make_client, oauth_client

    if not trigger.gmail_thread_id or trigger.mailbox_id is None:
        return ""
    mailbox = await session.get(Mailbox, trigger.mailbox_id)
    if mailbox is None or mailbox.kind != "gmail":
        return ""
    try:
        client_id, client_secret = await oauth_client(session, settings)
        client = make_client(client_id, client_secret, mailbox)
    except GmailError:
        return ""
    try:
        messages = await client.thread_message_ids(trigger.gmail_thread_id)
    except GmailError as exc:
        log.warning("sent hint skipped", extra={"reason": str(exc)[:200]})
        return ""
    finally:
        await client.aclose()
    if not messages:
        return ""
    n = 0
    for gid, labels in messages:
        if "SENT" in labels and await duplicates.known_gmail_row(session, mailbox.id, gid) is None:
            n += 1
    return K1_SENT_HINT.format(n=n) if n else ""


# Reopen --------------------------------------------------------------------------------------


async def reopen_group(
    session: AsyncSession,
    settings: Settings,
    root: Message,
    *,
    source: str,
    restore: bool,
    actor_user_id: uuid.UUID | None = None,
    hooks: list[Hook] | None = None,
) -> dict[str, Any]:
    """Every copy of the group becomes open again (``assigned`` with ticket, else ``new``),
    the done and archive bookkeeping is cleared, ``gmail_reopened_at`` is set for the source
    Gmail. With ``restore`` (CRM source and ``gmail_restore_inbox_on_reopen``) archived or
    trashed copies get ``gmail_expected_state = inbox`` and the restore job after the commit.
    Echo copies of own sent mails stay done."""
    from mhvp.core.db.tenancy import after_commit

    members = await duplicates.group_members(session, root) or [root]
    now = datetime.now(UTC)
    previous = {
        "previous_status": root.status,
        "previous_done_source": root.done_source,
        "previous_archive_status": root.archive_status,
        "previous_archived_at": root.archived_at.isoformat() if root.archived_at else None,
    }
    restore_ids: list[uuid.UUID] = []
    for member in members:
        if (member.classification or {}).get("own_sent_echo"):
            continue
        member.status = "assigned" if member.ticket_id else "new"
        member.done_source = None
        member.done_at = None
        member.archive_status = None
        member.archived_at = None
        member.archive_history_id = None
        member.archive_error = None
        member.gmail_expected_state = None
        member.gmail_reopened_at = now if source == "gmail" else None
        member.gmail_settle_until = None
        if (
            restore
            and member.gmail_message_id
            and member.mailbox_id is not None
            and member.gmail_state in RESTORE_STATES
        ):
            member.gmail_expected_state = "inbox"
            member.archive_status = "restore_pending"
            restore_ids.append(member.id)
    tenant_id = root.tenant_id
    await emit(
        session,
        tenant_id=tenant_id,
        type=gmail_state.EVENT_REOPENED,
        entity_type="message",
        entity_id=duplicates.group_root(root),
        actor_user_id=actor_user_id,
        payload={"source": source, "copy_ids": [str(m.id) for m in members], **previous},
    )
    if restore_ids:
        await emit(
            session,
            tenant_id=tenant_id,
            type=gmail_state.EVENT_RESTORE_REQUESTED,
            entity_type="message",
            entity_id=duplicates.group_root(root),
            actor_user_id=actor_user_id,
            payload={"copy_ids": [str(i) for i in restore_ids]},
        )

        async def _restore() -> None:
            await enqueue_restore_for_messages(settings, tenant_id, restore_ids)

        if hooks is not None:
            hooks.append(_restore)
        else:
            after_commit(session, _restore)
    return {"copies": len(members), "restore": len(restore_ids)}


async def enqueue_restore_for_messages(
    settings: Settings, tenant_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> None:
    if settings.ai_inline:
        from mhvp.communication.tasks import gmail_restore_inbox_once

        try:
            await gmail_restore_inbox_once(settings, tenant_id, list(message_ids))
        except Exception:
            log.exception("restore job failed inline", extra={"messages": len(message_ids)})
        return
    try:
        from mhvp.worker import get_celery

        get_celery().send_task(
            "mhvp.communication.gmail_restore_inbox",
            args=[str(tenant_id), [str(m) for m in message_ids]],
            queue="mail",
        )
    except Exception:
        log.exception("could not queue restore job", extra={"messages": len(message_ids)})


async def reopen_from_gmail(
    session: AsyncSession,
    settings: Settings,
    lead: Message,
    *,
    trigger: Message,
    mailbox: Mailbox,
    history_id: int,
) -> dict[str, Any]:
    """E10: the group opens again; the ticket (end of its chain) reopens inside the reopen
    window, otherwise it stays closed with a ``reopen_skipped`` event and comment K4 while the
    mail stays visible through ``gmail_reopened_at``. Never a follow-up ticket."""
    from mhvp.sla.models import SlaClock
    from mhvp.sla.service import reopen_clock
    from mhvp.tickets import follow_up
    from mhvp.tickets.models import TicketEvent, TicketStatus

    result = await reopen_group(session, settings, lead, source="gmail", restore=False)
    result["ticket_reopened"] = False
    if lead.ticket_id is None:
        return result
    ticket = (await follow_up.resolve(session, lead.ticket_id)).ticket
    if ticket is None or ticket.status.value not in follow_up.CLOSED_STATES:
        return result
    now = datetime.now(UTC)
    window_days = await follow_up.reopen_window_days(session, lead.tenant_id)
    date, time = _stamp(now)
    if not follow_up.within_reopen_window(follow_up.closed_at(ticket), now, window_days):
        session.add(
            TicketEvent(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind="reopen_skipped",
                data={
                    "reason": "window_elapsed",
                    "message_id": str(trigger.id),
                    "closed_at": follow_up.closed_at(ticket).isoformat(),
                    "window_days": window_days,
                    "source": "gmail",
                },
            )
        )
        await _comment(
            session, ticket, K4.format(subject=trigger.subject or "", window_days=window_days)
        )
        return result
    previous = ticket.status.value
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.resolved_at = None
    session.add(
        TicketEvent(
            tenant_id=ticket.tenant_id,
            ticket_id=ticket.id,
            kind="reopened",
            data={
                "from": previous,
                "to": "in_progress",
                "reason": "gmail_unarchive",
                "message_id": str(trigger.id),
                "mailbox_address": mailbox.address,
                "history_id": history_id,
            },
        )
    )
    clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket.id))
    if clock is not None:
        await reopen_clock(session, clock)
    await _comment(
        session, ticket, K2.format(mailbox_address=mailbox.address, date=date, time=time)
    )
    await _notify(
        session,
        ticket,
        await _recipients(session, ticket),
        "ticket.auto_reopened",
        f"Ticket {ticket.number} durch Gmail wieder geöffnet",
        f"Die Mail wurde im Postfach {mailbox.address} wieder in den Posteingang gelegt.",
    )
    result["ticket_reopened"] = True
    return result


async def reopen_from_crm(
    session: AsyncSession,
    settings: Settings,
    message: Message,
    *,
    actor_user_id: uuid.UUID | None,
    source: str = "user",
) -> dict[str, Any]:
    """P03: a done mail set back to assigned or new from the CRM. Writes INBOX back only with
    ``gmail_restore_inbox_on_reopen``."""
    tenant_settings = await gmail_state.tenant_settings_row(session)
    restore = bool(tenant_settings is not None and tenant_settings.gmail_restore_inbox_on_reopen)
    return await reopen_group(
        session, settings, message, source=source, restore=restore, actor_user_id=actor_user_id
    )


async def revert_gmail_decision(
    session: AsyncSession,
    settings: Settings,
    message: Message,
    *,
    event_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """P05 "Automatik zurücknehmen": applies only to a group completed by the back channel
    or a ticket closed by it; the ticket returns to in_progress without the window check and
    records ``reverted`` with the reverted event."""
    from mhvp.tickets.models import Ticket, TicketEvent, TicketStatus

    result = {"message_reopened": False, "ticket_reopened": False}
    ticket = (
        await session.get(Ticket, message.ticket_id, with_for_update=True)
        if message.ticket_id
        else None
    )
    closed_event = None
    if ticket is not None:
        closed_event = await session.scalar(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket.id, TicketEvent.kind == "status")
            .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
            .limit(1)
        )
        if closed_event is not None and closed_event.data.get("source") != "gmail":
            closed_event = None
    if message.done_source not in ("gmail", "reconcile") and closed_event is None:
        from mhvp.core.problems import ErrorCodes

        raise ProblemError(ErrorCodes.GMAIL_REVERT_NOT_APPLICABLE)
    if message.status == "done":
        await reopen_from_crm(
            session, settings, message, actor_user_id=actor_user_id, source="revert"
        )
        result["message_reopened"] = True
    if (
        ticket is not None
        and closed_event is not None
        and ticket.status.value in ("done", "closed", "rejected")
    ):
        previous = ticket.status.value
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.resolved_at = None
        session.add(
            TicketEvent(
                tenant_id=ticket.tenant_id,
                ticket_id=ticket.id,
                kind="reverted",
                user_id=actor_user_id,
                data={
                    "from": previous,
                    "to": "in_progress",
                    "reverted_event_id": str(event_id or closed_event.id),
                    "message_id": str(message.id),
                },
            )
        )
        result["ticket_reopened"] = True
    return result


# Settle run ----------------------------------------------------------------------------------


async def settle_due(
    session: AsyncSession, settings: Settings, now: datetime | None = None
) -> dict[str, int]:
    """Groups whose settle period ended: the decision is checked again with the current
    states (the copy may be back in the inbox, then nothing happens) and executed."""
    now = now or datetime.now(UTC)
    counts = {"checked": 0, "done": 0, "noted": 0}
    tenant_settings = await gmail_state.tenant_settings_row(session)
    if tenant_settings is None:
        return counts
    rows = (
        await session.scalars(
            select(Message).where(
                Message.gmail_settle_until.is_not(None), Message.gmail_settle_until <= now
            )
        )
    ).all()
    completed: list[gmail_state.Applied] = []
    boxes_seen: dict[uuid.UUID, Mailbox] = {}
    for row in rows:
        counts["checked"] += 1
        hooks: list[Hook] = []
        async with session.begin_nested():
            await gmail_state.lock_group(session, row)
            members = await gmail_state.locked_members(session, row)
            lead = members[0]
            lead.gmail_settle_until = None
            views = await gmail_state.copy_views(session, members)
            trigger = _settle_trigger(views, members, tenant_settings)
            if (
                trigger is None
                or str(tenant_settings.gmail_done_sync_mode) != gmail_state.MODE_DONE
            ):
                counts["noted"] += 1
                continue
            mailbox = boxes_seen.get(trigger.mailbox_id) if trigger.mailbox_id else None
            if mailbox is None and trigger.mailbox_id is not None:
                mailbox = await session.get(Mailbox, trigger.mailbox_id)
                if mailbox is not None:
                    boxes_seen[trigger.mailbox_id] = mailbox
            action = gmail_state.gmail_action_of(trigger.gmail_state or "archived")
            await gmail_state.complete_group(
                session,
                settings,
                lead,
                source="gmail",
                actor_user_id=None,
                mailbox_address=mailbox.address if mailbox else None,
                gmail_action=action,
                hooks=hooks,
            )
            completed.append(
                gmail_state.Applied(
                    "done",
                    root=lead,
                    ticket_id=lead.ticket_id,
                    gmail_action=action,
                    history_id=trigger.gmail_state_history_id,
                    trigger=trigger,
                )
            )
            counts["done"] += 1
        from mhvp.core.db.tenancy import after_commit

        for hook in hooks:
            after_commit(session, hook)
    by_box: dict[uuid.UUID | None, list[gmail_state.Applied]] = {}
    for applied in completed:
        key = applied.trigger.mailbox_id if applied.trigger is not None else None
        by_box.setdefault(key, []).append(applied)
    for mailbox_id, items in by_box.items():
        mailbox = boxes_seen.get(mailbox_id) if mailbox_id else None
        if mailbox is not None:
            await after_apply(session, settings, mailbox, items, tenant_settings)
    return counts


def _settle_trigger(
    views: Sequence[gmail_state.CopyView], members: Sequence[Message], tenant_settings: Any
) -> Message | None:
    """The authoritative copy that still justifies the completion, or None when a deciding
    copy came back into the inbox (or the group is done meanwhile)."""
    done, _ = gmail_state._group_done(views)
    if done:
        return None
    deciding = gmail_state.authoritative(views)
    if not deciding:
        return None
    done_on_trash = bool(tenant_settings.gmail_done_on_trash)
    trigger_id: uuid.UUID | None = None
    for view in deciding:
        if view.state == "spam":
            continue
        if view.state == gmail_state.STATE_INBOX or view.keep_open_label:
            return None
        if view.state in gmail_state.TRASH_STATES and not done_on_trash:
            return None
        trigger_id = trigger_id or view.message_id
    return next((m for m in members if m.id == trigger_id), None)
