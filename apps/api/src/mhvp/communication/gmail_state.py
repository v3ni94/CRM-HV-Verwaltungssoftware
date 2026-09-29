"""Rückkanal Gmail zu Plattform (rule M20-08, operator 28.09.2026).

Label changes read from the Gmail history (``GmailClient.history_since``) or found by the
reconcile are applied per mailbox copy: the copy remembers its state (``Message.gmail_state``,
inbox, archived, trashed, spam, deleted), who caused it (user, platform, reconcile) and the
last applied history id (monotone replay guard). In mode ``done`` a group of copies of one
mail becomes ``done`` when its authoritative copies left the inbox: the copies in collective
mailboxes decide; without a collective copy every personal copy must be archived (operator
standard). Own platform archivings are recognised by ``gmail_expected_state`` (set in the same
transaction as ``archive_status = pending``) or the history id of the own modify call and never
complete or reopen anything. Gmail events never write back to Gmail.

Pure decision functions (``authoritative``, ``fold``, ``classify_by``, ``decide_group``) are
session free and unit tested; ``apply_events`` applies them under the group lock of
``duplicates.lock_mail`` inside a savepoint per copy, ``reconcile_mailbox`` compares the
stored states with the inbox listing, ``complete_group`` and the sync state for the API
complete the module. The consequences of a decision in mode ``done`` (ticket close, reopen,
comments, notifications) live in ``mhvp.communication.gmail_done``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import duplicates
from mhvp.communication.gmail import OTHER_LABEL_KINDS, GmailClient, HistoryEvent, state_from_labels
from mhvp.communication.models import Mailbox, Message
from mhvp.core.config import Settings
from mhvp.core.events import emit

log = logging.getLogger(__name__)

Hook = Callable[[], Awaitable[None]]

STATE_INBOX = "inbox"
OUT_OF_INBOX = frozenset({"archived", "trashed", "spam", "deleted"})
TRASH_STATES = frozenset({"trashed", "deleted"})
# Done sources a restore in Gmail may reopen (an echo of an own sent mail never reopens).
REOPENABLE_SOURCES = frozenset({"gmail", "user", "bulk", "reconcile"})
MODE_OFF, MODE_RECORD, MODE_DONE = "off", "record_only", "done"
EVENT_STATE_CHANGED = "message.gmail_state_changed"
EVENT_COMPLETED = "message.completed"
EVENT_REOPENED = "message.reopened"
EVENT_RESTORE_REQUESTED = "message.gmail_restore_requested"
SYNC_EVENT_TYPES = (EVENT_STATE_CHANGED, EVENT_COMPLETED, EVENT_REOPENED, EVENT_RESTORE_REQUESTED)
# Sync state shown in the CRM (``gmail_sync.state``).
SYNC_OFF, SYNC_UNKNOWN, SYNC_OK, SYNC_DEVIATING, SYNC_PENDING, SYNC_DELETED = (
    "aus",
    "unbekannt",
    "synchron",
    "abweichend",
    "ausstehend",
    "geloescht",
)
RECONCILE_DAYS = 90


@dataclass(frozen=True)
class CopyView:
    message_id: uuid.UUID
    mailbox_id: uuid.UUID | None
    is_collective: bool
    is_echo: bool
    has_gmail_id: bool
    state: str
    expected_state: str | None
    state_history_id: int | None
    archive_history_id: int | None
    keep_open_label: str | None
    status: str = "new"
    done_source: str | None = None
    archive_status: str | None = None
    settle_until: datetime | None = None
    mailbox_address: str | None = None
    # False for a copy in a soft deleted or disabled mailbox: it receives no label events any
    # more and must neither decide nor block a decision.
    mailbox_active: bool = True


@dataclass(frozen=True)
class Decision:
    effect: str  # done, reopened, ignored_own, ignored_replay, ignored_personal,
    # ignored_spam, ignored_keep_open, skipped_mode, skipped_mailbox, noted, settle_pending
    new_state: str | None  # state to store on the copy
    by: str  # user | platform | reconcile
    group_action: str | None  # None | complete | reopen


@dataclass(frozen=True)
class Folded:
    state: str
    keep_open_label: str | None
    coalesced: int


def authoritative(copies: Sequence[CopyView]) -> list[CopyView]:
    """Copies that decide for the group: copies in collective mailboxes; without one, every
    copy bound to a live, enabled mailbox. Echo copies, copies without Gmail id and copies of
    deleted or disabled mailboxes never decide."""
    eligible = [
        c
        for c in copies
        if c.has_gmail_id and c.mailbox_id is not None and not c.is_echo and c.mailbox_active
    ]
    collective = [c for c in eligible if c.is_collective]
    return collective or eligible


def fold(state: str, events: Sequence[HistoryEvent], keep_open_labels: frozenset[str]) -> Folded:
    """End state of one copy after ``events`` (already in history order, E19): undo, snooze
    and a trash in two entries collapse into the last state; intermediate states count in
    ``coalesced``. A work label from ``keep_open_labels`` (label names, case insensitive) is
    remembered (E13); its removal clears it (``keep_open_label = ""``, the caller drops the
    stored label)."""
    label: str | None = None
    changes = 0
    for event in events:
        kind = event.kind
        if kind in OTHER_LABEL_KINDS:
            for raw in event.added_labels:
                if raw.lower() in keep_open_labels:
                    label = raw if kind == "label_added_other" else ""
            continue
        if kind == "added":
            new = state_from_labels(event.label_ids) if event.label_ids else STATE_INBOX
        elif kind == "inbox_removed":
            new = "archived" if state == STATE_INBOX else state
        elif kind == "inbox_added":
            new = STATE_INBOX
        elif kind == "trash_added":
            new = "trashed"
        elif kind == "trash_removed":
            new = "archived" if state == "trashed" else state
        elif kind == "spam_added":
            new = "spam"
        elif kind == "spam_removed":
            new = "archived" if state == "spam" else state
        elif kind == "deleted":
            new = "deleted"
        else:
            continue
        if new != state:
            changes += 1
            state = new
    return Folded(state, label, changes)


def attribution(copy: CopyView, new_state: str, history_id: int) -> tuple[str, bool]:
    """``(by, fallback)``: ``platform`` when the event is the echo of an own action, that is
    its history id is not newer than the id of the own modify call, or, as the fallback
    criterion, the observed state is the state the platform requested
    (``gmail_expected_state``); otherwise ``user``. ``fallback`` is True when only the
    expected state carried the attribution (counter ``fallback_attributions``, section 13
    of the rule: the spike checks how the modify history id relates to the history entry)."""
    if copy.archive_history_id is not None and history_id <= copy.archive_history_id:
        return "platform", False
    if copy.expected_state is not None and new_state == copy.expected_state:
        return "platform", True
    return "user", False


def classify_by(copy: CopyView, new_state: str, history_id: int) -> str:
    return attribution(copy, new_state, history_id)[0]


def classify(
    copy: CopyView, events: Sequence[HistoryEvent], *, keep_open_labels: frozenset[str]
) -> tuple[Folded, str]:
    """Folded end state of ``events`` on ``copy`` and who caused it (``classify_by``)."""
    folded = fold(copy.state, events, keep_open_labels)
    history_id = max(e.history_id for e in events)
    return folded, classify_by(copy, folded.state, history_id)


def _group_done(copies: Sequence[CopyView]) -> tuple[bool, str | None]:
    real = [c for c in copies if not c.is_echo] or list(copies)
    done = any(c.status == "done" for c in real)
    source = next((c.done_source for c in real if c.done_source), None)
    return done, source


def decide_group(
    copies: Sequence[CopyView],
    changed: CopyView,
    new_state: str,
    by: str,
    *,
    mode: str,
    done_on_trash: bool,
    reopen_on_unarchive: bool,
) -> Decision:
    """Decision table of rule M20-08 (E01 to E13, E16 to E18). ``changed`` carries the work
    label found in the same run (``fold``). Reconcile results (``by = reconcile``) count like
    user actions; only ``platform`` is never a user action."""
    if by == "platform":
        return Decision("ignored_own", new_state, by, None)
    if changed.is_echo:
        return Decision("noted", new_state, by, None)
    if new_state == "spam":
        return Decision("ignored_spam", new_state, by, None)
    deciding = {c.message_id for c in authoritative(copies)}
    if changed.message_id not in deciding:
        return Decision("ignored_personal", new_state, by, None)
    group_done, done_source = _group_done(copies)
    if new_state == STATE_INBOX:
        if (
            mode == MODE_DONE
            and reopen_on_unarchive
            and group_done
            and done_source in REOPENABLE_SOURCES
        ):
            return Decision("reopened", new_state, by, "reopen")
        return Decision("noted", new_state, by, None)
    if changed.keep_open_label:
        return Decision("ignored_keep_open", new_state, by, None)
    if group_done or mode != MODE_DONE:
        return Decision("noted", new_state, by, None)
    if new_state in TRASH_STATES and not done_on_trash:
        return Decision("noted", new_state, by, None)
    for copy in authoritative(copies):
        state = new_state if copy.message_id == changed.message_id else copy.state
        if state == "spam":
            continue  # neither counts as out of the inbox nor blocks
        if state == STATE_INBOX:
            return Decision("noted", new_state, by, None)
        if state in TRASH_STATES and not done_on_trash:
            return Decision("noted", new_state, by, None)
        if copy.keep_open_label and copy.message_id != changed.message_id:
            return Decision("ignored_keep_open", new_state, by, None)
    return Decision("done", new_state, by, "complete")


def gmail_action_of(state: str) -> str:
    return {"trashed": "trashed", "deleted": "deleted"}.get(state, "archived")


# Views and locks ---------------------------------------------------------------------------


def mail_key_of(row: Message) -> str | None:
    """Same key as ``duplicates.lock_mail`` for the parsed mail of this row."""
    if row.header_message_id:
        return f"id:{row.header_message_id}"
    if row.from_address and row.received_at:
        return f"fb:{row.from_address}|{row.subject or ''}|{row.received_at}"
    return None


async def lock_group(session: AsyncSession, row: Message) -> None:
    """Serialises group decisions with the ingest of a late copy of the same mail."""
    key = mail_key_of(row)
    if key is None:
        key = f"row:{row.id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"mhvp:mail-in:{row.tenant_id}:{key}"},
    )


async def locked_members(session: AsyncSession, row: Message) -> list[Message]:
    """Every copy of the group of ``row`` locked ``FOR UPDATE`` in id order (deadlock free
    order for two syncs meeting on the same group), the leading copy first afterwards."""
    root = duplicates.group_root(row)
    rows = (
        await session.scalars(
            select(Message)
            .where(or_(Message.id == root, Message.duplicate_of_id == root))
            .order_by(Message.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    return sorted(rows, key=lambda m: (m.duplicate_of_id is not None, m.created_at))


async def mailbox_info(
    session: AsyncSession, members: Sequence[Message]
) -> dict[uuid.UUID, tuple[bool, str, bool]]:
    """``(is_collective, address, enabled)`` per live mailbox of ``members``; soft deleted
    mailboxes are left out."""
    ids = {m.mailbox_id for m in members if m.mailbox_id is not None}
    if not ids:
        return {}
    rows = await session.execute(
        select(Mailbox.id, Mailbox.is_collective, Mailbox.address, Mailbox.enabled).where(
            Mailbox.id.in_(ids), Mailbox.deleted_at.is_(None)
        )
    )
    return {
        mid: (bool(collective), str(address), bool(enabled))
        for mid, collective, address, enabled in rows
    }


def view_of(row: Message, boxes: dict[uuid.UUID, tuple[bool, str, bool]]) -> CopyView:
    """View of one copy; a copy whose mailbox is soft deleted (missing in ``boxes``) or
    disabled is inactive (never authoritative)."""
    box = boxes.get(row.mailbox_id) if row.mailbox_id is not None else None
    return CopyView(
        message_id=row.id,
        mailbox_id=row.mailbox_id,
        is_collective=bool(box[0]) if box else False,
        mailbox_active=bool(box[2]) if box else False,
        is_echo=bool((row.classification or {}).get("own_sent_echo")),
        has_gmail_id=bool(row.gmail_message_id),
        state=row.gmail_state or STATE_INBOX,
        expected_state=row.gmail_expected_state,
        state_history_id=row.gmail_state_history_id,
        archive_history_id=row.archive_history_id,
        keep_open_label=row.gmail_keep_open_label,
        status=row.status,
        done_source=row.done_source,
        archive_status=row.archive_status,
        settle_until=row.gmail_settle_until,
        mailbox_address=box[1] if box else None,
    )


async def copy_views(session: AsyncSession, members: Sequence[Message]) -> list[CopyView]:
    boxes = await mailbox_info(session, members)
    return [view_of(m, boxes) for m in members]


# Completion of a group ---------------------------------------------------------------------


async def complete_group(
    session: AsyncSession,
    settings: Settings,
    root: Message,
    *,
    source: str,
    actor_user_id: uuid.UUID | None,
    mailbox_address: str | None = None,
    gmail_action: str | None = None,
    hooks: list[Hook] | None = None,
) -> dict[str, Any]:
    """Sets every copy of the group to ``done`` with ``done_source`` and ``done_at`` and
    requests the Gmail archiving (``mark_archive_pending`` plus ``gmail_expected_state``) for
    every copy with a Gmail id that is still in the inbox; the job runs after the commit. The
    hook is appended to ``hooks`` when given (savepoint safe registration by the caller),
    otherwise registered with ``after_commit``. Emits ``message.completed`` on the leading
    copy. The ticket check is the caller's business (``services.complete_message`` for user
    actions, ``gmail_done`` for the back channel)."""
    from mhvp.communication.services import enqueue_archive_for_messages, mark_archive_pending
    from mhvp.core.db.tenancy import after_commit

    members = await duplicates.group_members(session, root) or [root]
    now = datetime.now(UTC)
    pending: list[uuid.UUID] = []
    for member in members:
        member.status = "done"
        member.done_source = source
        member.done_at = now
        member.gmail_reopened_at = None
        member.gmail_settle_until = None
        if (member.gmail_state or STATE_INBOX) == STATE_INBOX and mark_archive_pending(member):
            pending.append(member.id)
    tenant_id = root.tenant_id
    if pending:

        async def _archive() -> None:
            await enqueue_archive_for_messages(session, settings, tenant_id, pending)

        if hooks is not None:
            hooks.append(_archive)
        else:
            after_commit(session, _archive)
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_COMPLETED,
        entity_type="message",
        entity_id=duplicates.group_root(root),
        actor_user_id=actor_user_id,
        payload={
            "source": source,
            "group_root_id": str(duplicates.group_root(root)),
            "copy_ids": [str(m.id) for m in members],
            "mailbox_address": mailbox_address,
            "gmail_action": gmail_action,
        },
    )
    return {"archive": bool(pending), "copy_ids": [m.id for m in members]}


# Applying events ---------------------------------------------------------------------------


@dataclass
class Applied:
    effect: str
    root: Message | None = None
    ticket_id: uuid.UUID | None = None
    gmail_action: str | None = None
    history_id: int | None = None
    trigger: Message | None = None


def _bump(counts: dict[str, Any], key: str, n: int = 1) -> None:
    counts[key] = int(counts.get(key, 0)) + n


async def tenant_settings_row(session: AsyncSession) -> Any:
    from mhvp.platform.models import TenantSettings

    return await session.scalar(select(TenantSettings))


def keep_open_set(tenant_settings: Any) -> frozenset[str]:
    labels = getattr(tenant_settings, "gmail_keep_open_labels", None) or []
    return frozenset(str(label).lower() for label in labels)


async def apply_events(
    session: AsyncSession,
    settings: Settings,
    mailbox: Mailbox,
    events: Sequence[HistoryEvent],
    tenant_settings: Any,
    *,
    source: str = "history",
) -> dict[str, Any]:
    """Applies label events of one mailbox (history or reconcile) copy by copy: events per
    Gmail id are folded (E19), unknown ids are dropped (E15), replays are refused by the
    monotone history id (E17), every copy runs in its own savepoint under the group lock, and
    after-commit hooks are registered only after the savepoint succeeded. Mode ``off``
    changes nothing; a mailbox with the back channel off or without ``gmail.modify`` only
    records the state (``skipped_mailbox``). Ticket consequences of completed groups are
    evaluated once per ticket after all events (``gmail_done.after_apply``)."""
    from mhvp.core.db.tenancy import after_commit

    counts: dict[str, Any] = {"events": len(events), "applied": 0}
    if tenant_settings is None or tenant_settings.gmail_done_sync_mode == MODE_OFF:
        counts["skipped_mode"] = len(events)
        return counts
    mode = str(tenant_settings.gmail_done_sync_mode)
    keep_open = keep_open_set(tenant_settings)
    skipped_mailbox = not mailbox.sync_back_enabled or mailbox.archive_scope_missing
    grouped: dict[str, list[HistoryEvent]] = {}
    for event in events:
        if event.kind == "added":
            continue
        if event.kind in OTHER_LABEL_KINDS and not keep_open:
            continue
        grouped.setdefault(event.message_id, []).append(event)
    completed: list[Applied] = []
    for mid, evs in grouped.items():
        row = await duplicates.known_gmail_row(session, mailbox.id, mid)
        if row is None:
            _bump(counts, "unknown")
            continue
        hooks: list[Hook] = []
        try:
            async with session.begin_nested():
                applied = await _apply_one(
                    session,
                    settings,
                    mailbox,
                    row,
                    evs,
                    tenant_settings,
                    keep_open,
                    mode=mode,
                    source=source,
                    skipped_mailbox=skipped_mailbox,
                    hooks=hooks,
                    counts=counts,
                )
        except Exception:
            log.exception(
                "gmail state event not applied",
                extra={"mailbox_id": str(mailbox.id), "gmail_id": mid},
            )
            _bump(counts, "failed")
            continue
        for hook in hooks:
            after_commit(session, hook)
        _bump(counts, "applied")
        _bump(counts, applied.effect)
        if applied.effect == "done":
            completed.append(applied)
    if completed:
        from mhvp.communication import gmail_done

        await gmail_done.after_apply(session, settings, mailbox, completed, tenant_settings)
    running = dict(mailbox.gmail_sync_back_counts or {})
    for key in ("events", "done", "reopened", "ignored_own", "ignored_replay", "unknown"):
        if counts.get(key):
            _bump(running, key, int(counts[key]))
    if counts.get("fallback_attributions"):
        _bump(running, "fallback_attributions", int(counts["fallback_attributions"]))
    mailbox.gmail_sync_back_counts = running
    return counts


async def _apply_one(
    session: AsyncSession,
    settings: Settings,
    mailbox: Mailbox,
    row: Message,
    events: Sequence[HistoryEvent],
    tenant_settings: Any,
    keep_open: frozenset[str],
    *,
    mode: str,
    source: str,
    skipped_mailbox: bool,
    hooks: list[Hook],
    counts: dict[str, Any],
) -> Applied:
    await lock_group(session, row)
    members = await locked_members(session, row)
    row = next((m for m in members if m.id == row.id), row)
    lead = members[0] if members else row
    history_id = max(e.history_id for e in events)
    if row.gmail_state_history_id is not None and history_id <= row.gmail_state_history_id:
        await _emit_state_event(
            session,
            mailbox,
            row,
            row.gmail_state or STATE_INBOX,
            row.gmail_state or STATE_INBOX,
            by=row.gmail_state_by or "user",
            history_id=history_id,
            source=source,
            effect="ignored_replay",
            coalesced=0,
            keep_open_label=None,
        )
        return Applied("ignored_replay")
    boxes = await mailbox_info(session, members)
    views = [view_of(m, boxes) for m in members]
    changed = next(v for v in views if v.message_id == row.id)
    previous = changed.state
    folded = fold(changed.state, events, keep_open)
    by, fallback = attribution(changed, folded.state, history_id)
    if source == "reconcile" and by != "platform":
        by = "reconcile"
    if fallback:
        _bump(counts, "fallback_attributions")
    # Work label (E13): a label added in this run is stored, its removal ("") drops the
    # stored one, a copy back in the inbox carries none.
    if folded.state == STATE_INBOX:
        keep_label = None
    elif folded.keep_open_label is None:
        keep_label = changed.keep_open_label
    else:
        keep_label = folded.keep_open_label or None
    label_changed = keep_label != changed.keep_open_label
    changed = replace(changed, keep_open_label=keep_label)
    if skipped_mailbox:
        decision = Decision("skipped_mailbox", folded.state, by, None)
    elif folded.state == previous and not label_changed:
        decision = Decision("ignored_own" if by == "platform" else "noted", folded.state, by, None)
    else:
        decision = decide_group(
            views,
            changed,
            folded.state,
            by,
            mode=mode,
            done_on_trash=bool(tenant_settings.gmail_done_on_trash),
            reopen_on_unarchive=bool(tenant_settings.gmail_reopen_on_unarchive),
        )
    now = datetime.now(UTC)
    row.gmail_state = folded.state
    row.gmail_state_at = now
    row.gmail_state_by = by
    row.gmail_state_history_id = history_id
    row.gmail_keep_open_label = keep_label
    effect = decision.effect
    applied = Applied(effect, root=lead, history_id=history_id, trigger=row)
    if (
        folded.state == STATE_INBOX
        and lead.gmail_settle_until is not None
        and decision.group_action is None
        and changed.message_id in {c.message_id for c in authoritative(views)}
    ):
        # Undo, snooze end or restore before the settle period ended: the pending
        # completion is dropped (E19), the settle run finds nothing to execute.
        lead.gmail_settle_until = None
    if decision.group_action == "complete":
        settle = int(tenant_settings.gmail_settle_seconds or 0)
        if settle > 0 and source != "settle":
            lead.gmail_settle_until = now + timedelta(seconds=settle)
            effect = "settle_pending"
        else:
            lead.gmail_settle_until = None
            await complete_group(
                session,
                settings,
                lead,
                source="gmail" if source != "reconcile" else "reconcile",
                actor_user_id=None,
                mailbox_address=mailbox.address,
                gmail_action=gmail_action_of(folded.state),
                hooks=hooks,
            )
            applied = Applied(
                "done",
                root=lead,
                ticket_id=lead.ticket_id,
                gmail_action=gmail_action_of(folded.state),
                history_id=history_id,
                trigger=row,
            )
    elif decision.group_action == "reopen":
        from mhvp.communication import gmail_done

        lead.gmail_settle_until = None
        await gmail_done.reopen_from_gmail(
            session, settings, lead, trigger=row, mailbox=mailbox, history_id=history_id
        )
        effect = "reopened"
    applied.effect = effect
    await _emit_state_event(
        session,
        mailbox,
        row,
        previous,
        folded.state,
        by=by,
        history_id=history_id,
        source=source,
        effect=effect,
        coalesced=folded.coalesced,
        keep_open_label=keep_label,
    )
    return applied


async def _emit_state_event(
    session: AsyncSession,
    mailbox: Mailbox,
    row: Message,
    previous: str,
    new_state: str,
    *,
    by: str,
    history_id: int,
    source: str,
    effect: str,
    coalesced: int,
    keep_open_label: str | None,
) -> None:
    await emit(
        session,
        tenant_id=row.tenant_id,
        type=EVENT_STATE_CHANGED,
        entity_type="message",
        entity_id=row.id,
        actor_user_id=None,
        payload={
            "mailbox_id": str(mailbox.id),
            "mailbox_address": mailbox.address,
            "gmail_message_id": row.gmail_message_id,
            "from": previous,
            "to": new_state,
            "by": by,
            "history_id": history_id,
            "source": source,
            "effect": effect,
            "coalesced": coalesced,
            "keep_open_label": keep_open_label,
        },
    )


# Sync state for the API --------------------------------------------------------------------


def sync_state(views: Sequence[CopyView], mode: str) -> str:
    """Aggregated state of a group for the CRM: ``aus`` in mode off, ``unbekannt`` without a
    Gmail copy, ``ausstehend`` while an own job or a settle period is open, ``geloescht`` when
    every deciding copy is deleted, ``synchron`` when the platform status and the inbox agree
    (done and out of the inbox, or open and in the inbox), otherwise ``abweichend``."""
    if mode == MODE_OFF:
        return SYNC_OFF
    copies = [
        v
        for v in views
        if v.has_gmail_id and v.mailbox_id is not None and not v.is_echo and v.mailbox_active
    ]
    if not copies:
        return SYNC_UNKNOWN
    if any(
        v.archive_status in ("pending", "failed", "scope_missing", "restore_pending")
        or v.settle_until is not None
        for v in copies
    ):
        return SYNC_PENDING
    deciding = authoritative(views) or copies
    if all(v.state == "deleted" for v in deciding):
        return SYNC_DELETED
    done, _ = _group_done(views)
    counted = [v for v in copies if v.archive_status != "skipped"]
    if done:
        return SYNC_OK if all(v.state in OUT_OF_INBOX for v in counted) else SYNC_DEVIATING
    return SYNC_OK if all(v.state == STATE_INBOX for v in counted) else SYNC_DEVIATING


async def sync_info_for(
    session: AsyncSession,
    rows: Sequence[Message],
    *,
    readable: Callable[[uuid.UUID | None], bool] | None = None,
) -> dict[uuid.UUID, dict[str, Any]]:
    """``gmail_sync`` per row (one batch of queries): ``state`` and the ``copies`` of the
    group. Copies in mailboxes the user may not read (``readable``) show address only."""
    if not rows:
        return {}
    tenant_settings = await tenant_settings_row(session)
    mode = str(getattr(tenant_settings, "gmail_done_sync_mode", MODE_RECORD) or MODE_RECORD)
    roots = {duplicates.group_root(r) for r in rows}
    members = (
        await session.scalars(
            select(Message).where(or_(Message.id.in_(roots), Message.duplicate_of_id.in_(roots)))
        )
    ).all()
    by_root: dict[uuid.UUID, list[Message]] = {}
    for m in members:
        by_root.setdefault(duplicates.group_root(m), []).append(m)
    boxes = await mailbox_info(session, members)
    deciding_cache: dict[uuid.UUID, dict[str, Any]] = {}
    for root, group in by_root.items():
        views = [view_of(m, boxes) for m in group]
        deciding = {v.message_id for v in authoritative(views)}
        copies: list[dict[str, Any]] = []
        for view in views:
            if view.is_echo or view.mailbox_id is None:
                continue
            if readable is not None and not readable(view.mailbox_id):
                copies.append({"mailbox_address": view.mailbox_address, "visible": False})
                continue
            copies.append(
                {
                    "message_id": view.message_id,
                    "mailbox_id": view.mailbox_id,
                    "mailbox_address": view.mailbox_address,
                    "is_collective": view.is_collective,
                    "authoritative": view.message_id in deciding,
                    "gmail_state": view.state if view.has_gmail_id else None,
                    "gmail_state_by": next(
                        (m.gmail_state_by for m in group if m.id == view.message_id), None
                    ),
                    "gmail_state_at": next(
                        (m.gmail_state_at for m in group if m.id == view.message_id), None
                    ),
                    "archive_status": view.archive_status,
                    "visible": True,
                }
            )
        deciding_cache[root] = {"state": sync_state(views, mode), "copies": copies}
    return {
        r.id: deciding_cache.get(duplicates.group_root(r), {"state": SYNC_UNKNOWN, "copies": []})
        for r in rows
    }


# Reconcile ---------------------------------------------------------------------------------

RECONCILE_KIND = {
    "deleted": "deleted",
    "trashed": "trash_added",
    "spam": "spam_added",
    "archived": "inbox_removed",
}


async def reconcile_mailbox(
    session: AsyncSession,
    settings: Settings,
    mailbox: Mailbox,
    client: GmailClient,
    *,
    mode: str = "run",
) -> dict[str, Any]:
    """Compares the stored copy states of a mailbox with its inbox (M20-08, hourly beat,
    after an expired history, on request). Order: profile history id (``stamp``) first, then
    the complete inbox listing; rows of the last 90 days that are in the inbox by the stored
    state but missing in the listing are checked with ``messages.get`` (at most
    ``gmail_state_reconcile_limit`` calls, rest ``deferred``), rows younger than the grace
    period are left alone, rows the platform itself archived are marked ``own`` without a
    call; rows stored as archived, trashed or spam but listed in the inbox come back
    (``returned``). Every finding is applied through ``apply_events`` with ``history_id =
    stamp`` and ``by = reconcile``. ``mode="preview"`` writes nothing and reports what a run
    would do (samples up to 50)."""
    counts: dict[str, Any] = {
        "checked": 0,
        "archived": 0,
        "trashed": 0,
        "spam": 0,
        "deleted": 0,
        "returned": 0,
        "unchanged": 0,
        "deferred": 0,
        "own": 0,
        "grace": 0,
    }
    preview = mode == "preview"
    now = datetime.now(UTC)
    tenant_settings = await tenant_settings_row(session)
    if not preview:
        mailbox.gmail_state_reconcile_status = "running"
    try:
        stamp = int(await client.profile_history_id())
        total = await client.label_total("INBOX")
        if total is not None and total > settings.gmail_reconcile_listing_max:
            return _reconcile_failed(mailbox, counts, "listing_too_large", preview)
        inbox_ids: set[str] = set()
        page: str | None = None
        while True:
            ids, page = await client.list_inbox_page(page, 500)
            inbox_ids.update(ids)
            if len(inbox_ids) > settings.gmail_reconcile_listing_max:
                return _reconcile_failed(mailbox, counts, "listing_too_large", preview)
            if not page:
                break
        grace = timedelta(
            seconds=int(getattr(tenant_settings, "gmail_reconcile_grace_seconds", 300))
        )
        since = now - timedelta(days=RECONCILE_DAYS)
        rows = (
            await session.scalars(
                select(Message)
                .where(
                    Message.mailbox_id == mailbox.id,
                    Message.direction == "in",
                    Message.gmail_message_id.is_not(None),
                    Message.created_at >= since,
                )
                .order_by(Message.created_at.desc())
            )
        ).all()
        events: list[HistoryEvent] = []
        samples: list[dict[str, Any]] = []
        calls = 0
        for row in rows:
            gid = str(row.gmail_message_id)
            state = row.gmail_state or STATE_INBOX
            if state == STATE_INBOX:
                if gid in inbox_ids:
                    counts["unchanged"] += 1
                    continue
                recent = [
                    t for t in (row.created_at, row.gmail_state_at, row.archive_attempted_at) if t
                ]
                if any(t > now - grace for t in recent):
                    counts["grace"] += 1
                    continue
                counts["checked"] += 1
                if row.gmail_expected_state == "archived":
                    counts["own"] += 1
                    if not preview:
                        row.gmail_state = "archived"
                        row.gmail_state_by = "platform"
                        row.gmail_state_at = now
                        row.gmail_state_history_id = max(row.gmail_state_history_id or 0, stamp)
                        await _emit_state_event(
                            session,
                            mailbox,
                            row,
                            STATE_INBOX,
                            "archived",
                            by="platform",
                            history_id=stamp,
                            source="reconcile",
                            effect="ignored_own",
                            coalesced=0,
                            keep_open_label=None,
                        )
                    continue
                if calls >= settings.gmail_state_reconcile_limit:
                    counts["deferred"] += 1
                    continue
                calls += 1
                labels = await client.message_labels(gid)
                found = "deleted" if labels is None else state_from_labels(labels[1])
                if found == STATE_INBOX:
                    counts["unchanged"] += 1  # listing lagged behind, message is back
                    continue
                counts[found] += 1
                events.append(HistoryEvent(stamp, gid, RECONCILE_KIND[found]))
                _sample(samples, row, found)
            elif state in ("archived", "trashed", "spam") and gid in inbox_ids:
                counts["returned"] += 1
                events.append(HistoryEvent(stamp, gid, "inbox_added"))
                _sample(samples, row, "returned")
            else:
                counts["unchanged"] += 1
        if preview:
            return {
                "checked": counts["checked"],
                "would_archive": counts["archived"],
                "would_trash": counts["trashed"] + counts["spam"],
                "would_delete": counts["deleted"],
                "would_reopen": counts["returned"],
                "own": counts["own"],
                "deferred": counts["deferred"],
                "grace": counts["grace"],
                "samples": samples[:50],
            }
        if events:
            applied = await apply_events(
                session, settings, mailbox, events, tenant_settings, source="reconcile"
            )
            counts["applied"] = applied
        mailbox.gmail_state_reconciled_at = now
        mailbox.gmail_state_reconcile_status = "done"
        mailbox.gmail_state_reconcile_counts = {
            k: v for k, v in counts.items() if not isinstance(v, dict)
        }
        mailbox.gmail_history_expired_at = None
        return counts
    except Exception:
        if not preview:
            mailbox.gmail_state_reconcile_status = "failed"
        raise


def _reconcile_failed(
    mailbox: Mailbox, counts: dict[str, Any], reason: str, preview: bool
) -> dict[str, Any]:
    counts["reason"] = reason
    if not preview:
        mailbox.gmail_state_reconcile_status = "failed"
        mailbox.gmail_state_reconcile_counts = dict(counts)
    counts["status"] = "failed"
    return counts


def _sample(samples: list[dict[str, Any]], row: Message, action: str) -> None:
    if len(samples) < 50:
        samples.append(
            {
                "message_id": row.id,
                "subject": row.subject,
                "ticket_id": row.ticket_id,
                "action": action,
            }
        )
