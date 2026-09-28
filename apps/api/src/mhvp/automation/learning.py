"""Lern-Workflow (rule M9-11, operator 27.09.2026): rule proposals from repeated manual
decisions. When members make the same manual decision for the same sender about
``tenant_settings.rule_proposal_threshold`` times (default 5) without a contradicting decision
in between, the platform proposes a rule; it never activates one by itself (rule 0.1.6).

Evidence is the existing decision log, nothing is recorded twice (rule 0.1.11):

* ``assignment_review.decided`` (``mhvp.communication.assignment_review``): Ja (``accept``) or
  manual choice (``manual``) of a contact, property or unit on a mail or ticket; a Nein
  (``reject``) of a proposed record contradicts a pattern for exactly that record.
* ``ticket.assigned`` with reason ``manuell`` (PATCH of the assignee by a member).
* ``ticket.topic_changed`` (PATCH of the ticket topic by a member).

The sender of a mail is its ``from_address``, the sender of a ticket the address of its first
inbound mail. Patterns are kept per sender address and, for domains that are not shared by
unrelated senders (public mail providers, the tenant's own mailbox domains), per sender domain
with at least two distinct addresses. Learnable fields are a closed list: contact, property
and unit assignment and ticket topic and assignee. Payees, IBANs, WEG resolutions, fees and
tax classification are never learnable, nothing here touches money or a release gate.

Accepting a proposal (``tenant_settings:update``) recomputes the evidence, and only when it
still holds creates an active ``automation_rule`` of the existing rule engine (trigger
``message.received``, condition on the sender, action ``assign_record`` or
``set_ticket_field``); the rule is visible, testable and switchable in the rule admin. The
accept deactivates the learned rules of earlier accepted proposals of the same pattern group
(``supersede_learned_rules``), so a group has one learned value at a time. A learned rule
never overrides a member's decision (``services.learned_field_kept``). A rejected pattern is
proposed again only when its evidence doubles.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.automation.models import (
    PROPOSAL_ACCEPTED,
    PROPOSAL_PROPOSED,
    PROPOSAL_REJECTED,
    PROPOSAL_STATUSES,
    PROPOSAL_WITHDRAWN,
    TRIGGER_EVENT,
    AutomationRule,
    AutomationRuleProposal,
)
from mhvp.automation.rules import is_automation_event
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import DomainEvent, emit
from mhvp.core.problems import ErrorCodes, ProblemError

log = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 5
MIN_THRESHOLD = 2
MAX_THRESHOLD = 50
# Newest decisions read per pattern; the trailing streak never needs more (threshold at most
# 50, doubling after a rejection is reached long before).
EVIDENCE_LIMIT = 500
ASSIGNMENT_FIELDS: tuple[str, ...] = ("contact", "property", "unit")
TICKET_FIELDS: tuple[str, ...] = ("topic", "assignee_user_id")
# Closed list (rule 0.1.6): never payees, IBANs, WEG resolutions, fees or tax classification.
LEARNABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "message": ("contact", "property"),
    "ticket": ("contact", "property", "unit", "topic", "assignee_user_id"),
}
FIELD_LABELS: dict[str, str] = {
    "contact": "Kontakt",
    "property": "Objekt",
    "unit": "Einheit",
    "topic": "Thema",
    "assignee_user_id": "Bearbeiter",
}
ENTITY_LABELS: dict[str, str] = {"message": "Mail", "ticket": "Ticket"}
SCOPE_ADDRESS = "address"
SCOPE_DOMAIN = "domain"
# Domains shared by unrelated senders (public mail providers): no domain pattern there
# (assumption A-071, docs/ASSUMPTIONS.md). The tenant's own mailbox domains are added at
# run time.
SHARED_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "gmx.de",
        "gmx.net",
        "gmx.at",
        "gmx.ch",
        "web.de",
        "t-online.de",
        "freenet.de",
        "arcor.de",
        "online.de",
        "posteo.de",
        "mailbox.org",
        "yahoo.com",
        "yahoo.de",
        "outlook.com",
        "outlook.de",
        "hotmail.com",
        "hotmail.de",
        "live.com",
        "live.de",
        "msn.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "aol.de",
        "protonmail.com",
        "proton.me",
        "1und1.de",
        "vodafone.de",
        "kabelmail.de",
        "email.de",
        "mail.de",
    }
)
DECISION_EVENTS: dict[str, str] = {
    "contact": "assignment_review.decided",
    "property": "assignment_review.decided",
    "unit": "assignment_review.decided",
    "assignee_user_id": "ticket.assigned",
    "topic": "ticket.topic_changed",
}
MANUAL_ASSIGN_REASON = "manuell"
RULE_TRIGGER = "message.received"


# Pure pattern detection (unit tested in tests/unit/test_rule_proposal_learning.py) ---------


@dataclass(frozen=True)
class Decision:
    """One manual decision: ``value`` is the chosen value; a Nein has no value and names the
    ``rejected`` proposal instead. ``address`` is the sender address of the record."""

    id: str
    at: datetime
    address: str
    value: str | None = None
    rejected: str | None = None


@dataclass(frozen=True)
class Streak:
    value: str
    decision_ids: tuple[str, ...]
    addresses: tuple[str, ...]
    first_at: datetime
    last_at: datetime

    @property
    def count(self) -> int:
        return len(self.decision_ids)

    @property
    def distinct_addresses(self) -> int:
        return len(set(self.addresses))


def normalise_address(address: str | None) -> str | None:
    value = (address or "").strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        return None
    return value


def sender_domain(address: str) -> str:
    return address.rsplit("@", 1)[1]


def sender_keys(address: str | None, own_domains: Collection[str] = ()) -> list[tuple[str, str]]:
    """Patterns a decision of this sender feeds: always the address, and the domain unless it
    is shared by unrelated senders (public mail provider) or is one of the tenant's own."""
    normal = normalise_address(address)
    if normal is None:
        return []
    keys = [(SCOPE_ADDRESS, normal)]
    domain = sender_domain(normal)
    if domain not in SHARED_MAIL_DOMAINS and domain not in {d.lower() for d in own_domains}:
        keys.append((SCOPE_DOMAIN, domain))
    return keys


