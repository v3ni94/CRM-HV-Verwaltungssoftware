"""Rule engine stage 1: context per event, action execution and the beat processing loop.

Processing (``process_tenant``): the beat job reads new rows of ``domain_event`` since the
tenant's watermark (ordered by ``occurred_at, id``, with a short lag so that a transaction
that commits late is not skipped), evaluates every active rule whose trigger matches the
event type and executes the actions of matching rules. Each rule and event pair runs at most
once (``automation_run`` unique constraint) and inside a savepoint, so one failing rule
neither blocks the others nor the watermark. Events written by rule actions carry the
``automation`` marker and never trigger a rule again (depth 1).

Stage 1 actions never post, pay, approve or send anything (rules 0.1.6, 0.1.7).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.automation.models import (
    RUN_STATUS_DRY_RUN,
    RUN_STATUS_EXECUTED,
    RUN_STATUS_FAILED,
    AutomationRule,
    AutomationRun,
    AutomationWatermark,
)
from mhvp.automation.rules import (
    automation_marker,
    evaluate,
    is_automation_event,
    normalise,
    render,
    resolve_value,
)
from mhvp.automation.schemas import (
    Action,
    CreateTicketAction,
    NotifyAction,
    SetTicketFieldAction,
    parse_actions,
)
from mhvp.core.events import DomainEvent, emit
from mhvp.core.numbering import next_number
from mhvp.tickets.models import (
    Priority,
    Team,
    Ticket,
    TicketEvent,
    TicketSource,
    TicketTemplate,
)
from mhvp.workspace.services import notify

log = logging.getLogger(__name__)

# Events younger than this are left for the next run (late commits with an older
# ``occurred_at``, see module docstring).
PROCESS_LAG = timedelta(seconds=5)
BATCH_LIMIT = 500
NOTIFICATION_KIND = "automation"
TICKET_CONTEXT_FIELDS: tuple[str, ...] = (
    "id",
    "number",
    "property_id",
    "unit_id",
    "contact_id",
    "template_id",
    "category",
    "topic",
    "title",
    "public_description",
    "status",
    "priority",
    "assignee_user_id",
    "team_id",
    "initiator_contact_id",
    "source",
    "sla_due_at",
    "created_at",
)


class ActionError(Exception):
    """An action could not be executed (recorded in the run, rule continues with the next event)."""


# --- context -------------------------------------------------------------------------------


def ticket_context(ticket: Ticket) -> dict[str, Any]:
    return {k: normalise(getattr(ticket, k)) for k in TICKET_CONTEXT_FIELDS}


async def build_context(
    session: AsyncSession,
    *,
    type: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    payload: dict[str, Any] | None,
    actor_user_id: uuid.UUID | None = None,
    entity_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluation context: event fields plus the current fields of a ticket entity."""
    entity: dict[str, Any] = dict(entity_override or {})
    if entity_type == "ticket" and entity_id is not None and not entity_override:
        ticket = await session.get(Ticket, entity_id)
        if ticket is not None:
            entity = ticket_context(ticket)
    return {
        "type": type,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "payload": {k: normalise(v) for k, v in (payload or {}).items()},
        "entity": entity,
    }


async def context_for_event(session: AsyncSession, event: DomainEvent) -> dict[str, Any]:
    return await build_context(
        session,
        type=event.type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        payload=event.payload,
        actor_user_id=event.actor_user_id,
    )


# --- actions ------------------------------------------------------------------------------


def _uuid_or_none(value: Any, label: str) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ActionError(f"{label}: keine gültige UUID ({value!r}).") from exc


async def _users_with_role(
    session: AsyncSession, tenant_id: uuid.UUID, codes: list[str]
) -> list[uuid.UUID]:
    from mhvp.platform.models import Membership, MembershipRole, MembershipStatus, Role

    if not codes:
        return []
    rows = await session.execute(
        select(Membership.user_id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == MembershipStatus.ACTIVE,
            Role.tenant_id == tenant_id,
            Role.code.in_(codes),
        )
        .distinct()
    )
    return [row[0] for row in rows]


async def _assert_team(session: AsyncSession, team_id: uuid.UUID | None) -> None:
    if team_id is not None and await session.get(Team, team_id) is None:
        raise ActionError("Team nicht gefunden.")