def trailing_streak(decisions: Sequence[Decision]) -> Streak | None:
    """The newest run of consistent decisions (``decisions`` oldest first). The run ends at the
    first older decision for another value, or at a Nein for the run's value; a Nein newer than
    every decision for a value leaves no run for it. A Nein for another value is neutral."""
    value: str | None = None
    ids: list[str] = []
    addresses: list[str] = []
    stamps: list[datetime] = []
    rejected_later: set[str] = set()
    for decision in reversed(decisions):
        if decision.value is None:
            if decision.rejected is None:
                continue
            if value is None:
                rejected_later.add(decision.rejected)
                continue
            if decision.rejected == value:
                break
            continue
        if value is None:
            if not decision.value or decision.value in rejected_later:
                return None
            value = decision.value
        elif decision.value != value:
            break
        ids.append(decision.id)
        addresses.append(decision.address)
        stamps.append(decision.at)
    if value is None or not ids:
        return None
    return Streak(
        value=value,
        decision_ids=tuple(reversed(ids)),
        addresses=tuple(reversed(addresses)),
        first_at=min(stamps),
        last_at=max(stamps),
    )


def qualifies(streak: Streak | None, threshold: int, scope: str) -> bool:
    if streak is None or streak.count < threshold:
        return False
    return scope == SCOPE_ADDRESS or streak.distinct_addresses >= 2


def next_status(current: str | None, rejected_evidence_count: int | None, count: int) -> str | None:
    """Status of the pattern row of a qualifying streak. ``None``: no row wanted. A proposal
    stays proposed, a withdrawn one is proposed again, an accepted one stays accepted, a
    rejected one is proposed again only once the evidence reached twice the count at the
    rejection."""
    if current in (None, PROPOSAL_WITHDRAWN, PROPOSAL_PROPOSED):
        return PROPOSAL_PROPOSED
    if current == PROPOSAL_REJECTED:
        return PROPOSAL_PROPOSED if count >= 2 * max(rejected_evidence_count or 0, 1) else current
    return current


def decision_from_event(
    field: str, payload: dict[str, Any], actor_user_id: uuid.UUID | None
) -> tuple[str | None, str | None] | None:
    """``(value, rejected)`` of a logged event, or ``None`` when the event is no manual
    decision (automatic, rule effect, other reason)."""
    if actor_user_id is None or is_automation_event(payload):
        return None
    if field in ASSIGNMENT_FIELDS:
        kind = payload.get("decision")
        if kind in ("accept", "manual") and payload.get("chosen_id"):
            return str(payload["chosen_id"]), None
        if kind == "reject" and payload.get("proposed_id"):
            return None, str(payload["proposed_id"])
        return None
    if field == "assignee_user_id":
        if payload.get("reason") != MANUAL_ASSIGN_REASON or not payload.get("to"):
            return None
        return str(payload["to"]), None
    if field == "topic":
        return str(payload.get("to") or ""), None
    return None