async def _assert_member(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None
) -> None:
    from mhvp.platform.models import Membership, MembershipStatus

    if user_id is None:
        return
    found = await session.scalar(
        select(Membership.id).where(
            Membership.tenant_id == tenant_id,
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if found is None:
        raise ActionError("Bearbeiter ist kein aktives Mitglied des Mandanten.")


async def _create_ticket(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    event_id: uuid.UUID,
    action: CreateTicketAction,
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    from mhvp.tickets.routers import SLA_HOURS

    tpl = await session.get(TicketTemplate, action.template_id)
    if tpl is None:
        raise ActionError("Ticketvorlage nicht gefunden.")
    if not tpl.active:
        raise ActionError("Ticketvorlage ist deaktiviert.")
    values = {k: resolve_value(v, context) for k, v in action.fields.items()}
    title = render(action.title, context) or tpl.title
    priority_raw = values.pop("priority", None)
    priority = Priority(priority_raw) if priority_raw else tpl.default_priority
    team_id = _uuid_or_none(values.pop("team_id", tpl.default_team_id), "team_id")
    assignee = _uuid_or_none(
        values.pop("assignee_user_id", tpl.default_assignee_user_id), "assignee_user_id"
    )
    await _assert_team(session, team_id)
    await _assert_member(session, tenant_id, assignee)
    refs = {
        k: _uuid_or_none(values.pop(k, None), k) for k in ("property_id", "unit_id", "contact_id")
    }
    texts = {k: values.pop(k, None) for k in ("public_description", "internal_description")}
    category = values.pop("category", None) or tpl.category
    preview = {
        "type": "create_ticket",
        "template_id": str(tpl.id),
        "title": title,
        "priority": priority.value,
        "team_id": str(team_id) if team_id else None,
        "assignee_user_id": str(assignee) if assignee else None,
        "category": category,
        **{k: (str(v) if v else None) for k, v in refs.items()},
    }
    if dry_run:
        return preview | {"ok": True, "detail": "Testlauf: Ticket würde angelegt."}
    hours = tpl.sla_hours or SLA_HOURS[priority]
    ticket = Ticket(
        tenant_id=tenant_id,
        created_by=None,
        number=await next_number(session, tenant_id, "ticket"),
        template_id=tpl.id,
        category=category,
        topic=tpl.topic,
        title=title,
        public_description=texts["public_description"],
        internal_description=texts["internal_description"],
        priority=priority,
        team_id=team_id,
        assignee_user_id=assignee,
        source=TicketSource.MANUAL,
        checklist=[
            {
                "key": c["key"],
                "label": c["label"],
                "required": c.get("required", False),
                "done": False,
                "done_by": None,
                "done_at": None,
            }
            for c in tpl.checklist
        ],
        sla_due_at=datetime.now(UTC) + timedelta(hours=hours),
        **refs,
    )
    session.add(ticket)
    await session.flush()
    from mhvp.sla.service import start_clock

    await start_clock(session, tenant_id, ticket.id, ticket.priority)
    session.add(
        TicketEvent(
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            kind="created",
            user_id=None,
            data={"routing": "automation", "rule_id": str(rule.id), "rule_name": rule.name},
        )
    )
    if assignee:
        await notify(
            session,
            tenant_id=tenant_id,
            user_id=assignee,
            kind="ticket_assigned",
            title=f"Ticket {ticket.number}: {ticket.title}",
            entity_type="ticket",
            entity_id=ticket.id,
        )
    await emit(
        session,
        tenant_id=tenant_id,
        type="ticket.created",
        entity_type="ticket",
        entity_id=ticket.id,
        actor_user_id=None,
        payload={"number": ticket.number, "source": ticket.source.value}
        | automation_marker(rule.id, event_id),
    )
    return preview | {
        "ok": True,
        "entity_type": "ticket",
        "entity_id": str(ticket.id),
        "detail": f"Ticket {ticket.number} angelegt.",
    }


async def _notify(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    action: NotifyAction,
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    recipients = set(action.user_ids)
    recipients.update(await _users_with_role(session, tenant_id, action.role_codes))
    title = render(action.title, context) or rule.name
    body = render(action.body, context)
    entity_id = _uuid_or_none(context.get("entity_id"), "entity_id")
    preview = {
        "type": "notify",
        "title": title,
        "body": body,
        "user_ids": sorted(str(u) for u in recipients),
    }
    if dry_run:
        return preview | {"ok": True, "detail": f"Testlauf: {len(recipients)} Empfänger."}
    created = 0
    for user_id in sorted(recipients, key=str):
        await _assert_member(session, tenant_id, user_id)
        row = await notify(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=NOTIFICATION_KIND,
            title=title[:300],
            body=body,
            entity_type=context.get("entity_type"),
            entity_id=entity_id,
        )
        created += 1 if row is not None else 0
    return preview | {"ok": True, "detail": f"{created} Benachrichtigungen angelegt."}


async def _set_ticket_field(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    event_id: uuid.UUID,
    action: SetTicketFieldAction,
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    if context.get("entity_type") != "ticket":
        raise ActionError("Feld setzen braucht ein Ereignis zu einem Ticket.")
    if not context.get("entity_id") and not dry_run:
        raise ActionError("Feld setzen braucht ein Ereignis zu einem Ticket.")
    value = resolve_value(action.value, context)
    ticket_id = uuid.UUID(str(context["entity_id"])) if context.get("entity_id") else None
    new_value: Any
    if action.field == "priority":
        new_value = Priority(str(value))
    elif action.field in ("team_id", "assignee_user_id"):
        new_value = _uuid_or_none(value, action.field)
        if action.field == "team_id":
            await _assert_team(session, new_value)
        else:
            await _assert_member(session, tenant_id, new_value)
    else:
        new_value = None if value in (None, "") else str(value)[:100]
    preview = {
        "type": "set_ticket_field",
        "field": action.field,
        "value": normalise(new_value),
        "entity_type": "ticket",
        "entity_id": str(ticket_id) if ticket_id else None,
    }
    if dry_run or ticket_id is None:
        return preview | {"ok": True, "detail": "Testlauf: Feld würde gesetzt."}
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ActionError("Ticket nicht gefunden.")
    if ticket.merged_into_ticket_id is not None:
        raise ActionError("Ticket ist zusammengeführt; keine Änderung.")
    old_value = normalise(getattr(ticket, action.field))
    if old_value == normalise(new_value):
        return preview | {"ok": True, "detail": "Wert bereits gesetzt."}
    setattr(ticket, action.field, new_value)
    ticket.updated_by = None
    session.add(
        TicketEvent(
            tenant_id=tenant_id,
            ticket_id=ticket.id,
            kind="automation",
            user_id=None,
            data={
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "field": action.field,
                "old": old_value,
                "new": normalise(new_value),
            },
        )
    )
    if action.field == "assignee_user_id" and new_value is not None:
        await notify(
            session,
            tenant_id=tenant_id,
            user_id=new_value,
            kind="ticket_assigned",
            title=f"Ticket {ticket.number}: {ticket.title}",
            entity_type="ticket",
            entity_id=ticket.id,
        )
    await emit(
        session,
        tenant_id=tenant_id,
        type="ticket.field_set",
        entity_type="ticket",
        entity_id=ticket.id,
        actor_user_id=None,
        payload={"field": action.field} | automation_marker(rule.id, event_id),
        changes={action.field: {"old": old_value, "new": normalise(new_value)}},
    )
    return preview | {"ok": True, "detail": f"{action.field} gesetzt."}


async def execute_actions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    event_id: uuid.UUID,
    context: dict[str, Any],
    dry_run: bool,
) -> list[dict[str, Any]]:
    """Run the rule's actions in order. Raises ``ActionError`` on the first failing action
    (the caller rolls back the savepoint and records the failure)."""
    results: list[dict[str, Any]] = []
    for action in parse_actions(rule.actions):
        results.append(
            await _execute_one(
                session,
                tenant_id=tenant_id,
                rule=rule,
                event_id=event_id,
                action=action,
                context=context,
                dry_run=dry_run,
            )
        )
    return results


async def _execute_one(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    event_id: uuid.UUID,
    action: Action,
    context: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    if isinstance(action, CreateTicketAction):
        return await _create_ticket(
            session,
            tenant_id=tenant_id,
            rule=rule,
            event_id=event_id,
            action=action,
            context=context,
            dry_run=dry_run,
        )
    if isinstance(action, NotifyAction):
        return await _notify(
            session, tenant_id=tenant_id, rule=rule, action=action, context=context, dry_run=dry_run
        )
    return await _set_ticket_field(
        session,
        tenant_id=tenant_id,
        rule=rule,
        event_id=event_id,
        action=action,
        context=context,
        dry_run=dry_run,
    )


# --- dry run ------------------------------------------------------------------------------


async def dry_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, rule: AutomationRule, context: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate a rule against a sample context without any effect (no run is recorded)."""
    trigger_matches = context.get("type") == rule.trigger_event_type
    matched = trigger_matches and evaluate(rule.conditions, context)
    actions: list[dict[str, Any]] = []
    error: str | None = None
    if matched:
        try:
            # dry_run=True: every action returns its preview before any write.
            actions = await execute_actions(
                session,
                tenant_id=tenant_id,
                rule=rule,
                event_id=uuid.uuid4(),
                context=context,
                dry_run=True,
            )
        except ActionError as exc:
            error = str(exc)
    return {
        "status": RUN_STATUS_DRY_RUN,
        "trigger_matches": trigger_matches,
        "matched": bool(matched),
        "actions": actions,
        "error": error,
        "context": context,
    }


# --- processing ---------------------------------------------------------------------------


async def _run_rule(
    session: AsyncSession, *, tenant_id: uuid.UUID, rule: AutomationRule, event: DomainEvent
) -> AutomationRun | None:
    """Execute one rule for one event, idempotent. ``None`` when already run or no match."""
    existing = await session.scalar(
        select(AutomationRun.id).where(
            AutomationRun.rule_id == rule.id, AutomationRun.event_id == event.id
        )
    )
    if existing is not None:
        return None
    context = await context_for_event(session, event)
    try:
        if not evaluate(rule.conditions, context):
            return None
    except Exception as exc:  # invalid stored tree: record and continue
        return await _record(session, tenant_id, rule, event, RUN_STATUS_FAILED, [], str(exc))
    try:
        async with session.begin_nested():
            actions = await execute_actions(
                session,
                tenant_id=tenant_id,
                rule=rule,
                event_id=event.id,
                context=context,
                dry_run=False,
            )
            run = await _record(session, tenant_id, rule, event, RUN_STATUS_EXECUTED, actions, None)
        return run
    except IntegrityError:
        # Concurrent worker already recorded this rule and event (unique constraint).
        return None
    except Exception as exc:
        log.warning(
            "automation rule failed",
            extra={"tenant_id": str(tenant_id), "rule_id": str(rule.id), "event_id": str(event.id)},
        )
        return await _record(
            session, tenant_id, rule, event, RUN_STATUS_FAILED, [], str(exc)[:2000]
        )


async def _record(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    rule: AutomationRule,
    event: DomainEvent,
    status: str,
    actions: list[dict[str, Any]],
    error: str | None,
) -> AutomationRun:
    run = AutomationRun(
        tenant_id=tenant_id,
        rule_id=rule.id,
        event_id=event.id,
        event_type=event.type,
        status=status,
        error=error,
        actions=actions,
        finished_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    return run


async def process_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime | None = None
) -> dict[str, int]:
    """Process new events of one tenant since its watermark (see module docstring)."""
    now = now or datetime.now(UTC)
    cutoff = now - PROCESS_LAG
    totals = {"events": 0, "runs": 0, "failed": 0}
    watermark = await session.scalar(
        select(AutomationWatermark).where(AutomationWatermark.tenant_id == tenant_id)
    )
    if watermark is None:
        # First run: start at the current cut-off; older events are history, not triggers.
        watermark = AutomationWatermark(
            tenant_id=tenant_id, last_occurred_at=cutoff, last_event_id=None
        )
        session.add(watermark)
        await session.flush()
        return totals
    rules = list(
        await session.scalars(
            select(AutomationRule)
            .where(AutomationRule.tenant_id == tenant_id, AutomationRule.active.is_(True))
            .order_by(AutomationRule.created_at, AutomationRule.id)
        )
    )
    by_type: dict[str, list[AutomationRule]] = {}
    for rule in rules:
        by_type.setdefault(rule.trigger_event_type, []).append(rule)
    query = (
        select(DomainEvent)
        .where(DomainEvent.tenant_id == tenant_id, DomainEvent.occurred_at <= cutoff)
        .order_by(DomainEvent.occurred_at, DomainEvent.id)
        .limit(BATCH_LIMIT)
    )
    if watermark.last_occurred_at is not None:
        last_at, last_id = watermark.last_occurred_at, watermark.last_event_id
        if last_id is None:
            query = query.where(DomainEvent.occurred_at > last_at)
        else:
            query = query.where(
                (DomainEvent.occurred_at > last_at)
                | ((DomainEvent.occurred_at == last_at) & (DomainEvent.id > last_id))
            )
    events = list(await session.scalars(query))
    for event in events:
        totals["events"] += 1
        if is_automation_event(event.payload):
            continue
        for rule in by_type.get(event.type, []):
            run = await _run_rule(session, tenant_id=tenant_id, rule=rule, event=event)
            if run is None:
                continue
            totals["runs"] += 1
            if run.status == RUN_STATUS_FAILED:
                totals["failed"] += 1
    if events:
        watermark.last_occurred_at = events[-1].occurred_at
        watermark.last_event_id = events[-1].id
    watermark.updated_at = now
    return totals