# Database -----------------------------------------------------------------------------------


async def tenant_threshold(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(
        select(TenantSettings.rule_proposal_threshold).where(TenantSettings.tenant_id == tenant_id)
    )
    return int(value) if value else DEFAULT_THRESHOLD


async def own_domains(session: AsyncSession) -> set[str]:
    from mhvp.communication.models import Mailbox

    rows = await session.scalars(select(Mailbox.address))
    return {sender_domain(a) for a in (normalise_address(r) for r in rows) if a}


async def sender_of(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> str | None:
    """Sender address of a mail, or of the first inbound mail of a ticket."""
    from mhvp.communication.models import Message

    if entity_type == "message":
        row = (
            await session.execute(
                select(Message.from_address, Message.direction).where(Message.id == entity_id)
            )
        ).first()
        return normalise_address(row.from_address) if row and row.direction == "in" else None
    address = await session.scalar(
        select(Message.from_address)
        .where(Message.ticket_id == entity_id, Message.direction == "in")
        .order_by(Message.created_at, Message.id)
        .limit(1)
    )
    return normalise_address(address)


async def load_decisions(
    session: AsyncSession, *, entity_type: str, field: str, scope: str, key: str
) -> list[Decision]:
    """Manual decisions of the pattern from the domain event log, oldest first.

    The sender is ``Message.from_address_norm`` (generated ``lower(btrim(from_address))``,
    migration 0220). For an address pattern the lookup compares that plain column, so the
    index ``ix_message_tenant_from_address_norm`` is an index condition also under row level
    security (a comparison through ``lower()`` is not leakproof and never would be); for a
    ticket the candidate tickets come from that index before the first inbound mail of each
    is determined. A domain pattern (``split_part``) cannot use a btree index on the address
    and stays a filter over the inbound mails of the tenant."""
    from mhvp.communication.models import Message

    address = Message.from_address_norm
    senders: Select[Any]
    if entity_type == "message":
        senders = select(Message.id.label("entity_id"), address.label("address")).where(
            Message.direction == "in", address.is_not(None)
        )
        if scope == SCOPE_ADDRESS:
            senders = senders.where(address == key)
    else:
        senders = (
            select(Message.ticket_id.label("entity_id"), address.label("address"))
            .where(
                Message.direction == "in",
                Message.ticket_id.is_not(None),
                address.is_not(None),
            )
            .distinct(Message.ticket_id)
            .order_by(Message.ticket_id, Message.created_at, Message.id)
        )
        if scope == SCOPE_ADDRESS:
            # Only tickets with an inbound mail of the sender can have it as first sender;
            # the outer match below still checks that it is the first one.
            candidates = select(Message.ticket_id).where(
                Message.direction == "in", Message.ticket_id.is_not(None), address == key
            )
            senders = senders.where(Message.ticket_id.in_(candidates))
    sub = senders.subquery()
    match = (
        sub.c.address == key
        if scope == SCOPE_ADDRESS
        else func.split_part(sub.c.address, "@", 2) == key
    )
    query = (
        select(DomainEvent, sub.c.address)
        .join(sub, sub.c.entity_id == DomainEvent.entity_id)
        .where(
            DomainEvent.type == DECISION_EVENTS[field],
            DomainEvent.entity_type == entity_type,
            match,
        )
    )
    if field in ASSIGNMENT_FIELDS:
        query = query.where(DomainEvent.payload["dimension"].astext == field)
    rows = (
        await session.execute(
            query.order_by(DomainEvent.occurred_at.desc(), DomainEvent.id.desc()).limit(
                EVIDENCE_LIMIT
            )
        )
    ).all()
    out: list[Decision] = []
    for event, sender in rows:
        parsed = decision_from_event(field, event.payload or {}, event.actor_user_id)
        if parsed is None:
            continue
        out.append(
            Decision(
                id=str(event.id),
                at=event.occurred_at,
                address=str(sender),
                value=parsed[0],
                rejected=parsed[1],
            )
        )
    out.reverse()
    return out


async def value_label(
    session: AsyncSession, tenant_id: uuid.UUID, field: str, value: str
) -> str | None:
    """Display label of the target, or ``None`` when it no longer exists (deleted contact,
    inactive member, unknown topic): such a pattern is never proposed or accepted."""
    if field == "topic":
        from mhvp.communication.assignment import _tenant_extra_catalogue
        from mhvp.tickets.competences import is_known_code, label_for

        extra = await _tenant_extra_catalogue(session, tenant_id)
        return label_for(value, extra) if is_known_code(value, extra) else None
    try:
        ident = uuid.UUID(value)
    except ValueError:
        return None
    if field == "contact":
        from mhvp.contacts.models import Contact

        contact = await session.get(Contact, ident)
        if contact is None or contact.deleted_at is not None:
            return None
        return str(contact.display_name)
    if field == "property":
        from mhvp.properties.models import Property

        prop = await session.get(Property, ident)
        return f"{prop.number} {prop.name}" if prop is not None else None
    if field == "unit":
        from mhvp.properties.models import Unit

        unit = await session.get(Unit, ident)
        return f"Einheit {unit.number}" if unit is not None else None
    if field == "assignee_user_id":
        from mhvp.platform.models import Membership, MembershipStatus, User

        name = await session.scalar(
            select(User.display_name)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == ident,
                Membership.tenant_id == tenant_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        return str(name) if name else None
    return None


def _evidence(streak: Streak) -> dict[str, Any]:
    return {
        "decision_ids": list(streak.decision_ids),
        "addresses": sorted(set(streak.addresses)),
        "first_at": streak.first_at.isoformat(),
        "last_at": streak.last_at.isoformat(),
    }


async def _emit(
    session: AsyncSession,
    row: AutomationRuleProposal,
    kind: str,
    actor_user_id: uuid.UUID | None,
    **extra: Any,
) -> None:
    await emit(
        session,
        tenant_id=row.tenant_id,
        type=f"rule_proposal.{kind}",
        entity_type="rule_proposal",
        entity_id=row.id,
        actor_user_id=actor_user_id,
        payload={
            "entity_type": row.entity_type,
            "field": row.field,
            "scope": row.scope,
            "sender_key": row.sender_key,
            "value": row.value,
            "evidence_count": row.evidence_count,
        }
        | extra,
    )


async def refresh_pattern(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    field: str,
    scope: str,
    key: str,
    threshold: int,
    actor_user_id: uuid.UUID | None,
) -> AutomationRuleProposal | None:
    """Recomputes one pattern group (entity type, field, scope, sender key): withdraws open
    proposals the newest decisions no longer carry and creates, updates or proposes again the
    row of a qualifying streak. Returns that row when it is (now) proposed."""
    streak = trailing_streak(
        await load_decisions(session, entity_type=entity_type, field=field, scope=scope, key=key)
    )
    ok = qualifies(streak, threshold, scope)
    rows = list(
        await session.scalars(
            select(AutomationRuleProposal)
            .where(
                AutomationRuleProposal.entity_type == entity_type,
                AutomationRuleProposal.field == field,
                AutomationRuleProposal.scope == scope,
                AutomationRuleProposal.sender_key == key,
            )
            .with_for_update()
        )
    )
    for row in rows:
        carried = ok and streak is not None and row.value == streak.value
        if row.status == PROPOSAL_PROPOSED and not carried:
            row.status = PROPOSAL_WITHDRAWN
            await _emit(session, row, "withdrawn", actor_user_id)
    if not ok or streak is None:
        return None
    target = next((r for r in rows if r.value == streak.value), None)
    status = next_status(
        target.status if target else None,
        target.rejected_evidence_count if target else None,
        streak.count,
    )
    if status != PROPOSAL_PROPOSED:
        return None
    label = await value_label(session, tenant_id, field, streak.value)
    if label is None:
        return None
    if target is None:
        target = AutomationRuleProposal(
            tenant_id=tenant_id,
            created_by=actor_user_id,
            entity_type=entity_type,
            field=field,
            scope=scope,
            sender_key=key,
            value=streak.value,
            status=PROPOSAL_PROPOSED,
            threshold=threshold,
        )
        session.add(target)
        newly = True
    else:
        newly = target.status != PROPOSAL_PROPOSED
        if newly:
            target.status = PROPOSAL_PROPOSED
            target.decided_by = target.decided_at = target.decision_reason = None
    target.value_label = label[:300]
    target.evidence = _evidence(streak)
    target.evidence_count = streak.count
    target.threshold = threshold
    target.updated_by = actor_user_id
    await session.flush()
    if newly:
        await _emit(session, target, "proposed", actor_user_id)
    return target


async def observe(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    field: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Hook after a manual decision (assignment review, ticket PATCH). Runs in a savepoint and
    never fails the decision itself: an error is logged and the proposal waits for the next
    decision."""
    if field not in LEARNABLE_FIELDS.get(entity_type, ()):
        return
    try:
        async with session.begin_nested():
            address = await sender_of(session, entity_type, entity_id)
            keys = sender_keys(address, await own_domains(session))
            if not keys:
                return
            threshold = await tenant_threshold(session, tenant_id)
            for scope, key in keys:
                await refresh_pattern(
                    session,
                    tenant_id=tenant_id,
                    entity_type=entity_type,
                    field=field,
                    scope=scope,
                    key=key,
                    threshold=threshold,
                    actor_user_id=actor_user_id,
                )
    except Exception:
        log.warning(
            "rule proposal detection failed",
            extra={"tenant_id": str(tenant_id), "entity_type": entity_type, "field": field},
            exc_info=True,
        )


# Accept and reject -------------------------------------------------------------------------


def rule_definition(row: AutomationRuleProposal, label: str) -> dict[str, Any]:
    """Definition of the automation rule an accepted proposal creates (validated with the
    rule schema like any rule from the admin)."""
    sender_field = "entity.from_address" if row.scope == SCOPE_ADDRESS else "entity.from_domain"
    conditions: list[dict[str, Any]] = [
        {"field": sender_field, "op": "eq", "value": row.sender_key}
    ]
    action: dict[str, Any]
    if row.field in ASSIGNMENT_FIELDS:
        action = {
            "type": "assign_record",
            "target": row.entity_type,
            "dimension": row.field,
            "value": row.value,
        }
    else:
        # Only the ticket the mail opened, never an existing ticket a reply joins.
        conditions.append({"field": "entity.opens_ticket", "op": "eq", "value": True})
        action = {"type": "set_ticket_field", "field": row.field, "value": row.value}
    return {
        "name": (
            f"Lernregel {ENTITY_LABELS[row.entity_type]} {row.sender_key}: "
            f"{FIELD_LABELS[row.field]} {label}"
        )[:190],
        "description": (
            f"Aus Regelvorschlag {row.id}: {row.evidence_count} gleiche manuelle "
            f"Entscheidungen ohne Widerspruch (Schwelle {row.threshold}). Füllt nur leere "
            "Felder, beim Thema auch eine automatische Erkennung; eine Entscheidung eines "
            "Mitglieds gewinnt immer. Die Regel kann hier jederzeit deaktiviert werden."
        ),
        "active": True,
        "trigger_kind": TRIGGER_EVENT,
        "trigger_event_type": RULE_TRIGGER,
        "conditions": {"op": "and", "conditions": conditions},
        "actions": [action],
    }


async def _locked(session: AsyncSession, proposal_id: uuid.UUID) -> AutomationRuleProposal:
    row = await session.get(
        AutomationRuleProposal, proposal_id, with_for_update=True, populate_existing=True
    )
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Regelvorschlag nicht gefunden.")
    if row.status != PROPOSAL_PROPOSED:
        raise ProblemError(ErrorCodes.RULE_PROPOSAL_NOT_OPEN)
    return row


SUPERSEDED_REASON = "superseded"


async def supersede_learned_rules(
    session: AsyncSession,
    row: AutomationRuleProposal,
    rule: AutomationRule,
    *,
    actor_user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Deactivates the active rules created from other accepted proposals of the same pattern
    group (entity type, field, scope, sender key) as ``row``: the group has one learned value
    at a time. Without this two learned rules would compete, for ``set_ticket_field`` both ran
    (duplicate notifications), for ``assign_record`` the older one kept winning and the new
    one never took effect. Hand written rules of the admin (no proposal) are never touched.
    Each deactivation is logged as ``automation_rule.updated`` with the acceptor as actor and
    the superseding proposal and rule; returns what was deactivated for the response."""
    rows = (
        await session.execute(
            select(AutomationRule, AutomationRuleProposal)
            .join(AutomationRuleProposal, AutomationRuleProposal.rule_id == AutomationRule.id)
            .where(
                AutomationRuleProposal.entity_type == row.entity_type,
                AutomationRuleProposal.field == row.field,
                AutomationRuleProposal.scope == row.scope,
                AutomationRuleProposal.sender_key == row.sender_key,
                AutomationRuleProposal.status == PROPOSAL_ACCEPTED,
                AutomationRuleProposal.id != row.id,
                AutomationRule.id != rule.id,
                AutomationRule.active.is_(True),
            )
            .order_by(AutomationRule.created_at, AutomationRule.id)
            .with_for_update(of=AutomationRule)
        )
    ).all()
    now = datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for old_rule, old_row in rows:
        old_rule.active = False
        old_rule.updated_by = actor_user_id
        await emit(
            session,
            tenant_id=row.tenant_id,
            type="automation_rule.updated",
            entity_type="automation_rule",
            entity_id=old_rule.id,
            actor_user_id=actor_user_id,
            payload={
                "fields": ["active"],
                "reason": SUPERSEDED_REASON,
                "proposal_id": str(old_row.id),
                "superseded_by_proposal_id": str(row.id),
                "superseded_by_rule_id": str(rule.id),
            },
            changes={"active": {"old": True, "new": False}},
        )
        out.append(
            {
                "rule_id": old_rule.id,
                "rule_name": old_rule.name,
                "proposal_id": old_row.id,
                "value": old_row.value,
                "value_label": old_row.value_label,
                "deactivated_by": actor_user_id,
                "deactivated_at": now,
            }
        )
    if out:
        await session.flush()
    return out


async def accept(
    session: AsyncSession, proposal_id: uuid.UUID, *, actor_user_id: uuid.UUID
) -> tuple[AutomationRuleProposal, list[dict[str, Any]]]:
    """Deterministic check of the evidence at the moment of the accept, then an active rule of
    the rule engine; the proposal records who accepted when and which rule was created. Active
    rules of earlier accepted proposals of the same pattern group are deactivated
    (``supersede_learned_rules``) and returned as the second element."""
    from mhvp.automation.schemas import AutomationRuleIn
    from mhvp.automation.services import seal_actions

    row = await _locked(session, proposal_id)
    threshold = await tenant_threshold(session, row.tenant_id)
    streak = trailing_streak(
        await load_decisions(
            session,
            entity_type=row.entity_type,
            field=row.field,
            scope=row.scope,
            key=row.sender_key,
        )
    )
    label = await value_label(session, row.tenant_id, row.field, row.value)
    if (
        streak is None
        or streak.value != row.value
        or not qualifies(streak, threshold, row.scope)
        or label is None
    ):
        raise ProblemError(ErrorCodes.RULE_PROPOSAL_STALE)
    row.evidence = _evidence(streak)
    row.evidence_count = streak.count
    row.threshold = threshold
    definition = rule_definition(row, label)
    name = definition["name"]
    if await session.scalar(select(AutomationRule.id).where(AutomationRule.name == name)):
        definition["name"] = f"{name} ({row.id.hex[-6:]})"
    values = AutomationRuleIn.model_validate(
        definition | {"owner_user_id": actor_user_id}
    ).model_dump()
    values["actions"] = seal_actions(values["actions"])
    rule = AutomationRule(
        tenant_id=row.tenant_id, created_by=actor_user_id, updated_by=actor_user_id, **values
    )
    session.add(rule)
    await session.flush()
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="automation_rule.created",
        entity_type="automation_rule",
        entity_id=rule.id,
        actor_user_id=actor_user_id,
        payload={"name": rule.name, "active": rule.active, "proposal_id": str(row.id)},
    )
    superseded = await supersede_learned_rules(session, row, rule, actor_user_id=actor_user_id)
    row.status = PROPOSAL_ACCEPTED
    row.rule_id = rule.id
    row.value_label = label[:300]
    row.decided_by = row.updated_by = actor_user_id
    row.decided_at = datetime.now(UTC)
    await session.flush()
    await _emit(
        session,
        row,
        "accepted",
        actor_user_id,
        rule_id=str(rule.id),
        superseded_rule_ids=[str(s["rule_id"]) for s in superseded],
    )
    await session.refresh(row, ["updated_at"])
    return row, superseded


async def reject(
    session: AsyncSession,
    proposal_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID,
    reason: str | None,
) -> AutomationRuleProposal:
    row = await _locked(session, proposal_id)
    row.status = PROPOSAL_REJECTED
    row.rejected_evidence_count = row.evidence_count
    row.decision_reason = reason or None
    row.decided_by = row.updated_by = actor_user_id
    row.decided_at = datetime.now(UTC)
    await session.flush()
    await _emit(session, row, "rejected", actor_user_id, reason=reason)
    await session.refresh(row, ["updated_at"])
    return row


# API ----------------------------------------------------------------------------------------

router = APIRouter(prefix="/automation", tags=["Automatisierung"])
READ = require_permission("tenant_settings:read")
MANAGE = require_permission("tenant_settings:update")
StatusFilter = Literal["proposed", "accepted", "rejected", "withdrawn", "all"]


class RuleProposalEvidence(BaseModel):
    decision_ids: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    first_at: str | None = None
    last_at: str | None = None


class SupersededRuleOut(BaseModel):
    """A learned rule of the same pattern group that the accept deactivated."""

    rule_id: uuid.UUID
    rule_name: str
    proposal_id: uuid.UUID
    value: str
    value_label: str | None
    deactivated_by: uuid.UUID
    deactivated_at: datetime


class RuleProposalOut(BaseModel):
    id: uuid.UUID
    entity_type: Literal["message", "ticket"]
    field: str
    scope: Literal["address", "domain"]
    sender_key: str
    value: str
    value_label: str | None
    status: str
    evidence_count: int
    threshold: int
    evidence: RuleProposalEvidence
    rejected_evidence_count: int | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_reason: str | None
    rule_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    # Only in the answer of the accept: learned rules of the same pattern group deactivated by
    # it (also logged as ``automation_rule.updated`` with reason ``superseded``).
    superseded_rules: list[SupersededRuleOut] = Field(default_factory=list)


class RuleProposalRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


def proposal_out(
    row: AutomationRuleProposal, superseded: Sequence[dict[str, Any]] = ()
) -> RuleProposalOut:
    return RuleProposalOut(
        superseded_rules=[SupersededRuleOut.model_validate(s) for s in superseded],
        id=row.id,
        entity_type=row.entity_type,
        field=row.field,
        scope=row.scope,
        sender_key=row.sender_key,
        value=row.value,
        value_label=row.value_label,
        status=row.status,
        evidence_count=row.evidence_count,
        threshold=row.threshold,
        evidence=RuleProposalEvidence.model_validate(row.evidence or {}),
        rejected_evidence_count=row.rejected_evidence_count,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        decision_reason=row.decision_reason,
        rule_id=row.rule_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/rule-proposals", summary="Regelvorschläge aus wiederholten Entscheidungen")
async def list_proposals(
    request: Request,
    status: StatusFilter = Query(default="proposed"),
    limit: int = Query(default=100, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[RuleProposalOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AutomationRuleProposal)
        if status != "all":
            query = query.where(AutomationRuleProposal.status == status)
        rows = await session.scalars(
            query.order_by(
                AutomationRuleProposal.updated_at.desc(), AutomationRuleProposal.id.desc()
            ).limit(limit)
        )
        return [proposal_out(r) for r in rows]


def _human(principal: TenantPrincipal) -> uuid.UUID:
    """Only a signed in member decides a proposal (rule 0.1.6), never an API key alone."""
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Regelvorschläge entscheidet nur ein angemeldetes Mitglied.",
            developer_message="Rule proposals need a user principal, not an API key.",
        )
    return principal.user_id


@router.post(
    "/rule-proposals/{proposal_id}/accept",
    summary="Regelvorschlag annehmen (legt eine aktive Regel an)",
)
async def accept_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> RuleProposalOut:
    async with tenant_tx(request, principal) as session:
        row, superseded = await accept(session, proposal_id, actor_user_id=_human(principal))
        return proposal_out(row, superseded)


@router.post("/rule-proposals/{proposal_id}/reject", summary="Regelvorschlag ablehnen")
async def reject_proposal(
    proposal_id: uuid.UUID,
    body: RuleProposalRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> RuleProposalOut:
    async with tenant_tx(request, principal) as session:
        row = await reject(
            session, proposal_id, actor_user_id=_human(principal), reason=body.reason
        )
        return proposal_out(row)


__all__ = [
    "LEARNABLE_FIELDS",
    "PROPOSAL_STATUSES",
    "Decision",
    "Streak",
    "accept",
    "next_status",
    "observe",
    "qualifies",
    "reject",
    "router",
    "sender_keys",
    "trailing_streak",
]
